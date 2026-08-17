"""EvidenceGraph — nodes of Evidence joined by labelled relationships.

The graph is BugTrail's technical identity: deterministic analysis fills
it, the detective engine scores it, and the AI layer reasons over it.
Nothing is ever sent to an LLM that is not already represented here.
"""
from __future__ import annotations

from bugtrail.evidence.models import Evidence, EvidenceKind, Frame

REL_EXCEPTION_FRAME = "contains_frame"
REL_FRAME_FILE = "in_file"
REL_FILE_MODIFIED_BY = "modified_by"
REL_COMMIT_CHANGED = "changed"
REL_FILE_DB = "issued"
REL_DB_TO_EXCEPTION = "explains"
REL_LOG_TO_EXCEPTION = "contextualizes"
REL_DEP_TO_EXCEPTION = "implicates"


def _normalize_path(path: str) -> str:
    """Canonical repo-relative key: forward slashes, no leading separator.

    Keeps frame paths from a stack trace (e.g. Laravel's '/var/www/html/...')
    and repo-resolved paths (e.g. 'var/www/html/...') on the same file node.
    """
    return str(path).replace("\\", "/").lstrip("/")


class EvidenceGraph:
    def __init__(self) -> None:
        self._nodes: dict[str, Evidence] = {}
        # source -> [(relation, target)]
        self._edges: dict[str, list[tuple[str, str]]] = {}

    # -- mutation ---------------------------------------------------------
    def add(self, evidence: Evidence) -> Evidence:
        self._nodes.setdefault(evidence.id, evidence)
        return evidence

    def link(self, source: str, relation: str, target: str) -> None:
        self._edges.setdefault(source, [])
        links = self._edges[source]
        if (relation, target) not in links:
            links.append((relation, target))

    # -- queries ----------------------------------------------------------
    def nodes(self) -> list[Evidence]:
        return list(self._nodes.values())

    def node(self, node_id: str) -> Evidence | None:
        return self._nodes.get(node_id)

    def of_kind(self, kind: EvidenceKind | str) -> list[Evidence]:
        if isinstance(kind, str):
            kind = EvidenceKind(kind)
        return [n for n in self._nodes.values() if n.kind is kind]

    def edges_from(self, node_id: str) -> list[tuple[str, str]]:
        return self._edges.get(node_id, [])

    def edges_to(self, relation: str) -> list[tuple[str, str]]:
        return [(s, t) for s, links in self._edges.items() for r, t in links if r == relation]

    def neighbors(self, node_id: str) -> list[Evidence]:
        ids = [t for _, t in self.edges_from(node_id)]
        return [n for n in self._nodes.values() if n.id in ids]

    def file_node(self, path: str) -> Evidence:
        key = _normalize_path(path)
        for node in self.of_kind(EvidenceKind.FILE):
            if _normalize_path(node.data.get("path", "")) == key:
                return node
        return self.add(Evidence.file(key))

    def ensure_commit(self, sha: str, message: str, *, author: str = "", date: str = "") -> Evidence:
        for node in self.of_kind(EvidenceKind.COMMIT):
            if node.data.get("sha") == sha:
                return node
        return self.add_commit(sha, message, author=author, date=date)

    def exceptions(self) -> list[Evidence]:
        return self.of_kind(EvidenceKind.EXCEPTION)

    def exception_frames(self) -> list[Frame]:
        frames: list[Frame] = []
        for exc in self.exceptions():
            for raw in exc.data.get("frames", []):
                frames.append(Frame.model_validate(raw))
        return frames

    def add_exception_with_frames(self, exc: Evidence) -> None:
        self.add(exc)
        for raw in exc.data.get("frames", []):
            frame = Frame.model_validate(raw)
            file_node = self.file_node(str(frame.file).replace("\\", "/"))
            frames = file_node.data.setdefault("frames", [])
            entry = {"file": str(frame.file).replace("\\", "/"), "line": frame.line, "fn": frame.fn}
            if entry not in frames:
                frames.append(entry)
            self.link(exc.id, REL_EXCEPTION_FRAME, file_node.id)
            self.link(file_node.id, REL_FRAME_FILE, exc.id)

    def add_commit(self, sha: str, message: str, *, author: str = "", date: str = "") -> Evidence:
        return self.add(Evidence.commit(sha, message, author=author, date=date))

    def add_database_query(self, description: str) -> Evidence:
        return self.add(Evidence.database_query(description))

    def add_log(self, level: str, message: str, *, line: int = 0, source: str = "") -> Evidence:
        return self.add(Evidence.log(level, message, line=line, source=source))

    def add_dependency(self, name: str, *, declared: bool = False, manifest: str = "") -> Evidence:
        return self.add(Evidence.dependency(name, declared=declared, manifest=manifest))

    def link_file_commit(self, file_path: str, commit_id: str) -> None:
        for n in self.of_kind(EvidenceKind.FILE):
            if n.data.get("path") == file_path:
                self.link(n.id, REL_FILE_MODIFIED_BY, commit_id)
                break

    # -- persistence ------------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "nodes": [n.model_dump(mode="json") for n in self._nodes.values()],
            "edges": {s: [list(edge) for edge in links] for s, links in self._edges.items()},
        }

    @classmethod
    def from_dict(cls, data: dict) -> "EvidenceGraph":
        graph = cls()
        for raw in data.get("nodes", []):
            graph.add(Evidence.model_validate(raw))
        for source, links in data.get("edges", {}).items():
            for relation, target in links:
                graph.link(source, relation, target)
        return graph
