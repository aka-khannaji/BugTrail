"""FastAPI app — OpenAI-compatible chat completions backed by a tiny local model.

Endpoints:
  GET  /health              -> service + model status
  GET  /v1/models           -> the model id BugTrail is pointed at
  POST /v1/chat/completions -> OpenAI-compatible (what bugtrail.ai.provider calls)

BugTrail connects by setting `base_url` to this service's /v1 in bugtrail.toml.
No API key needed; keep it free by design (YAGNI: no auth, no streaming yet).
"""
from __future__ import annotations

import time
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app import __version__
from app.model import get_llm

app = FastAPI(title="bugtrail-ai", version=__version__)

MODEL_ID = "qwen2.5-coder-0.5b-instruct"


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    model: str = MODEL_ID
    messages: list[ChatMessage]
    temperature: float = 0.2


@app.get("/health")
def health() -> dict[str, Any]:
    loaded = False
    try:
        get_llm()
        loaded = True
    except RuntimeError:
        loaded = False
    return {"status": "ok" if loaded else "degraded", "model": MODEL_ID, "loaded": loaded}


@app.get("/v1/models")
def models() -> dict[str, Any]:
    return {"object": "list", "data": [{"id": MODEL_ID, "object": "model", "owned_by": "local"}]}


@app.post("/v1/chat/completions")
def chat_completions(request: ChatRequest) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        llm = get_llm()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=f"Model unavailable: {exc}") from exc
    try:
        result = llm.create_chat_completion(
            messages=[m.model_dump() for m in request.messages],
            temperature=request.temperature,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Bad request: {exc}") from exc
    usage = result.get("usage") or {}
    result["model"] = MODEL_ID
    result["created"] = int(started)
    result["latency_ms"] = int((time.perf_counter() - started) * 1000)
    result["usage"] = {
        "prompt_tokens": int(usage.get("prompt_tokens", 0)),
        "completion_tokens": int(usage.get("completion_tokens", 0)),
        "total_tokens": int(usage.get("total_tokens", 0)),
    }
    return result


def run() -> None:  # pragma: no cover - dev convenience entry point
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=False)
