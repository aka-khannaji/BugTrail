# BugTrail

Find the likely root cause of a bug by connecting the runtime error with real evidence:
your code, Git history, diffs, logs, dependencies, and database errors.

Deterministic first, AI second — the evidence graph is built from facts, then ranked
deterministically. An optional AI step reasons over that graph at the end (and only that
graph: no API key is ever stored, and by default only stack frames and small snippets
leave your machine).

## Quickstart

```bash
# 1. Install (no account needed)
pip install getbugtrail
# pre-publication: pip install "bugtrail @ git+https://github.com/aka-khannaji/BugTrail.git"

# 2. Point BugTrail at your repo
cd your-project
bugtrail init

# 3. Investigate a bug — paste a stack trace
bugtrail investigate --error trace.txt
# or:  cat trace.txt | bugtrail investigate
```

The report shows the ranked root causes, every piece of evidence behind each one, and
saves the full session to `.bugtrail/sessions/` for later (`bugtrail report`).

## Requirements

- Python 3.11+
- A Git repository with commit history (BugTrail ranks root causes by blaming real commits)
- A stack trace in a supported format: **Python**, **JavaScript (V8/Node)**, or **PHP/Laravel**

## How it works

1. **Parse** the stack trace into an evidence graph (exception, frames, files, logs, database queries, dependencies).
2. **Connect** it to your repo: blame the lines that appear in the trace, scan recent commits, detect whitespace-only cosmetic commits, extract timestamped log lines, and resolve missing-module errors against your manifests (`package.json`, `composer.json`, `requirements.txt`, `pyproject.toml`).
3. **Rank deterministically** — every hypothesis gets a confidence score with human-readable reasons (e.g. *"commit message mentions 'failed'"*). No AI required.
4. **Reason over it (optional)** — an LLM reads the ranked evidence and adds a plain-English note. The ranking is decided by evidence, never delegated to the model.

## AI setup

Three ways to get the AI note — pick one:

**Free local (recommended, $0, private):** run the bundled microservice with Docker:

```bash
docker run -p 8000:8000 ghcr.io/aka-khannaji/bugtrail-ai:latest
bugtrail init --base-url http://127.0.0.1:8000/v1 --model qwen2.5-coder-0.5b-instruct
```

**BYO key:** any OpenAI-compatible provider (OpenAI, Groq's free tier, Ollama):

```bash
bugtrail init --base-url https://api.groq.com/openai/v1 --model llama-3.1-8b-instant
export BUGTRAIL_API_KEY=...    # read from env; never stored in config
```

**No AI at all:** BugTrail is fully functional without it — `--no-ai` forces
deterministic-only mode, or set `privacy.scope = "local"` in `bugtrail.toml`.

Local endpoints (`localhost`, `127.0.0.1`, etc.) are auto-detected and billed **$0**.
Every investigation prints an itemized AI cost ledger.

## Privacy

| scope  | behavior                                                        |
| ------ | --------------------------------------------------------------- |
| `local`   | no AI calls at all (deterministic only)                         |
| `scoped`  | only stack frames + small snippets leave your machine (default) |
| `full`    | full files may be sent to the provider (opt-in)                 |

The API key is read from `BUGTRAIL_API_KEY` (configurable via `api_key_env`); it is
never written to `bugtrail.toml`.

## Automate it: GitHub Action for bug reports

BugTrail ships a reusable GitHub Action that investigates new bug reports and posts the
ranked root cause as a comment on the issue:

```yaml
# .github/workflows/bug-investigation.yml
on:
  issues:
    types: [opened]

permissions:
  contents: read
  issues: write

jobs:
  investigate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0        # full history for blame
      - uses: actions/github-script@v7
        id: body
        with:
          script: |
            const fs = require('fs');
            fs.writeFileSync('bugtrail-body.txt', context.payload.issue.body || '');
      - uses: aka-khannaji/BugTrail@main
        id: investigate
        with:
          error-file: bugtrail-body.txt
        env:
          BUGTRAIL_API_KEY: ${{ secrets.BUGTRAIL_API_KEY }}
      - uses: actions/github-script@v7
        env:
          REPORT: ${{ steps.investigate.outputs.report-path }}
        with:
          script: |
            const fs = require('fs');
            const report = fs.readFileSync(process.env.REPORT, 'utf8');
            await github.rest.issues.createComment({
              owner: context.repo.owner, repo: context.repo.repo,
              issue_number: context.payload.issue.number,
              body: '**BugTrail analysis**\n\n```\n' + report.slice(0, 28000) + '\n```',
            });
```

Pass `base-url` and `model` inputs (and a `BUGTRAIL_API_KEY` secret) to enable the AI
note; without them the action is deterministic-only.

## Development

```bash
git clone https://github.com/aka-khannaji/BugTrail.git
cd bugtrail
uv sync                    # or: pip install -e ".[dev]"
uv run pytest              # or: python -m pytest
uv run ruff check .        # or: python -m ruff check .
```

To publish to PyPI (making `pip install getbugtrail` resolve to this package):

```bash
uv build                   # builds dist/getbugtrail-*.whl + sdist
uv publish                 # needs PYPI_TOKEN env var (pypi.org API token)
```

Published under the name `getbugtrail` (the bare name `bugtrail` is blocked on
PyPI by a similar-name rule against the existing `bug-trail`).

Layout: `src/bugtrail/` is the core (evidence graph, adapters, deterministic engine, AI
provider, CLI); `services/bugtrail-ai/` is the optional local-AI microservice;
`tests/fixtures/zoo/` holds the end-to-end bug scenarios used as both tests and showcase.

See `CONTRIBUTING.md` to add a language adapter or a bug-zoo scenario.

## License

MIT
