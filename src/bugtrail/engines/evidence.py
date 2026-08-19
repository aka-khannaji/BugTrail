"""EvidenceEngine — deterministic collection of every piece of evidence.

Raw input (error text, git history) -> language-agnostic Evidence in a graph.
No AI is involved anywhere in this module.
"""
from __future__ import annotations

import re
from pathlib import Path

from bugtrail.adapters.registry import parse_stacktrace
from bugtrail.evidence.graph import (
    REL_DB_TO_EXCEPTION,
    REL_DEP_TO_EXCEPTION,
    REL_FILE_MODIFIED_BY,
    REL_LOG_TO_EXCEPTION,
    REL_REQUEST_TO_EXCEPTION,
    EvidenceGraph,
)
from bugtrail.evidence.models import Evidence

DB_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"duplicate entry", re.IGNORECASE), "Unique constraint violation (duplicate entry)"),
    (re.compile(r"integrity constraint", re.IGNORECASE), "Integrity constraint violation"),
    (re.compile(r"foreign key", re.IGNORECASE), "Foreign key constraint violation"),
    (re.compile(r"deadlock", re.IGNORECASE), "Deadlock detected"),
    (re.compile(r"null value in column", re.IGNORECASE), "NOT NULL constraint violation"),
]

# Log-shaped lines inside pasted error text: optional timestamp, then the
# line's own text is a `[timestamp] source.LEVEL: message` (Laravel) entry.
# ORDER NOTE: `source` is captured before `level` so "app.ERROR: ..." parses.
LOG_PATTERNS: list[re.Pattern] = [
    re.compile(
        r"^\s*(?P<prefix>\[[^\]]*\]\s*)?"
        r"(?P<source>[\w./\-]+\.)?"
        r"(?P<level>ERROR|WARN|WARNING|INFO|DEBUG|CRITICAL|FATAL)\s*[:\-]\s*"
        r"(?P<message>.*)$",
        re.IGNORECASE,
    ),
]

# HTTP request line carried in error text, e.g. "POST /api/orders HTTP/1.1".
REQUEST_PATTERN = re.compile(
    r"\b(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\s+([^\s\"']+)(?:\s+HTTP/\d)?",
    re.IGNORECASE,
)

TIMESTAMP_PATTERN = re.compile(r"(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?)")

# A missing symbol the error message names, e.g. "discountRate is not a
# function". Used to find commits whose diff removed that symbol (API break).
MISSING_SYMBOL_PATTERNS: list[re.Pattern] = [
    re.compile(r"(\w+) is not a function", re.IGNORECASE),
    re.compile(r"has no attribute ['\"]([\w.]+)['\"]", re.IGNORECASE),
    re.compile(r"['\"]([\w]+)['\"] is not defined", re.IGNORECASE),
    re.compile(r"Call to undefined method [\w\\\\]+::([\w]+)", re.IGNORECASE),
]

RECENT_COMMIT_WINDOW = 20

# A commit that touched hundreds of files (a branch merge, a giant feature
# commit) must not win the ranking by volume alone, so only the first handful
# of changed files contribute strength. Merge commits contribute nothing at
# all — they introduce no changes of their own.
MAX_FILES_SCORED_PER_COMMIT = 20

# Dependency manifests searched in the repo root; used both for the declared
# status of a missing dependency and as a blame fallback when every stack
# frame lives outside the repo (node_modules, vendor, site-packages).
MANIFEST_FILES: tuple[str, ...] = (
    "package.json",
    "composer.json",
    "requirements.txt",
    "pyproject.toml",
    "go.mod",
)

