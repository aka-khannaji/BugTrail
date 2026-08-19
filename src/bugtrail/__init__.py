"""BugTrail — find the likely root cause of bugs with evidence."""

import importlib.metadata


def _version() -> str:
    try:
        return importlib.metadata.version("getbugtrail")
    except importlib.metadata.PackageNotFoundError:  # pragma: no cover - source checkout
        return "0.1.0"


__version__ = _version()
