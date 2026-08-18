"""Go (runtime panic) stack trace adapter.

Go panic traces look like:

    panic: runtime error: index out of range [0] with length 0

    goroutine 6 [running]:
    main.handleOrder(0xc00003a700)
        /app/services/orders.go:5 +0x1f
    main.main()
        /app/main.go:22 +0x5a

Frames are listed innermost-first (the panic site is the top of the goroutine
stack), like V8 and PHP.
"""
from __future__ import annotations

import re
from pathlib import Path

from bugtrail.adapters.base import ErrorParse, LanguageAdapter
from bugtrail.evidence.models import Frame

PANIC_RE = re.compile(r"^\s*(?P<kind>panic|fatal error):\s*(?P<message>.*)$", re.IGNORECASE)
# A goroutine stack function line: `main.main()`, `app.Calculate(0xc000022080)`,
# `net/http.(*Server).Serve(...)`, `created by main.run in goroutine 5`.
FN_RE = re.compile(r"^\s*(?P<fn>[\w./\[\]()<>\-\*]+)\([^)]*\)\s*$")
CREATED_BY_RE = re.compile(r"^\s*created by (?P<fn>.+)$")
FILE_LINE_RE = re.compile(r"^\s+(?P<file>(?:[A-Za-z]:)?/[\w./\-]+\.go):(?P<line>\d+)")


class GoAdapter(LanguageAdapter):
    name = "go"
    extensions = (".go",)
    frames_innermost_first = True

    @classmethod
    def detect(cls, repo_root: Path) -> bool:
        return cls.match_extension(repo_root, cls.extensions)

    @classmethod
    def parse_stacktrace(cls, text: str) -> ErrorParse | None:
        header = None
        for line in text.splitlines():
            match = PANIC_RE.match(line)
            if match:
                header = match
                break
        if header is None:
            return None

        frames: list[Frame] = []
        pending_fn: str | None = None
        for line in text.splitlines():
            file_match = FILE_LINE_RE.match(line)
            if file_match:
                frames.append(
                    Frame(
                        file=Path(file_match.group("file")),
                        line=int(file_match.group("line")),
                        fn=pending_fn,
                    )
                )
                pending_fn = None
                continue
            fn_match = FN_RE.match(line)
            if fn_match and PANIC_RE.match(line) is None:
                pending_fn = fn_match.group("fn").strip()
                continue
            created = CREATED_BY_RE.match(line)
            if created:
                pending_fn = f"created by {created.group('fn').strip()}"
                continue

        kind = header.group("kind").strip().lower()
        name = "FatalError" if kind == "fatal error" else "panic"
        return name, header.group("message").strip(), frames
