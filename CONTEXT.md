# BugTrail — Portable OpenCode Context

> Pick this repo up on any machine with opencode and be productive in minutes.
> This file is the single source of session memory. **Keep the status section
> updated** whenever work lands — on this PC or any other — and commit it.

opencode loads this file automatically (see `opencode.json` at the repo root,
which also loads `AGENTS.md`). If you open the repo somewhere new, you get full
context immediately.

---

## 1. What this is

**BugTrail** answers one question: *\"Why did this bug happen?\"* A developer pastes
an error/stack trace (or points at a commit), and BugTrail produces a ranked,
evidence-backed root-cause investigation in minutes.

- CLI-first Python tool (`bugtrail init` / `investigate` / `report` / `history` /
  `recent`).
- **Deterministic first, AI second** (hard rule): evidence is collected into a graph
  and ranked by rules; an optional LLM only reasons over that graph at the end.
- Free local AI via `services/bugtrail-ai` (tiny Qwen2.5-Coder model, $0, no key),
  or BYO API key for any OpenAI-compatible provider.
- Not a Sentry clone, not a SaaS, not an AI coding agent.

## 2. The product in one screen

```
BUGTRAIL INVESTIGATION
✖ IntegrityError  UNIQUE constraint failed: orders.id
LIKELY ROOT CAUSE
  Add retry handling for failed orders          Confidence: 95%
EVIDENCE
  1. Exception: IntegrityError (1 frames)
  2. Frame line 24 in app/services/order_service.py was last modified by commit a91f42
  3. Database: Unique constraint violation (duplicate entry)
TIMELINE
  2026-08-01T09:00:00  report generated ok
  2026-08-01T09:01:00  failed to generate hourly report  ✗
  Summary: 2 ok events before first failure
RECURRING
  This error signature was investigated before:
  - 2026-08-18T...  Move changelog signals setup to a context manager [sess-id]
NEXT INVESTIGATION
  -> Run: git show a91f42
  -> Write a regression test covering app/services/order_service.py
```

Honesty is a feature: when evidence is thin it prints **NO STRONG ROOT CAUSE**
instead of inventing one; commit-mode prints **MOST RELEVANT COMMIT** with a note
that it is a change overview, not a root cause.

## 3. Repo layout (monorepo)

- `src/bugtrail/` — the CLI/core:
  - `adapters/` — language stack-trace parsers: `python.py`, `javascript.py`,
    `php.py`, `go.py`, plus `git.py` (blame, recent/file history, diff analysis),
    `registry.py` (parser dispatch — **order matters**).
  - `evidence/` — the graph: node kinds (exception, request, log, file, commit,
    dependency, database_query…) + labelled relations; `models.py` factories.
  - `engines/` — `evidence.py` (deterministic collection: DB patterns, log
    extraction, request, dependencies, manifest blame, file-history fallback),
    `detective.py` (ranking + reasons + next-steps).
  - `investigation/` — `pipeline.py` (orchestrates, builds the AI prompt),
    `report.py` (terminal renderer), `session.py` (persisted model).
  - `ai/` — `provider.py` (OpenAI-compatible, `/v1` normalization, local=$0),
    `cost.py` (cost ledger).
  - `storage.py` — JSON sessions + SQLite index, recurrence, `history`.
  - `cli.py` — typer CLI (tiny on purpose).
- `services/bugtrail-ai/` — standalone FastAPI microservice hosting the local model
  (own `pyproject.toml`, Dockerfile, GGUF baked in).
- `tests/zoo.py` — **the bug zoo**: 22 real-ish bug scenarios, materialized as real
  git repos; the benchmark that gates every change. `tests/test_zoo.py` is the pytest
  gate. `tests/test_*.py` are unit tests.
- `CONTRIBUTING.md` — how to add an adapter or zoo scenario.
- `PRODUCT.md`, `PLAN.md`, `MVP.md` — product plan, roadmap, status.

## 4. Commands (dev)

```bash
# from the repo root (this PC uses the repo venv):
.venv\Scripts\python.exe -m pytest -q            # full suite (84 passing)
.venv\Scripts\python.exe -m tests.zoo            # zoo pass-rate table (22/22)
.venv\Scripts\python.exe -m ruff check .         # lint
.venv\Scripts\python.exe -m bugtrail ...         # run the CLI (console script is flaky HERE only)

# anywhere (Python 3.11+; uv on other machines):
uv sync
uv run pytest && uv run ruff check . && uv run python -m tests.zoo
```

