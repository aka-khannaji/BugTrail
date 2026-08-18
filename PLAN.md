# BugTrail — Main Project Plan

> BugTrail helps developers find the likely root cause of bugs by connecting runtime errors with code, Git history, dependencies, requests, and database evidence.

**Core principles**
- Open source forever.
- CLI-first.
- AI-assisted, not AI-dependent.
- Language/framework agnostic at the core.

---

## 1. The product

BugTrail answers one question extremely well:

> "Why did this bug happen?"

A developer gives BugTrail an error/incident, and BugTrail produces an evidence-backed investigation.

**Inputs** — discovered or accepted:

- stack trace
- application logs
- Git repository
- recent commits
- changed files
- project dependencies
- HTTP/request information
- database errors

**Output** — a `BUGTRAIL INVESTIGATION` report:

```
❌ POST /api/orders
   500 Internal Server Error

🎯 LIKELY ROOT CAUSE
   A database transaction was retried without
   preserving the original order ID.
   Confidence: 91%

🔎 EVIDENCE
   1. Exception   app/Services/OrderService.php:142
   2. Database    Duplicate entry for order_id
   3. Git         Commit a91f42 "Add retry handling for failed orders"
   4. Code change Transaction handling changed in OrderService.php
   5. Timeline    ✓ 43 successful requests / ✗ first failure after deployment

💡 NEXT INVESTIGATION
   → Inspect commit a91f42
   → Check retry/idempotency logic
   → Reproduce failed request

AI cost: $0.012
```

That is the MVP. **Not** an AI coding agent, **not** a SaaS dashboard, **not** another Sentry clone.

---

## 2. Ecosystem support (phase-1 target)

Deliberately multiple ecosystems, without pretending to deeply support 20 frameworks on day one.

- **Languages:** Python, JavaScript, TypeScript, PHP
- **Frameworks/runtimes:** Node.js, Laravel, basic React awareness, basic Next.js awareness
- **Data:** PostgreSQL, MySQL
- **Infrastructure:** Git, basic Docker awareness

Later: Go → Java → Ruby → Rust → C# → Kotlin → etc. Frameworks plug into their respective language adapters.

---

## 3. Architecture

```
┌───────────────┐
│   BugTrail    │
│      CLI      │
└───────┬───────┘
┌───────▼───────┐
│ BugTrail Core │
└───────┬───────┘
        │
   ┌────┴────────────┐
   ↓                 ↓
Evidence Engine  Graph Engine     Timeline Engine
   │                 │
   └───────┬─────────┘
           ↓
   Investigation Engine
           │
    ┌──────┴───────┐
    ↓              ↓
Deterministic   AI Layer
  Analysis
```

- **Language adapters:** `adapters/{python, javascript, typescript, php}`
- **Framework adapters:** `frameworks/{laravel, node, react, nextjs}`

The core should never care whether evidence came from Laravel or Python.

## 4. The evidence model

This is the heart of BugTrail. Everything BugTrail discovers becomes an evidence object:

- Exception, Request, Log, Function, File, Commit, Diff, DatabaseQuery, Dependency, Deployment, Environment, Test

**Relationships** eventually form an evidence graph:

```
Request → Function → File → Commit → DatabaseQuery → Exception
```

The evidence graph is BugTrail's real technical identity. Deterministic analysis fills it, the detective engine scores it, and the AI layer reasons over it. Nothing is ever sent to an LLM that is not already represented in the graph.

## 5. Deterministic first, AI second (hard rule)

- **No AI needed:** parse stack traces, identify changed files, inspect Git history, calculate file changes, build dependency relationships, detect known error patterns, correlate timestamps, inspect package versions, parse logs.
- **AI useful for:** connecting evidence, ranking possible causes, explaining relationships, generating investigation summaries, suggesting next investigations.

```
Raw data → Deterministic analysis → Evidence graph → AI reasoning → Root-cause hypothesis
```

Never: `Raw logs → LLM → ¯\_(ツ)_/¯`

## 6. AI cost tracking from day one

Every AI operation records: provider, model, input tokens, output tokens, estimated cost, latency, task. This feeds the future **ModelBudget** project without prematurely building it.

## 7. CLI (keep it tiny)

- `bugtrail init`
- `bugtrail investigate`
- `bugtrail investigate --error error.txt`
- `bugtrail investigate --commit <sha>`
- `bugtrail report`

No 30 commands.

## 8. MVP workflow

