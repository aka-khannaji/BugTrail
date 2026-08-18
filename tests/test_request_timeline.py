"""Tests for request evidence and timeline reconstruction."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from bugtrail.engines.evidence import build_timeline, timeline_summary
from bugtrail.evidence.graph import EvidenceGraph
from bugtrail.evidence.models import Evidence


def test_request_extraction(tmp_path: Path):
    from bugtrail.investigation.pipeline import run_investigation

    target = tmp_path / "app/services/checkout_service.js"
    target.parent.mkdir(parents=True)
    target.write_text("function finalize() {}\nmodule.exports = { finalize };\n", encoding="utf-8")

    class NoGit:
        available = False

    error_text = (
        "POST /api/checkout HTTP/1.1\n"
        "TypeError: Cannot read properties of undefined (reading 'toUpperCase')\n"
        "    at finalize (app/services/checkout_service.js:1:38)\n"
    )

    session = run_investigation(
        repo_root=tmp_path,
        error_text=error_text,
        git=NoGit(),
        allow_ai=False,
    )
    requests = [n for n in session.graph["nodes"] if n["kind"] == "request"]
    assert len(requests) == 1
    assert requests[0]["data"] == {"method": "POST", "path": "/api/checkout"}

    from bugtrail.investigation.report import render_report

    assert "Request: POST /api/checkout" in render_report(session)


def test_request_not_extracted_without_http_context(tmp_path: Path):
    from bugtrail.engines.evidence import EvidenceEngine

    graph = EvidenceGraph()
    engine = EvidenceEngine(tmp_path, git=None)
    engine.detect_request(graph, "TypeError: boom\n    at foo (app.js:1:1)\n")
    assert graph.of_kind("request") == []


def test_timeline_build_and_summary():
    graph = EvidenceGraph()
    exc = Evidence.exception("KeyError", "'hourly'", [])
    graph.add(exc)
    graph.add_log("INFO", "deployed version 1.3.0", line=1, ts="2026-08-01T08:59:00")
    graph.add_log("INFO", "report generated ok", line=2, ts="2026-08-01T09:00:05")
    graph.add_log("ERROR", "failed to generate hourly report", line=3, ts="2026-08-01T09:01:00")

    timeline = build_timeline(graph)
    assert [e["ts"] for e in timeline] == [
        "2026-08-01T08:59:00",
        "2026-08-01T09:00:05",
        "2026-08-01T09:01:00",
        "",
    ]
    assert timeline[0]["deploy"] is True
    assert timeline[3]["level"] == "EXCEPTION"

    summary = timeline_summary(timeline)
    assert "1 ok event before first failure" in summary
    assert "first failure after deployed version 1.3.0" in summary


def test_timeline_empty_without_timestamps():
    graph = EvidenceGraph()
    graph.add_log("ERROR", "boom", line=1)
    assert build_timeline(graph) == []


def test_report_is_honest_without_hypotheses(tmp_path: Path):
    from bugtrail.investigation.pipeline import run_investigation
    from bugtrail.investigation.report import render_report

    (tmp_path / "app").mkdir(parents=True)

    class NoGit:
        available = False

    session = run_investigation(
        repo_root=tmp_path,
        error_text="TimeoutError: timed out\n    at Timeout (node:internal/timers:1:1)\n",
        git=NoGit(),
        allow_ai=False,
    )
    report = render_report(session)
    assert "NO STRONG ROOT CAUSE" in report
    assert "Evidence is insufficient to name a commit" in report


@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
def test_manifest_blame_fires_for_declared_but_bumped_dependency(tmp_path: Path):
    """A version bump that breaks an import is blamed even though the package is declared."""
    from bugtrail.adapters.git import GitAdapter
    from bugtrail.investigation.pipeline import run_investigation

    (tmp_path / "requirements.txt").write_text("requests==2.28.0\n", encoding="utf-8")
    (tmp_path / "app").mkdir(parents=True)
    (tmp_path / "app/main.py").write_text("import requests\n", encoding="utf-8")

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
    g("commit", "-m", "Initial commit")

    (tmp_path / "requirements.txt").write_text("requests==3.0.0\n", encoding="utf-8")
    g("add", "requirements.txt")
    g("commit", "-m", "Bump requests library to 3.0")
    head = g("rev-parse", "HEAD")

    error_text = (
        "Traceback (most recent call last):\n"
        '  File "/app/.venv/lib/python3.11/site-packages/requests/api.py", line 10, in <module>\n'
        "    from .sessions import Session\n"
        "ImportError: cannot import name 'Session' from 'requests'\n"
    )

    session = run_investigation(
        repo_root=tmp_path,
        error_text=error_text,
        git=GitAdapter(tmp_path),
        allow_ai=False,
    )
    deps = [n for n in session.graph["nodes"] if n["kind"] == "dependency"]
    assert deps and deps[0]["data"]["name"] == "requests"
    assert deps[0]["data"]["declared"] is True

    assert session.hypotheses
    top = session.hypotheses[0]
    assert top.commit_sha == head
    assert "requirements.txt" in top.files
