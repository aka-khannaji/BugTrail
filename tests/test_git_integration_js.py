"""Integration test: a real git repo and a real JS bug-zoo scenario.

Bug: "Optimize cart total calculation" hoisted the first line item out of the
loop. For an empty cart, cart.items[0] is undefined and reading '.price'
throws a TypeError. The stack trace points at the hoisted line.
BugTrail should rank that commit first, deterministically.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

V1 = '''\
function computeTotal(cart) {
  let total = 0;
  for (const item of cart.items) {
    total += item.price * item.quantity;
  }
  return total;
}

module.exports = { computeTotal };
'''

V2 = '''\
function computeTotal(cart) {
  const subtotal = cart.items[0].price * cart.items[0].quantity;
  let total = subtotal;
  for (let i = 1; i < cart.items.length; i++) {
    total += cart.items[i].price * cart.items[i].quantity;
  }
  return total;
}

module.exports = { computeTotal };
'''

FILE = "app/services/cart_service.js"
BUGGY_LINE = 2

ERROR_TEXT = f'''\
TypeError: Cannot read properties of undefined (reading 'price')
    at computeTotal ({FILE}:{BUGGY_LINE}:30)
    at getCartTotal (app/controllers/cart_controller.js:48:17)
    at processRequest (app/server.js:23:9)
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
def test_cart_service_js_bug_zoo(tmp_path: Path):
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
    _git(tmp_path, "commit", "-m", "Optimize cart total calculation")
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
        "expected the hoisted-loop commit to be ranked first, got "
        f"{top.commit_sha} ({top.commit_message})"
    )
    assert any("last modified by commit" in reason for reason in top.reasons)

    from bugtrail.investigation.report import render_report

    report = render_report(session)
    assert FILE in report
    assert "TypeError" in report