# Patterns yield the missing package/module name. Group 1 is the module;
# the "cannot import name X from pkg" pattern puts the *package* in group 2
# because the import name itself is never a declared dependency.
MISSING_DEP_PATTERNS: list[tuple[re.Pattern, int]] = [
    (re.compile(r"No module named ['\"]([^'\"]+)['\"]", re.IGNORECASE), 1),
    (re.compile(r"Cannot find module ['\"]([^'\"]+)['\"]", re.IGNORECASE), 1),
    (re.compile(r"Class ['\"]([^'\"]+)['\"] not found", re.IGNORECASE), 1),
    (
        re.compile(
            r"cannot import name ['\"]([^'\"]+)['\"] from ['\"]([^'\"]+)['\"]",
            re.IGNORECASE,
        ),
        2,
    ),
]


def resolve_repo_path(repo_root: Path, raw: Path) -> str | None:
    """Map a stack-trace file path onto a repo-relative path, or None."""
    try:
        if raw.is_absolute():
            try:
                rel = raw.resolve().relative_to(repo_root.resolve())
                if raw.exists():
                    return str(rel).replace("\\", "/")
            except (ValueError, OSError):
                pass
    except OSError:
        pass
    candidate = Path(str(raw).replace("\\", "/").lstrip("/"))
    if (repo_root / candidate).exists():
        return str(candidate).replace("\\", "/")
    if (repo_root / candidate.name).exists():
        return str(candidate.name).replace("\\", "/")
    return None


def normalize_ts(raw: str) -> str | None:
    """Parse an ISO-ish timestamp into a comparable ``YYYY-MM-DDTHH:MM[:SS]`` string."""
    match = TIMESTAMP_PATTERN.search(raw)
    if not match:
        return None
    value = match.group(1)
    if "T" not in value:
        value = value.replace(" ", "T", 1)
    return value


def extract_log_lines(error_text: str) -> list[dict]:
    """Deterministic scan of pasted error text for log-shaped lines."""
    entries: list[dict] = []
    for line_no, line in enumerate(error_text.splitlines(), start=1):
        for pattern in LOG_PATTERNS:
            match = pattern.match(line)
            if not match:
                continue
            entries.append(
                {
                    "level": match.group("level").upper(),
                    "message": match.group("message").strip(),
                    "line": line_no,
                    "source": (match.groupdict().get("source") or "").rstrip("."),
                    "ts": normalize_ts(match.group("prefix") or ""),
                }
            )
            break
    return entries


def extract_missing_symbol(error_text: str) -> str | None:
    """The symbol the error says is missing/not a function, or None."""
    for pattern in MISSING_SYMBOL_PATTERNS:
        match = pattern.search(error_text)
        if match:
            return match.group(1)
    return None


def extract_missing_dependency(error_text: str) -> str | None:
    """Package/module name the error says is missing, or None."""
    for pattern, group in MISSING_DEP_PATTERNS:
        match = pattern.search(error_text)
        if match:
            return _top_level(match.group(group))
    return None


def _top_level(name: str) -> str:
    """'@scope/pkg/sub.module' -> '@scope/pkg', 'requests.foo' -> 'requests'."""
    name = name.strip()
    if name.startswith("@"):
        parts = name.split("/", 1)
        if len(parts) == 2:
            return f"{parts[0]}/{parts[1].split('.')[0].split('/')[0]}"
        return name
    return name.split(".")[0]


DEPLOY_PATTERN = re.compile(r"\bdeploy(?:ed|ing|s)?\b", re.IGNORECASE)
ERROR_LEVELS = {"ERROR", "CRITICAL", "FATAL"}


def build_timeline(graph: EvidenceGraph) -> list[dict]:
    """Chronological dated facts: timestamped log lines plus the exception.

    Only entries with a parseable timestamp are included; the exception is
    appended last. Deploy markers are log lines that mention a deployment.
    Returns an empty list when there is no temporal signal.
    """
    events: list[dict] = []
    for node in graph.of_kind("log"):
        ts = node.data.get("ts")
        if not ts:
            continue
        events.append(
            {
                "ts": ts,
                "level": node.data.get("level"),
                "message": node.data.get("message", ""),
                "deploy": bool(DEPLOY_PATTERN.search(node.data.get("message", ""))),
            }
        )
    if not events:
        return []
    events.sort(key=lambda event: event["ts"])
    for exc in graph.exceptions():
        events.append(
            {
                "ts": "",
                "level": "EXCEPTION",
                "message": f"{exc.data.get('name')}: {exc.data.get('message', '')}",
                "deploy": False,
            }
        )
    return events


