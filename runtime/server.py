"""Generic expert MCP server: one compiled graph, served over stdio or HTTP.

Configured entirely by environment so a single image serves any expert:
  EXPERT_NAME   display name
  EXPERT_GRAPH  path to graph.json
  EXPERT_REPO   path to the source checkout the graph was built from
  EXPERT_PORT   HTTP port (default 8800)
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import cast

import networkx as nx
from graphify import serve as _g
from graphify.build import edge_data
from graphify.security import sanitize_label
from mcp.server.fastmcp import FastMCP

NAME = os.environ.get("EXPERT_NAME", "expert")
GRAPH_PATH = Path(os.environ["EXPERT_GRAPH"])
REPO_ROOT = Path(os.environ["EXPERT_REPO"]).resolve()
PORT = int(os.environ.get("EXPERT_PORT", "8800"))

MAX_LINES = 400


class GraphHandle:
    """Holds the loaded graph, reloading when graph.json changes on disk.

    The maintainer rewrites graph.json out from under a running server, so the
    stamp is rechecked per call rather than loaded once at startup.
    """

    def __init__(self, path: Path):
        self._path = path
        self._stamp: tuple[int, int] | None = None
        self._graph: nx.DiGraph | None = None

    def get(self) -> nx.DiGraph:
        st = self._path.stat()
        stamp = (st.st_mtime_ns, st.st_size)
        graph = self._graph
        if graph is None or stamp != self._stamp:
            # _load_graph is annotated -> nx.Graph but returns a DiGraph; the
            # directed successors/predecessors split below depends on that.
            graph = cast(nx.DiGraph, _g._load_graph(str(self._path)))
            self._graph, self._stamp = graph, stamp
        return graph


HANDLE = GraphHandle(GRAPH_PATH)


def read_build_commit() -> str | None:
    # A top-level graph.json key that networkx's node_link_graph drops, written
    # near the end of a file too large to reparse just for one field.
    with GRAPH_PATH.open("rb") as handle:
        handle.seek(0, os.SEEK_END)
        tail_start = max(0, handle.tell() - 4096)
        handle.seek(tail_start)
        tail = handle.read().decode("utf-8", errors="replace")
    key = '"built_at_commit"'
    if key not in tail:
        return None
    return tail.rsplit(key, 1)[1].strip().lstrip(":").strip().strip('",}\n ') or None


def resolve_node(graph, ref: str) -> tuple[str, dict] | None:
    data = graph.nodes.get(ref)
    if data is not None:
        return ref, data
    for hit in _g._find_node(graph, ref):
        return hit, graph.nodes[hit]
    return None


def read_lines(rel_path: str, location: str | None, before: int, after: int) -> dict:
    target = (REPO_ROOT / rel_path).resolve()
    if not target.is_relative_to(REPO_ROOT):
        return {"error": "path escapes the repository root"}
    if not target.is_file():
        return {"error": f"not present in the checkout: {rel_path}"}

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


mcp = FastMCP(NAME, host="0.0.0.0", port=PORT, json_response=True, stateless_http=True)


@mcp.tool()
def search(question: str, mode: str = "bfs", depth: int = 3, token_budget: int = 2000) -> str:
    """Find symbols and relationships in this library's knowledge graph.

    Returns matching nodes with their source file and line, plus the edges
    between them. Use bfs for broad context and dfs to trace one chain. Ask with
    exact symbol or module names. Node ids in the result feed read_source.
    """
    return _g._query_graph_text(
        HANDLE.get(), question, mode=mode, depth=depth, token_budget=token_budget
    )


@mcp.tool()
def read_source(node_id: str, before: int = 5, after: int = 60) -> dict:
    """Read the real source text behind a graph node.

    The graph stores only structure, so use this to see actual implementation,
    signatures, or documented examples. Pass a node id from search; a plain
    symbol name is fuzzy-matched and may resolve elsewhere.
    """
    graph = HANDLE.get()
    found = resolve_node(graph, node_id)
    if found is None:
        return {"error": f"no node matching {node_id!r}"}
    resolved_id, data = found
    source_file = data.get("source_file")
    if not source_file:
        return {"error": "node has no source file", "node": resolved_id}
    result = read_lines(source_file, data.get("source_location"), before, after)
    result["node"] = resolved_id
    return result


@mcp.tool()
def neighbors(node_id: str, relation_filter: str = "", token_budget: int = 1500) -> str:
    """List what a symbol directly connects to: callers, imports, types, methods.

    Use this to learn how a symbol is wired up before changing or relying on it.
    Set relation_filter to one relation name to narrow a large result.
    """
    graph = HANDLE.get()
    found = resolve_node(graph, node_id)
    if found is None:
        return f"no node matching {node_id!r}"
    resolved_id, data = found
    wanted = relation_filter.lower()
    lines = [f"Neighbors of {sanitize_label(data.get('label', resolved_id))}:"]
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
                f"[{sanitize_label(relation)}] [{sanitize_label(str(edge.get('confidence', '')))}]{at}"
            )
    return _g._cut_lines_to_budget(lines, token_budget, "Narrow with relation_filter")


@mcp.tool()
def corpus_info() -> dict:
    """Report what this expert covers: size, extraction confidence, build commit.

    Use it to orient before deep questions, or to check how current the graph is.
    """
    graph = HANDLE.get()
    return {
        "expert": NAME,
        "nodes": graph.number_of_nodes(),
        "edges": graph.number_of_edges(),
        "built_at_commit": read_build_commit(),
        "repo_root": str(REPO_ROOT),
    }


if __name__ == "__main__":
    transport = os.environ.get("EXPERT_TRANSPORT", "streamable-http")
    mcp.run(transport="stdio" if transport == "stdio" else "streamable-http")
