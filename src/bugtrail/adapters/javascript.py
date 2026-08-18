"""JavaScript / TypeScript (V8, Node.js) stack trace adapter."""
from __future__ import annotations

import re
from pathlib import Path

from bugtrail.adapters.base import ErrorParse, LanguageAdapter
from bugtrail.evidence.models import Frame

NAMED_FRAME_RE = re.compile(r"\s+at\s+(?P<fn>\S+?)\s+\((?P<file>[^\)]+):(?P<line>\d+):(?P<col>\d+)\)")
BARE_FRAME_RE = re.compile(r"\s+at\s+(?P<file>[^\s]+):(?P<line>\d+):(?P<col>\d+)")
ERROR_RE = re.compile(r"\s*(?P<name>\w+Error):\s*(?P<message>.*)")


class JavaScriptAdapter(LanguageAdapter):
    name = "javascript"
    extensions = (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs")
    frames_innermost_first = True

    @classmethod
    def detect(cls, repo_root: Path) -> bool:
        return cls.match_extension(repo_root, cls.extensions)

    @classmethod
    def parse_stacktrace(cls, text: str) -> ErrorParse | None:
        lines = text.splitlines()
        frames: list[Frame] = []
        for line in lines:
            match = NAMED_FRAME_RE.search(line) or BARE_FRAME_RE.search(line)
            if match:
                frames.append(
                    Frame(
                        file=Path(match.group("file")),
                        line=int(match.group("line")),
                        fn=match.groupdict().get("fn"),
                    )
                )
        error = None
        for line in lines:
            match = ERROR_RE.search(line)
            if match:
                error = (match.group("name"), match.group("message").strip())
                break
        if not frames and not error:
            return None
        name, message = error or ("Error", "Could not parse exception header.")
        return name, message, frames
