"""EvidenceEngine — deterministic collection of every piece of evidence.

Raw input (error text, git history) -> language-agnostic Evidence in a graph.
No AI is involved anywhere in this module.
"""
from __future__ import annotations

import re
from pathlib import Path

from bugtrail.adapters.registry import parse_stacktrace
from bugtrail.evidence.graph import (
    REL_DB_TO_EXCEPTION,
    REL_FILE_MODIFIED_BY,
    EvidenceGraph,
)
from bugtrail.evidence.models import Evidence

DB_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"duplicate entry", re.IGNORECASE), "Unique constraint violation (duplicate entry)"),
    (re.compile(r"integrity constraint", re.IGNORECASE), "Integrity constraint violation"),
    (re.compile(r"foreign key", re.IGNORECASE), "Foreign key constraint violation"),
    (re.compile(r"deadlock", re.IGNORECASE), "Deadlock detected"),
    (re.compile(r"null value in column", re.IGNORECASE), "NOT NULL constraint violation"),
]

RECENT_COMMIT_WINDOW = 20


def resolve_repo_path(repo_root: Path, raw: Path) -> str | None:
    """Map a stack-trace file path onto a repo-relative path, or None."""
    try:
        if raw.is_absolute():
            try:
                rel = raw.resolve().relative_to(repo_root.resolve())
                if raw.exists():
                    return str(rel).replace("\\", "/")
            except (ValueError, OSError):
                pass
    except OSError:
        pass
    candidate = Path(str(raw).replace("\\", "/").lstrip("/"))
    if (repo_root / candidate).exists():
        return str(candidate).replace("\\", "/")
    if (repo_root / candidate.name).exists():
        return str(candidate.name).replace("\\", "/")
    return None


class EvidenceEngine:
    def __init__(self, repo_root: Path, git):
        self.repo_root = repo_root
        self.git = git

    def collect_error(self, graph: EvidenceGraph, error_text: str) -> Evidence | None:
        exc = parse_stacktrace(error_text)
        if exc is not None:
            graph.add_exception_with_frames(exc)
            self.add_database_evidence(graph)
        return exc

    def add_database_evidence(self, graph: EvidenceGraph) -> Evidence | None:
        for exc in graph.exceptions():
            message = exc.data.get("message", "")
            for pattern, description in DB_PATTERNS:
                if pattern.search(message):
                    db = graph.add_database_query(description)
                    graph.link(db.id, REL_DB_TO_EXCEPTION, exc.id)
                    graph.link(exc.id, REL_DB_TO_EXCEPTION, db.id)
                    return db
        return None

    def attach_git(self, graph: EvidenceGraph) -> None:
        """Blame every frame line and note commits that touched those files."""
        if not self.git.available:
            return
        for frame in graph.exception_frames():
            rel = resolve_repo_path(self.repo_root, frame.file)
            if rel is None:
                continue
            node = graph.file_node(rel)
            blamed = self.git.blame_line(rel, frame.line)
            if blamed:
                commit = graph.ensure_commit(
                    blamed["sha"],
                    blamed["message"],
                    author=blamed["author"],
                    date=blamed["date"],
                )
                graph.link(node.id, REL_FILE_MODIFIED_BY, commit.id)
                strength = node.data.setdefault("commit_strength", {})
                strength[blamed["sha"]] = max(strength.get(blamed["sha"], 0.0), 1.0)
        for info in self.git.recent_commits(RECENT_COMMIT_WINDOW):
            for rel in self.git.changed_files(info["sha"]):
                node = graph.file_node(rel)
                commit = graph.ensure_commit(
                    info["sha"], info["message"], author=info["author"], date=info["date"]
                )
                graph.link(node.id, REL_FILE_MODIFIED_BY, commit.id)
                strength = node.data.setdefault("commit_strength", {})
                strength[info["sha"]] = max(strength.get(info["sha"], 0.0), 0.4)
