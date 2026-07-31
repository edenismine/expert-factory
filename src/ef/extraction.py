"""Wraps graphify's extract and update entry points.

Owns the semantic-versus-AST decision, backend resolution, and PDF text
sidecars. Everything below this boundary is graphify's own and already tested
upstream; ef's job is deciding what to hand it.
"""

from __future__ import annotations

import hashlib
import json
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from . import EfError
from .manifest import DOCUMENT_SUFFIXES, IMAGE_SUFFIXES, PAPER_SUFFIXES
from .workspace import graph_dir, graph_json

SEMANTIC_SUFFIXES = DOCUMENT_SUFFIXES | PAPER_SUFFIXES | IMAGE_SUFFIXES

CODE_ONLY_BACKEND_HINT = (
    "no backend available for semantic extraction.\n"
    "Pass --backend <name>, or set the matching API key in the environment.\n"
    "`--backend claude-cli` is excluded from graphify's auto-detection and must be "
    "named explicitly; it bills your Claude subscription rather than a metered API key.\n"
    "Or pass --code-only to build the free AST-only graph."
)


def resolve_backend(data: dict, flag: str | None, needs_llm: bool) -> str | None:
    """Effective backend: explicit flag, else the persisted value, else auto-detect.

    Returns None when no LLM will be called, so cheap paths need no credentials.
    """
    if not needs_llm:
        return flag
    if flag:
        return flag
    persisted = data.get("extraction", {}).get("backend")
    if persisted:
        return persisted

    from graphify.llm import detect_backend

    detected = detect_backend()
    if not detected:
        raise EfError(CODE_ONLY_BACKEND_HINT)
    return detected


def check_vision(backend: str | None, sources: list[dict]) -> str | None:
    """Warn before extracting when image sources meet a backend with no vision."""
    images = [s["path"] for s in sources if s.get("kind") == "image"]
    if not images or backend is None:
        return None

    from graphify.llm import _backend_supports_vision

    if _backend_supports_vision(backend):
        return None
    return (
        f"{len(images)} image source(s) but backend {backend!r} has no vision support; "
        f"they will not be described. Choose a vision-capable backend "
        f"(claude, claude-cli, gemini, openai, kimi, bedrock)."
    )


def code_only_warning(sources: list[dict]) -> str | None:
    """Explain the cost/coverage tradeoff when --code-only would drop material."""
    semantic = [s for s in sources if s.get("kind") in ("document", "paper", "note", "image")]
    if not semantic:
        return None
    kinds = sorted({s["kind"] for s in semantic})
    return (
        f"--code-only with {len(semantic)} {'/'.join(kinds)} source(s): the doc, paper and "
        "image sets are emptied before the semantic pass, so those files get only a free "
        "AST link-scan (file nodes and link edges) and nothing describing their content. "
        "Drop --code-only to index them."
    )


@dataclass(frozen=True)
class UpdatePath:
    kind: str  # noop | ast | semantic
    reason: str

    @property
    def needs_llm(self) -> bool:
        return self.kind == "semantic"


def decide_update_path(changed: list[str], *, force: bool = False) -> UpdatePath:
    """Map a set of changed pack-relative paths to a refresh path.

    A doc change demands the expensive path because graphify's AST-only update
    deliberately *preserves* existing semantic nodes rather than regenerating
    them — correct for its incremental model, but it would leave stale doc nodes
    describing text no longer in the tree.
    """
    semantic = [p for p in changed if _is_semantic(p)]
    if semantic:
        shown = ", ".join(sorted(semantic)[:3])
        more = f" (+{len(semantic) - 3} more)" if len(semantic) > 3 else ""
        return UpdatePath("semantic", f"doc/paper/image changes: {shown}{more}")
    if force:
        return UpdatePath("semantic", "forced")
    if not changed:
        return UpdatePath("noop", "no source changed")
    shown = ", ".join(sorted(changed)[:3])
    more = f" (+{len(changed) - 3} more)" if len(changed) > 3 else ""
    return UpdatePath("ast", f"code-only changes: {shown}{more}")


def _is_semantic(path: str) -> bool:
    """Whether a changed path holds prose whose nodes must be regenerated."""
    return Path(path).suffix.lower() in SEMANTIC_SUFFIXES


#: graphify defaults to 60k, which packs ~20 heterogeneous files into one request.
#: The model then answers about a few of them and silently omits the rest: the
#: response is valid JSON and non-empty, so it trips none of graphify's retry
#: signals (those fire only on a truncated or wholly hollow response) and the
#: omitted files are simply absent from the graph. Smaller chunks cost the same
#: input tokens spread over more calls, and buy coverage that no retry recovers.
TOKEN_BUDGET = 12_000


