"""Unit tests for diff analysis (whitespace-only commit detection)."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from bugtrail.adapters.git import GitAdapter

ORIGINAL = "const x = 1;\nconst y = 2;\n"


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    return result.stdout.strip()


def _new_repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-b", "main")
    _git(tmp_path, "config", "user.email", "ziggy@bugtrail.dev")
    _git(tmp_path, "config", "user.name", "BugTrail Bot")
    (tmp_path / "a.js").write_text(ORIGINAL, encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "Initial commit")
    return tmp_path


@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
def test_whitespace_only_reformat_detected(tmp_path: Path):
    repo = _new_repo(tmp_path)
    (repo / "a.js").write_text("\tconst x = 1;\n\tconst y = 2;\n", encoding="utf-8")
    _git(repo, "add", "a.js")
    _git(repo, "commit", "-m", "Reformat with tabs")
    sha = _git(repo, "rev-parse", "HEAD")
    assert GitAdapter(repo).is_whitespace_only(sha)


@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
def test_content_change_not_whitespace_only(tmp_path: Path):
    repo = _new_repo(tmp_path)
    (repo / "a.js").write_text("const x = 5;\nconst y = 2;\n", encoding="utf-8")
    _git(repo, "add", "a.js")
    _git(repo, "commit", "-m", "Change x to 5")
    sha = _git(repo, "rev-parse", "HEAD")
    assert not GitAdapter(repo).is_whitespace_only(sha)


@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
def test_initial_commit_is_not_whitespace_only(tmp_path: Path):
    repo = _new_repo(tmp_path)
    sha = _git(repo, "rev-parse", "HEAD")
    assert not GitAdapter(repo).is_whitespace_only(sha)