```
Developer encounters bug
  ↓
bugtrail investigate
  ↓
Collect evidence → Parse stack trace → Inspect Git → Inspect relevant code
  ↓
Build evidence graph → Identify suspicious changes → AI ranks hypotheses
  ↓
Generate report
```

From "Something broke." to "Here's probably why." in minutes.

## 9. What we explicitly DON'T build in the MVP

Web dashboard, SaaS, VS Code extension, Slack/Jira/Sentry integration, OpenTelemetry ingestion, Kubernetes, autonomous code fixing, autonomous PR creation, 20 language adapters, multi-agent architecture, fancy visualization, hosted AI service. All later.

## 10. Phase roadmap

- **Phase 0 — Foundation** (goal: architecture): repository, CLI skeleton, evidence schema, adapter interface, configuration, privacy model, AI provider interface, testing strategy. **→ DONE (commit `e91de6a`)**
- **Phase 1 — MVP** (goal: first useful investigation): Python + JS/TS + PHP/Laravel with Git + PostgreSQL + MySQL; stack trace parsing, log analysis, Git history, diff analysis, dependency analysis, evidence graph, basic AI reasoning, cost tracking, investigation report. **→ NEXT**
- **Phase 2 — Make it genuinely good:** better root-cause ranking, timeline reconstruction, framework-specific evidence, Docker awareness, React/Next.js awareness, better Laravel analysis, investigation caching, reproducibility, test recommendations.
- **Phase 3 — Ecosystem:** Go, Java, Ruby, Rust, C#, Kubernetes, GitHub Actions, Redis, Kafka, etc. Open the adapter system to contributors.
- **Phase 4 — Integrations:** GitHub, GitLab, Sentry, OpenTelemetry, VS Code, CI/CD, Slack/Teams.
- **Phase 5 — BugTrail Cloud:** core remains open source; cloud provides team investigations, shared incident history, production telemetry, centralized evidence, collaboration, private org features, AI usage management. Monetization without making the OSS project bait.

## 11. The eventual BugTrail ecosystem

```
            BUGTRAIL
              │
    ┌─────────┼─────────┐
    ↓         ↓         ↓
BugTrail  ChangeRadar  ModelBudget
 "Why?"   "What breaks?" "How much?"
    │         │         │
    └─────────┼─────────┘
              ↓
   Developer Intelligence
```

Not built now. We build BugTrail.

## 12. How we'll know it succeeded

Not "it works on my laptop." Not "we got 1,000 GitHub stars."

The MVP succeeds when a developer gives it a real bug and says:

> "Holy shit, it found the suspicious commit faster than I did."

Stars, forks, contributors, and eventually revenue are consequences of usefulness.

## First milestone

> Given a real project, a stack trace, and its Git history, BugTrail can produce a ranked list of likely root causes with evidence explaining why each one was selected.

If we can make that work reliably, we have a product.

---

## Current status & baselines

