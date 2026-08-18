"""Investigation pipeline — evidence -> graph -> deterministic scoring -> AI.

Deterministic analysis always runs. AI is an optional last step that ranks
hypotheses and writes a summary; if it is unavailable, the report is still
complete. Cost usage is recorded for every operation.
"""
from __future__ import annotations

from pathlib import Path

from bugtrail.adapters.git import GitAdapter
from bugtrail.ai.cost import CostLedger, CostRow
from bugtrail.ai.provider import AIProvider
from bugtrail.config import BugTrailConfig, load_config
from bugtrail.engines.detective import DetectiveEngine, Hypothesis
from bugtrail.engines.evidence import (
    MAX_FILES_SCORED_PER_COMMIT,
    EvidenceEngine,
    build_timeline,
)
from bugtrail.evidence.graph import REL_FILE_MODIFIED_BY, EvidenceGraph
from bugtrail.investigation.session import InvestigationSession
from bugtrail.storage import new_session_id

DETERMINISTIC_TASKS = ("stack parsing", "git analysis", "evidence ranking")

# Keep the AI prompt small enough for the bundled 0.5B model (16k ctx) and any
# small local model. Deterministic ranking never depends on this.
MAX_PROMPT_CHARS = 7000

SYSTEM_PROMPT = (
    "You are BugTrail, a root-cause investigation assistant for developers. "
    "Reason strictly from the evidence provided. Do not speculate beyond it. "
    "Answer in 2-4 sentences. If a database error is present, treat constraint "
    "violations as strong evidence."
)


def run_investigation(
    *,
    repo_root: Path,
    error_text: str = "",
    commit_ref: str | None = None,
    config: BugTrailConfig | None = None,
    git: GitAdapter | None = None,
    allow_ai: bool = True,
) -> InvestigationSession:
    config = config or load_config(repo_root)
    git = git or GitAdapter.discover(repo_root)

    ledger = CostLedger()
    for task in DETERMINISTIC_TASKS:
        ledger.record_deterministic(task)

    graph = EvidenceGraph()
    engine = EvidenceEngine(repo_root, git)
    exc = engine.collect_error(graph, error_text) if error_text else None
    engine.attach_git(graph)

    commit_head = None
    if commit_ref and git.available:
        info = git.commit_info(commit_ref)
        if info:
            commit_head = info
            commit = graph.ensure_commit(
                info["sha"], info["message"], author=info["author"], date=info["date"]
            )
            if len(info.get("parents") or []) > 1:
                commit.data["merge"] = True
            else:
                for index, rel in enumerate(git.changed_files(info["sha"])):
                    node = graph.file_node(rel)
                    if index < MAX_FILES_SCORED_PER_COMMIT:
                        strength = node.data.setdefault("commit_strength", {})
                        strength[info["sha"]] = max(strength.get(info["sha"], 0.0), 0.6)
                    graph.link(node.id, REL_FILE_MODIFIED_BY, commit.id)

    if exc is None and commit_head is None:
        raise ValueError(
            "Nothing to investigate: provide error text (--error or stdin) or --commit."
        )

    detective = DetectiveEngine(git)
    hypotheses = detective.investigate(graph, require_frames=commit_head is None)

    ai_summary = ""
    if allow_ai and config.ai_enabled:
        provider = AIProvider(config.ai, config.api_key())
        if provider.available:
            prompt = _build_ai_prompt(graph, hypotheses)
            result = provider.chat("evidence ranking", prompt, SYSTEM_PROMPT)
            if result is not None:
                ledger.record(
                    CostRow(
                        task="evidence ranking (ai)",
                        provider=result.provider,
                        model=result.model,
                        input_tokens=result.input_tokens,
                        output_tokens=result.output_tokens,
                        latency_ms=result.latency_ms,
                        cost_usd=result.cost_usd,
                    )
                )
                hypotheses = _maybe_rerank(hypotheses, result.content)
                ai_summary = result.content.strip()

    session = InvestigationSession.create(
        session_id=new_session_id(),
        repo_root=str(repo_root),
        error_text=error_text,
        exception=exc.data if exc else None,
        graph=graph.to_dict(),
        hypotheses=hypotheses,
        costs=ledger,
        ai_summary=ai_summary,
        timeline=build_timeline(graph),
    )
    return session


def _build_ai_prompt(graph: EvidenceGraph, hypotheses: list[Hypothesis]) -> str:
    sections: list[str] = ["Evidence:"]
    for exception in graph.exceptions():
        sections.append(f"- {exception.data['name']}: {exception.data['message']}")
        for raw in exception.data.get("frames", [])[:15]:
            sections.append(f"    at {raw['file']}:{raw['line']} -> {raw.get('fn') or ''}".rstrip())
    for node in graph.of_kind("database_query"):
        sections.append(
            f"- Database signal: {node.data.get('description', node.label)}"
        )
    for node in graph.of_kind("log")[:15]:
        sections.append(
            f"- Log [{node.data.get('level')}] line {node.data.get('line')}: "
            f"{node.data.get('message')}"
        )
    for node in graph.of_kind("dependency"):
        status = "declared" if node.data.get("declared") else "not declared in repo manifests"
        sections.append(f"- Dependency signal: {node.data.get('name')} ({status})")

    sections.append("")
    sections.append("Suspected root causes (deterministic ranking):")
    for index, hypothesis in enumerate(hypotheses[:5], start=1):
        files = ", ".join(hypothesis.files[:5])
        sections.append(
            f"{index}. commit {hypothesis.commit_sha[:10]} "
            f"'{hypothesis.commit_message[:80]}' "
            f"confidence={hypothesis.confidence} files={files}"
        )
    sections.append("")
    sections.append(
        "Task: is the top cause consistent with the evidence? If another listed cause "
        "fits better, say so. Reply with the best commit sha then a short justification."
    )
    prompt = "\n".join(sections)
    if len(prompt) > MAX_PROMPT_CHARS:
        prompt = prompt[:MAX_PROMPT_CHARS] + "\n...[truncated]"
    return prompt


def _maybe_rerank(hypotheses: list[Hypothesis], ai_text: str) -> list[Hypothesis]:
    """If the AI clearly names one of our hypotheses, move it to the front."""
    if not hypotheses:
        return hypotheses
    for hypothesis in hypotheses:
        if hypothesis.commit_sha[:10] in ai_text or hypothesis.commit_sha in ai_text:
            if hypothesis is hypotheses[0]:
                return hypotheses
            order = [hypothesis, *[h for h in hypotheses if h is not hypothesis]]
            return order
    return hypotheses
