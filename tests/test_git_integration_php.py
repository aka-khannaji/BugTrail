"""Integration test: a real git repo and a real PHP (Laravel) bug-zoo scenario.

Bug: "Use Eloquent create() for order placement" replaced an exists()-guarded
insert with Order::create(). On retry the order already exists and the unique
constraint throws a duplicate-entry SQLSTATE. The stack trace points at the
Order::create line. Laravel frames carry the deploy-root path (/var/www/html),
so the test repo mirrors that layout.
BugTrail should rank that commit first, deterministically.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

V1 = '''\
<?php

namespace App\\Services;

use App\\Models\\Order;
use Illuminate\\Support\\Facades\\DB;

class OrderService
{
    public function createOrder(int $orderId): array
    {
        $exists = DB::table('orders')->where('id', $orderId)->exists();
        if ($exists) {
            return ['id' => $orderId];
        }
        DB::table('orders')->insert(['id' => $orderId]);
        return ['id' => $orderId];
    }
}
'''

V2 = '''\
<?php

namespace App\\Services;

use App\\Models\\Order;

class OrderService
{
    public function createOrder(int $orderId): array
    {
        $order = Order::create(['id' => $orderId]);
        return ['id' => $order->id];
    }
}
'''

FILE = "var/www/html/app/Services/OrderService.php"
BUGGY_LINE = 11

ERROR_TEXT = (
    "SQLSTATE[23000]: Integrity constraint violation: 1062 Duplicate entry "
    "'42' for key 'orders.id' (SQL: insert into `orders` (`id`) values (42))\n"
    f"#0 /{FILE}({BUGGY_LINE}): App\\Services\\OrderService->createOrder()\n"
    "#1 /var/www/html/app/Http/Controllers/OrderController.php(88): "
    "App\\Http\\Controllers\\OrderController->store()\n"
)


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
def test_order_placement_php_bug_zoo(tmp_path: Path):
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
    _git(tmp_path, "commit", "-m", "Use Eloquent create() for order placement")
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
        "expected the Eloquent refactor commit to be ranked first, got "
        f"{top.commit_sha} ({top.commit_message})"
    )
    assert any("last modified by commit" in reason for reason in top.reasons)

    from bugtrail.investigation.report import render_report

    report = render_report(session)
    assert FILE in report
    assert "Duplicate" in report or "duplicate" in report
