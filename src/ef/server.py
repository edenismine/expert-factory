"""Expert MCP server: one pack, one graph, served over stdio.

Read-only by construction — there is no write path here. That keeps two clients
able to serve the same pack concurrently and keeps a pack usable on read-only
media. Extraction happens only under build/update/sync; a server that could
rebuild would make an agent's read-only query capable of spending money.

Diagnostics go to stderr: on stdio, stdout is the JSON-RPC framing and a stray
print corrupts the stream.
"""

from __future__ import annotations

import contextlib
import sys
from pathlib import Path
from typing import cast

from . import EfError
from .extraction import sidecar_name
from .manifest import PAPER_SUFFIXES, sources_by_kind
from .workspace import MANIFEST_NAME, graph_dir, graph_json, is_pack

MAX_LINES = 400


def preflight(pack: Path) -> Path:
    """Validate the pack before the transport starts.

    A failed MCP handshake gives a client almost nothing to report, so a wrong
    `cwd` or an unbuilt pack has to fail loudly here instead.
    """
    if not is_pack(pack):
        raise EfError(
            f"{pack} is not a pack: no {MANIFEST_NAME}. Check the `cwd` in your MCP client config."
        )
    graph = graph_json(pack)
    if not graph.is_file():
        raise EfError(f"{pack} has no graph at {graph.relative_to(pack)}; run `ef build` first.")
    return graph


class GraphHandle:
    """Holds the loaded graph, reloading when graph.json changes on disk.

    `ef update` rewrites graph.json out from under a running server, so the stamp
    is rechecked per call rather than loaded once at startup.
    """

    def __init__(self, path: Path):
        self._path = path
        self._stamp: tuple[int, int] | None = None
        self._graph = None

    def get(self):
        import networkx as nx
        from graphify import serve as _g

        st = self._path.stat()
        stamp = (st.st_mtime_ns, st.st_size)
        graph = self._graph
        if graph is None or stamp != self._stamp:
            # graphify's loader is annotated -> nx.Graph but returns a DiGraph;
            # the directed successors/predecessors split below depends on that.
            with contextlib.redirect_stdout(sys.stderr):
                graph = cast(nx.DiGraph, _g._load_graph(str(self._path)))
            self._graph, self._stamp = graph, stamp
        return graph


def resolve_node(graph, ref: str):
    from graphify import serve as _g

    data = graph.nodes.get(ref)
    if data is not None:
        return ref, data
    for hit in _g._find_node(graph, ref):
        return hit, graph.nodes[hit]
    return None


def read_material(pack: Path, rel_path: str, location: str | None, before: int, after: int) -> dict:
    """Read a pack-relative source across any layer, refusing to escape the pack.

    A PDF is served from the text sidecar written at build, and line arguments are
    reported as inapplicable rather than answered with a misleading window: PDFs
    have no char-offset model, so a line anchor has nothing behind it.
    """
    root = pack.resolve()
    target = (root / rel_path).resolve()
    if not target.is_relative_to(root):
        return {"error": "path escapes the pack root"}

    if target.suffix.lower() in PAPER_SUFFIXES:
        sidecar = graph_dir(root) / "converted" / sidecar_name(root, target)
        if not sidecar.is_file():
            return {
                "error": f"no text sidecar for {rel_path}; re-run `ef build` to convert it",
                "file": rel_path,
            }
        text = sidecar.read_text(encoding="utf-8", errors="replace")
        return {
            "file": rel_path,
            "text": text[: MAX_LINES * 200],
            "truncated": len(text) > MAX_LINES * 200,
            "lines_not_applicable": "PDF-backed: no char-offset model, so before/after are ignored",
        }

    if not target.is_file():
        return {"error": f"not present in the pack: {rel_path}"}

    anchor = 1
    if location:
        digits = "".join(c for c in location.split("-")[0] if c.isdigit())
        if digits:
            anchor = int(digits)

    lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
    start = max(1, anchor - before)
    span = min(before + after, MAX_LINES)
    return {
        "file": rel_path,
        "start_line": start,
        "text": "\n".join(lines[start - 1 : start - 1 + span]),
        "truncated": start - 1 + span < len(lines),
    }


