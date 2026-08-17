"""Tiny open model, loaded lazily behind an OpenAI-compatible API.

Default: Qwen2.5-Coder-0.5B-Instruct (Q4_K_M GGUF, ~400 MB) — the smallest code
model that can still follow the short "reason from the evidence" instructions
BugTrail sends. 32K native context, so the 16k window below is fully supported.
Override with BUGTRAIL_AI_GGUF (path to a GGUF file).
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

DEFAULT_REPO = "Qwen/Qwen2.5-Coder-0.5B-Instruct-GGUF"
DEFAULT_FILE = "qwen2.5-coder-0.5b-instruct-q4_k_m.gguf"
MODELS_DIR = Path(__file__).resolve().parent.parent / ".models"


def _resolve_model_path() -> Path:
    env = os.environ.get("BUGTRAIL_AI_GGUF")
    if env:
        path = Path(env)
        if not path.is_file():
            raise RuntimeError(f"BUGTRAIL_AI_GGUF is not a file: {env}")
        return path
    path = MODELS_DIR / DEFAULT_FILE
    if path.is_file():
        return path
    try:
        from huggingface_hub import hf_hub_download
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise RuntimeError(
            "Model not found locally. Install huggingface-hub and run once to download: "
            "`uv sync --extra model` then `python -c 'from app.model import get_llm; get_llm()'`"
        ) from exc
    return Path(hf_hub_download(DEFAULT_REPO, DEFAULT_FILE, local_dir=MODELS_DIR))


@lru_cache(maxsize=1)
def get_llm() -> Any:
    try:
        from llama_cpp import Llama

        path = _resolve_model_path()
        return Llama(model_path=str(path), n_ctx=16384, verbose=False)
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise RuntimeError(
            "llama-cpp-python is not installed. Install it with: `uv sync --extra model`"
        ) from exc
    except Exception as exc:  # pragma: no cover - download/load failures
        raise RuntimeError(f"Failed to load model: {exc}") from exc
