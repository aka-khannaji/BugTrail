"""Live HTTP verification of the AI path against an OpenAI-compatible endpoint.

The bundled `services/bugtrail-ai` microservice speaks the OpenAI chat-
completions protocol, so any OpenAI-compatible server exercises the same
client wiring (keyless local detection, request/response shape, $0 cost).
These tests spin up a tiny mock server on an ephemeral port so the full
AIProvider -> pipeline path is verified without needing the ~400MB model,
which also can't be installed on this machine (llama-cpp-python needs MSVC).
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from bugtrail.ai.cost import CostRow
from bugtrail.ai.provider import AIProvider
from bugtrail.config import AIConfig, BugTrailConfig, PrivacyConfig


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")
        content = self.server.response_content
        payload = {
            "id": "chatcmpl-mock",
            "object": "chat.completion",
            "model": body.get("model", "qwen2.5-0.5b-instruct"),
            "choices": [
                {"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}
            ],
            "usage": {"prompt_tokens": 12, "completion_tokens": 4, "total_tokens": 16},
        }
        data = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


class _MockAI:
    def __init__(self, content: str):
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self._server.response_content = content
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self._server.server_address[1]}/v1"

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()


class _FakeGit:
    available = True
    repo_root: Path | None = None

    def recent_commits(self, count: int = 20):
        return [
            {
                "sha": "bee123",
                "message": "Add retry handling for failed orders",
                "author": "dev",
                "date": "2026-01-01T00:00:00Z",
            }
        ]

    def blame_line(self, file: str, line: int):
        return {
            "sha": "bee123",
            "message": "Add retry handling for failed orders",
            "author": "dev",
            "date": "2026-01-01T00:00:00Z",
        }

    def changed_files(self, sha: str):
        return ["app/services/order_service.py"]


HELP_FILE = Path("app/services/order_service.py")

ERROR_TEXT = (
    "Traceback (most recent call last):\n"
    f'  File "{HELP_FILE}", line 24, in create_order\n'
    '    tx.execute("INSERT INTO orders (id) VALUES (?)", (order_id,))\n'
    "sqlite3.IntegrityError: UNIQUE constraint failed: orders.id: "
    "Duplicate entry '42' for key 'orders.id'\n"
)


def test_provider_chat_against_openai_compatible_endpoint():
    mock = _MockAI("bee123 is the best root cause")
    try:
        provider = AIProvider(
            AIConfig(provider="bugtrail-ai", base_url=mock.base_url, model="qwen2.5-0.5b-instruct"),
            api_key=None,
        )
        assert provider.available
        assert provider.is_local

        result = provider.chat("evidence ranking", "some evidence", "be brief")
        assert result is not None
        assert "bee123" in result.content
        assert result.input_tokens == 12
        assert result.output_tokens == 4
        assert result.provider == "bugtrail-ai"
        assert result.cost_usd == 0.0
    finally:
        mock.close()


def test_investigation_with_live_ai_endpoint(tmp_path: Path):
    from bugtrail.investigation.pipeline import run_investigation

    mock = _MockAI("bee123 is consistent with the evidence")
    try:
        config = BugTrailConfig(
            ai=AIConfig(provider="bugtrail-ai", base_url=mock.base_url, model="qwen2.5-0.5b-instruct"),
            privacy=PrivacyConfig(scope="scoped"),
        )
        target = tmp_path / HELP_FILE
        target.parent.mkdir(parents=True)
        target.write_text("class OrderService:\n    pass\n", encoding="utf-8")

        session = run_investigation(
            repo_root=tmp_path,
            error_text=ERROR_TEXT,
            git=_FakeGit(),
            config=config,
            allow_ai=True,
        )

        assert session.ai_summary
        assert "bee123" in session.ai_summary
        assert session.hypotheses[0].commit_sha == "bee123"

        ai_rows = [
            row
            for row in session.costs.rows
            if isinstance(row, CostRow) and row.task == "evidence ranking (ai)"
        ]
        assert len(ai_rows) == 1
        assert ai_rows[0].provider == "bugtrail-ai"
        assert ai_rows[0].cost_usd == 0.0
    finally:
        mock.close()


def test_ai_unavailable_when_service_down(tmp_path: Path):
    from bugtrail.investigation.pipeline import run_investigation

    config = BugTrailConfig(
        ai=AIConfig(
            provider="bugtrail-ai",
            base_url="http://127.0.0.1:1/v1",  # nothing listens here
            model="qwen2.5-0.5b-instruct",
            timeout_seconds=1.0,
        ),
        privacy=PrivacyConfig(scope="scoped"),
    )
    target = tmp_path / HELP_FILE
    target.parent.mkdir(parents=True)
    target.write_text("class OrderService:\n    pass\n", encoding="utf-8")

    session = run_investigation(
        repo_root=tmp_path,
        error_text=ERROR_TEXT,
        git=_FakeGit(),
        config=config,
        allow_ai=True,
    )
    # graceful degradation: report still complete without any AI.
    assert session.hypotheses
    assert session.ai_summary == ""
    assert not [row for row in session.costs.rows if "ai" in row.task]
