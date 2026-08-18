"""Bug Zoo eval harness — BugTrail's regression benchmark.

A zoo scenario describes a real-ish bug: an initial repo tree, a sequence of
commits, and the error text a developer pastes. The harness materializes it as
a real git repository, runs the full deterministic pipeline, and asserts the
outcome — either the correct root cause ranks inside the top N, or the engine
honestly reports low confidence instead of fabricating one.

The zoo is the moat: every engine change is proven against it before shipping.

Run the whole zoo and print a pass-rate table:

    python -m tests.zoo

Or as a pytest gate (one test per scenario): tests/test_zoo.py
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping


@dataclass(frozen=True)
class CommitStep:
    """One commit in the scenario's history.

    ``changes`` maps repo-relative paths to their new full content; an empty
    string deletes the file.
    """

    message: str
    changes: Mapping[str, str]


@dataclass(frozen=True)
class Scenario:
    name: str
    error_text: str
    files: Mapping[str, str] = field(default_factory=dict)
    commits: tuple[CommitStep, ...] = ()
    culprit_message: str | None = None
    top_n: int = 1
    honest_low: bool = False
    notes: str = ""


@dataclass
class ZooResult:
    scenario: Scenario
    passed: bool
    detail: str
    top: list[str] = field(default_factory=list)


def build_repo(scenario: Scenario, root: Path) -> dict[str, str]:
    """Materialize the scenario as a real git repo. Returns {message: sha}."""
    if shutil.which("git") is None:
        raise RuntimeError("git is not installed")

    def git(*args: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        return result.stdout.strip()

    for rel, content in scenario.files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    git("init", "-b", "main")
    git("config", "user.email", "ziggy@bugtrail.dev")
    git("config", "user.name", "BugTrail Bot")
    git("add", ".")
    git("commit", "-m", "Initial commit")

    shas: dict[str, str] = {}
    for step in scenario.commits:
        for rel, content in step.changes.items():
            path = root / rel
            if content == "":
                path.unlink(missing_ok=True)
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
        git("add", ".")
        git("commit", "-m", step.message)
        shas[step.message] = git("rev-parse", "HEAD")
    return shas


def run_scenario(scenario: Scenario, workdir: Path) -> ZooResult:
    from bugtrail.adapters.git import GitAdapter
    from bugtrail.investigation.pipeline import run_investigation

    build_repo(scenario, workdir)
    session = run_investigation(
        repo_root=workdir,
        error_text=scenario.error_text,
        git=GitAdapter(workdir),
        allow_ai=False,
    )
    top = [h.commit_message for h in session.hypotheses[: scenario.top_n]]

    if scenario.honest_low:
        fabricated = [h for h in session.hypotheses if h.confidence > 0.5]
        if fabricated:
            worst = fabricated[0]
            return ZooResult(
                scenario,
                False,
                f"fabricated confidence: {worst.commit_sha} at {worst.confidence}",
                top,
            )
        return ZooResult(
            scenario,
            True,
            f"honest low confidence ({len(session.hypotheses)} hypotheses)",
            top,
        )

    if scenario.culprit_message is None:
        raise ValueError(f"scenario '{scenario.name}' needs culprit_message or honest_low")

    if scenario.culprit_message in top:
        return ZooResult(scenario, True, f"culprit in top {scenario.top_n}", top)
    ranked = [h for h in session.hypotheses if h.commit_message == scenario.culprit_message]
    if ranked:
        rank = session.hypotheses.index(ranked[0]) + 1
        detail = f"culprit '{scenario.culprit_message}' ranked #{rank} (need top {scenario.top_n})"
    else:
        detail = f"culprit '{scenario.culprit_message}' not in hypotheses"
    return ZooResult(scenario, False, detail, top)


def run_all(base: Path) -> list[ZooResult]:
    results: list[ZooResult] = []
    for scenario in SCENARIOS:
        results.append(run_scenario(scenario, base / scenario.name))
    return results


def _main() -> int:
    base = Path(tempfile.mkdtemp(prefix="bugtrail-zoo-"))
    results = run_all(base)
    passed = sum(1 for result in results if result.passed)
    print(f"Bug Zoo: {passed}/{len(results)} scenarios passed\n")
    for result in results:
        status = "PASS" if result.passed else "FAIL"
        top = " | ".join(f"'{m[:40]}'" for m in result.top) or "(none)"
        print(f"  [{status}] {result.scenario.name}")
        print(f"         {result.detail}")
        if not result.passed:
            print(f"         top: {top}")
    print(f"\npass rate: {passed}/{len(results)}")
    return 0 if passed == len(results) else 1


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------

ORDER_SERVICE = Scenario(
    name="order_service",
    notes="Python duplicate-insert retry: 'Add retry handling for failed orders' re-inserts the row.",
    files={
        "app/services/order_service.py": '''\
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
''',
    },
    commits=(
        CommitStep(
            "Add retry handling for failed orders",
            {
                "app/services/order_service.py": '''\
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
''',
            },
        ),
    ),
    error_text='''\
Traceback (most recent call last):
  File "app/services/order_service.py", line 24, in create_order
    tx.execute("INSERT INTO orders (id) VALUES (?)", (order_id,))  # retry
sqlite3.IntegrityError: UNIQUE constraint failed: orders.id: Duplicate entry '42' for key 'orders.id'
''',
    culprit_message="Add retry handling for failed orders",
)

CART_SERVICE = Scenario(
    name="cart_service",
    notes="JS/V8 hoisted-loop bug: empty cart reads items[0].price -> TypeError.",
    files={
        "app/services/cart_service.js": '''\
function computeTotal(cart) {
  let total = 0;
  for (const item of cart.items) {
    total += item.price * item.quantity;
  }
  return total;
}

module.exports = { computeTotal };
''',
    },
    commits=(
        CommitStep(
            "Optimize cart total calculation",
            {
                "app/services/cart_service.js": '''\
function computeTotal(cart) {
  const subtotal = cart.items[0].price * cart.items[0].quantity;
  let total = subtotal;
  for (let i = 1; i < cart.items.length; i++) {
    total += cart.items[i].price * cart.items[i].quantity;
  }
  return total;
}

module.exports = { computeTotal };
''',
            },
        ),
    ),
    error_text='''\
TypeError: Cannot read properties of undefined (reading 'price')
    at computeTotal (app/services/cart_service.js:2:30)
    at getCartTotal (app/controllers/cart_controller.js:48:17)
    at processRequest (app/server.js:23:9)
''',
    culprit_message="Optimize cart total calculation",
)

ORDER_PLACEMENT = Scenario(
    name="order_placement",
    notes="PHP/Laravel deploy-root paths: Eloquent create() on a duplicate row -> SQLSTATE 23000.",
    files={
        "var/www/html/app/Services/OrderService.php": '''\
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
''',
    },
    commits=(
        CommitStep(
            "Use Eloquent create() for order placement",
            {
                "var/www/html/app/Services/OrderService.php": '''\
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
''',
            },
        ),
    ),
    error_text=(
        "SQLSTATE[23000]: Integrity constraint violation: 1062 Duplicate entry "
        "'42' for key 'orders.id' (SQL: insert into `orders` (`id`) values (42))\n"
        "#0 /var/www/html/app/Services/OrderService.php(11): "
        "App\\Services\\OrderService->createOrder()\n"
        "#1 /var/www/html/app/Http/Controllers/OrderController.php(88): "
        "App\\Http\\Controllers\\OrderController->store()\n"
    ),
    culprit_message="Use Eloquent create() for order placement",
)

CHECKOUT_DISCOUNT = Scenario(
    name="checkout_discount",
    notes="Low-confidence trap: a cosmetic reformat masks the true culprit; diff analysis must drop it.",
    files={
        "app/services/checkout.js": '''\
function applyDiscount(cart, payment) {
  const rate = payment.response.discountRate || 0;
  let total = cart.total * (1 - rate);
  return total;
}

module.exports = { applyDiscount };
''',
    },
    commits=(
        CommitStep(
            "Handle undefined response from payments gateway",
            {
                "app/services/checkout.js": '''\
function applyDiscount(cart, payment) {
  const rate = payment.response.discount.amount / 100;
  let total = cart.total * (1 - rate);
  return total;
}

module.exports = { applyDiscount };
''',
            },
        ),
        CommitStep(
            "Reformat checkout with tabs",
            {
                "app/services/checkout.js": '''\
function applyDiscount(cart, payment) {
\tconst rate = payment.response.discount.amount / 100;
\tlet total = cart.total * (1 - rate);
\treturn total;
}

module.exports = { applyDiscount };
''',
            },
        ),
    ),
    error_text='''\
TypeError: Cannot read properties of undefined (reading 'amount')
    at applyDiscount (app/services/checkout.js:2:30)
    at getTotal (app/controllers/checkout_controller.js:31:17)
''',
    culprit_message="Handle undefined response from payments gateway",
)

OLD_COMMIT_REGRESSION = Scenario(
    name="old_commit_regression",
    notes="The culprit is an old commit; newer unrelated commits must not outrank the blamed line.",
    files={
        "app/services/billing.py": '''\
class BillingService:
    def __init__(self, rates):
        self.rates = rates

    def calculate(self, order):
        base = sum(item.price for item in order.items)
        return base
''',
        "app/api/health.py": "def health():\n    return {'status': 'ok'}\n",
        "README.md": "# Billing API\n",
    },
    commits=(
        CommitStep(
            "Add discount stacking to billing",
            {
                "app/services/billing.py": '''\
class BillingService:
    def __init__(self, rates):
        self.rates = rates

    def calculate(self, order):
        base = sum(item.price for item in order.items)
        for coupon in order.coupons:
            base -= self.rates[coupon]
        return base
''',
            },
        ),
        CommitStep(
            "Add healthcheck endpoint",
            {
                "app/api/health.py": "def health():\n    return {'status': 'ok', 'db': 'up'}\n",
            },
        ),
        CommitStep(
            "Document billing usage",
            {"README.md": "# Billing API\n\nSee docs/billing.md for usage.\n"},
        ),
    ),
    error_text='''\
Traceback (most recent call last):
  File "app/api/billing_controller.py", line 21, in charge
    total = billing.calculate(order)
  File "app/services/billing.py", line 11, in calculate
    base -= self.rates[coupon]
KeyError: 'FREESHIP'
''',
    culprit_message="Add discount stacking to billing",
)

DEPENDENCY_BUMP = Scenario(
    name="dependency_bump",
    notes="Version bump breaks an import name; every frame is outside the repo, so the manifest commit is blamed.",
    files={
        "requirements.txt": "requests==2.28.0\n",
        "app/main.py": "import requests\n\n\ndef fetch(url):\n    return requests.get(url)\n",
    },
    commits=(
        CommitStep(
            "Bump requests library to 3.0",
            {"requirements.txt": "requests==3.0.0\n"},
        ),
        CommitStep(
            "Add telemetry middleware",
            {
                "app/main.py": (
                    "import requests\n\n\ndef fetch(url):\n    return requests.get(url)\n\n\n"
                    "def middleware(req):\n    return req\n"
                ),
            },
        ),
    ),
    error_text='''\
Traceback (most recent call last):
  File "/app/.venv/lib/python3.11/site-packages/requests/__init__.py", line 22, in <module>
    from .api import request
  File "/app/.venv/lib/python3.11/site-packages/requests/api.py", line 10, in <module>
    from .sessions import Session
ImportError: cannot import name 'Session' from 'requests'
''',
    culprit_message="Bump requests library to 3.0",
)

CHAINED_EXCEPTION = Scenario(
    name="chained_exception",
    notes="Python 'During handling' chain: inner KeyError is the real cause, surfaced under a wrapper.",
    files={
        "app/services/pricing.py": '''\
class PricingService:
    def __init__(self):
        self.rates = {"SAVE10": 0.1}

    def quote(self, cart, code):
        rate = self.rates.get(code, 0.0)
        return cart.total * (1 - rate)
''',
        "app/services/checkout.py": '''\
class CheckoutError(Exception):
    pass


class CheckoutService:
    def __init__(self):
        self.pricing = PricingService()

    def apply_coupon(self, cart, code):
        return self.pricing.quote(cart, code)
''',
    },
    commits=(
        CommitStep(
            "Add coupon handling to checkout",
            {
                "app/services/pricing.py": '''\
class PricingService:
    def __init__(self):
        self.rates = {"SAVE10": 0.1}

    def quote(self, cart, code):
        rate = self.rates[code]
        return cart.total * (1 - rate)
''',
                "app/services/checkout.py": '''\
class CheckoutError(Exception):
    pass


class CheckoutService:
    def __init__(self):
        self.pricing = PricingService()

    def apply_coupon(self, cart, code):
        try:
            return self.pricing.quote(cart, code)
        except KeyError as exc:
            raise CheckoutError(f"coupon failed: {code}") from exc
''',
            },
        ),
    ),
    error_text='''\
Traceback (most recent call last):
  File "app/services/checkout.py", line 11, in apply_coupon
    return self.pricing.quote(cart, code)
  File "app/services/pricing.py", line 6, in quote
    rate = self.rates[code]
KeyError: 'SAVE10'

During handling of the above exception, another exception occurred:

Traceback (most recent call last):
  File "app/services/checkout.py", line 13, in apply_coupon
    raise CheckoutError(f"coupon failed: {code}") from exc
CheckoutError: coupon failed: SAVE10
''',
    culprit_message="Add coupon handling to checkout",
)

DEPLOY_MARKER = Scenario(
    name="deploy_marker",
    notes="Log lines carry timestamps and a deploy marker; the report should show a timeline before the failure.",
    files={
        "app/services/reporting.py": '''\
class ReportingService:
    def __init__(self, settings):
        self.settings = settings

    def build_report(self, cfg):
        fmt = self.settings.format_map.get(cfg, "default")
        return f"report-{cfg}-{fmt}"
''',
        "app/version.py": "VERSION = '1.2.0'\n",
    },
    commits=(
        CommitStep(
            "Add scheduling to reports",
            {
                "app/services/reporting.py": '''\
class ReportingService:
    def __init__(self, settings):
        self.settings = settings

    def build_report(self, cfg):
        fmt = self.settings.format_map[cfg]
        return f"report-{cfg}-{fmt}"
''',
            },
        ),
        CommitStep(
            "Deploy release v1.3.0",
            {"app/version.py": "VERSION = '1.3.0'\n"},
        ),
    ),
    error_text='''\
[2026-08-01 08:59:00] app.INFO: deployed version 1.3.0
[2026-08-01 09:00:00] app.INFO: scheduler started, version 1.3.0
[2026-08-01 09:00:05] app.INFO: report generated ok
[2026-08-01 09:01:00] app.ERROR: failed to generate hourly report
Traceback (most recent call last):
  File "app/services/reporting.py", line 8, in build_report
    fmt = self.settings.format_map[cfg]
KeyError: 'hourly'
''',
    culprit_message="Add scheduling to reports",
)

INTERMITTENT_TIMEOUT = Scenario(
    name="intermittent_timeout",
    notes="Honest low confidence: an opaque timeout with no repo frame or manifest signal must not invent a cause.",
    honest_low=True,
    files={
        "app/server.js": "const express = require('express');\nconst app = express();\napp.listen(3000);\n",
    },
    error_text='''\
TimeoutError: operation timed out after 30000ms
    at Timeout._onTimeout (node:internal/timers:464:7)
    at listOnTimeout (node:internal/timers:496:5)
    at process.processTicksAndRejections (node:internal/process/task_queues:95:5)
''',
)

REQUEST_ROUTE = Scenario(
    name="request_route",
    notes="HTTP request context in the error text becomes request evidence; blame still finds the culprit.",
    files={
        "app/services/checkout_service.js": '''\
function finalize(cart) {
  const subtotal = cart.items.reduce((s, i) => s + i.price * i.quantity, 0);
  const total = Math.round(subtotal * 100) / 100;
  return { total };
}

module.exports = { finalize };
''',
        "app/routes/checkout.js": (
            "const { finalize } = require('../services/checkout_service');\n\n"
            "function handleCheckout(req, res) {\n  res.json(finalize(req.body.cart));\n}\n\n"
            "module.exports = { handleCheckout };\n"
        ),
    },
    commits=(
        CommitStep(
            "Change checkout total rounding",
            {
                "app/services/checkout_service.js": '''\
function finalize(cart) {
  const subtotal = cart.items.reduce((s, i) => s + i.price * i.quantity, 0);
  const total = Math.round(subtotal * 100) / 100;
  return { total, currency: cart.currency.toUpperCase() };
}

module.exports = { finalize };
''',
            },
        ),
    ),
    error_text='''\
POST /api/checkout HTTP/1.1
TypeError: Cannot read properties of undefined (reading 'toUpperCase')
    at finalize (app/services/checkout_service.js:4:38)
    at handleCheckout (app/routes/checkout.js:4:11)
    at Layer.handle [as handle_request] (node_modules/express/lib/router/layer.js:95:5)
''',
    culprit_message="Change checkout total rounding",
)

REMOVED_FUNCTION = Scenario(
    name="removed_function",
    notes="Multi-file API break: a refactor removed an exported function the caller still uses.",
    files={
        "app/services/pricing.js": '''\
function discountRate(code) {
  const rates = { SAVE10: 0.1 };
  return rates[code] || 0;
}

function applyCoupon(cart, code) {
  return cart.total * (1 - discountRate(code));
}

module.exports = { applyCoupon, discountRate };
''',
        "app/routes/checkout.js": '''\
const { applyCoupon, discountRate } = require('../services/pricing');

function handleCheckout(req, res) {
  const coupon = discountRate(req.body.code);
  res.json({ total: applyCoupon(req.body.cart, req.body.code), coupon });
}

module.exports = { handleCheckout };
''',
    },
    commits=(
        CommitStep(
            "Use single discount lookup",
            {
                "app/services/pricing.js": '''\
function applyCoupon(cart, code) {
  const rates = { SAVE10: 0.1 };
  return cart.total * (1 - (rates[code] || 0));
}

module.exports = { applyCoupon };
''',
            },
        ),
    ),
    error_text='''\
TypeError: discountRate is not a function
    at handleCheckout (app/routes/checkout.js:4:20)
    at Layer.handle [as handle_request] (node_modules/express/lib/router/layer.js:95:5)
''',
    culprit_message="Use single discount lookup",
)

DEADLOCK = Scenario(
    name="deadlock",
    notes="DB deadlock: a locking change under concurrency; the raise-site line is blamed.",
    files={
        "app/services/order_service.py": '''\
class OrderService:
    def process_payment(self, order_id):
        tx = db_transaction()
        tx.execute("UPDATE orders SET status = 'paid' WHERE id = ?", (order_id,))
        tx.commit()
        return {"id": order_id}
''',
    },
    commits=(
        CommitStep(
            "Add locking to payment processing",
            {
                "app/services/order_service.py": '''\
class OrderService:
    def process_payment(self, order_id):
        tx = db_transaction()
        tx.execute("SELECT * FROM orders WHERE id = ? FOR UPDATE", (order_id,))
        tx.execute("UPDATE orders SET status = 'paid' WHERE id = ?", (order_id,))
        tx.commit()
        return {"id": order_id}
''',
            },
        ),
    ),
    error_text='''\
Traceback (most recent call last):
  File "app/services/order_service.py", line 4, in process_payment
    tx.execute("SELECT * FROM orders WHERE id = ? FOR UPDATE", (order_id,))
MySQLdb._exceptions.OperationalError: (1213, 'Deadlock found when trying to get lock; try restarting transaction')
''',
    culprit_message="Add locking to payment processing",
)

NOT_NULL = Scenario(
    name="not_null",
    notes="DB NOT NULL violation: a commit stopped persisting a required column.",
    files={
        "app/services/order_service.py": '''\
class OrderService:
    def create_order(self, order_id, customer_id):
        tx = db_transaction()
        tx.execute("INSERT INTO orders (id, customer_id) VALUES (?, ?)", (order_id, customer_id))
        tx.commit()
        return {"id": order_id}
''',
    },
    commits=(
        CommitStep(
            "Stop persisting customer on order creation",
            {
                "app/services/order_service.py": '''\
class OrderService:
    def create_order(self, order_id, customer_id):
        tx = db_transaction()
        tx.execute("INSERT INTO orders (id) VALUES (?)", (order_id,))
        tx.commit()
        return {"id": order_id}
''',
            },
        ),
    ),
    error_text='''\
Traceback (most recent call last):
  File "app/services/order_service.py", line 4, in create_order
    tx.execute("INSERT INTO orders (id) VALUES (?)", (order_id,))
sqlite3.IntegrityError: NOT NULL constraint failed: orders.customer_id
''',
    culprit_message="Stop persisting customer on order creation",
)

LARAVEL_REQUEST = Scenario(
    name="laravel_request",
    notes="PHP/Laravel with HTTP request context: property access on a null FX object.",
    files={
        "var/www/html/app/Services/PaymentService.php": '''\
<?php

namespace App\\Services;

class PaymentService
{
    public function charge(int $orderId, float $amount): array
    {
        $rate = $this->fx()->latest();
        return ['id' => $orderId, 'charged' => $amount * $rate];
    }
}
''',
    },
    commits=(
        CommitStep(
            "Use cached FX rate for payments",
            {
                "var/www/html/app/Services/PaymentService.php": '''\
<?php

namespace App\\Services;

class PaymentService
{
    public function charge(int $orderId, float $amount): array
    {
        $rate = $this->fx()->cached;
        return ['id' => $orderId, 'charged' => $amount * $rate];
    }
}
''',
            },
        ),
    ),
    error_text=(
        "POST /api/orders HTTP/1.1\n"
        "ErrorException: Trying to get property 'cached' of non-object\n"
        "#0 /var/www/html/app/Services/PaymentService.php(9): "
        "App\\Services\\PaymentService->charge()\n"
        "#1 /var/www/html/app/Http/Controllers/PaymentController.php(31): "
        "App\\Http\\Controllers\\PaymentController->pay()\n"
    ),
    culprit_message="Use cached FX rate for payments",
)

SCENARIOS: tuple[Scenario, ...] = (
    ORDER_SERVICE,
    CART_SERVICE,
    ORDER_PLACEMENT,
    CHECKOUT_DISCOUNT,
    OLD_COMMIT_REGRESSION,
    DEPENDENCY_BUMP,
    CHAINED_EXCEPTION,
    DEPLOY_MARKER,
    INTERMITTENT_TIMEOUT,
    REQUEST_ROUTE,
    REMOVED_FUNCTION,
    DEADLOCK,
    NOT_NULL,
    LARAVEL_REQUEST,
)


if __name__ == "__main__":
    sys.exit(_main())