## 5. Machine / environment quirks (important)

- **This dev machine**: Windows, Python 3.14.6, uv. Ports 8000/8001 are taken by the
  user's other projects; **bugtrail-ai runs on 8765** here.
- Proot-Debian machine (Android/Termux, aarch64): no uv and no `pkg` as root. Baseline runs via a pip venv — `python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'`. glibc wheels work (pydantic-core, ruff); don't use Termux's bionic python (3.14), its Rust wheels fail to build. Commands are `.venv/bin/python -m pytest -q`, `.venv/bin/python -m ruff check .`, `.venv/bin/python -m tests.zoo`. Use Debian `/usr/bin/python3` (3.13) for the venv.
- **Exe-trampoline flakiness on THIS machine only**: an opaque corporate security
  layer denies some freshly-generated `.exe`s (even uv's own `pytest.exe`). Not a
  packaging bug — `pip install .` + `python -m bugtrail` work in clean venvs, and CI
  asserts the console script on clean runners. Use `python -m bugtrail` locally.
- **Docker is NOT installed on this dev machine** — never build/verify the Docker
  image locally; CI's `docker` job does it.
- The `services/bugtrail-ai` GGUF lives in `services/bugtrail-ai/.models/` (gitignored).
  On a fresh machine: `cd services/bugtrail-ai && uv sync --extra model`, then
  `uv run uvicorn app.main:app --port 8000` (first run downloads ~410 MB from HF).
- Launch detached on this PC (already running, PID varies):
  `services\bugtrail-ai\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8765`.
- Health: `GET http://127.0.0.1:8765/health` → `{"model":"qwen2.5-coder-0.5b-instruct","loaded":true}`.

## 6. Working principles (hard rules, from AGENTS.md)

1. **YAGNI** — build nothing ahead of need. Add only what the current task requires.
2. **Deterministic first, AI second** — the evidence graph is built deterministically;
   AI only ranks/reasons over it at the end.
3. **Commit only, never push.** The user owns upstream. No remotes, no pushing.
4. **Zoo-gated** — every engine change is proven against `tests/zoo.py` before
   shipping. New bug class → add a scenario first (red), then fix (green).
5. **Honesty** — never fabricate a root cause or confidence. Report low confidence.

## 7. Key architecture facts

- **Frame order convention** (`adapters/base.py`): `frames_innermost_first` — Python
  `False` (outermost first), V8/Go/PHP `True`. The innermost resolved frame breaks
  blame ties in `detective.py`.
- **Adapter registry order matters** (`adapters/registry.py`): first match wins.
  Go sits before PHP because PHP's generic `name: message` regex would swallow
  Go `panic:` traces.
- **Git blame follows content, not position**: a line moved by a refactor still
  blames its original author. Zoo panics must land on a line the culprit introduced.
- **Scoring signals** (in `detective.py`): exact-line blame (1.0) + innermost boost
  (0.1) > missing-symbol diff removal (1.3, strongest) > file-history fallback
  (0.4) > recent-commit file changes (0.4 each, 0.2 after half-weight) with
  keyword boost, cosmetic (`×0.15`) and merge (`×0.05`) penalties.
- **Manifest blame fallback**: when a missing-module/class error has every frame
  outside the repo, the manifest's last change is blamed (works for
  requirements.txt, package.json, composer.json, pyproject.toml, go.mod).
- **Dedupe**: sessions get an error signature (name + message + frame positions);
  `investigate` attaches a RECURRING section for repeat signatures.
- **AI prompt is bounded** (`MAX_PROMPT_CHARS=7000`) to fit the small local model;
  the microservice serves `qwen2.5-coder-0.5b-instruct` with `n_ctx=16384`.

## 8. The bug zoo (22 scenarios, 22/22)

Coverage: duplicate-insert retry (Py), hoisted-loop (JS), Eloquent duplicate (PHP),
reformat-masked (JS), old-commit regression, dependency version bump, chained
exception, deploy marker + timeline, intermittent timeout (honest low), HTTP request
route, removed-function API break, DB deadlock, DB NOT NULL, Laravel request+HTTP,
reformat-masks-old-culprit, rename-symbol (Py), PHP missing-class, Node dependency
bump, giant-feature-commit volume guard, timeout-with-logs, Go index-panic, Go
nil-deref. Plus honest-low cases that must NOT invent a cause.