def build_server(pack: Path, data: dict):
    """Wire the tools over one pack. Called only after preflight."""
    from graphify import serve as _g
    from graphify.build import edge_data
    from graphify.security import sanitize_label
    from mcp.server.fastmcp import FastMCP

    handle = GraphHandle(graph_json(pack))
    name = data.get("name", pack.name)
    mcp = FastMCP(f"{name}-expert")

    @mcp.tool()
    def search(question: str, mode: str = "bfs", depth: int = 3, token_budget: int = 2000) -> str:
        """Find symbols, documents and relationships in this expert's knowledge graph.

        Returns matching nodes with their source file and line, plus the edges
        between them. Use bfs for broad context and dfs to trace one chain. Ask
        with exact symbol, module or document names. Node ids feed read_source.
        """
        with contextlib.redirect_stdout(sys.stderr):
            return _g._query_graph_text(
                handle.get(), question, mode=mode, depth=depth, token_budget=token_budget
            )

    @mcp.tool()
    def read_source(node_id: str, before: int = 5, after: int = 60) -> dict:
        """Read the real text behind a graph node: code, a page, a paper, or a note.

        The graph stores only structure, so use this to see actual implementation,
        signatures, or what a document argues. Pass a node id from search; a plain
        name is fuzzy-matched and may resolve elsewhere. On a PDF-backed node the
        line arguments do not apply and the response says so.
        """
        graph = handle.get()
        found = resolve_node(graph, node_id)
        if found is None:
            return {"error": f"no node matching {node_id!r}"}
        resolved_id, node = found
        source_file = node.get("source_file")
        if not source_file:
            return {"error": "node has no source file", "node": resolved_id}
        result = read_material(pack, source_file, node.get("source_location"), before, after)
        result["node"] = resolved_id
        return result

    @mcp.tool()
    def neighbors(node_id: str, relation_filter: str = "", token_budget: int = 1500) -> str:
        """List what a node directly connects to: callers, imports, types, references.

        Use this to learn how something is wired up before changing or relying on
        it. Set relation_filter to one relation name to narrow a large result.
        """
        graph = handle.get()
        found = resolve_node(graph, node_id)
        if found is None:
            return f"no node matching {node_id!r}"
        resolved_id, node = found
        wanted = relation_filter.lower()
        lines = [f"Neighbors of {sanitize_label(node.get('label', resolved_id))}:"]
        for arrow, others, order in (
            ("-->", graph.successors(resolved_id), lambda nb: (resolved_id, nb)),
            ("<--", graph.predecessors(resolved_id), lambda nb: (nb, resolved_id)),
        ):
            for neighbor in others:
                edge = edge_data(graph, *order(neighbor))
                relation = str(edge.get("relation", ""))
                if wanted and wanted not in relation.lower():
                    continue
                site = str(edge.get("source_location") or "")
                at = (
                    f" at={sanitize_label(str(edge.get('source_file') or ''))}:{sanitize_label(site)}"
                    if site
                    else ""
                )
                lines.append(
                    f"  {arrow} {sanitize_label(graph.nodes[neighbor].get('label', neighbor))} "
                    f"[{sanitize_label(relation)}] "
                    f"[{sanitize_label(str(edge.get('confidence', '')))}]{at}"
                )
        return _g._cut_lines_to_budget(lines, token_budget, "Narrow with relation_filter")

    @mcp.tool()
    def corpus_info() -> dict:
        """Report what this expert covers: size, source composition, last reconciled.

        Use it to orient before deep questions, or to judge how current the corpus is.
        """
        graph = handle.get()
        return {
            "expert": name,
            "title": data.get("title") or name,
            "nodes": graph.number_of_nodes(),
            "edges": graph.number_of_edges(),
            "sources": sources_by_kind(data),
            "last_reconciled": (data.get("graph") or {}).get("last_reconciled"),
        }

    return mcp


def serve(pack: Path) -> None:
    """Preflight, then hand the process to the MCP stdio transport."""
    from .manifest import load

    preflight(pack)
    data = load(pack)
    # graphify's import-time and wiring chatter would land on stdout and corrupt
    # the JSON-RPC framing. Only FastMCP itself may own stdout.
    with contextlib.redirect_stdout(sys.stderr):
        server = build_server(pack, data)
    server.run(transport="stdio")
