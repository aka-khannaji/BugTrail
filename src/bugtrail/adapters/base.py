"""Language adapters turn framework-specific raw evidence (stack traces)
into a language-agnostic Exception evidence. The core never cares whether
the frames came from Laravel or Python.
"""
from __future__ import annotations

import re
from abc import ABC, abstractmethod
from pathlib import Path

from bugtrail.evidence.models import Evidence, Frame

ErrorParse = tuple[str, str, list[Frame]]  # (name, message, frames) or None


class LanguageAdapter(ABC):
    name: str
    extensions: tuple[str, ...] = ()
    # Stack-trace formats disagree on frame order. Python lists frames
    # outermost-first (the raise site is the LAST frame); V8/Node and
    # PHP/Laravel list them innermost-first (raise site is the FIRST frame).
    frames_innermost_first: bool = False

    @classmethod
    @abstractmethod
    def detect(cls, repo_root: Path) -> bool:  # pragma: no cover - abstract
        ...

    @classmethod
    def parse_stacktrace(cls, text: str) -> ErrorParse | None:  # pragma: no cover
        raise NotImplementedError

    # -- shared helpers ---------------------------------------------------
    @classmethod
    def build_exception(cls, name: str, message: str, frames: list[Frame]) -> Evidence:
        return Evidence.exception(name, message, frames)

    @classmethod
    def match_extension(cls, repo_root: Path, extensions: tuple[str, ...]) -> bool:
        for candidate in repo_root.rglob("*"):
            if candidate.is_file() and candidate.suffix in extensions:
                return True
        return False


def first_match(lines: list[str], patterns: list[re.Pattern]) -> tuple[str, str] | None:
    for line in lines:
        for pattern in patterns:
            match = pattern.search(line)
            if match:
                groups = match.groupdict()
                return groups["name"], groups["message"].strip()
    return None
