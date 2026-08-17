"""Render an InvestigationSession as a terminal report."""
from __future__ import annotations

from bugtrail.ai.cost import format_cost
from bugtrail.investigation.session import InvestigationSession

BAR = "=" * 60
THIN = "-" * 60

# A commit touching hundreds of files could otherwise drown the report in
# "changed in commit X" lines. Show a handful, then summarize the rest.
MAX_REASONS_PER_HYPOTHESIS = 15


def render_report(session: InvestigationSession) -> str:
    lines: list[str] = []
    lines.append("BUGTRAIL INVESTIGATION")
    lines.append(BAR)

    if session.exception:
        exc = session.exception
        lines.append("")
        lines.append(f"✖ {exc.get('name', 'UnknownError')}")
        lines.append(f"  {exc.get('message', '')}")

    if session.hypotheses:
        top = session.hypotheses[0]
        lines.append("")
        if session.exception:
            lines.append("LIKELY ROOT CAUSE")
        else:
            lines.append("MOST RELEVANT COMMIT")
        lines.append(THIN)
        lines.append(top.commit_message)
        for path in top.files:
            lines.append(f"   {path}")
        lines.append(f"Confidence: {top.confidence * 100:.0f}%")
        if not session.exception:
            lines.append("(no error text supplied — this is a change overview, not a root cause)")

    lines.append("")
    lines.append("EVIDENCE")
    lines.append(THIN)
    number = 1
    for evidence in _evidence_list(session):
        lines.append(f"{number}. {evidence}")
        number += 1
    for hypothesis in session.hypotheses[:3]:
        for reason in hypothesis.reasons[:MAX_REASONS_PER_HYPOTHESIS]:
            lines.append(f"{number}. {reason}")
            number += 1
        remaining = len(hypothesis.reasons) - MAX_REASONS_PER_HYPOTHESIS
        if remaining > 0:
            lines.append(
                f"{number}. +{remaining} more evidence entries for commit {hypothesis.commit_sha[:10]}"
            )
            number += 1

    lines.append("")
    lines.append("NEXT INVESTIGATION")
    lines.append(THIN)
    if session.hypotheses:
        for step in session.hypotheses[0].next_steps:
            lines.append(f"  -> {step}")
    if session.ai_summary:
        summary = session.ai_summary.strip().replace("\n", "\n  ")
        lines.append("")
        lines.append("AI NOTES")
        lines.append("  " + summary)

    lines.append("")
    lines.append("AI COST")
    lines.append(THIN)
    max_width = max((len(row.description) for row in session.costs.rows), default=20)
    for row in session.costs.rows:
        lines.append(f"{row.description:<{max_width}}")
    lines.append("-" * max_width)
    lines.append(f"{format_cost(session.costs.total):>8}  Total")
    return "\n".join(lines)


def _evidence_list(session: InvestigationSession) -> list[str]:
    nodes = session.graph.get("nodes", [])
    items: list[str] = []
    for node in nodes:
        kind = node.get("kind")
        if kind == "exception":
            data = node.get("data", {})
            items.append(
                f"Exception: {data.get('name')} ({len(data.get('frames', []))} frames)"
            )
        elif kind == "database_query":
            items.append(f"Database: {node.get('label', node.get('data', {}).get('description', ''))}")
        elif kind == "log":
            data = node.get("data", {})
            items.append(
                f"Log [{data.get('level')}] line {data.get('line')}: {data.get('message')}"
            )
        elif kind == "dependency":
            data = node.get("data", {})
            status = "declared" if data.get("declared") else "missing from manifests"
            items.append(f"Dependency: {data.get('name')} ({status})")
    for hypothesis in session.hypotheses[:3]:
        items.append(
            f"Suspicious commit {hypothesis.commit_sha[:10]}: {hypothesis.commit_message}"
        )
    return items
