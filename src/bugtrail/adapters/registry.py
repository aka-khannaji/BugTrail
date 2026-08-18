"""Registry of language adapters and stack-trace dispatch."""
from __future__ import annotations

from pathlib import Path

from bugtrail.adapters.base import ErrorParse, LanguageAdapter
from bugtrail.adapters.go import GoAdapter
from bugtrail.adapters.javascript import JavaScriptAdapter
from bugtrail.adapters.php import PHPAdapter
from bugtrail.adapters.python import PythonAdapter
from bugtrail.evidence.models import Evidence

ADAPTERS: tuple[type[LanguageAdapter], ...] = (
    PythonAdapter,
    JavaScriptAdapter,
    GoAdapter,
    PHPAdapter,
)


def detect_adapters(repo_root: Path) -> list[type[LanguageAdapter]]:
    return [adapter for adapter in ADAPTERS if adapter.detect(repo_root)]


def parse_stacktrace(text: str) -> Evidence | None:
    """Pick the best-matching language parser. Order matters: most specific first."""
    best: tuple[type[LanguageAdapter], ErrorParse] | None = None
    for adapter in ADAPTERS:
        parsed = adapter.parse_stacktrace(text)
        if parsed is not None:
            best = (adapter, parsed)
            break
    if best is None:
        return None
    adapter, (name, message, frames) = best
    exc = Evidence.exception(name, message, frames)
    exc.data["frames_innermost_first"] = adapter.frames_innermost_first
    return exc
