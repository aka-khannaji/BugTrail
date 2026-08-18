"""Tests for log analysis — log-shaped lines extracted from pasted error text."""
from __future__ import annotations

from pathlib import Path

from bugtrail.engines.evidence import extract_log_lines

TIMESTAMPED = (
    "[2026-08-17 09:00:00] app.ERROR: Failed to place order, retrying\n"
    "[2026-08-17 09:00:01] app.INFO: Retry attempt 1\n"
)
SOURCE_TAGGED = (
    "app.ERROR: SQLSTATE[23000]: Integrity constraint violation\n"
    "worker.WARNING: consumer lagging\n"
)
PLAIN = (
    "Traceback (most recent call last):\n"
    '  File "app/services/order_service.py", line 24, in create_order\n'
    "sqlite3.IntegrityError: UNIQUE constraint failed: orders.id\n"
)


def test_timestamped_log_lines():
    entries = extract_log_lines(TIMESTAMPED)
    assert len(entries) == 2
    assert entries[0]["level"] == "ERROR"
    assert entries[0]["line"] == 1
    assert "Failed to place order" in entries[0]["message"]
    assert entries[1]["level"] == "INFO"


def test_source_tagged_log_lines():
    entries = extract_log_lines(SOURCE_TAGGED)
    assert len(entries) == 2
    assert entries[0]["source"] == "app"
    assert entries[0]["level"] == "ERROR"
    assert entries[1]["level"] == "WARNING"
    assert entries[1]["line"] == 2


def test_plain_stack_trace_has_no_log_lines():
    assert extract_log_lines(PLAIN) == []


def test_empty_input():
    assert extract_log_lines("") == []


def test_pipeline_includes_log_evidence(tmp_path):
    from bugtrail.investigation.pipeline import run_investigation

    target = tmp_path / "app/services/order_service.py"
    target.parent.mkdir(parents=True)
    target.write_text("class OrderService:\n    pass\n", encoding="utf-8")

    error_text = (
        "[2026-08-17 09:00:03] app.ERROR: Retry failed again\n"
        "Traceback (most recent call last):\n"
        f'  File "{target.as_posix()}", line 24, in create_order\n'
        '    tx.execute("INSERT INTO orders (id) VALUES (?)", (order_id,))\n'
        "sqlite3.IntegrityError: UNIQUE constraint failed: orders.id: "
        "Duplicate entry '42' for key 'orders.id'\n"
    )

    session = run_investigation(
        repo_root=tmp_path,
        error_text=error_text,
        git=_FakeGit(),
        allow_ai=False,
    )
    logs = [n for n in session.graph["nodes"] if n["kind"] == "log"]
    assert len(logs) == 1
    assert logs[0]["data"]["level"] == "ERROR"
    assert logs[0]["data"]["line"] == 1
    assert "Retry failed again" in logs[0]["data"]["message"]

    from bugtrail.investigation.report import render_report

    report = render_report(session)
    assert "Log [ERROR]" in report
    assert "Retry failed again" in report
    assert "2026-08-17T09:00:03" in report


class _FakeGit:
    available = True
    repo_root: Path | None = None

    def recent_commits(self, count: int = 20):
        return []

    def blame_line(self, file: str, line: int):
        return None

    def changed_files(self, sha: str):
        return []
