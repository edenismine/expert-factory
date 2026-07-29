"""Generate SKILL.md from graph facts and the manifest."""

from __future__ import annotations

from pathlib import Path

from .manifest import sources_by_kind
from .workspace import SKILL_NAME

TEMPLATE = """---
name: {name}-expert
description: "{description}"
---

# {title} expert

Answers about {title} are grounded in a knowledge graph over this expert's corpus
({nodes:,} nodes, {edges:,} edges), served by an MCP server over stdio. Ground every
non-trivial claim in that server rather than in recollection, and keep the mechanism
out of user-facing prose.

{freshness}

## Tools

- `search` — find symbols, documents and how they relate. Name exact symbols,
  modules or titles and say which relationship matters. `bfs` for surrounding
  context, `dfs` to trace one chain. Start at `depth` 2-3 and a `token_budget`
  near 2000.
- `read_source` — the actual text behind a node, whether that is source code, a
  fetched page, a paper, or a note. The graph carries only structure, so read the
  material before describing behaviour, a signature, or what a document argues.
- `neighbors` — direct callers, imports, types, methods, and references of one
  node. Use `relation_filter` when a result is large.
- `corpus_info` — what this corpus holds and when it was last reconciled. Useful
  for orientation and for judging staleness.

## Working method

1. `search` for the exact symbol, title or relationship in question.
2. `read_source` on the most relevant hit before asserting what it says or does.
3. `neighbors` when the question is about wiring, dependencies, or blast radius.

Pass `read_source` the `node` id from a `search` result, not a bare name: names
repeat across a large corpus, and a fuzzy match on a common one silently returns a
different definition. Check the `file` in the response against the source you meant,
and re-read with a wider `after` when `truncated` is true. On a PDF-backed node the
line arguments do not apply — the response says so rather than returning a
misleading window.

Treat `EXTRACTED` edges as direct source evidence and `INFERRED` edges as leads
needing corroboration. Assert only relationships the tools actually returned, and
cite the file and line they came with.

## Scope

Prominent areas in this corpus: {hub_list}.
Indexed file types: {ext_list}.

When a consuming project has its own copy of something this corpus describes, that
copy and its type checker win — the graph may describe a different revision. Say so
when a version difference could matter.

If the server is unreachable, say the expert is unavailable and fall back to the
consuming project's own sources instead of guessing.
"""

#: Plural labels for the aggregate freshness line, in a stable reading order.
KIND_LABELS = (
    ("code", "git"),
    ("document", "docs"),
    ("paper", "papers"),
    ("note", "notes"),
    ("image", "images"),
)


def freshness_line(data: dict) -> str:
    """One aggregate line covering all sources, never a per-source table.

    A table grows without bound as a pack grows, and a skill competes for the
    context budget it is trying to save.
    """
    counts = sources_by_kind(data)
    total = sum(counts.values())
    parts = [f"{counts[kind]} {label}" for kind, label in KIND_LABELS if counts.get(kind)]
    composition = f" ({', '.join(parts)})" if parts else ""
    reconciled = (data.get("graph") or {}).get("last_reconciled") or "unknown"
    return (
        f"Built from {total} source{'s' if total != 1 else ''}{composition}, "
        f"last reconciled {reconciled[:10]}."
    )


def render(data: dict, facts: dict) -> str:
    title = data.get("title") or data["name"]
    return TEMPLATE.format(
        name=data["name"],
        title=title,
        description=(
            f"{title} questions, implementation, debugging, and review, grounded in a "
            f"knowledge graph of the {title} corpus. Use when the task involves "
            f"{title} APIs, internals, idioms, or the material collected about it."
        ),
        freshness=freshness_line(data),
        nodes=facts["nodes"],
        edges=facts["edges"],
        hub_list=", ".join(facts["hubs"][:10]) or "n/a",
        ext_list=", ".join(facts["extensions"]) or "n/a",
    )


def write(pack: Path, data: dict, facts: dict) -> Path:
    target = pack / SKILL_NAME
    target.write_text(render(data, facts), encoding="utf-8")
    return target
