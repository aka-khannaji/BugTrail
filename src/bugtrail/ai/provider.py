"""AI provider interface — OpenAI-compatible chat completions.

Works with OpenAI, Groq (free tier), Ollama (local, $0), and anything else
that speaks the OpenAI chat-completions protocol. BugTrail is
AI-assisted, not AI-dependent: this module is called only at the very end
of the pipeline and degrades gracefully.
"""
from __future__ import annotations

import time
from itertools import count

import httpx

from bugtrail.ai.cost import estimate_cost_usd
from bugtrail.config import AIConfig


class AIResult:
    _ids = count(1)

    def __init__(
        self,
        task: str,
        provider: str,
        model: str,
        content: str,
        input_tokens: int,
        output_tokens: int,
        latency_ms: int,
    ):
        self.task = task
        self.provider = provider
        self.model = model
        self.content = content
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.latency_ms = latency_ms
        self.cost_usd = estimate_cost_usd(model, input_tokens, output_tokens)

    @property
    def is_local(self) -> bool:
        return self.provider in ("ollama", "local")


class AIProvider:
    def __init__(self, config: AIConfig, api_key: str | None):
        self._config = config
        self._api_key = api_key

    @property
    def available(self) -> bool:
        return bool(self._api_key)

    def chat(self, task: str, user_prompt: str, system_prompt: str | None = None) -> AIResult | None:
        if not self.available:
            return None
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_prompt})
        payload = {
            "model": self._config.model,
            "messages": messages,
            "temperature": self._config.temperature,
        }
        headers = {"Authorization": f"Bearer {self._api_key}"}
        url = self._config.base_url.rstrip("/") + "/chat/completions"
        started = time.perf_counter()
        try:
            with httpx.Client(timeout=self._config.timeout_seconds) as client:
                response = client.post(url, json=payload, headers=headers)
                response.raise_for_status()
        except httpx.HTTPError:
            return None
        latency_ms = int((time.perf_counter() - started) * 1000)
        data = response.json()
        usage = data.get("usage") or {}
        content = "".join(
            choice.get("message", {}).get("content", "")
            for choice in data.get("choices", [])
        )
        return AIResult(
            task=task,
            provider=self._config.provider,
            model=self._config.model,
            content=content,
            input_tokens=int(usage.get("prompt_tokens", 0)),
            output_tokens=int(usage.get("completion_tokens", 0)),
            latency_ms=latency_ms,
        )
