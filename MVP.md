# BugTrail — MVP Plan

The MVP answers one question extremely well: **"Why did this bug happen?"**

A developer gives BugTrail an error/incident and gets an evidence-backed investigation — from "Something broke." to "Here's probably why." in minutes. Not an AI coding agent, not a SaaS dashboard, not another Sentry clone.

> **MVP success metric:** a developer gives it a real bug and says *"Holy shit, it found the suspicious commit faster than I did."*

## Critical path (makes or breaks the MVP)

> **Reliably mapping a stack-trace frame → source file → git commit.**

If that mapping is solid, everything else (evidence graph, AI ranking, confidence) is plumbing. If it's flaky, no amount of AI fixes it. Verified per language, since Python tracebacks, V8 traces, and Laravel stack traces format very differently.

## MVP scope

- **Languages:** Python, JavaScript/TypeScript, PHP (Laravel)
- **Data:** Git, PostgreSQL, MySQL
- **Features:**
  - stack trace parsing
  - log analysis
  - Git history
  - diff analysis
  - dependency analysis
  - evidence graph
  - basic AI reasoning
  - cost tracking
  - investigation report

## What we explicitly DON'T build

Web dashboard, SaaS, VS Code extension, Slack/Jira/Sentry integration, OpenTelemetry ingestion, Kubernetes, autonomous code fixing, autonomous PR creation, 20 language adapters, multi-agent architecture, fancy visualization, hosted AI service. All later.

## Design decisions (locked)

- **Core/CLI language:** Python (>= 3.11), `uv` + hatchling, `src/` layout.
- **AI access:** free local AI first — bundled **bugtrail-ai** microservice (`services/bugtrail-ai/`, FastAPI hosting Qwen2.5-Coder-0.5B-Instruct GGUF, ~400 MB, $0, no key) auto-detected at `http://127.0.0.1:8000/v1`. Later, BYO API key for external providers (OpenAI, Groq free tier, etc.) via `base_url` + `BUGTRAIL_API_KEY`. Both speak OpenAI-compatible chat completions. Local calls are billed at $0; no key → `local` mode.
- **Deterministic first, AI second** (hard rule): evidence graph is built deterministically; AI only ranks/reasons over the graph at the end.
- **Cost tracking from day one:** provider, model, input/output tokens, estimated cost, latency, task recorded per AI operation.
- **Storage:** per-project `.bugtrail/` JSON sessions (SQLite deferred for MVP).
- **Privacy:** `local` / `scoped` (default — only frames + snippets leave the machine) / `full` (opt-in). API key never stored in config.
- **CLI (tiny):** `init`, `investigate [--error PATH] [--commit SHA] [--no-ai]`, `report`. No 30 commands.
- **Commit only, never push** — user handles upstream.

## Phase 0 — Foundation (DONE)

Goal: architecture. Deliverables, all implemented and committed (`e91de6a`):

1. **Repo scaffold** — `pyproject.toml`, `src/bugtrail/`, ruff + pytest, GitHub Actions CI on push/PR.
2. **Evidence schema + graph** — node kinds (exception, request, log, function, file, commit, diff, database query, dependency, deployment, environment, test), labelled relationships, `EvidenceGraph`.
3. **Storage layer** — per-project `.bugtrail/sessions/*.json`, `report` reads the latest.
4. **Config + privacy model** — `bugtrail init` writes `bugtrail.toml`; three privacy scopes.
5. **Adapter interface** — language adapters (detect / parse_stacktrace / extract) + `GitAdapter`; registry maps project → adapters.
6. **AI provider interface (BYO key + free models)** — OpenAI-compatible REST; usage + cost recorded; no key → `local` mode.
7. **CLI skeleton** — `init` / `investigate` / `report` wired to the pipeline (evidence → graph → deterministic scoring → optional AI → report).
8. **Bug zoo — first fixture + eval harness** — one real-ish project with a stack trace and known root cause; test asserts BugTrail ranks the correct commit/file in the top-3.

**Phase 0 exit criteria (met):** `bugtrail investigate` runs end-to-end on a zoo fixture — collects evidence, builds the graph, runs deterministic analysis, dry-runs AI in local mode, writes a session with per-task cost; and it named the right commit (retry commit **#1 at 97%**).

## Phase 1 — MVP (NEXT)

Goal: **first useful investigation.**

- Support Python + JS/TS + PHP/Laravel with Git + PostgreSQL + MySQL.
- Ship the remaining Phase 1 features (log analysis, diff analysis, dependency analysis, real AI reasoning with `BUGTRAIL_API_KEY`).
- Grow the bug zoo to 20–50 real scenarios (project + stack trace + known root cause). Doubles as the OSS showcase and evaluation benchmark. Cover:
  - Python, JS/V8, Laravel stack-trace formats
  - a bare low-confidence case (old commit, dependency bug, intermittent failure) — define honest behavior instead of fabricating a high number
- Eval harness asserts correct root cause ranks top-3 on every fixture.

## Remaining known gaps from Phase 0

- Real AI ran end-to-end on this dev machine: the `services/bugtrail-ai` microservice (free local **Qwen2.5-Coder-0.5B** — the code-focused half-size variant) is fully usable. `llama-cpp-python` came from the abetlen CPU wheel index (`py3-none-win_amd64`, no MSVC needed) wired via `[[tool.uv.index]]` + `[tool.uv.sources]`. Verified live: model server on `127.0.0.1:8765`, a real `investigate` run produced an AI reasoning note and a `$0.000` cost row. Note: ports 8000/8001 were taken on this machine by other dev servers, so the microservice runs on 8765 here. External BYO-key providers remain the later option.
- Commit-mode is honest: ranking excludes **merge commits** (no changes of their own) and caps how many files a giant commit can score by, so `--commit` reports a change overview ("MOST RELEVANT COMMIT") rather than pretending there's a root cause when no error text was supplied.
- Bug zoo now has **4 fixtures** (Python, JS/V8, PHP/Laravel, and a reformat-masked low-confidence case); still short of the 20–50 target. No JS/PHP end-to-end beyond the two new fixtures; no bare old-commit / intermittent-failure case yet.
- Console-script `.exe` trampolines are flaky **on this dev machine** (an opaque corporate security layer denies some freshly-generated exes — even uv's own `pytest.exe`; not Defender, not MOTW, not our packaging: `pip install .` + `python -m bugtrail` and `bugtrail --version` work in a clean venv, and CI asserts the console script on clean runners). Run `python -m bugtrail` locally; the packaged `bugtrail` console script is verified in CI.
- **Drop-in pass (done):** root README + Quickstart, packaging metadata (readme/classifiers/urls), CLI polish (no-git warning, AI-unreachable + enable-AI tips), GitHub Actions CI matrix (pytest + ruff + console-script smoke on py3.11–3.14 × win/linux/mac), reusable `bugtrail investigate` GitHub Action + example issue workflow, and a Dockerfile for the AI microservice (GGUF baked in, health-checked in CI).
