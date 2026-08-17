# bugtrail-ai

Free local AI microservice for BugTrail. Hosts a tiny open model (default **Qwen2.5-Coder-0.5B-Instruct**, ~400 MB) behind an OpenAI-compatible API, so BugTrail gets AI reasoning at **$0** with no API key.

## Run

### Docker (easiest — model baked in, fully offline)

```bash
docker build -t bugtrail-ai .     # from services/bugtrail-ai
docker run -p 8000:8000 bugtrail-ai
```

The image ships with the GGUF included, so the container runs without a network at
runtime. Built and health-checked in CI (`.github/workflows/ci.yml`).

### From source

```bash
cd services/bugtrail-ai
uv sync --extra model        # installs fastapi + uvicorn + llama-cpp-python (prebuilt wheels, no compiler)
uv run python -c "from app.model import get_llm; get_llm()"   # downloads the GGUF once
uv run uvicorn app.main:app --port 8000
```

First start downloads the model into `services/bugtrail-ai/.models/`. Use a different model with the `BUGTRAIL_AI_GGUF` env var (path to any GGUF, e.g. Qwen2.5-1.5B for better reasoning).

## Point BugTrail at it

In `bugtrail.toml`:

```toml
[ai]
base_url = "http://127.0.0.1:8000/v1"
model = "qwen2.5-coder-0.5b-instruct"
```

No `BUGTRAIL_API_KEY` needed — BugTrail auto-detects the local endpoint and charges $0. To switch back to an external provider (OpenAI/Groq/etc.), just set `base_url` + `BUGTRAIL_API_KEY`.

## Endpoints

- `GET /health` — service + model status
- `GET /v1/models` — model id
- `POST /v1/chat/completions` — OpenAI-compatible (the one BugTrail calls)

## Scope (YAGNI)

Deliberately no auth, no streaming, no multi-model routing, no DB. Add only when a real task needs it.
