from pathlib import Path

import pytest

from bugtrail.config import default_config, load_config, write_default_config
from bugtrail.storage import Storage


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
