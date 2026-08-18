"""InvestigationSession — the persisted artifact of one investigation."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from bugtrail.ai.cost import CostLedger
from bugtrail.engines.detective import Hypothesis


class InvestigationSession(BaseModel):
    id: str
    repo_root: str = ""
    error_text: str = ""
    exception: dict[str, Any] | None = None
    graph: dict[str, Any] = Field(default_factory=dict)
    hypotheses: list[Hypothesis] = Field(default_factory=list)
    timeline: list[dict[str, Any]] = Field(default_factory=list)
    ai_summary: str = ""
    costs: CostLedger = Field(default_factory=CostLedger)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @classmethod
    def create(
        cls,
        session_id: str,
        repo_root: str,
        error_text: str,
        exception: dict[str, Any] | None,
        graph: dict[str, Any],
        hypotheses: list[Hypothesis],
        costs: CostLedger,
        ai_summary: str = "",
        timeline: list[dict[str, Any]] | None = None,
    ) -> "InvestigationSession":
        return cls(
            id=session_id,
            repo_root=repo_root,
            error_text=error_text,
            exception=exception,
            graph=graph,
            hypotheses=hypotheses,
            ai_summary=ai_summary,
            timeline=timeline or [],
            costs=costs,
        )
