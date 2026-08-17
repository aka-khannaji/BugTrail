from pathlib import Path

from bugtrail.evidence.graph import EvidenceGraph
from bugtrail.evidence.models import Evidence, EvidenceKind, Frame


def make_order_exception() -> Evidence:
    return Evidence.exception(
        "IntegrityError",
        "Duplicate entry '5' for key 'orders.id'",
        [
            Frame(file=Path("app/services/order_service.py"), line=24, fn="create_order"),
            Frame(file=Path("app/controllers/orders.py"), line=10, fn="process"),
        ],
    )


def test_exception_with_frames_graph():
    graph = EvidenceGraph()
    exc = make_order_exception()
    graph.add_exception_with_frames(exc)

    assert len(graph.exceptions()) == 1
    files = graph.of_kind(EvidenceKind.FILE)
    assert len(files) == 2
    order = graph.file_node("app/services/order_service.py")
    assert order.data["frames"][0]["line"] == 24


def test_file_node_dedupes_by_path():
    graph = EvidenceGraph()
    a = graph.file_node("src/app.py")
    b = graph.file_node("src/app.py")
    assert a.id == b.id
    assert len(graph.of_kind(EvidenceKind.FILE)) == 1


def test_commit_round_trip():
    graph = EvidenceGraph()
    graph.ensure_commit("abc123", "Add retry handling")
    graph.ensure_commit("abc123", "Add retry handling")
    assert len(graph.of_kind(EvidenceKind.COMMIT)) == 1

    restored = EvidenceGraph.from_dict(graph.to_dict())
    assert len(restored.of_kind(EvidenceKind.COMMIT)) == 1
    assert restored.node(graph.of_kind(EvidenceKind.COMMIT)[0].id).data["sha"] == "abc123"


def test_edges_survive_serialization():
    graph = EvidenceGraph()
    exc = make_order_exception()
    graph.add_exception_with_frames(exc)
    db = graph.add_database_query("Unique constraint violation (duplicate entry)")
    graph.link(db.id, "explains", exc.id)

    restored = EvidenceGraph.from_dict(graph.to_dict())
    db_restored = restored.of_kind(EvidenceKind.DATABASE_QUERY)[0]
    assert exc.id in [target for _, target in restored.edges_from(db_restored.id)]
