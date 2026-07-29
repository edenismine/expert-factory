## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).

### External repo graphs (direct, no global graph)

Graphs of other repos are read by pointing `--graph` at their `graph.json` directly. Nothing needs to
be registered or merged first — a graph is just a file.

Available graphs:

| Topic | Repo dir (for MCP `project_path`) | Graph path (for `--graph`) |
|---|---|---|
| graphify itself (CLI flags, internals, skill behavior) | `~/.graphify/repos/Graphify-Labs/graphify` | `<repo dir>/graphify-out/graph.json` |
| Effect TS (`effect`, `@effect/*` source) | `~/.graphify/repos/effect-ts/effect` | `<repo dir>/graphify-out/graph.json` |

```
graphify query "<question>" --graph ~/.graphify/repos/Graphify-Labs/graphify/graphify-out/graph.json
```

Notes:
- `query`, `path`, `explain`, `affected`, `god-nodes`, and `tree` all take `--graph`. It defaults to
  `graphify-out/graph.json` in the cwd, so this project's own graph needs no flag.
- There is no env var or config file for the default graph path — `--graph` must be explicit.
- `GRAPH_REPORT.md` and `wiki/` sit next to the graph and can be read directly for broad navigation.
- Clone more repos with `graphify clone <github-url>` (lands in `~/.graphify/repos/<owner>/<repo>`),
  graph them once, then add a row above. Do not re-graph a repo that already has `graphify-out/`.
- Ignore `graphify global ...` and `merge-graphs` for this: they build a separate combined graph and
  are only worth it when you need one namespace spanning several repos at once.

### MCP server

`.mcp.json` registers a `graphify` MCP server with **no default graph**, so every tool call selects its
target with `project_path` (the repo dir column above). Tools: `query_graph`, `get_node`,
`get_neighbors`, `get_community`, `god_nodes`, `graph_stats`, `shortest_path`. The CLI with `--graph` and
the MCP tools read the same files — use whichever fits; MCP avoids re-reading a 23 MB graph per shell-out.

The `command` is the mise pipx interpreter, because the system `python3` and the `.graphify_python`
interpreter cannot both import `graphify` and `mcp`. It points at the `latest` symlink so graphify
upgrades don't break it. Verify with:
`"$(head -1 "$(command -v graphify)" | sed 's/^#!//')" -c "import graphify, mcp"`.

Adding a graph is a clone + one-time extract; no config change is needed, just a new table row:
`graphify clone <url>` then graph it, then call tools with that repo dir as `project_path`.
