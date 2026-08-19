# BugTrail — Product Plan (beyond MVP → v1)

> BugTrail tells a developer *why* a bug happened, backed by evidence, in minutes.
> MVP answered the question on a laptop. This plan makes it a product: reliable on
> real bugs, honest about what it knows, proven against a real benchmark corpus.

The MVP is done (4 committed phases worth of engine + packaging + AI + CI). This plan
is the working roadmap **from MVP to v1**. It is deliberately concrete: every phase has
deliverables and an exit criterion, and nothing enters a phase that a prior phase
doesn't need (YAGNI stays law).

---

## 1. Product definition

**One-liner:** "Paste a stack trace, get a ranked, evidence-backed root-cause
investigation in minutes — for free, local, and honest."

**Who it's for (primary first):**
- Backend/full-stack developers debugging their **own repo**, solo or small team,
  without a Sentry/Datadog budget.
- OSS maintainers triaging bug reports (the GitHub Action turns an issue into an
  investigation comment).

**Jobs-to-be-done:**
1. "Find which commit/change caused this regression — fast."
2. "Make sense of a crash I have no context on."
3. "Triaging incoming bug reports without reproducing each one."

**What it is NOT** (unchanged from MVP): an AI coding agent, a SaaS dashboard,
another Sentry clone.

## 2. What v1 "done" looks like (exit bar for the whole plan)

1. A developer takes **any real error from a supported ecosystem** and gets a useful
   ranked investigation in **under 2 minutes** (including AI latency budget).
2. **Bug zoo ≥ 20 real scenarios**; the eval harness asserts the correct root cause
   ranks **top-3** (or honestly low-confidence) on **every** fixture.
3. **Dogfooded on ≥ 2 non-trivial external repos** with genuinely new bugs solved
   (People-Portal counts as one; we pick a second).
4. Deterministic quality holds with AI off (A/B: zoo pass-rate with `--no-ai` ≈ with AI).
5. `bugtrail` installs anywhere (`pip install "bugtrail @ git+…"`) and the console
   script works on CI-clean runners.

## 3. Strategic pillars (the moat)

1. **Evidence-backed honesty.** Never fabricate confidence. Every score has reasons.
   When there's no error text, say "change overview", not "root cause". This is what
   makes developers trust the tool over an LLM guess.
2. **Deterministic first, AI second** (hard rule, stays). Works offline, $0, private,
   testable. AI reasons over the graph at the end only.
3. **The Bug Zoo is the moat.** A growing, real benchmark corpus of bugs. Every
   improvement is proven against it before shipping. Quality over star count.
4. **Depth before breadth.** One language/framework understood deeply beats ten
   shallowly. New ecosystem coverage is gated by zoo fixtures passing.

## 4. Phase 2 — Make the investigation genuinely good (NEXT)

Goal: the core loop stops being "good enough for the demo" and becomes reliable on
real bugs.

**Deliverables**

1. **Formal eval harness (key deliverable).** One pytest test per zoo fixture
   asserting top-3 rank (or honest low-confidence). A single command runs the whole
   zoo and reports a pass-rate. This becomes the gate for every future change.
2. **Bug zoo growth: 4 → 20+.** Priority scenario classes (each with a fixture + known
   root cause):
   - old-commit regression (culprit is NOT the newest change)
   - intermittent failure / race / timeout
   - dependency upgrade break (version bump in a manifest)
   - deploy / environment change (deploy marker, env var, config)
   - DB-specific: deadlock, unique-constraint, migration drift
   - chained exception (Python `During handling…`, JS `cause`)
   - multi-file refactor that broke a calling site
   - each class must include an honest low-confidence variant
