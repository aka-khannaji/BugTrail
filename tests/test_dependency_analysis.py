"""Tests for dependency analysis — missing-module errors and manifest blame."""
from __future__ import annotations

from pathlib import Path

from bugtrail.engines.evidence import (
    extract_missing_dependency,
    extract_missing_symbol,
    parse_manifest_names,
)


def test_extract_missing_dependency_python():
    assert extract_missing_dependency("ModuleNotFoundError: No module named 'requests'") == "requests"
    assert (
        extract_missing_dependency("ModuleNotFoundError: No module named 'django.db'")
        == "django"
    )


def test_extract_missing_dependency_node():
    assert extract_missing_dependency("Error: Cannot find module 'express'") == "express"
    assert (
        extract_missing_dependency("Error: Cannot find module '@scope/pkg/sub'")
        == "@scope/pkg"
    )


def test_extract_missing_dependency_php():
    assert (
        extract_missing_dependency('Class "StripeClient" not found') == "StripeClient"
    )


def test_extract_missing_dependency_none():
    assert extract_missing_dependency("TypeError: x is undefined") is None


def test_extract_missing_dependency_import_name():
    assert (
        extract_missing_dependency("ImportError: cannot import name 'Session' from 'requests'")
        == "requests"
    )
    assert (
        extract_missing_dependency(
            "ImportError: cannot import name 'JSONDecodeError' from 'requests.requests'"
        )
        == "requests"
    )


def test_extract_missing_symbol():
    assert extract_missing_symbol("TypeError: discountRate is not a function") == "discountRate"
    assert (
        extract_missing_symbol("AttributeError: 'BillingService' object has no attribute 'compute'")
        == "compute"
    )
    assert extract_missing_symbol("NameError: name 'render' is not defined") == "render"
    assert (
        extract_missing_symbol("Error: Call to undefined method App\\Services\\PaymentService::charge")
        == "charge"
    )
    assert extract_missing_symbol("KeyError: 'hourly'") is None


def test_parse_manifest_names_package_json(tmp_path: Path):
    (tmp_path / "package.json").write_text(
        '{"dependencies": {"express": "^4.0", "axios": "~1.0"}, "devDependencies": {"jest": "^29"}}',
        encoding="utf-8",
    )
    assert set(parse_manifest_names(tmp_path, "package.json")) == {"express", "axios", "jest"}


def test_parse_manifest_names_composer(tmp_path: Path):
    (tmp_path / "composer.json").write_text(
        '{"require": {"laravel/framework": "^11", "guzzlehttp/guzzle": "^7"},'
        ' "require-dev": {"phpunit/phpunit": "^10"}}',
        encoding="utf-8",
    )
    assert "laravel/framework" in parse_manifest_names(tmp_path, "composer.json")
    assert "phpunit/phpunit" in parse_manifest_names(tmp_path, "composer.json")


def test_parse_manifest_names_requirements(tmp_path: Path):
    (tmp_path / "requirements.txt").write_text(
        "requests==2.31.0\nDjango>=5.0\n# comment\n-r base.txt\n", encoding="utf-8"
    )
    names = parse_manifest_names(tmp_path, "requirements.txt")
    assert "requests" in names
    assert "Django" in names
    assert "base" not in names


def test_manifest_blame_fallback_when_all_frames_in_node_modules(tmp_path: Path):
    from bugtrail.adapters.git import GitAdapter
    from bugtrail.investigation.pipeline import run_investigation

    (tmp_path / "package.json").write_text(
        '{"name": "demo", "dependencies": {"express": "^4.0"}}', encoding="utf-8"
    )
    app = tmp_path / "src/app.js"
    app.parent.mkdir(parents=True)
    app.write_text("require('axios');\n", encoding="utf-8")

    import shutil
    import subprocess

    if shutil.which("git") is None:
        import pytest

        pytest.skip("git not installed")

    def g(*args: str) -> str:
        return subprocess.run(
            ["git", "-C", str(tmp_path), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        ).stdout.strip()

    g("init", "-b", "main")
    g("config", "user.email", "ziggy@bugtrail.dev")
    g("config", "user.name", "BugTrail Bot")
    g("add", ".")
    g("commit", "-m", "Add axios usage to app entrypoint")

    # second commit removes axios from the manifest and the code; the runtime
    # error "Cannot find module 'axios'" points back at this commit.
    (tmp_path / "package.json").write_text(
        '{"name": "demo", "dependencies": {}}', encoding="utf-8"
    )
    (tmp_path / "src/app.js").write_text("// now only a stub\n", encoding="utf-8")
    g("add", "package.json", "src/app.js")
    g("commit", "-m", "Drop axios in favor of native fetch")
    head = g("rev-parse", "HEAD")

    error_text = (
        "Error: Cannot find module 'axios'\n"
        "    at Object.<anonymous> (node_modules/axios/lib/axios.js:1:1)\n"
        "    at Module._compile (internal/modules/cjs/loader.js:1063:30)\n"
    )

    session = run_investigation(
        repo_root=tmp_path,
        error_text=error_text,
        git=GitAdapter(tmp_path),
        allow_ai=False,
    )

    deps = [n for n in session.graph["nodes"] if n["kind"] == "dependency"]
    assert len(deps) == 1
    assert deps[0]["data"]["name"] == "axios"
    assert deps[0]["data"]["declared"] is False
    assert deps[0]["data"]["manifest"] == "package.json"

    # every real frame is in node_modules, so the detective must blame the
    # manifest's last-touched commit (the one that dropped axios).
    assert session.hypotheses, "expected a manifest-based hypothesis"
    top = session.hypotheses[0]
    assert top.commit_sha == head
    assert "package.json" in top.files

    from bugtrail.investigation.report import render_report

    report = render_report(session)
    assert "Dependency: axios (missing from manifests)" in report
