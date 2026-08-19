"""Storage of investigation sessions under .bugtrail/.

Single sessions are JSON files (portable, inspectable). A SQLite index
(.bugtrail/bugtrail.db) powers search, history, and the recurrence check:
"this error signature was investigated before — here's the previous result."
"""
from __future__ import annotations

import hashlib
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bugtrail.investigation.session import InvestigationSession

DIR_NAME = ".bugtrail"
LATEST_FILE = "latest.txt"
DB_FILE = "bugtrail.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    repo_root TEXT NOT NULL,
    exception_name TEXT NOT NULL,
    signature TEXT NOT NULL,
    created_at TEXT NOT NULL,
    data TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sessions_signature ON sessions(signature);
"""


class Storage:
    def __init__(self, repo_root: Path):
        self._dir = repo_root / DIR_NAME
        self._dir.mkdir(parents=True, exist_ok=True)

    @property
    def sessions_dir(self) -> Path:
        d = self._dir / "sessions"
        d.mkdir(parents=True, exist_ok=True)
        return d

    @property
    def db_path(self) -> Path:
        return self._dir / DB_FILE

    def save(self, session: InvestigationSession) -> Path:
        path = self.sessions_dir / f"{session.id}.json"
        path.write_text(session.model_dump_json(indent=2), encoding="utf-8")
        self._write_latest(session.id)
        self._index(session)
        return path

    def load(self, session_id: str | None = None) -> InvestigationSession:
        sid = session_id or self.latest_id()
        if sid is None:
            raise FileNotFoundError("No BugTrail session found yet. Run `bugtrail investigate` first.")
        with self._connect() as conn:
            row = conn.execute(
                "SELECT data FROM sessions WHERE id = ?", (sid,)
            ).fetchone()
        if row is not None:
            return InvestigationSession.model_validate_json(row[0])
        path = self.sessions_dir / f"{sid}.json"
        return InvestigationSession.model_validate_json(path.read_text(encoding="utf-8"))

    def list_ids(self) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute("SELECT id FROM sessions ORDER BY created_at DESC").fetchall()
        if rows:
            return [row[0] for row in rows]
        return [p.stem for p in self.sessions_dir.glob("*.json")]

    def latest_id(self) -> str | None:
        p = self._dir / LATEST_FILE
        if not p.exists():
            return None
        value = p.read_text(encoding="utf-8").strip()
        return value or None

    def history(self, limit: int = 20) -> list[dict[str, Any]]:
        """Past sessions, newest first: id, date, repo, exception, top cause."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, repo_root, exception_name, created_at, data "
                "FROM sessions ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        items: list[dict[str, Any]] = []
        for row in rows:
            session = InvestigationSession.model_validate_json(row[4])
            items.append(
                {
                    "id": session.id,
                    "created_at": session.created_at.isoformat(),
                    "repo_root": session.repo_root,
                    "exception_name": session.exception.get("name") if session.exception else "",
                    "top_commit": session.hypotheses[0].commit_message
                    if session.hypotheses
                    else "",
                    "top_confidence": session.hypotheses[0].confidence
                    if session.hypotheses
                    else None,
                }
            )
        return items

    def find_similar(
        self, signature: str, exclude_id: str, limit: int = 3
    ) -> list[dict[str, Any]]:
        """Previous investigations with the same error signature, newest first."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, created_at, data FROM sessions "
                "WHERE signature = ? AND id != ? ORDER BY created_at DESC LIMIT ?",
                (signature, exclude_id, limit),
            ).fetchall()
        results: list[dict[str, Any]] = []
        for row in rows:
            session = InvestigationSession.model_validate_json(row[2])
            results.append(
                {
                    "id": session.id,
                    "created_at": session.created_at.isoformat(),
                    "top_commit": session.hypotheses[0].commit_message
                    if session.hypotheses
                    else "",
                }
            )
        return results

    def cost_summary(self) -> dict[str, Any]:
        """Aggregate the cost ledger across all indexed sessions."""
        tasks: dict[str, dict[str, Any]] = {}
        session_count = 0
        with self._connect() as conn:
            rows = conn.execute("SELECT data FROM sessions").fetchall()
        for row in rows:
            session = InvestigationSession.model_validate_json(row[0])
            session_count += 1
            for cost in session.costs.rows:
                entry = tasks.setdefault(
                    cost.task, {"calls": 0, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0}
                )
                entry["calls"] += 1
                entry["input_tokens"] += cost.input_tokens
                entry["output_tokens"] += cost.output_tokens
                entry["cost_usd"] += cost.cost_usd
        total = sum(entry["cost_usd"] for entry in tasks.values())
        return {"session_count": session_count, "tasks": tasks, "total": total}

    @staticmethod
    def error_signature(session: InvestigationSession) -> str:
        """Stable fingerprint of the error: name, message, and frame positions."""
        raw = ["commit", session.error_text.strip()[:80]]
        exc = session.exception
        if exc:
            parts = [exc.get("name", ""), (exc.get("message") or "")[:120]]
            for frame in (exc.get("frames") or [])[:5]:
                parts.append(f"{frame.get('file')}:{frame.get('line')}")
            raw = parts
        digest = hashlib.sha256("|".join(raw).encode("utf-8", "replace")).hexdigest()
        return f"{len(raw)}:{digest[:32]}"

    # -- internals --------------------------------------------------------
    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.executescript(_SCHEMA)
        return conn

    def _index(self, session: InvestigationSession) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO sessions "
                "(id, repo_root, exception_name, signature, created_at, data) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    session.id,
                    session.repo_root,
                    session.exception.get("name", "") if session.exception else "",
                    self.error_signature(session),
                    session.created_at.isoformat(),
                    session.model_dump_json(),
                ),
            )

    def _write_latest(self, session_id: str) -> None:
        (self._dir / LATEST_FILE).write_text(session_id, encoding="utf-8")


def new_session_id() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{timestamp}-{uuid.uuid4().hex[:6]}"
