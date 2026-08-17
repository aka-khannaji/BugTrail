"""Integration test: a bug-zoo scenario where blame is masked by a reformat.

Culprit commit "Handle undefined response from payments gateway" replaced a
safe `discountRate || 0` fallback with `payment.response.discount.amount`.
A LATER cosmetic commit ("Reformat checkout with tabs") touched the same line,
so raw git blame points at the innocent reformat. Diff analysis must detect
the whitespace-only commit and drop it, letting the true culprit rank first.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

V1 = '''\
function applyDiscount(cart, payment) {
  const rate = payment.response.discountRate || 0;
  let total = cart.total * (1 - rate);
  return total;
}

module.exports = { applyDiscount };
'''

CULPRIT = '''\
function applyDiscount(cart, payment) {
  const rate = payment.response.discount.amount / 100;
  let total = cart.total * (1 - rate);
  return total;
}

module.exports = { applyDiscount };
'''

REFORMAT = '''\
function applyDiscount(cart, payment) {
\tconst rate = payment.response.discount.amount / 100;
\tlet total = cart.total * (1 - rate);
\treturn total;
}

module.exports = { applyDiscount };
'''

FILE = "app/services/checkout.js"
BUGGY_LINE = 2

ERROR_TEXT = f'''\
TypeError: Cannot read properties of undefined (reading 'amount')
    at applyDiscount ({FILE}:{BUGGY_LINE}:30)
    at getTotal (app/controllers/checkout_controller.js:31:17)
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
def test_checkout_discount_low_confidence(tmp_path: Path):
    target = tmp_path / FILE
    target.parent.mkdir(parents=True)
    target.write_text(V1, encoding="utf-8")

    _git(tmp_path, "init", "-b", "main")
    _git(tmp_path, "config", "user.email", "ziggy@bugtrail.dev")
    _git(tmp_path, "config", "user.name", "BugTrail Bot")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "Initial commit")

    target.write_text(CULPRIT, encoding="utf-8")
    _git(tmp_path, "add", FILE)
    _git(tmp_path, "commit", "-m", "Handle undefined response from payments gateway")
    culprit = _git(tmp_path, "rev-parse", "HEAD")

    target.write_text(REFORMAT, encoding="utf-8")
    _git(tmp_path, "add", FILE)
    _git(tmp_path, "commit", "-m", "Reformat checkout with tabs")
    reformat = _git(tmp_path, "rev-parse", "HEAD")

    assert culprit != reformat

    from bugtrail.adapters.git import GitAdapter
    from bugtrail.investigation.pipeline import run_investigation

    session = run_investigation(
        repo_root=tmp_path,
        error_text=ERROR_TEXT,
        git=GitAdapter(tmp_path),
        allow_ai=False,
    )

    assert session.hypotheses, "no root-cause hypotheses produced"
    shas = [h.commit_sha for h in session.hypotheses]
    # diff analysis drops the whitespace-only reformat despite it being the
    # blame target, so the true culprit must rank first.
    assert shas[0] == culprit, f"expected the culprit first, got {shas}"
    reformat_h = next((h for h in session.hypotheses if h.commit_sha == reformat), None)
    assert reformat_h is not None, "reformat hypothesis missing"
    assert reformat_h.score < session.hypotheses[0].score
    assert any("whitespace-only" in reason for reason in reformat_h.reasons)
