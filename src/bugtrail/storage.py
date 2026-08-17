"""Storage of investigation sessions under .bugtrail/."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from bugtrail.investigation.session import InvestigationSession

DIR_NAME = ".bugtrail"
LATEST_FILE = "latest.txt"


class Storage:
    def __init__(self, repo_root: Path):
        self._dir = repo_root / DIR_NAME
        self._dir.mkdir(parents=True, exist_ok=True)

    @property
    def sessions_dir(self) -> Path:
        d = self._dir / "sessions"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def save(self, session: InvestigationSession) -> Path:
        path = self.sessions_dir / f"{session.id}.json"
        path.write_text(session.model_dump_json(indent=2), encoding="utf-8")
        self._write_latest(session.id)
        return path

    def load(self, session_id: str | None = None) -> InvestigationSession:
        sid = session_id or self.latest_id()
        if sid is None:
            raise FileNotFoundError("No BugTrail session found yet. Run `bugtrail investigate` first.")
        path = self.sessions_dir / f"{sid}.json"
        data = path.read_text(encoding="utf-8")
        return InvestigationSession.model_validate_json(data)

    def list_ids(self) -> list[str]:
        return [p.stem for p in self.sessions_dir.glob("*.json")]

    def latest_id(self) -> str | None:
        p = self._dir / LATEST_FILE
        if not p.exists():
            return None
        value = p.read_text(encoding="utf-8").strip()
        return value or None

    def _write_latest(self, session_id: str) -> None:
        (self._dir / LATEST_FILE).write_text(session_id, encoding="utf-8")


def new_session_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
