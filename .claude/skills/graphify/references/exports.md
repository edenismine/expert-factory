# graphify reference: extra exports and benchmark

Load this when the user passed one of the export flags (`--wiki`, `--neo4j`, `--neo4j-push`, `--falkordb`, `--falkordb-push`, `--svg`, `--graphml`, `--mcp`), or when the corpus is large enough for the token-reduction benchmark. Each step runs only for its own flag.

### Step 6b - Wiki (only if --wiki flag)

**Only run this step if `--wiki` was explicitly given in the original command.**

Run this before Step 9 (cleanup) so `.graphify_labels.json` is still available.

```bash
graphify export wiki
```

### Step 7 - Neo4j export (only if --neo4j or --neo4j-push flag)

**If `--neo4j`** - generate a Cypher file for manual import:

```bash
graphify export neo4j
```

**If `--neo4j-push <uri>`** - push directly to a running Neo4j instance. Ask the user for credentials if not provided:

```bash
graphify export neo4j --push bolt://localhost:7687 --user neo4j --password PASSWORD
```

Default URI is `bolt://localhost:7687`, default user is `neo4j`. Uses MERGE - safe to re-run without creating duplicates.

### Step 7a - FalkorDB export (only if --falkordb or --falkordb-push flag)

**If `--falkordb`** - generate a Cypher file. The statements are OpenCypher, but FalkorDB's `GRAPH.QUERY` runs one statement at a time (no bulk script import like Neo4j's `cypher-shell`), so prefer `--falkordb-push` to load a graph. Use this only when you want the portable `cypher.txt` artifact:

```bash
graphify export falkordb
```

**If `--falkordb-push <uri>`** - push directly to a running FalkorDB instance. Credentials are optional; ask the user only if the instance requires auth:

```bash
graphify export falkordb --push falkordb://localhost:6379
```

Default URI is `falkordb://localhost:6379` (the scheme is informational - `redis://` or a bare `host:port` work too), auth is optional, and the target graph defaults to `graphify`. Uses MERGE - safe to re-run without creating duplicates.

### Step 7b - SVG export (only if --svg flag)

```bash
graphify export svg
```

### Step 7c - GraphML export (only if --graphml flag)

```bash
graphify export graphml
```

### Step 7d - MCP server (only if --mcp flag)

```bash
$(cat graphify-out/.graphify_python) -m graphify.serve graphify-out/graph.json
```

This starts a stdio MCP server that exposes tools: `query_graph`, `get_node`, `get_neighbors`, `get_community`, `god_nodes`, `graph_stats`, `shortest_path`. Add to Claude Desktop or any MCP-compatible agent orchestrator so other agents can query the graph live.

**Picking the interpreter.** MCP clients can't run `$(...)`, and the system `python3` usually can't import graphify — so `command` must be an absolute interpreter path. `graphify-out/.graphify_python` is *not* reliable here: it can point at a bare `uv` cache interpreter that imports `graphify` but **not** `mcp`, so the server dies with `ModuleNotFoundError: No module named 'mcp'`. Prefer the interpreter that actually runs the installed CLI, and verify before wiring it up:

```bash
PY=$(head -1 "$(command -v graphify)" | sed 's/^#!//')
"$PY" -c "import graphify, mcp; print('OK')"   # must print OK
```

If that fails, install the extra: `pip install "graphifyy[mcp]"`. For a versioned install dir, prefer a stable `latest`-style symlink over a pinned version number so the config survives upgrades.

```json
{
  "mcpServers": {
    "graphify": {
      "command": "<absolute interpreter path verified above>",
      "args": ["-m", "graphify.serve", "/absolute/path/to/graphify-out/graph.json"]
    }
  }
}
```

**Serving several graphs from one server.** Every tool takes an optional `project_path` (an absolute path to a directory containing `graphify-out/graph.json`) that selects the graph for that call, with each graph cached and hot-reloaded on `(mtime, size)` change. Omit the positional graph argument entirely to run as a pure multi-project server: it starts with no default graph and each call picks its own target.

```json
{ "mcpServers": { "graphify": { "command": "<interpreter>", "args": ["-m", "graphify.serve"] } } }
```

Note `project_path` takes a *project directory*, not a graph file — a graph with a non-default name (e.g. `merged-graph.json`) can only be reached via the startup argument.

**HTTP transport.** `--transport http` serves Streamable HTTP instead of stdio: `--host` (default `127.0.0.1`), `--port` (8080), `--path` (`/mcp`), `--json-response`, `--stateless`, `--session-timeout`. Require a key with `--api-key` / `GRAPHIFY_API_KEY`; keep the bind on loopback unless a key is set.

### Step 8 - Token reduction benchmark (only if total_words > 5000)

If `total_words` from `graphify-out/.graphify_detect.json` is greater than 5,000, run:

```bash
graphify benchmark
```

Print the output directly in chat. If `total_words <= 5000`, skip silently - the graph value is structural clarity, not token compression, for small corpora.
