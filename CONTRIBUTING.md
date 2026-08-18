# Contributing to BugTrail

BugTrail's moat is its bug zoo: every engine change is proven against real bug
scenarios before it ships. Contributions land the same way — add a scenario, then
make it pass. Don't build ahead of need (YAGNI): add only what the task requires.

**Ground rules**
- Deterministic first, AI second. Evidence is collected and ranked without an LLM.
- Every change keeps the zoo green: `python -m tests.zoo` (currently 22/22).
- Commit locally only; the user owns upstream. Never configure remotes or push.

## Setup

```bash
uv sync                  # or: pip install -e ".[dev]"
uv run pytest            # or: python -m pytest
uv run ruff check .      # or: python -m ruff check .
```

## Adding a language adapter

The adapter interface is the public plugin surface. A language adapter turns a
framework-specific stack trace into a language-agnostic exception. Look at
`src/bugtrail/adapters/go.py` as the smallest worked example.

### The contract (`src/bugtrail/adapters/base.py`)

```python
class LanguageAdapter(ABC):
    name: str                       # "python", "go", ...
    extensions: tuple[str, ...]     # (".go",) — used by detect()
    frames_innermost_first: bool    # True: V8/Go/PHP list the raise site first;
                                    # False: Python lists it last

    @classmethod
    def detect(cls, repo_root: Path) -> bool            # is this repo our language?
    @classmethod
    def parse_stacktrace(cls, text: str) -> ErrorParse | None
```

`ErrorParse` is a 3-tuple: `(name, message, list[Frame])`. `Frame` is
`(file: Path, line: int, fn: str | None)`. Return `None` when the text is not one
of your traces.

**Frame order matters.** BugTrail uses the innermost resolved frame to break blame
ties, so get `frames_innermost_first` right:

- Python `Traceback` lists frames outermost-first → `False`.
- V8/Node, Go goroutine stacks, and PHP/Laravel `#0...` lists innermost-first → `True`.

### Register it

Add the adapter to `ADAPTERS` in `src/bugtrail/adapters/registry.py`. **Order is
semantic**: more specific parsers come first, because the first adapter that
matches wins. Go sits before PHP because PHP's generic `name: message` regex would
otherwise swallow Go `panic:` traces.

### Prove it

1. Add parse tests to `tests/test_adapters.py` (a realistic trace + a garbage case).
2. Add 1–3 end-to-end scenarios to the zoo (below) with a known root cause.
3. Run `python -m tests.zoo` — every scenario must pass.

## Adding a zoo scenario

The zoo (`tests/zoo.py`) materializes each scenario as a real git repo and asserts
the pipeline ranks the true culprit. It is the product's benchmark corpus — every
bug class you add makes the engine measurably better.

```python
Scenario(
    name="go_nil_deref",                 # unique, snake_case
    notes="Go nil-pointer dereference: a nil guard was removed.",
    files={                              # initial repo tree
        "app/services/storage.go": "package main\n\n...",
    },
    commits=(                            # git history, oldest first
        CommitStep(
            "Remove connection guard",   # the culprit (what a dev would blame)
            {"app/services/storage.go": "..."},   # new full content of changed files
        ),
    ),
    error_text='''\                       # what the developer pastes
panic: runtime error: invalid memory address or nil pointer dereference
...
''',
    culprit_message="Remove connection guard",   # must rank in top `top_n` (default 1)
    # honest_low=True                        # use instead when the engine must NOT invent a cause
)
```

Add the scenario to `SCENARIOS` and it becomes a pytest case automatically.

**Two gotchas the zoo teaches:**
- **Git blame follows content, not position.** If the panicking line's text already
  existed in an earlier commit (even at a different line), blame points at that old
  commit. The culprit must introduce the new buggy line.
- **Cosmetic reformats mask blame.** A whitespace-only commit that touches the error
  line shadows the real author; the engine handles this via diff analysis and
  file-history fallback — scenarios covering those paths are valuable.

## Development loop

1. Add the scenario (red): `python -m tests.zoo` shows it failing.
2. Change the engine to make it pass (green).
3. `python -m pytest -q && python -m ruff check .`
4. Commit locally with a message describing the bug class and the fix.