def extract(
    pack: Path,
    *,
    code_only: bool,
    backend: str | None,
    force: bool = False,
    token_budget: int = TOKEN_BUDGET,
) -> None:
    """Run graphify's full extraction pipeline over the pack.

    graphify's extract is a sys.argv-driven CLI branch with no callable form, so
    it is invoked by building the argv it parses. GRAPHIFY_OUT is already set to
    the pack's graph directory name by ef's package import.

    `--no-gitignore` is mandatory, not a preference. A pack's whole point is to
    hold material that is deliberately *not* committed — clones and graphs are
    reconstructible, so every sane workspace gitignores them, and graphify walks
    up to the VCS root honoring what it finds. Left on, the ignore rule that keeps
    a pack out of git also empties its corpus, and gitignore's parent-exclusion
    rule means no negation inside the pack can win it back. The pack's own
    generated .graphifyignore is still honored, so per-source scoping survives.

    `force` is the caller's to decide and defaults off, because graphify reads it
    as "skip the semantic cache read" — passing it unconditionally re-dispatches
    (and re-pays for) every file in the pack on every refresh.
    """
    argv = ["graphify", "extract", str(pack), "--no-gitignore"]
    argv += ["--token-budget", str(token_budget)]
    if code_only:
        argv.append("--code-only")
    if backend:
        argv += ["--backend", backend]
    if force:
        argv.append("--force")
    _dispatch(argv, "extract")


def update_ast(pack: Path) -> None:
    """graphify's AST-only incremental update. Makes no LLM calls."""
    from graphify.watch import _rebuild_code

    _rebuild_code(pack.resolve(), block_on_lock=True)


def _dispatch(argv: list[str], command: str) -> None:
    from graphify.cli import dispatch_command

    saved = sys.argv
    sys.argv = argv
    try:
        dispatch_command(command)
    except SystemExit as exc:
        if exc.code not in (0, None):
            raise EfError(f"graphify {command} failed (exit {exc.code})") from exc
    finally:
        sys.argv = saved


def sidecar_name(pack: Path, pdf: Path) -> str:
    """Mirror graphify's Office sidecar naming: stem plus a hash of the relative path."""
    try:
        key = pdf.resolve().relative_to(pack.resolve()).as_posix()
    except ValueError:
        key = str(pdf.resolve())
    digest = hashlib.sha256(unicodedata.normalize("NFC", key).encode("utf-8")).hexdigest()[:8]
    return f"{pdf.stem}_{digest}.md"


def write_pdf_sidecars(pack: Path) -> list[Path]:
    """Persist PDF text next to the graph so serving never parses a PDF.

    graphify's own PDF extractor does not cache, so this persistence is ef's
    addition: it buys per-request speed and a serving path with no PDF library.
    """
    pdfs = [
        pdf
        for layer in ("raw", "repos", "notes")
        for pdf in sorted((pack / layer).rglob("*.pdf"))
        if pdf.is_file()
    ]
    if not pdfs:
        return []

    from graphify.detect import extract_pdf_text

    out = graph_dir(pack) / "converted"
    out.mkdir(parents=True, exist_ok=True)
    written = []
    for pdf in pdfs:
        target = out / sidecar_name(pack, pdf)
        if target.exists() and target.stat().st_mtime >= pdf.stat().st_mtime:
            continue
        text = extract_pdf_text(pdf)
        if not text:
            continue
        target.write_text(f"<!-- converted from {pdf.name} -->\n\n{text}", encoding="utf-8")
        written.append(target)
    return written


def graph_facts(pack: Path) -> dict:
    """Node and edge counts plus prominent hubs, read from the graph on disk."""
    import collections

    path = graph_json(pack)
    if not path.is_file():
        raise EfError(f"no graph at {path}; run `ef build` first")

    data = json.loads(path.read_text(encoding="utf-8"))
    links = data.get("links", data.get("edges", []))
    degree: collections.Counter = collections.Counter()
    for link in links:
        degree[link["source"]] += 1
        degree[link["target"]] += 1
    labels = {n["id"]: n.get("label", n["id"]) for n in data["nodes"]}
    extensions: collections.Counter = collections.Counter()
    for node in data["nodes"]:
        source = node.get("source_file") or ""
        if "." in source:
            extensions[source.rsplit(".", 1)[-1]] += 1
    return {
        "nodes": len(data["nodes"]),
        "edges": len(links),
        "hubs": [labels.get(i, i) for i, _ in degree.most_common(12)],
        "extensions": [ext for ext, _ in extensions.most_common(6)],
    }


HOLLOW_THRESHOLD = 4


def hollow_warning(facts: dict, sources: list[dict]) -> str | None:
    """Flag a graph too small for its corpus, which usually means a mis-scoped ignore."""
    semantic = [s for s in sources if s.get("kind") in ("document", "paper", "note", "image")]
    if not semantic:
        return None
    if facts["nodes"] >= len(semantic) * HOLLOW_THRESHOLD:
        return None
    return (
        f"{facts['nodes']:,} nodes from {len(semantic)} prose source(s) — that is close to "
        "one node per file, which usually means an ignore rule kept the material out of "
        f"the scan. Check {graph_dir(Path('.')).name}/ and the generated .graphifyignore "
        "before querying."
    )
