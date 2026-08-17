"""Python traceback adapter."""
from __future__ import annotations

import re
from pathlib import Path

from bugtrail.adapters.base import ErrorParse, LanguageAdapter
from bugtrail.evidence.models import Frame

FRAME_RE = re.compile(r'File "(?P<file>[^"]+)", line (?P<line>\d+)(, in (?P<fn>.+))?')
ERROR_RE = re.compile(r"\s*(?P<name>[A-Za-z_][A-Za-z0-9_.]*(?:Error|Exception|Warning)):\s*(?P<message>.*)")


class PythonAdapter(LanguageAdapter):
    name = "python"
    extensions = (".py",)

    @classmethod
    def detect(cls, repo_root: Path) -> bool:
        return cls.match_extension(repo_root, cls.extensions)

    @classmethod
    def parse_stacktrace(cls, text: str) -> ErrorParse | None:
        lines = text.splitlines()
        frames: list[Frame] = []
        for line in lines:
            match = FRAME_RE.search(line)
            if match:
                frames.append(
                    Frame(
                        file=Path(match.group("file")),
                        line=int(match.group("line")),
                        fn=match.group("fn"),
                    )
                )
        error = None
        for line in reversed(lines):
            match = ERROR_RE.search(line)
            if match and (line.strip().startswith(("Traceback",))) is False:
                if "Traceback" not in line:
                    error = (match.group("name"), match.group("message").strip())
                    break
        if not frames and error is None:
            return None
        # Python's header regex is generic; require a real traceback signal.
        if not frames and "Traceback (most recent call last)" not in text:
            return None
        name, message = error or ("UnknownError", "Could not parse exception header.")
        name = name.rsplit(".", 1)[-1]
        return name, message, frames
