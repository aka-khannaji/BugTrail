"""The Evidence Model — everything BugTrail discovers becomes an Evidence node."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class EvidenceKind(str, Enum):
    EXCEPTION = "exception"
    REQUEST = "request"
    LOG = "log"
    FUNCTION = "function"
    FILE = "file"
    COMMIT = "commit"
    DIFF = "diff"
    DATABASE_QUERY = "database_query"
    DEPENDENCY = "dependency"
    DEPLOYMENT = "deployment"
    ENVIRONMENT = "environment"
    TEST = "test"


class Frame(BaseModel):
    """A single stack frame."""

    file: Path
    line: int
    fn: str | None = None
    context: str | None = None


class Evidence(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    kind: EvidenceKind
    label: str = ""
    data: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def __hash__(self) -> int:
        return hash(self.id)

    @classmethod
    def exception(cls, name: str, message: str, frames: list[Frame]) -> "Evidence":
        return cls(
            kind=EvidenceKind.EXCEPTION,
            label=name,
            data={"name": name, "message": message, "frames": [f.model_dump(mode="json") for f in frames]},
        )

    @classmethod
    def file(cls, path: Path | str, *, evidence: str = "") -> "Evidence":
        key = str(path).replace("\\", "/")
        return cls(kind=EvidenceKind.FILE, label=key, data={"path": key, "evidence": evidence})

    @classmethod
    def commit(cls, sha: str, message: str, *, author: str = "", date: str = "") -> "Evidence":
        data = {"sha": sha, "message": message, "author": author, "date": date}
        return cls(kind=EvidenceKind.COMMIT, label=sha[:10], data=data)

    @classmethod
    def database_query(cls, description: str) -> "Evidence":
        return cls(kind=EvidenceKind.DATABASE_QUERY, label=description, data={"description": description})

    @classmethod
    def request(cls, method: str, path: str) -> "Evidence":
        return cls(
            kind=EvidenceKind.REQUEST,
            label=f"{method} {path}",
            data={"method": method, "path": path},
        )

    @classmethod
    def log(
        cls, level: str, message: str, *, line: int = 0, source: str = "", ts: str = ""
    ) -> "Evidence":
        data = {"level": level, "message": message, "line": line}
        if source:
            data["source"] = source
        if ts:
            data["ts"] = ts
        return cls(kind=EvidenceKind.LOG, label=f"{level}: {message[:60]}", data=data)

    @classmethod
    def dependency(cls, name: str, *, declared: bool = False, manifest: str = "") -> "Evidence":
        data = {"name": name, "declared": declared, "manifest": manifest}
        return cls(kind=EvidenceKind.DEPENDENCY, label=name, data=data)
