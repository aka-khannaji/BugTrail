"""DetectiveEngine — deterministic root-cause ranking.

Given the evidence graph, produces ranked hypotheses with the reasons for
each, without touching an LLM. This is the "deterministic first" layer.
"""
from __future__ import annotations

import re

from pydantic import BaseModel

from bugtrail.evidence.graph import EvidenceGraph
from bugtrail.evidence.models import EvidenceKind


class Hypothesis(BaseModel):
    commit_sha: str
    commit_message: str
    files: list[str]
    score: float
    confidence: float
    reasons: list[str]
    next_steps: list[str]


class DetectiveEngine:
    def __init__(self, git) -> None:
        self.git = git

    def investigate(
        self, graph: EvidenceGraph, limit: int = 5, require_frames: bool = True
    ) -> list[Hypothesis]:
        error_keywords = self._extract_keywords(graph)
        commits = {n.data.get("sha"): n for n in graph.of_kind(EvidenceKind.COMMIT)}
        hits: dict[str, dict] = {}

        for node in graph.of_kind(EvidenceKind.FILE):
            strength = node.data.get("commit_strength") or {}
            frames = node.data.get("frames") or []
            if not strength:
                continue
            if require_frames and not frames:
                continue
            path = node.data.get("path", "?")
            for sha, base in strength.items():
                entry = hits.setdefault(
                    sha,
                    {
                        "message": commits.get(sha).data["message"] if sha in commits else sha,
                        "score": 0.0,
                        "reasons": [],
                        "files": [],
                        "lines": [],
                    },
                )
                if base >= 1.0 and frames:
                    line = frames[0]["line"]
                    entry["lines"].append(line)
                    entry["reasons"].append(
                        f"Frame line {line} in {path} was last modified by commit {sha[:10]}"
                    )
                    entry["score"] += base
                else:
                    entry["reasons"].append(f"{path} changed in commit {sha[:10]}")
                    entry["score"] += base * 0.5
                entry["files"].append(path)

        max_score = max((entry["score"] for entry in hits.values()), default=0.0)
        hypotheses: list[Hypothesis] = []
        for sha, entry in hits.items():
            message = entry["message"].lower()
            matched = [word for word in error_keywords if word in message]
            if matched:
                entry["score"] += min(0.3, 0.12 * len(matched))
                entry["reasons"].append(f'Commit message mentions "{", ".join(matched)}"')
            commit_node = commits.get(sha)
            if commit_node is not None and commit_node.data.get("cosmetic"):
                entry["score"] *= 0.15
                entry["reasons"].append(f"Commit {sha[:10]} is whitespace-only (diff analysis)")
            if commit_node is not None and commit_node.data.get("merge"):
                entry["score"] *= 0.05
                entry["reasons"].append(f"Commit {sha[:10]} is a merge commit (no changes of its own)")
            confidence = 0.0
            if max_score > 0:
                confidence = round(min(0.99, 0.3 + 0.6 * (entry["score"] / max_score)), 2)
            files = list(dict.fromkeys(entry["files"]))
            lines = sorted(set(entry["lines"]))
            next_steps = [f"Inspect commit {sha[:10]}"]
            if files and lines:
                next_steps.append(f"Review {files[0]}:{lines[0]}")
            hypotheses.append(
                Hypothesis(
                    commit_sha=sha,
                    commit_message=entry["message"],
                    files=files,
                    score=round(entry["score"], 3),
                    confidence=confidence,
                    reasons=entry["reasons"],
                    next_steps=next_steps,
                )
            )
        hypotheses.sort(key=lambda hypothesis: hypothesis.score, reverse=True)
        return hypotheses[:limit]

    @staticmethod
    def _extract_keywords(graph: EvidenceGraph) -> set[str]:
        words: set[str] = set()
        for exception in graph.exceptions():
            for value in (exception.data.get("message", "") or "").split():
                clean = re.sub(r"[^a-zA-Z]", "", value).lower()
                if len(clean) >= 4:
                    words.add(clean)
        return words