## 9. Current status (as of 2026-08-18)

- **Tests:** 84 passing. **Lint:** ruff clean. **Zoo:** 22/22. **Tree:** clean.
- **Published on PyPI as `getbugtrail` 0.1.2** (2026-08-19) — `pip install getbugtrail`; the bare `bugtrail` name is blocked by PyPI's similar-name rule against the existing `bug-trail`. Console command and import stay `bugtrail`; `--version` reads from installed metadata.
- **Fresh-machine baseline verified on proot-Debian (2026-08-18):** 84/84, ruff clean, 22/22.
- **Commit history (all local, never pushed):**
  ```
  9541019 Phase 3: CONTRIBUTING.md adapter + zoo contribution docs
  ade1563 Phase 3: SQLite session store, history command, recurrence detection
  3b6eaf1 Phase 3: Go adapter + go.mod manifest support
  2fb4452 Sprint 3: zoo to 20, file-history proximity when blame is unreliable
  b2b3111 Sprint 2: missing-symbol diff analysis, actionable next-steps, zoo to 14
  763bb0c docs: mark Phase 2 sprint 1 items done, record Netbox dogfooding result
  001cbf1 Ranking: innermost resolved frame breaks blame ties (dogfooding finding)
  ef00d46 Phase 2 sprint 1: zoo eval harness, request evidence, timeline, dependency-bump blame
  6bbf709 Drop-in polish: README, packaging metadata, CLI tips, CI matrix, GitHub Action
  54b09f7 bugtrail-ai: free local AI microservice (Qwen2.5-Coder-0.5B)
  a5047c4 AI provider: local microservice integration and /v1 normalization
  b391f96 Deterministic engine: log/diff/dependency analysis, merge-commit handling
  e91de6a Phase 0 scaffold: evidence graph, adapters, deterministic detective engine, CLI
  ```
- **Phase 2 — complete.** Eval harness, zoo to 20, timeline, request evidence,
  chained exceptions, missing-symbol diff analysis, file-history proximity,
  actionable next-investigation, honest no-cause. Dogfooded on 2 real repos
  (user's `People-Portal`, and **Netbox issue #22923** → engine found the true
  culprit `986ef2b8e6`, the 2020 commit that introduced `event_tracking()`
  without `finally`).
- **Phase 3 — in progress.** Done: Go adapter, `go.mod` manifests, SQLite index +
  `history` + RECURRING dedupe, `CONTRIBUTING.md`. Pending: console-script/
  packaging polish (only verifiable on a clean Windows CI runner, blocked on this
  dev machine's corporate security layer).
- **Phase 4 (not started)** — integrations by demand (Sentry / VS Code / other CI),
  `bugtrail cost` summary when asked. **Phase 5 (BugTrail Cloud)** — explicitly
  parked until real usage signals.

## 10. Handoff protocol (working from another PC)

When you move to another machine (or back):

1. **Bring the repo** — copy the whole folder (including `.venv` if it travels, or
   recreate with `uv sync`) or use git locally. Remember: never push.
2. **First thing on a fresh machine:** `uv sync`, then
   `uv run pytest && uv run ruff check . && uv run python -m tests.zoo` — confirm
   the baseline (84 passing / 22/22) before changing anything.
3. **When you finish work anywhere:** update this file's **§9 status** (new features,
   test counts, zoo count, commit list — you can get the log with
   `git log --oneline`), commit it alongside your work.
4. **When you come back here:** merge/pull the new commits into this machine's
   checkout (git), re-run the baseline, and tell me "read CONTEXT.md" — I'll pick up
   the updated status and continue from there.
5. Anything you changed in `opencode.json` / config on another machine belongs to
   that machine; keep repo-level config minimal and identical everywhere.

## 11. Gotchas & lessons (cheat sheet)

- Adapter ordering in the registry is load-bearing.
- `frames_innermost_first` is per-language and used for tie-breaking.
- Git blame tracks content; refactors move blame to the original author.
- Whitespace-only commits mask blame → diff analysis + file-history rescue handle it.
- The zoo's honest-low scenarios must never fabricate high confidence.
- `MAX_FILES_SCORED_PER_COMMIT` stops giant commits from winning by volume; merges
  are skipped entirely.
- Session ids are timestamp+uuid (they used to collide within the same second).
- On THIS machine, always `python -m bugtrail`, never the `.exe`.