def timeline_summary(timeline: list[dict]) -> str | None:
    """Summarize the ok-before-failure / deploy relationship, or None."""
    failure = next(
        (
            index
            for index, event in enumerate(timeline)
            if event.get("level") in ERROR_LEVELS or event.get("level") == "EXCEPTION"
        ),
        None,
    )
    if failure is None:
        return None
    before = timeline[:failure]
    ok = [event for event in before if event.get("deploy") is False]
    deploys = [event for event in before if event.get("deploy")]
    parts: list[str] = []
    if ok:
        count = len(ok)
        parts.append(f"{count} ok event{'s' if count != 1 else ''} before first failure")
    if deploys:
        parts.append(f"first failure after {deploys[-1]['message']}")
    return " · ".join(parts) if parts else None


def parse_manifest_names(repo_root: Path, manifest: str) -> list[str]:
    """Top-level dependency names declared in a root manifest, best effort."""
    path = repo_root / manifest
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8", errors="replace")
    if manifest == "package.json":
        return list(_json_object(text, "dependencies", "devDependencies"))
    if manifest == "composer.json":
        return list(_json_object(text, "require", "require-dev"))
    if manifest == "requirements.txt":
        names = []
        for line in text.splitlines():
            clean = line.strip()
            if not clean or clean.startswith(("#", "-")):
                continue
            names.append(re.split(r"[=<>~!;\s]", clean, maxsplit=1)[0].strip())
        return names
    if manifest == "pyproject.toml":
        names = []
        in_deps = False
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("dependencies") and "=" in stripped:
                in_deps = True
                continue
            if in_deps:
                if stripped.startswith("["):
                    in_deps = False
                elif stripped.startswith("]"):
                    in_deps = False
                elif stripped:
                    match = re.match(r"['\"]([\w.\-]+)['\"]", stripped.lstrip("- "))
                    if match:
                        names.append(match.group(1))
        return names
    if manifest == "go.mod":
        names: list[str] = []
        in_block = False
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("require"):
                rest = stripped[len("require"):].strip()
                if rest.startswith("(") or not rest:
                    in_block = True
                elif rest:
                    names.append(rest.split()[0])
                continue
            if in_block:
                if stripped == ")":
                    in_block = False
                elif stripped:
                    names.append(stripped.split()[0])
        return names
    return []


def _json_object(text: str, *keys: str) -> dict:
    try:
        import json

        data = json.loads(text)
    except (ValueError, TypeError):
        return {}
    merged: dict = {}
    for key in keys:
        merged.update(data.get(key, {}) or {})
    return merged


