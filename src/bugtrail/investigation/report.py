"""Render an InvestigationSession as a terminal report."""
from __future__ import annotations

from bugtrail.ai.cost import format_cost
from bugtrail.engines.evidence import timeline_summary
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
    else:
        lines.append("")
        lines.append("NO STRONG ROOT CAUSE")
        lines.append(THIN)
        lines.append(
            "Evidence is insufficient to name a commit. Add a longer trace, "
            "logs, or the failing request for a lead."
        )

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

    if session.recurrence:
        lines.append("")
        lines.append("RECURRING")
        lines.append(THIN)
        lines.append("This error signature was investigated before:")
        for prior in session.recurrence[:3]:
            when = prior["created_at"]
            cause = prior["top_commit"] or "(no strong cause)"
            lines.append(f"  - {when}  {cause}  [{prior['id']}]")

    if session.timeline:
        lines.append("")
        lines.append("TIMELINE")
        lines.append(THIN)
        width = max((len(event["ts"]) for event in session.timeline), default=0)
        for event in session.timeline:
            ts = event["ts"].ljust(width) if event["ts"] else " " * width
            marker = ""
            if event["deploy"]:
                marker = "  (deploy)"
            elif event["level"] in ("ERROR", "CRITICAL", "FATAL", "EXCEPTION"):
                marker = "  ✗"
            lines.append(f"{ts}  {event['message']}{marker}")
        summary = timeline_summary(session.timeline)
        if summary:
            lines.append(f"Summary: {summary}")

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
            ts = data.get("ts", "")
            stamp = f" {ts}" if ts else ""
            items.append(
                f"Log [{data.get('level')}]{stamp} line {data.get('line')}: {data.get('message')}"
            )
        elif kind == "request":
            data = node.get("data", {})
            items.append(f"Request: {data.get('method')} {data.get('path')}")
        elif kind == "dependency":
            data = node.get("data", {})
            status = "declared" if data.get("declared") else "missing from manifests"
            items.append(f"Dependency: {data.get('name')} ({status})")
    for hypothesis in session.hypotheses[:3]:
        items.append(
            f"Suspicious commit {hypothesis.commit_sha[:10]}: {hypothesis.commit_message}"
        )
    return items