- **Repo:** `bugtrail` v0.1.0, Python >= 3.11, deps: `httpx`, `pydantic`, `typer`; dev: `pytest`, `ruff`. Managed with `uv`.
- **Phase 0 complete** — committed as `e91de6a "Phase 0 scaffold: evidence graph, adapters, deterministic detective engine, CLI"`.
- **Working tree:** clean. **Tests:** 43 passing. **Lint:** ruff clean (120 col, py311, `E/F/I/W`).
- **CLI:** `bugtrail init` / `investigate [-e error.txt] [-c sha] [--no-ai]` / `report`, run as `python -m bugtrail`.
- **Evidence graph:** node kinds (exception, file, database query, log, dependency, commit) + labelled relations; paths canonicalized to forward slashes (leading separators normalized so Laravel deploy-root frames unify with repo-relative paths).
- **Adapters:** Python, JavaScript (V8/Node), PHP (Laravel) stack traces; Git adapter (blame, recent commits, changed files, whitespace-only diff detection).
- **Deterministic engine:** ranks hypotheses with reasons; DB error pattern detection (duplicate entry, integrity/FK/NOT NULL constraint, deadlock); **diff analysis** penalizes whitespace-only commits (0.15x) so a cosmetic reformat can't shadow the true culprit; **merge commits are ignored for rank** (no changes of their own; detected via parent count) and a commit touching hundreds of files can't win by volume alone (score capped to the first 20 changed files); **log analysis** extracts timestamped/severity-tagged lines from pasted error text into the graph + report; **dependency analysis** flags missing-module errors against manifests (package.json / composer.json / requirements.txt / pyproject.toml) and blames the manifest's last-touched commit when every stack frame is outside the repo (node_modules/vendor).
- **AI layer:** OpenAI-compatible provider (OpenAI/Groq/Ollama/bundled microservice), cost ledger with built-in model price table, local endpoints auto-detected and billed $0, degrades gracefully when unavailable. **Verified live** end-to-end: local Qwen produced a real AI reasoning note at `$0.000` cost.
- **Free local AI:** `services/bugtrail-ai` — FastAPI microservice hosting a tiny open model (**Qwen2.5-Coder-0.5B-Instruct** GGUF, ~410 MB, 32K native context; the coder variant fits the "reason from evidence about code" task better than plain instruct) behind `/v1/chat/completions`; point `base_url` at `http://127.0.0.1:8765/v1`, no key. BYO API key remains the external option. Runs on this dev machine: `llama-cpp-python` installs from the abetlen CPU wheel index (`[[tool.uv.index]]` + `[tool.uv.sources]` in `services/bugtrail-ai/pyproject.toml`), so no MSVC/nmake toolchain is needed. Ports 8000/8001 were taken by other dev servers here, so the microservice uses 8765. The provider auto-appends `/v1` to a base_url that lacks it, the pipeline caps the AI prompt (7000 chars) so it fits a small model, and oversized prompts return a clean 400 from the service.
- **Privacy:** `local` / `scoped` (default) / `full`; API key never stored in config.
- **Storage:** per-project `.bugtrail/sessions/*.json` + `latest.txt` (SQLite deliberately deferred for MVP).
- **Drop-in packaging:** hatchling build; `pip install .` works; `pip install "bugtrail @ git+..."` is the documented install. Console script asserted in CI. Root `README.md` + Quickstart.
- **CI:** GitHub Actions — `test` matrix (pytest + ruff + console-script smoke on py3.11–3.14 × win/linux/mac), `microservice` ruff, `docker` (build `services/bugtrail-ai/Dockerfile`, health `loaded:true`, chat smoke). Reusable `bugtrail investigate` action (`action.yml`) + example issue workflow in `.github/workflows/bug-investigation.yml`.
- **Known limitations:** console-script `.exe` trampolines flaky on this dev machine (opaque corporate security layer denies some freshly-generated exes — even uv's own `pytest.exe`; not our packaging, clean venv install + `python -m bugtrail` work, CI asserts the console script). Use `python -m bugtrail` locally.
- **Bug zoo:** 22 scenarios (`tests/zoo.py` + `tests/test_zoo.py`) — Python duplicate-insert retry, JS hoisted-loop, PHP/Laravel Eloquent duplicate, reformat-masked low-confidence case, old-commit regression, dependency version bump, chained exception, deploy marker + timeline, intermittent timeout (honest low), HTTP request route, removed-function API break, DB deadlock, DB NOT NULL, Laravel request + HTTP context, reformat-masks-old-culprit, rename-symbol (Python), PHP missing-class, Node dependency bump, giant-feature-commit volume guard, timeout-with-logs, and two Go scenarios (index-out-of-range panic, nil deref). The zoo materializes each scenario as a real git repo and gates every change on a pass-rate; **22/22 passing** (`python -m tests.zoo`).
- **Missing-symbol diff analysis:** error messages that name a missing symbol (`X is not a function`, `has no attribute 'X'`, `'X' is not defined`, `Call to undefined method`) trigger a scan of recent commits' diffs; a commit that deleted the symbol's definition/export is ranked with the strongest deterministic signal and an explicit reason. Fixes the multi-file-refactor class where the failing call site blames an innocent commit.
- **File-history proximity:** when exact-line blame for a frame file is unreliable (cosmetic reformat masked the line, or the line is unblamable), the last few commits that touched the file (`git log --follow`) are surfaced as suspects even outside the recent-20 window — the fix for "old culprit hidden behind a fresh reformat".
- **Dogfooded (Phase 2):** Netbox clone investigated against real issue **#22923** (`event_tracking()` leaks context vars on exception). The engine named the true culprit `986ef2b8e6` (introduced the no-`finally` context manager, 2020) — after a dogfood-driven fix where adapters now declare frame order (V8/PHP innermost-first, Python outermost-first) and the innermost resolved frame breaks blame ties. Tests: **84 passing**.
- **Phase 3 in progress:** Go adapter (panic/fatal-error goroutine traces, innermost-first, registered before PHP) + `go.mod` manifest parsing; SQLite session index with error signatures, `bugtrail history`, and RECURRING detection for repeat error signatures (fixed a same-second session-id collision the tests exposed); `CONTRIBUTING.md` documents the adapter contract + zoo workflow.