class EvidenceEngine:
    def __init__(self, repo_root: Path, git, commit_window: int = RECENT_COMMIT_WINDOW):
        self.repo_root = repo_root
        self.git = git
        # How many recent commits the global scan considers. -1 means "deep":
        # skip the (expensive) global loop and lean on per-file history instead.
        self.commit_window = commit_window

    def collect_error(self, graph: EvidenceGraph, error_text: str) -> Evidence | None:
        exc = parse_stacktrace(error_text)
        if exc is not None:
            symbol = extract_missing_symbol(error_text)
            if symbol:
                exc.data["missing_symbol"] = symbol
            graph.add_exception_with_frames(exc)
            self.add_database_evidence(graph)
            self.add_log_evidence(graph, error_text)
            self.detect_request(graph, error_text)
            self.detect_dependencies(graph, error_text)
        return exc

    def detect_request(self, graph: EvidenceGraph, error_text: str) -> None:
        """Record HTTP request context (e.g. ``POST /api/orders HTTP/1.1``)."""
        match = REQUEST_PATTERN.search(error_text)
        if match:
            request = graph.add_request(match.group(1).upper(), match.group(2))
            for exc in graph.exceptions():
                graph.link(request.id, REL_REQUEST_TO_EXCEPTION, exc.id)

    def attach_file_history(self, graph: EvidenceGraph, frame_files: set[str], depth: int = 5) -> None:
        """Give recent commits that touched a frame file a modest score.

        Used only when exact-line blame for that file is unreliable — a later
        cosmetic reformat masked the line, or the line is not blamable. The
        true culprit may then sit outside the recent-commit window, so a few
        commits from the file's own history are surfaced as suspects: weaker
        than a direct blame, stronger than a random change. A deep scan
        (``--all``) raises the per-file depth so old culprits still surface.
        """
        if not frame_files:
            return
        file_history = getattr(self.git, "file_history", None)
        if file_history is None:
            return
        for rel in frame_files:
            for info in file_history(rel, depth):
                node = graph.file_node(rel)
                commit = graph.ensure_commit(
                    info["sha"],
                    info["message"],
                    author=info["author"],
                    date=info["date"],
                )
                graph.link(node.id, REL_FILE_MODIFIED_BY, commit.id)
                strength = node.data.setdefault("commit_strength", {})
                strength[info["sha"]] = max(strength.get(info["sha"], 0.0), 0.4)

    def _innermost_resolved_frames(self, graph: EvidenceGraph) -> set[str]:
        """The deepest frame of each exception chain that maps onto a repo file.

        Stack-trace formats disagree on frame order, so each exception records
        whether its frames are innermost-first (V8, PHP) or outermost-first
        (Python). Whichever end is the raise site, its commit wins strength
        ties: the line where the exception actually propagated is a better
        lead than an outer call-site frame.
        """
        innermost: set[str] = set()
        for exc in graph.exceptions():
            resolved: list[str] = []
            for raw in exc.data.get("frames", []):
                rel = resolve_repo_path(self.repo_root, Path(raw.get("file", "")))
                if rel is not None:
                    resolved.append(rel)
            if not resolved:
                continue
            if exc.data.get("frames_innermost_first"):
                innermost.add(resolved[0])
            else:
                innermost.add(resolved[-1])
        return innermost

    def detect_dependencies(self, graph: EvidenceGraph, error_text: str) -> None:
        """Record dependency evidence for missing-module errors.

        If the error names a dependency the repo does not declare, link that
        to the exception. When every stack frame lives outside the repo (e.g.
        node_modules) and nothing else is blamable, point the detective at the
        commit that last touched the dependency manifest.
        """
        missing = extract_missing_dependency(error_text)
        manifests = [name for name in MANIFEST_FILES if (self.repo_root / name).exists()]
        if missing is None and not manifests:
            return

        if missing is not None:
            declared = False
            manifest = ""
            for name in manifests:
                if missing.lower() in {n.lower() for n in parse_manifest_names(self.repo_root, name)}:
                    declared = True
                    manifest = name
                    break
            if not declared and manifests:
                manifest = manifests[0]
            dep = graph.add_dependency(missing, declared=declared, manifest=manifest)
            for exc in graph.exceptions():
                graph.link(dep.id, REL_DEP_TO_EXCEPTION, exc.id)

        if missing is not None and manifests and not self._any_resolved_frame(graph):
            # No repo frame is blamable (site-packages/node_modules/vendor all
            # the way down), so the best lead is the manifest's last change —
            # whether the module was dropped (undeclared) or its version was
            # bumped and broke an import (still declared).
            target = manifests[0]
            node = graph.file_node(target)
            frames = node.data.setdefault("frames", [])
            pseudo = {"file": target, "line": 1, "fn": None}
            if pseudo not in frames:
                frames.append(pseudo)

    def _any_resolved_frame(self, graph: EvidenceGraph) -> bool:
        """True when at least one stack frame maps onto a real repo file."""
        for node in graph.of_kind("file"):
            for frame in node.data.get("frames") or []:
                raw = frame.get("file")
                if raw and resolve_repo_path(self.repo_root, Path(raw)) is not None:
                    return True
        return False

    def add_log_evidence(self, graph: EvidenceGraph, error_text: str) -> None:
        for entry in extract_log_lines(error_text):
            node = graph.add_log(
                entry["level"],
                entry["message"],
                line=entry["line"],
                source=entry["source"],
                ts=entry["ts"] or "",
            )
            for exc in graph.exceptions():
                graph.link(node.id, REL_LOG_TO_EXCEPTION, exc.id)

    def add_database_evidence(self, graph: EvidenceGraph) -> Evidence | None:
        for exc in graph.exceptions():
            message = exc.data.get("message", "")
            for pattern, description in DB_PATTERNS:
                if pattern.search(message):
                    db = graph.add_database_query(description)
                    graph.link(db.id, REL_DB_TO_EXCEPTION, exc.id)
                    graph.link(exc.id, REL_DB_TO_EXCEPTION, db.id)
                    return db
        return None

    def attach_git(self, graph: EvidenceGraph) -> None:
        """Blame every frame line and note commits that touched those files."""
        if not self.git.available:
            return
        innermost = self._innermost_resolved_frames(graph)
        resolved_frame_files: set[str] = set()
        unreliable_blame: set[str] = set()
        for node in graph.of_kind("file"):
            for frame in node.data.get("frames") or []:
                raw = frame.get("file")
                if not raw:
                    continue
                rel = resolve_repo_path(self.repo_root, Path(raw))
                if rel is None:
                    continue
                resolved_frame_files.add(rel)
                blamed = self.git.blame_line(rel, frame["line"])
                if blamed:
                    commit = graph.ensure_commit(
                        blamed["sha"],
                        blamed["message"],
                        author=blamed["author"],
                        date=blamed["date"],
                    )
                    graph.link(node.id, REL_FILE_MODIFIED_BY, commit.id)
                    strength = node.data.setdefault("commit_strength", {})
                    strength[blamed["sha"]] = max(strength.get(blamed["sha"], 0.0), 1.0)
                    if rel in innermost:
                        node.data["innermost"] = True
                    cosmetic = bool(
                        getattr(self.git, "is_whitespace_only", None)
                        and self.git.is_whitespace_only(blamed["sha"])
                    )
                    if cosmetic:
                        unreliable_blame.add(rel)
                    else:
                        unreliable_blame.discard(rel)
                else:
                    unreliable_blame.add(rel)
        if self.commit_window > 0:
            for info in self.git.recent_commits(self.commit_window):
                sha = info["sha"]
                commit = graph.ensure_commit(
                    sha, info["message"], author=info["author"], date=info["date"]
                )
                if len(info.get("parents") or []) > 1:
                    commit.data["merge"] = True
                    continue
                cosmetic = bool(getattr(self.git, "is_whitespace_only", None) and self.git.is_whitespace_only(sha))
                base = 0.1 if cosmetic else 0.4
                for index, rel in enumerate(self.git.changed_files(sha)):
                    node = graph.file_node(rel)
                    if cosmetic:
                        commit.data["cosmetic"] = True
                    graph.link(node.id, REL_FILE_MODIFIED_BY, commit.id)
                    if index >= MAX_FILES_SCORED_PER_COMMIT:
                        continue
                    strength = node.data.setdefault("commit_strength", {})
                    strength[sha] = max(strength.get(sha, 0.0), base)
        depth = 200 if self.commit_window < 0 else 5
        self.attach_file_history(graph, resolved_frame_files & unreliable_blame, depth=depth)
