from pathlib import Path

import pytest

from bugtrail.config import default_config, load_config, write_default_config
from bugtrail.storage import Storage


def test_commit_window_threads_into_evidence(tmp_path: Path):
    from bugtrail.investigation.pipeline import run_investigation

    (tmp_path / "app.js").write_text("module.exports = {};\n", encoding="utf-8")
    calls: dict[str, int] = {}

    class StubGit:
        available = True

        def recent_commits(self, count):
            calls["count"] = count
            return []

        def blame_line(self, file, line):
            return None

        def changed_files(self, sha):
            return []

        def is_whitespace_only(self, sha):
            return False

        def file_history(self, file, count):
            calls["depth"] = count
            return []

        def diff_removes_symbol(self, sha, symbol):
            return False

    error_text = "TypeError: boom\n    at app.js:1:1\n"

    run_investigation(
        repo_root=tmp_path, error_text=error_text, git=StubGit(), allow_ai=False, commit_window=50
    )
    assert calls["count"] == 50
    assert calls["depth"] == 5

    calls.clear()
    run_investigation(
        repo_root=tmp_path, error_text=error_text, git=StubGit(), allow_ai=False, commit_window=-1
    )
    assert "count" not in calls
    assert calls["depth"] == 200


class FakeGit:
    available = True
    repo_root: Path | None = None

    def __init__(self) -> None:
        self._boss_sha = "bee123"
        self._boss = {
            "sha": "bee123",
            "message": "Add retry handling for failed orders",
            "author": "dev",
            "date": "2026-01-01T00:00:00Z",
        }

    def recent_commits(self, count: int = 20):
        return [self._boss]

    def blame_line(self, file: str, line: int):
        return dict(self._boss)

    def changed_files(self, sha: str):
        return ["app/services/order_service.py"]

    def commit_info(self, sha: str):
        return dict(self._boss)


HELP_FILE = Path("app/services/order_service.py")

ERROR_TEXT = (
    "Traceback (most recent call last):\n"
    f'  File "{HELP_FILE}", line 24, in create_order\n'
    '    tx.execute("INSERT INTO orders (id) VALUES (?)", (order_id,))\n'
    "sqlite3.IntegrityError: UNIQUE constraint failed: orders.id: "
    "Duplicate entry '42' for key 'orders.id'\n"
)


def test_pipeline_end_to_end(tmp_path: Path):
    from bugtrail.investigation.pipeline import run_investigation

    target = tmp_path / HELP_FILE
    target.parent.mkdir(parents=True)
    target.write_text("class OrderService:\n    pass\n", encoding="utf-8")

    session = run_investigation(
        repo_root=tmp_path,
        error_text=ERROR_TEXT,
        git=FakeGit(),
        allow_ai=False,
    )

    assert session.exception is not None
    assert session.exception["name"] == "IntegrityError"
    assert session.hypotheses
    assert session.hypotheses[0].commit_sha == "bee123"
    assert session.hypotheses[0].confidence > 0

    nodes = session.graph["nodes"]
    assert any(n["kind"] == "exception" for n in nodes)
    assert any(n["kind"] == "database_query" for n in nodes)
    assert any(n["kind"] == "commit" for n in nodes)

    tasks = [row.task for row in session.costs.rows]
    assert "stack parsing" in tasks and "git analysis" in tasks
    assert session.costs.total == 0.0


def test_session_round_trip_via_storage(tmp_path: Path):
    from bugtrail.investigation.pipeline import run_investigation

    target = tmp_path / HELP_FILE
    target.parent.mkdir(parents=True)
    target.write_text("class OrderService:\n    pass\n", encoding="utf-8")

    session = run_investigation(
        repo_root=tmp_path,
        error_text=ERROR_TEXT,
        git=FakeGit(),
        allow_ai=False,
    )
    storage = Storage(tmp_path)
    storage.save(session)
    restored = storage.load()
    assert restored.id == session.id
    assert restored.hypotheses[0].commit_sha == "bee123"


def test_config_defaults_and_env_key(tmp_path: Path, monkeypatch):
    cfg = default_config()
    assert cfg.privacy.scope == "scoped"
    assert cfg.api_key() is None

    monkeypatch.setenv("BUGTRAIL_API_KEY", "sk-test")
    assert cfg.api_key() == "sk-test"

    path = write_default_config(tmp_path)
    assert path.exists()
    loaded = load_config(tmp_path)
    assert loaded.ai.model == "gpt-4o-mini"


def test_config_rejects_bad_scope(tmp_path: Path):
    from bugtrail.config import CONFIG_NAME

    (tmp_path / CONFIG_NAME).write_text('[privacy]\nscope = "everything"\n', encoding="utf-8")
    with pytest.raises(ValueError):
        load_config(tmp_path)


def test_merge_commit_is_skipped_by_attach_git(tmp_path: Path):
    from bugtrail.engines.detective import DetectiveEngine
    from bugtrail.engines.evidence import EvidenceEngine
    from bugtrail.evidence.graph import EvidenceGraph

    class MergeGit:
        available = True

        def recent_commits(self, count=20):
            return [
                {
                    "sha": "fee1deaddd",
                    "message": "Merge branch 'feature' into main",
                    "author": "d",
                    "date": "2026-01-01T00:00:00Z",
                    "parents": ["p1", "p2"],
                },
                {
                    "sha": "bee1239999",
                    "message": "fix: real error",
                    "author": "d",
                    "date": "2026-01-02T00:00:00Z",
                    "parents": ["p0"],
                },
            ]

        def changed_files(self, sha):
            if sha.startswith("fee"):
                return [f"app/components/widget_{i}.jsx" for i in range(60)]
            return ["app/services/order_service.py"]

        def is_whitespace_only(self, sha):
            return False

        def blame_line(self, file, line):
            return None

    graph = EvidenceGraph()
    EvidenceEngine(tmp_path, MergeGit()).attach_git(graph)
    hypotheses = DetectiveEngine(MergeGit()).investigate(graph, require_frames=False)

    assert [h.commit_sha for h in hypotheses] == ["bee1239999"]
    assert not any("widget_" in reason for h in hypotheses for reason in h.reasons)


def test_ai_prompt_is_bounded_even_for_large_evidence(tmp_path: Path):
    from bugtrail.engines.detective import Hypothesis
    from bugtrail.evidence.graph import EvidenceGraph
    from bugtrail.evidence.models import Evidence, Frame
    from bugtrail.investigation.pipeline import MAX_PROMPT_CHARS, _build_ai_prompt

    graph = EvidenceGraph()
    frames = [
        Frame(
            file=f"app/modules/module_{i}/deep/nested/sub/module.py",
            line=i,
            fn=f"func_{i}",
        )
        for i in range(50)
    ]
    exc = Evidence.exception(
        name="RuntimeError",
        message="boom" * 5000,
        frames=frames,
    )
    graph.add_exception_with_frames(exc)
    for i in range(80):
        graph.add_log("ERROR" if i % 2 else "INFO", f"message {i}", line=i)

    hypotheses = [
        Hypothesis(
            commit_sha=f"abcdef0123456789{i:08x}",
            commit_message=f"fix something {i}" * 30,
            files=[f"src/{j}/file_{j}.py" for j in range(200)],
            score=0.9 - i * 0.05,
            confidence=0.9 - i * 0.05,
            reasons=[f"reason {i}"],
            next_steps=["next"],
        )
        for i in range(10)
    ]

    prompt = _build_ai_prompt(graph, hypotheses)
    assert len(prompt) <= MAX_PROMPT_CHARS + len("\n...[truncated]")
    assert prompt.endswith("...[truncated]")
