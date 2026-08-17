
from bugtrail.adapters.registry import parse_stacktrace
from bugtrail.evidence.models import EvidenceKind

PYTHON_TRACEBACK = """
Traceback (most recent call last):
  File "app/services/order_service.py", line 24, in create_order
    tx.execute("INSERT INTO orders (id) VALUES (?)", (order_id,))
sqlite3.IntegrityError: Duplicate entry '5' for key 'orders.id'
"""

JS_STACK = """
TypeError: Cannot read properties of undefined (reading 'id')
    at createOrder (app/services/order_service.js:142:25)
    at processRequest (app/controllers/orders.js:10:5)
"""

LARAVEL_STACK = (
    "SQLSTATE[23000]: Integrity constraint violation: 1062 Duplicate entry "
    "'5' for key 'orders.id' (SQL: insert into `orders` values (...))\n"
    "#0 /var/www/html/app/Services/OrderService.php(142): "
    "App\\Services\\OrderService->createOrder()\n"
    "#1 /var/www/html/app/Http/Controllers/OrderController.php(88): "
    "App\\Http\\Controllers\\OrderController->store()\n"
)


def test_python_parse():
    exc = parse_stacktrace(PYTHON_TRACEBACK)
    assert exc is not None
    assert exc.kind is EvidenceKind.EXCEPTION
    assert exc.data["name"] == "IntegrityError"
    assert "Duplicate entry" in exc.data["message"]
    frames = exc.data["frames"]
    assert frames[0]["file"].endswith("order_service.py")
    assert frames[0]["line"] == 24
    assert frames[0]["fn"] == "create_order"


def test_javascript_parse():
    exc = parse_stacktrace(JS_STACK)
    assert exc is not None
    assert exc.data["name"] == "TypeError"
    frames = exc.data["frames"]
    assert frames[0]["line"] == 142
    assert frames[0]["fn"] == "createOrder"


def test_php_parse():
    exc = parse_stacktrace(LARAVEL_STACK)
    assert exc is not None
    assert exc.data["name"] == "DatabaseException"
    assert "SQLSTATE" in exc.data["message"]
    frames = exc.data["frames"]
    assert frames[0]["file"].endswith("OrderService.php")
    assert frames[0]["line"] == 142


def test_garbage_returns_none():
    assert parse_stacktrace("no meaningful content") is None
    assert parse_stacktrace("") is None
