"""BugTrail CLI — kept intentionally tiny."""
from __future__ import annotations

import sys
from pathlib import Path

import typer

from bugtrail import __version__
from bugtrail.adapters.git import GitAdapter
from bugtrail.config import load_config, write_default_config
from bugtrail.investigation.pipeline import run_investigation
from bugtrail.investigation.report import render_cost_summary, render_report
from bugtrail.storage import Storage


def _enable_utf8() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):  # pragma: no cover - not always writable
            pass


_enable_utf8()

app = typer.Typer(
    add_completion=False,
    help="Find the likely root cause of bugs with evidence.",
    no_args_is_help=True,
)


def _version_callback(value: bool) -> None:
    if value:
        print(f"bugtrail {__version__}")
        raise typer.Exit()


@app.callback()
def _main(
    version: bool = typer.Option(False, "--version", callback=_version_callback, is_eager=True),
) -> None:  # pragma: no cover - trivial
    pass


@app.command()
def init(
    model: str = typer.Option("", help="Default AI model (e.g. gpt-4o-mini, llama-3.1-8b-instant)."),
    base_url: str = typer.Option(
        "", help="OpenAI-compatible endpoint (e.g. https://api.openai.com/v1, http://localhost:11434/v1)."
    ),
) -> None:
    """Initialize BugTrail in the current project."""
    root = _repo_root()
    config_path = write_default_config(root)
    if model or base_url:
        _patch_config(config_path, model=model or None, base_url=base_url or None)
    (root / ".bugtrail").mkdir(exist_ok=True)
    print(f"BugTrail initialized in {root}")
    print(f"Config: {config_path}")
    print("Set BUGTRAIL_API_KEY in your environment to enable AI (or use a local/Ollama endpoint for $0).")


@app.command()
def investigate(
    error: Path | None = typer.Option(
        None, "--error", "-e", help="Path to a file containing the stack trace / error."
    ),
    commit: str | None = typer.Option(
        None, "--commit", "-c", help="Investigate around a specific commit instead of an error."
    ),
    no_ai: bool = typer.Option(False, "--no-ai", help="Force deterministic-only mode."),
) -> None:
    """Investigate a bug: collect evidence, build a graph, rank root causes."""
    root = _repo_root()
    git = GitAdapter.discover(_cwd())
    if not git.available:
        print(
            "Warning: no Git repository or commit history found — evidence is limited to the trace itself.",
            file=sys.stderr,
        )
    error_text = _read_error_text(error)

    try:
        config = load_config(root)
        session = run_investigation(
            repo_root=root,
            error_text=error_text,
            commit_ref=commit,
            config=config,
            git=git or GitAdapter(root),
            allow_ai=not no_ai,
        )
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise typer.Exit(1) from exc

    path = Storage(root).save(session)
    signature = Storage.error_signature(session)
    recurrence = Storage(root).find_similar(signature, exclude_id=session.id)
    if recurrence:
        session = session.model_copy(update={"recurrence": recurrence})
        Storage(root).save(session)
    print(render_report(session))
    if not no_ai:
        if config.ai_enabled and not session.ai_summary:
            print(
                "\nTip: AI is configured but unreachable. Start the local service "
                "(`docker run -p 8000:8000 ghcr.io/OWNER/bugtrail-ai:latest`) or "
                "check your BUGTRAIL_API_KEY / base_url.",
                file=sys.stderr,
            )
        elif not config.ai_enabled:
            print(
                "\nTip: enable AI notes for a plain-English explanation of the ranking "
                "(`bugtrail init --base-url http://127.0.0.1:8000/v1 --model qwen2.5-coder-0.5b-instruct` "
                "for a free local model, or set BUGTRAIL_API_KEY for a cloud provider).",
                file=sys.stderr,
            )
    print(f"\nSession saved to {path}")


@app.command()
def report(
    session_id: str | None = typer.Argument(None, help="Session id (defaults to the latest)."),
) -> None:
    """Display a saved investigation report."""
    root = _repo_root()
    try:
        session = Storage(root).load(session_id)
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise typer.Exit(1) from exc
    print(render_report(session))


@app.command()
def history(limit: int = typer.Option(20, "--limit", help="How many sessions to list.")) -> None:
    """List past investigations, newest first."""
    root = _repo_root()
    items = Storage(root).history(limit)
    if not items:
        print("No investigations recorded yet. Run `bugtrail investigate` first.")
        return
    for item in items:
        exc = item["exception_name"] or "(change overview)"
        top = item["top_commit"] or ""
        confidence = f"  {item['top_confidence'] * 100:.0f}%" if item["top_confidence"] else ""
        print(f"{item['created_at']}  {exc:<28} {top[:60]}{confidence}")
        print(f"      {item['id']}  {item['repo_root']}")


@app.command()
def cost() -> None:
    """Show the cost ledger aggregated across all investigations."""
    root = _repo_root()
    summary = Storage(root).cost_summary()
    print(render_cost_summary(summary))


# -- helpers -------------------------------------------------------------
def _cwd() -> Path:
    return Path.cwd()


def _git_root() -> Path | None:
    return GitAdapter.discover(_cwd()).repo_root


def _repo_root() -> Path:
    return _git_root() or _cwd()


def _read_error_text(error: Path | None) -> str:
    if error is not None:
        if not error.exists():
            raise typer.BadParameter(f"File not found: {error}")
        return error.read_text(encoding="utf-8", errors="replace")
    if not sys.stdin.isatty():
        return sys.stdin.read()
    return ""


def _patch_config(config_path: Path, *, model: str | None, base_url: str | None) -> None:
    content = config_path.read_text(encoding="utf-8")
    if base_url:
        content = content.replace('base_url = "https://api.openai.com/v1"', f'base_url = "{base_url}"')
    if model:
        content = content.replace('model = "gpt-4o-mini"', f'model = "{model}"')
    config_path.write_text(content, encoding="utf-8")
