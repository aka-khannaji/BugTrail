"""Tests for the SQLite-backed session store and recurrence detection."""
from __future__ import annotations

from pathlib import Path

from bugtrail.investigation.session import InvestigationSession
from bugtrail.storage import Storage, new_session_id

ERROR_TEXT_A = (
    "Traceback (most recent call last):\n"
    '  File "app/services/order_service.py", line 24, in create_order\n'
    "    tx.execute('INSERT INTO orders (id) VALUES (?)')\n"
    "sqlite3.IntegrityError: UNIQUE constraint failed: orders.id\n"
)

ERROR_TEXT_B = (
    "TypeError: Cannot read properties of undefined (reading 'price')\n"
    "    at computeTotal (app/services/cart_service.js:2:30)\n"
)


def _session(tmp_path: Path, error_text: str) -> InvestigationSession:
    from bugtrail.ai.cost import CostLedger

    return InvestigationSession.create(
        session_id=new_session_id(),
        repo_root=str(tmp_path),
        error_text=error_text,
        exception={
            "name": "IntegrityError" if "IntegrityError" in error_text else "TypeError",
            "message": "boom",
            "frames": [],
        },
        graph={},
        hypotheses=[],
        costs=CostLedger(),
        ai_summary="",
    )


def test_save_load_roundtrip(tmp_path: Path):
    storage = Storage(tmp_path)
    session = _session(tmp_path, ERROR_TEXT_A)
    path = storage.save(session)
    assert path.exists()
    loaded = storage.load(session.id)
    assert loaded.id == session.id
    assert loaded.error_text == session.error_text


def test_similar_signatures(tmp_path: Path):
    storage = Storage(tmp_path)
    first = _session(tmp_path, ERROR_TEXT_A)
    storage.save(first)
    duplicate = _session(tmp_path, ERROR_TEXT_A)
    storage.save(duplicate)
    unrelated = _session(tmp_path, ERROR_TEXT_B)
    storage.save(unrelated)

    similar = storage.find_similar(storage.error_signature(duplicate), exclude_id=duplicate.id)
    assert [item["id"] for item in similar] == [first.id]
    assert Storage.error_signature(first) == Storage.error_signature(duplicate)


def test_history_newest_first(tmp_path: Path):
    storage = Storage(tmp_path)
    first = _session(tmp_path, ERROR_TEXT_A)
    storage.save(first)
    second = _session(tmp_path, ERROR_TEXT_B)
    storage.save(second)
    items = storage.history()
    assert items[0]["id"] == second.id
    assert items[1]["id"] == first.id


def test_error_signature_ignores_commit_mode_text(tmp_path: Path):
    a = _session(tmp_path, "")
    b = _session(tmp_path, "")
    assert Storage.error_signature(a) == Storage.error_signature(b)


def test_signature_differs_between_errors(tmp_path: Path):
    assert Storage.error_signature(_session(tmp_path, ERROR_TEXT_A)) != Storage.error_signature(
        _session(tmp_path, ERROR_TEXT_B)
    )
