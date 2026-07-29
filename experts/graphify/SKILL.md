---
name: graphify-expert
description: "graphify questions, implementation, debugging, and review, grounded in a knowledge graph of the graphify source tree. Use when the task involves graphify APIs, internals, or idioms."
---

# graphify expert

Answers about graphify are grounded in a knowledge graph built from its source at
commit `0b2bd93` (12,399 nodes, 22,179 edges), served by the
`graphify-expert` MCP server over HTTP at `http://127.0.0.1:8802/mcp`. Ground every non-trivial claim in that
server rather than in recollection, and keep the mechanism out of user-facing prose.

## Tools

Exposed as `mcp__graphify-expert__<tool>`:

- `search` — find symbols and how they relate. Name exact symbols or modules and
  say which relationship matters. `bfs` for surrounding context, `dfs` to trace
  one chain. Start at `depth` 2-3 and a `token_budget` near 2000.
- `read_source` — the actual source text behind a node. The graph carries only
  structure, so read the code before describing behaviour or a signature.
- `neighbors` — direct callers, imports, types, and methods of one symbol. Use
  `relation_filter` when a result is large.
- `corpus_info` — coverage and build commit. Useful for orientation and for
  judging staleness.

## Working method

1. `search` for the exact symbol or relationship in question.
2. `read_source` on the most relevant hit before asserting how it behaves.
3. `neighbors` when the question is about wiring, dependencies, or blast radius.

Pass `read_source` the `node` id from a `search` result, not a bare symbol name:
names repeat across a large tree, and a fuzzy match on a common one silently
returns a different definition. Check the `file` in the response against the
`src=` you meant, and re-read with a wider `after` when `truncated` is true.

Treat `EXTRACTED` edges as direct source evidence and `INFERRED` edges as leads
needing corroboration. Assert only relationships the tools actually returned, and
cite the file and line they came with.

## Scope

Prominent areas in this corpus: extract.py, extract(), test_languages.py, test_detect.py, test_extract.py, Changelog, manifest.json, build_from_json(), test_serve.py, cli.py.
Indexed file types: py, md, json, xaml, pas, php.

The graph reflects one commit. When a consuming project has its own copy of this
dependency, that copy and its type checker win — the graph may describe a
different revision. Say so when a version difference could matter.

If `graphify-expert` is unreachable, say the expert is unavailable and fall back to the
consuming project's installed source instead of guessing.
