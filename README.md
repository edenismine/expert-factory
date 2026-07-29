# expert-factory

Compiles a repository into an **expert**: a knowledge graph of its source, an HTTP
MCP server that answers questions against that graph, and a skill that teaches
agents how to use it. The server runs independently of this repo's tooling — any
project on the machine can point an MCP client at it.

## Build an expert

```bash
./compile.py build https://github.com/effect-ts/effect --title "Effect TS"
./compile.py build ~/src/some-repo --name myrepo
./compile.py list
docker compose up -d
```

Each build produces `experts/<name>/`:

| Path | Contents |
|---|---|
| `repo/` | Pristine clone, mounted read-only into the container |
| `graph/` | `graph.json` + `GRAPH_REPORT.md`, kept **outside** the checkout |
| `expert.json` | Name, port, URL, build commit, node/edge counts |
| `SKILL.md` | Generated skill teaching agents the served tools |

The graph lives beside the clone rather than inside it (via `GRAPHIFY_OUT`), so
`git status` in `repo/` stays clean and the maintainer can always fast-forward.

Extraction defaults to `--code-only` (AST, no API cost). `--deep` adds the
semantic pass, which spends LLM tokens. `--reuse-graph` adopts an existing
`graphify-out/` next to the source instead of extracting again.

## Consume an expert

Add to a consuming project's `.mcp.json`, then copy its `SKILL.md` to
`~/.claude/skills/<name>-expert/SKILL.md` (or the project's `.claude/skills/`):

```json
{
  "mcpServers": {
    "effect-expert": { "type": "http", "url": "http://127.0.0.1:8801/mcp" }
  }
}
```

Tools: `search` (graph traversal), `read_source` (real file text — the graph
stores structure only), `neighbors` (callers, imports, methods), `corpus_info`
(coverage and build commit).

## Keep it fresh

```bash
./maintain.sh status                  # what each expert serves vs upstream
./maintain.sh refresh                 # pull + AST-only graph update, all experts
./maintain.sh refresh effect --deep   # full semantic re-extraction
```

The maintainer runs on the host, where the full graphify toolchain lives; the
containers only serve. It aborts rather than discarding local changes in a
checkout, calls `./compile.py sync <name>` to refresh the counts and commit baked
into `SKILL.md`, and restarts the affected container.

Staleness is tracked in `graph/synced_at` rather than the graph's own
`built_at_commit`: graphify leaves outputs untouched when a pull changes no
topology, so that stamp can legitimately trail HEAD.

## Layout

- `compile.py` — the compiler; also regenerates `docker-compose.yml`
- `maintain.sh` — pull upstream, rebuild graphs, restart servers
- `runtime/` — one image shared by every expert; `server.py` is configured
  entirely through `EXPERT_*` environment variables
