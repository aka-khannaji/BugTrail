from pathlib import Path

from bugtrail.engines.detective import DetectiveEngine
from bugtrail.evidence.graph import REL_FILE_MODIFIED_BY, EvidenceGraph
from bugtrail.evidence.models import Evidence, Frame


def build_graph() -> EvidenceGraph:
    graph = EvidenceGraph()
    exc = Evidence.exception(
        "IntegrityError",
        "UNIQUE constraint failed: orders.id Duplicate entry during retry",
        [Frame(file=Path("app/services/order_service.py"), line=24, fn="create_order")],
    )
    graph.add_exception_with_frames(exc)

    commit = graph.add_commit("bee123", "Fix duplicate order retry")
    node = graph.file_node("app/services/order_service.py")
    node.data.setdefault("commit_strength", {})["bee123"] = 1.0
    graph.link(node.id, REL_FILE_MODIFIED_BY, commit.id)
    return graph


def test_ranks_blamed_commit_first():
    graph = build_graph()
    hypotheses = DetectiveEngine(git=None).investigate(graph)
    assert hypotheses, "expected at least one hypothesis"
    top = hypotheses[0]
    assert top.commit_sha == "bee123"
    assert top.files == ["app/services/order_service.py"]
    assert any("modified by commit" in reason for reason in top.reasons)
    assert any("duplicate" in reason or "retry" in reason for reason in top.reasons)
    assert 0 < top.confidence <= 0.99
    assert top.next_steps[0].startswith("Inspect commit")


def test_ignores_recent_files_without_frames():
    graph = build_graph()
    unrelated = graph.file_node("app/config/database.py")
    unrelated.data["commit_strength"] = {"abc999": 0.4}
    hypotheses = DetectiveEngine(git=None).investigate(graph)
    for hypothesis in hypotheses:
        assert "app/config/database.py" not in hypothesis.files


def test_weak_evidence_scores_lower():
    weak_graph = build_graph()
    weak_node = weak_graph.file_node("app/inventory/inventory.py")
    weak_node.data["frames"] = [{"line": 3, "fn": None}]
    weak_node.data["commit_strength"] = {"abc999": 0.4}
    weak_commit = weak_graph.add_commit("abc999", "Reorder inventory API")
    weak_graph.link(weak_node.id, REL_FILE_MODIFIED_BY, weak_commit.id)

    hypotheses = DetectiveEngine(git=None).investigate(weak_graph)
    by_sha = {h.commit_sha: h for h in hypotheses}
    assert by_sha["bee123"].confidence > by_sha["abc999"].confidence
    assert hypotheses[0].commit_sha == "bee123"