3. **Timeline reconstruction.** Order evidence by time — log timestamps, commit
   dates, deploy markers — and render `✓ 43 ok / ✗ first failure after deploy X`
   in the report. (The trace alone can't do this; we build it from git + logs.)
4. **Chained exceptions.** Link `During handling of the above exception` / `cause`
   chains into one exception with a cause edge, instead of treating them as
   unrelated errors.
5. **Request / route evidence.** When the error text carries HTTP context
   (`POST /api/orders`), attach it to frames via route-to-file mapping for
   Laravel / Express / FastAPI-style projects.
6. **Deploy / environment evidence.** Recognize deploy markers (version tags, "deployed"
   log lines, git tag bumps) as graph nodes so "what changed between ok and fail"
   is explicit.
7. **Commit-mode depth.** Match error frames against each commit's changed files even
   when exact-line blame misses (transpilation, async, line drift) — score by
   file-level proximity, not just line-level blame.
8. **"Next investigation" suggestions become actionable.** After the report, offer
   concrete follow-ups (`git show <sha>`, reproduce command, suggested test) driven
   by the winning hypothesis — not boilerplate.

**Exit criterion:** zoo ≥ 20 with top-3/low-confidence assertions all passing;
dogfooded on People-Portal plus one fresh external repo with real new bugs; report
includes timeline + actionable next-investigation; `--no-ai` pass-rate within ~5 pts
of AI pass-rate.

## 5. Phase 3 — Ecosystem depth & memory

Goal: broad enough to be someone's daily tool, and smart enough to remember.

**Deliverables**

1. **Go adapter** (first new language since MVP; simple, widely wanted) + 2–3 Go zoo
   fixtures. Adds a manifest type (`go.mod`).
2. **SQLite-backed session store** (JSON is kept for single sessions; SQLite powers
   search and dedupe). `bugtrail history`, and repeat-investigation detection:
   "this error signature was investigated before — here's the previous result."
3. **Caching / dedupe:** identical stack signature → reuse prior findings, mark as
   known/recurring in the report.
4. **Adapter contribution docs** + a CONTRIBUTING.md for the ecosystem (the adapter
   interface becomes the public plugin surface).
5. **Console/packaging polish** — resolve the exe-trampoline flakiness documented on
   this dev machine (verify on a clean Windows runner, not locally).

**Exit criterion:** Go fixtures pass in the zoo; SQLite migration green with history +
dedupe demonstrated on a repeated real error; one external contributor-style PR
validates the adapter docs.

## 6. Phase 4 — Integrations & team surface (start small)

Goal: meet developers where they already are — but only the integrations real usage
proves people need. **Not a big-bang integration spree.**

**Candidates (pick by demand, not enthusiasm):**
- Sentry issue → `bugtrail investigate` (import an event's stack trace)
- OpenTelemetry error span ingestion
- GitLab CI / other CI variant of the existing GitHub Action
- VS Code extension (view investigation inline on a file)
- Slack/Teams one-liner summary

**Also here (small, data-driven):** the existing cost ledger grows a per-project
`bugtrail cost` summary — the seed of ModelBudget. Build the CLI summary only when a
user asks; ModelBudget as a separate product stays parked (YAGNI).

**Exit criterion:** 1–2 integrations shipped that at least one real user relies on
weekly; integration code paths covered by zoo-style fixtures.

## 7. Phase 5 — BugTrail Cloud (only when the OSS has pull)

**Explicitly parked.** Cloud/team/SaaS only becomes a plan when: ≥ N weekly active
users, ≥ 2 orgs asking for team investigations, and the OSS repo has organic
adoption. When that day comes: core stays MIT, cloud sells collaboration/telemetry/
managed AI. We will not design it now (YAGNI).

## 8. Quality bar & how we measure it

| metric | definition | target |
| ------ | ---------- | ------ |
| zoo pass-rate | fixtures where correct root cause ranks top-3 OR honesty is proven (low-confidence correctly reported) | 100% |
| determinism parity | zoo pass-rate with `--no-ai` vs with AI | within 5 pts |
| time-to-report | paste → ranked report | < 2 min |
| false-confidence | low-confidence fixtures that fabricate a high number | 0 |
| dogfood wins | real bugs solved on non-zoo repos | ≥ 2 repos |

The zoo pass-rate is the single number we optimize. Everything else is plumbing.

## 9. Risks & open decisions

**Risks**
- **Scope creep into "20 languages".** Mitigated: depth-first, zoo-gated coverage.
- **AI-hallucinated confidence.** Mitigated: deterministic-first hard rule, honest
  low-confidence labels, determinism-parity metric.
- **Adoption friction.** Debugging tools are fragmented; switching costs are real.
  Mitigated: zero-config `init`, paste→report in one command, drop-in package,
  the GitHub Action that works where issues already live.
- **Zoo fixtures drift from reality.** Mitigated: dogfooding real repos (Phase 2
  exit criterion) keeps fixtures honest.

**Open decisions for you**
1. **Second dogfooding repo** — pick one with real traffic (open source? a work repo?).
2. **Language order after Go** — Java vs Rust vs Ruby next? (Not needed until Phase 3.)
3. **Integration priority** (Phase 4) — Sentry first, or VS Code, or CI variant?
   Decide when Phase 3 lands.
4. **Public identity** — placeholders filled with the real repo (`aka-khannaji/BugTrail`); done as part of the PyPI publish (2026-08-18).
5. **Monetization timing** — parked at Phase 5; revisit on real usage signals.

## 10. Immediate backlog (Phase 2, sprint 1 — highest value first)

1. ~~Formal eval harness (zoo runner: one command, pass-rate output)~~ **DONE** — `tests/zoo.py`; `python -m tests.zoo` prints a pass-rate table; `tests/test_zoo.py` is the pytest gate (one test per scenario).
2. ~~Zoo growth to 8–10 fixtures~~ **DONE** — 10 scenarios: duplicate-insert retry (Py), hoisted-loop (JS), Eloquent duplicate (PHP), reformat-masked (JS), old-commit regression, dependency version bump, chained exception, deploy marker, intermittent timeout (honest low), request route. **10/10 passing.**
3. ~~Timeline reconstruction~~ **DONE** — timestamped log lines + exception + deploy markers, with an `N ok events before first failure · first failure after …` summary.
4. ~~Chained-exception linking~~ **DONE (no new code needed)** — the Python adapter already collected every block's frames; now covered by a zoo scenario.
5. ~~Request/route evidence~~ **DONE** — `METHOD /path HTTP` becomes a Request evidence node + report line.
6. Real-world dogfood — **IN PROGRESS:** Netbox (Django, ~2.2k files) cloned and investigated. Real issue #22923: engine found the true culprit `986ef2b8e6` (introduced `event_tracking()` without `finally` in 2020) after the innermost-frame tiebreak fix; that fix was itself dogfood-driven. Second repo still to do.
7. Update PLAN.md/MVP.md statuses as items land — **in progress.**

Ordering note: the harness came first because every later item is proven against it.

## Sprint 3 (done)

- **Zoo 14 → 20 scenarios — full Phase-2 growth target reached. 20/20 passing.** New: reformat-masks-old-culprit (file-history rescue), rename-symbol (Python API break), PHP missing-class, Node dependency bump, giant-feature-commit volume guard, timeout-with-logs (honest low + timeline).
- **File-history proximity (`git log --follow` per frame file)** — the commit-mode-depth deliverable. When exact-line blame is *unreliable* (a cosmetic reformat masked the line, or the line isn't blamable), the last few commits that touched the frame file are surfaced as suspects (strength 0.4) even when they sit outside the recent-20 window. Deliberately *not* applied when blame is solid, so the initial/creation commit doesn't pollute rankings (caught by a zoo regression during the sprint).
- Dogfood (Netbox #22923) re-verified green after the change.

## Phase 3 — Ecosystem depth & memory (in progress)

- **Go adapter — DONE.** `GoAdapter` parses runtime panic traces (`panic:` / `fatal error:` + goroutine stacks, innermost-first), registered ahead of PHP so PHP's generic regex can't steal Go traces; `go.mod` added to manifest parsing (block + single `require`). Zoo +2 Go scenarios (22/22). Gotcha recorded: git blame follows content, so panics must land on a line the culprit introduced.
- **SQLite session store + history + recurrence — DONE.** Sessions now also index into `.bugtrail/bugtrail.db` (signature = name + message + frame positions). `bugtrail history` lists past investigations; `investigate` attaches a RECURRING section when the same error signature was seen before. The new tests exposed and fixed a real bug: `new_session_id()` had second resolution, so same-second sessions collided and overwrote each other; ids now carry a unique suffix.
- **Adapter contribution docs — DONE.** `CONTRIBUTING.md`: the adapter contract, frame-order rule, registry ordering, and the zoo workflow (scenario → red → green), with the Go adapter as the worked example.
- **Console/packaging polish (exe trampolines)** — still pending; can only be verified on a clean Windows runner (CI), not on this dev machine.

---

## How to work through this plan

- One phase at a time; a phase is "done" only when its exit criterion is met.
- Every sprint starts by running the zoo and ends by re-running it.
- Commit locally only (never push) until we agree publishing is ready.
- If a deliverable stops earning its keep during dogfooding, we drop it — the plan is
  a hypothesis, the zoo and real bugs are the evidence.