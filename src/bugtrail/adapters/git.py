"""Git adapter — all git interaction happens here so the rest of BugTrail
only ever talks to a small, duck-typed interface (easy to stub in tests).
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any


class GitAdapter:
    def __init__(self, repo_root: Path | None = None):
        self._repo_root = repo_root

    @classmethod
    def discover(cls, start: Path) -> "GitAdapter":
        """Find the git repo root by walking up from `start`."""
        current = start.resolve()
        for directory in (current, *current.parents):
            if (directory / ".git").exists():
                return cls(repo_root=directory)
        return cls(repo_root=None)

    @property
    def repo_root(self) -> Path | None:
        return self._repo_root

    @property
    def available(self) -> bool:
        return self._repo_root is not None

    def _git(self, *args: str) -> str:
        if not self.available:
            raise RuntimeError("Not inside a git repository.")
        result = subprocess.run(
            ["git", "-C", str(self._repo_root), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        return result.stdout.strip()

    # -- info -------------------------------------------------------------
    def recent_commits(self, count: int = 30) -> list[dict[str, Any]]:
        out = self._git(
            "log",
            f"-{count}",
            "--pretty=format:%H%x1f%s%x1f%an%x1f%aI%x1f%P",
        )
        return [self._parse_commit(line) for line in out.splitlines() if line]

    def blame_line(self, file: str, line: int) -> dict[str, Any] | None:
        """Single-line porcelain blame -> the commit that last touched it."""
        if line < 1:
            return None
        try:
            out = self._git("blame", "-L", f"{line},{line}", "--porcelain", "--", file)
        except RuntimeError:
            return None
        first = out.splitlines()[0] if out else ""
        parts = first.split()
        if not parts:
            return None
        sha = parts[0]
        info = self.commit_info(sha)
        if info is None:
            return None
        info["file"] = file
        info["line"] = line
        return info

    def commit_info(self, sha: str) -> dict[str, Any] | None:
        try:
            out = self._git(
                "show",
                "-s",
                "--format=%H%x1f%s%x1f%an%x1f%aI%x1f%P",
                sha,
            )
        except RuntimeError:
            return None
        return self._parse_commit(out) if out else None

    def changed_files(self, sha: str) -> list[str]:
        try:
            out = self._git("show", "--name-only", "--format=", f"{sha}~1..{sha}")
        except RuntimeError:
            out = ""
        return [line for line in out.splitlines() if line]

    def diff_stat(self, sha: str) -> str:
        try:
            out = self._git("show", "--stat", "--format=%s", sha)
        except RuntimeError:
            out = ""
        return out

    def is_whitespace_only(self, sha: str) -> bool:
        """True when the commit changes no non-whitespace content.

        A cosmetic reformat (indentation, trailing whitespace) that a later
        commit applied to a frame line would otherwise shadow the commit that
        actually introduced the buggy code.
        """
        try:
            plain = self._git("diff", "--numstat", f"{sha}~1", sha)
            ignoring_ws = self._git("diff", "-w", "--numstat", f"{sha}~1", sha)
        except RuntimeError:
            return False
        return bool(plain.strip()) and not ignoring_ws.strip()

    @staticmethod
    def _parse_commit(line: str) -> dict[str, Any]:
        sha, subject, author, date, parents = (line.split("\x1f", 4) + ["", "", "", "", ""])[:5]
        return {
            "sha": sha,
            "message": subject,
            "author": author,
            "date": date,
            "parents": [p for p in parents.split() if p],
        }
