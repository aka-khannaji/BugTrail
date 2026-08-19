# BugTrail — dev guide (memory for agent sessions)

## Principles (remember these)

- **YAGNI — do not build ahead of need.** No speculative features, endpoints, abstractions, or dependencies. Add only what a concrete task requires. Before adding anything, ask: does the current task need it? If not, skip it and note it as a future idea instead.
- **Deterministic first, AI second** (hard rule). Evidence graph is built deterministically; AI only ranks/reasons over the graph at the end.
- **Commit and push to origin only.** The user owns upstream (origin = https://github.com/being-yash/BugTrail). Pushing is allowed; never force-push or rewrite shared history.
- **AI access strategy:** BYO API key for external providers (OpenAI/Groq/etc. via `base_url` + `BUGTRAIL_API_KEY`) OR free local AI via the `services/bugtrail-ai` FastAPI microservice (tiny open model, $0, no key). Local endpoints must be auto-detected and billed at $0.

## Repo layout (monorepo)

- `src/bugtrail/` — the CLI/core (evidence graph, adapters, deterministic detective engine, AI provider, investigation pipeline).
- `services/bugtrail-ai/` — standalone FastAPI microservice hosting a tiny local open model behind an OpenAI-compatible API. Separate `pyproject.toml`.

## Commands

- Tests: `.venv\Scripts\python -m pytest -q`
- Lint: `.venv\Scripts\ruff check .`
- Run CLI: `.venv\Scripts\python -m bugtrail` — console-script `.exe` trampolines are flaky on THIS machine (opaque corporate security layer denies some freshly-generated exes, even uv's own `pytest.exe`; not our packaging — clean-venv install + CI assert the console script).
- Run local AI service: `cd services/bugtrail-ai; uv run uvicorn app.main:app --port 8000` (first run downloads the GGUF; needs `uv sync --extra model`). On this dev machine ports 8000/8001 are taken by other projects — use `--port 8765` here; `base_url = http://127.0.0.1:8765/v1`.
- Docker: NOT installed on this dev machine — never build/verify the image locally; rely on the CI `docker` job. Dockerfile + `.dockerignore` live in `services/bugtrail-ai/`.
- CI/Action files: `.github/workflows/ci.yml` (test matrix, microservice lint, docker build+health), `action.yml` (reusable `bugtrail investigate` action), `.github/workflows/bug-investigation.yml` (example issue workflow). README/URL placeholders use `OWNER/bugtrail` — user's real repo owner must be filled in when they publish.
