"""PHP / Laravel stack trace adapter."""
from __future__ import annotations

import re
from pathlib import Path

from bugtrail.adapters.base import ErrorParse, LanguageAdapter
from bugtrail.evidence.models import Frame

LARAVEL_FRAME_RE = re.compile(r"#\d+\s+(?P<file>/[^\(\s]+)\((?P<line>\d+)\)\s*:")
PHP_FRAME_RE = re.compile(r"(?P<file>/[^:\s]+\.php):(?P<line>\d+)")
# e.g. SQLSTATE[23000]: Integrity constraint violation: 1062 Duplicate entry ...
SQLSTATE_RE = re.compile(r"SQLSTATE\[(?P<sqlstate>\w+)\]:(?P<message>.*)")
EXCEPTION_RE = re.compile(r"\s*(?P<name>[\w\\\\]+):\s*(?P<message>.*)")


class PHPAdapter(LanguageAdapter):
    name = "php"
    extensions = (".php",)

    @classmethod
    def detect(cls, repo_root: Path) -> bool:
        return cls.match_extension(repo_root, cls.extensions)

    @classmethod
    def parse_stacktrace(cls, text: str) -> ErrorParse | None:
        lines = text.splitlines()
        frames: list[Frame] = []
        for line in lines:
            match = LARAVEL_FRAME_RE.search(line) or PHP_FRAME_RE.search(line)
            if match:
                frames.append(
                    Frame(file=Path(match.group("file")), line=int(match.group("line")))
                )
        error = None
        for line in lines:
            match = SQLSTATE_RE.search(line)
            if match:
                message = f"SQLSTATE[{match.group('sqlstate')}]: {match.group('message').strip()}"
                error = ("DatabaseException", message)
                break
        if error is None:
            for line in lines:
                match = EXCEPTION_RE.search(line)
                if match and " at /" not in line:
                    error = (match.group("name").rsplit("\\", 1)[-1], match.group("message").strip())
                    break
        if not frames and not error:
            return None
        name, message = error or ("Exception", "Could not parse exception header.")
        return name, message, frames
