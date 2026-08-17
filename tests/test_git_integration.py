"""Integration test: a real git repository and a real bug-zoo scenario.

Bug: "Add retry handling for failed orders" introduced a duplicate-insert
retry in OrderService. The stack trace points at the retry line.
BugTrail should rank that commit first, purely deterministically.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

V1 = '''\
import time


def db_transaction():
    return DatabaseTransaction()


class DatabaseTransaction:
    def __init__(self):
        self.committed = False

    def execute(self, query, params):
        pass

    def commit(self):
        self.committed = True


class OrderService:
    def create_order(self, order_id: int) -> dict:
        tx = db_transaction()
        tx.execute("INSERT INTO orders (id) VALUES (?)", (order_id,))
        tx.commit()
        return {"id": order_id}
'''

V2 = '''\
import time


def db_transaction():
    return DatabaseTransaction()


class DatabaseTransaction:
    def __init__(self):
        self.committed = False

    def execute(self, query, params):
        pass

    def commit(self):
        self.committed = True


class OrderService:
    def create_order(self, order_id: int) -> dict:
        tx = db_transaction()
        tx.execute("INSERT INTO orders (id) VALUES (?)", (order_id,))
        for attempt in range(3):
            if tx.committed:
                break
            tx.execute("INSERT INTO orders (id) VALUES (?)", (order_id,))  # retry
        tx.commit()
        return {"id": order_id}
'''

FILE = "app/services/order_service.py"
FALLBACK_LINE = 24

ERROR_TEXT = f'''\
Traceback (most recent call last):
  File "{FILE}", line {FALLBACK_LINE}, in create_order
    tx.execute("INSERT INTO orders (id) VALUES (?)", (order_id,))  # retry
sqlite3.IntegrityError: UNIQUE constraint failed: orders.id: Duplicate entry '42' for key 'orders.id'
'''


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    return result.stdout.strip()


@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
def test_order_service_bug_zoo(tmp_path: Path):
    target = tmp_path / FILE
    target.parent.mkdir(parents=True)
    target.write_text(V1, encoding="utf-8")

    _git(tmp_path, "init", "-b", "main")
    _git(tmp_path, "config", "user.email", "ziggy@bugtrail.dev")
    _git(tmp_path, "config", "user.name", "BugTrail Bot")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "Initial commit")
    commit_a = _git(tmp_path, "rev-parse", "HEAD")

    target.write_text(V2, encoding="utf-8")
    _git(tmp_path, "add", FILE)
    _git(tmp_path, "commit", "-m", "Add retry handling for failed orders")
    commit_b = _git(tmp_path, "rev-parse", "HEAD")

    assert commit_a != commit_b

    from bugtrail.adapters.git import GitAdapter
    from bugtrail.investigation.pipeline import run_investigation

    session = run_investigation(
        repo_root=tmp_path,
        error_text=ERROR_TEXT,
        git=GitAdapter(tmp_path),
        allow_ai=False,
    )

    assert session.hypotheses, "no root-cause hypotheses produced"
    top = session.hypotheses[0]
    assert top.commit_sha == commit_b, (
        "expected the retry commit to be ranked first, got "
        f"{top.commit_sha} ({top.commit_message})"
    )
    assert any("modified by commit" in reason for reason in top.reasons)

    from bugtrail.investigation.report import render_report

    report = render_report(session)
    assert FILE in report
    assert "Duplicate" in report or "duplicate" in report
