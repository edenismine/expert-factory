"""expert.json: load, validate, write, and reconcile against files on disk.

Pure functions over paths and dicts. No network, no subprocess, no LLM.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from . import EfError
from .workspace import IGNORE_NAME, MANIFEST_NAME, SKILL_NAME, graph_dir

KINDS = ("code", "document", "paper", "note", "image")
LIFECYCLES = ("refreshable", "snapshot")

# `video` is recognized only so `ef add` can reject it with a specific message.
VIDEO_SUFFIXES = frozenset({".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"})
IMAGE_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg", ".tiff"})
PAPER_SUFFIXES = frozenset({".pdf"})
DOCUMENT_SUFFIXES = frozenset(
    {".md", ".mdx", ".markdown", ".txt", ".rst", ".html", ".htm", ".docx", ".xlsx", ".adoc"}
)
#: Markdown is treated as authored prose, so adoption routes it to notes/.
PROSE_SUFFIXES = frozenset({".md", ".mdx", ".markdown"})

#: Layers whose files must each have a manifest entry. repos/ is excluded: a
#: clone has one entry for the whole tree, not one per file.
RECONCILED_LAYERS = ("raw", "notes")


def now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return "sha256:" + digest.hexdigest()


def classify(path: Path) -> str:
    """Map a path to a source kind by extension, defaulting to document."""
    suffix = path.suffix.lower()
    if suffix in VIDEO_SUFFIXES:
        return "video"
    if suffix in IMAGE_SUFFIXES:
        return "image"
    if suffix in PAPER_SUFFIXES:
        return "paper"
    if suffix in DOCUMENT_SUFFIXES:
        return "document"
    return "document"


def kind_for_adoption(path: Path, layer: str) -> str:
    """Kind for a file being adopted. Everything under notes/ is authored prose."""
    if layer == "notes":
        return "note"
    return classify(path)


def read_frontmatter(path: Path) -> dict[str, str]:
    """Lift graphify's provenance frontmatter from a fetched markdown file.

    Deliberately not a YAML parse: the block graphify writes is flat
    `key: value` pairs, and pulling in a YAML dependency to read five keys would
    also mean handling arbitrary YAML from a fetched page.
    """
    if path.suffix.lower() not in {".md", ".markdown", ".mdx"}:
        return {}
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    if not text.startswith("---"):
        return {}
    _, _, rest = text.partition("\n")
    body, sep, _ = rest.partition("\n---")
    if not sep:
        return {}
    found: dict[str, str] = {}
    for line in body.splitlines():
        key, colon, value = line.partition(":")
        if colon and key.strip() and not key.startswith(" "):
            found[key.strip()] = value.strip().strip("\"'")
    return found


def snapshot_entry(pack: Path, path: Path, layer: str) -> dict:
    """Build a manifest entry for a file in raw/ or notes/."""
    front = read_frontmatter(path)
    kind = front.get("type") if front.get("type") in KINDS else None
    entry = {
        "name": front.get("title") or path.stem,
        "kind": kind or kind_for_adoption(path, layer),
        "path": path.relative_to(pack).as_posix(),
        "origin": (
            {"type": "fetch", "url": front["source_url"]}
            if front.get("source_url")
            else {"type": "authored"}
        ),
        "lifecycle": "snapshot",
        "captured_at": front.get("captured_at") or now(),
        "checksum": checksum(path),
    }
    contributor = front.get("contributor") or front.get("author")
    if contributor:
        entry["contributor"] = contributor
    return entry


def git_entry(pack: Path, clone: Path, url: str, ref: str, rev: str) -> dict:
    return {
        "name": clone.relative_to(pack / "repos").as_posix(),
        "kind": "code",
        "path": clone.relative_to(pack).as_posix(),
        "origin": {"type": "git", "url": url},
        "lifecycle": "refreshable",
        "ref": ref,
        "rev": rev,
        "last_synced": now(),
    }


def load(pack: Path) -> dict:
    path = pack / MANIFEST_NAME
    if not path.is_file():
        raise EfError(f"{pack} is not a pack: no {MANIFEST_NAME}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise EfError(f"{path} is not valid JSON: {exc}") from exc
    data.setdefault("sources", [])
    data.setdefault("extraction", {})
    data.setdefault("graph", {})
    return data


def save(pack: Path, data: dict) -> None:
    ordered = {
        "name": data["name"],
        "title": data.get("title") or data["name"],
        "extraction": data.get("extraction", {}),
        "graph": data.get("graph", {}),
        "sources": data.get("sources", []),
    }
    (pack / MANIFEST_NAME).write_text(json.dumps(ordered, indent=2) + "\n", encoding="utf-8")


def blank(name: str, title: str | None = None) -> dict:
    return {
        "name": name,
        "title": title or name,
        "extraction": {},
        "graph": {},
        "sources": [],
    }


def sources_by_kind(data: dict) -> dict[str, int]:
    counts: dict[str, int] = {}
    for source in data.get("sources", []):
        kind = source.get("kind", "document")
        counts[kind] = counts.get(kind, 0) + 1
    return counts


def refreshable(data: dict) -> list[dict]:
    return [s for s in data.get("sources", []) if s.get("lifecycle") == "refreshable"]


def upsert(data: dict, entry: dict) -> None:
    """Replace the entry with the same path, or append."""
    sources = data.setdefault("sources", [])
    for index, existing in enumerate(sources):
        if existing.get("path") == entry["path"]:
            sources[index] = entry
            return
    sources.append(entry)


def is_metadata(pack: Path, path: Path) -> bool:
    return path.name in (MANIFEST_NAME, SKILL_NAME, IGNORE_NAME) and path.parent == pack


def pack_files(pack: Path) -> list[Path]:
    """Every file in the reconciled layers, excluding the graph output."""
    found: list[Path] = []
    output = graph_dir(pack)
    for layer in RECONCILED_LAYERS:
        directory = pack / layer
        if not directory.is_dir():
            continue
        for path in sorted(directory.rglob("*")):
            if not path.is_file() or path.name.startswith("."):
                continue
            if output in path.parents:
                continue
            found.append(path)
    return found


def irreplaceable_counts(pack: Path) -> dict[str, int]:
    """File counts per reconciled layer (raw/notes) — content `ef delete` cannot rebuild."""
    counts: dict[str, int] = {}
    for path in pack_files(pack):
        layer = path.relative_to(pack).parts[0]
        counts[layer] = counts.get(layer, 0) + 1
    return counts


@dataclass
class Reconciliation:
    strays: list[Path] = field(default_factory=list)
    orphans: list[str] = field(default_factory=list)
    altered: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not (self.strays or self.orphans)


def reconcile(pack: Path, data: dict) -> Reconciliation:
    """Compare manifest entries against files on disk.

    Strays are files with no entry; orphans are entries whose file is gone.
    Altered snapshots are reported but do not block: a changed checksum is
    information, not a broken pack.
    """
    result = Reconciliation()
    recorded = {s["path"]: s for s in data.get("sources", [])}

    for path in pack_files(pack):
        rel = path.relative_to(pack).as_posix()
        entry = recorded.get(rel)
        if entry is None:
            result.strays.append(path)
        elif entry.get("checksum") and entry["checksum"] != checksum(path):
            result.altered.append(rel)

    for rel, entry in recorded.items():
        target = pack / rel
        if entry.get("lifecycle") == "refreshable":
            if not target.is_dir():
                result.orphans.append(rel)
        elif not target.is_file():
            result.orphans.append(rel)

    return result


def adopt(pack: Path, data: dict, strays: list[Path]) -> list[dict]:
    """Create entries for every stray in one pass."""
    added = []
    for path in strays:
        layer = path.relative_to(pack).parts[0]
        entry = snapshot_entry(pack, path, layer)
        upsert(data, entry)
        added.append(entry)
    return added
