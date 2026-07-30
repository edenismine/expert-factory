# expert-factory

`ef` builds a queryable **expert** out of a pack of material — cloned repos,
fetched pages, papers, and your own notes — and serves it to an agent as one
knowledge graph over stdio MCP, plus a skill that teaches the agent to use it.

```bash
uv tool install .          # or: pipx install .
```

One install carries the whole toolchain: `ef` imports graphify as a library, so
there is no separate binary, interpreter, or container to line up.

## Build a pack

Packs live in `./experts/<name>`, resolved from the **current directory** — so a
workspace is just a directory you `cd` into, and `ef` never searches upward.

```bash
ef clone research https://github.com/effect-ts/effect --title "Effect TS"
ef clone research https://github.com/some/monorepo --paths content/docs
ef add research https://arxiv.org/pdf/2501.12345
ef add research ~/Downloads/notes-on-fibers.md
ef build research
```

`ef build` extracts everything in the pack into a single graph and writes the
skill. Semantic extraction is the default and spends LLM tokens; `--code-only`
takes the cheap AST-only path and drops docs, papers and images from the
semantic pass. `--backend` is required only when an LLM is actually invoked.

Each pack holds four content layers plus its graph and metadata:

| Path | Contents |
|---|---|
| `repos/<owner>/<repo>/` | Pristine clones, fast-forwarded by `ef update` |
| `raw/` | Fetched pages, papers and images, with provenance frontmatter |
| `notes/` | Markdown you wrote yourself |
| `graph/` | `graph.json`, `GRAPH_REPORT.md`, and `converted/` PDF text sidecars |
| `expert.json` | The authoritative source list: origin, lifecycle, checksums |
| `SKILL.md` | Generated skill teaching agents the served tools |

The graph sits at `graph/` rather than inside a clone, so `git status` in a
checkout stays clean and every clone can always fast-forward.

`expert.json` is authoritative, not a cache: every file in `raw/` and `notes/`
needs an entry. `ef build` refuses on files with no recorded origin (listing
them, and suggesting `--adopt-all`) and on entries whose file is gone, because a
graph that misreports its own coverage is worse than one that fails to build.

Extraction deliberately ignores VCS ignore files. A pack holds material that is
meant to stay uncommitted, so any sane workspace gitignores `repos/` and
`graph/` — and since the extractor walks up to the VCS root, honoring those
rules would let the line that keeps a pack out of git silently empty its corpus.
The pack's generated `.graphifyignore` still applies, and it restates the
credential patterns (`.env`, `*.pem`, `id_rsa`, …) that the clone's own
`.gitignore` would otherwise have covered, so a stray secret is never sent to an
LLM.

## Serve a pack

`ef run` is a plain stdio process — no container, port, image, or daemon. It
writes nothing and validates the pack before the MCP handshake, so a wrong `cwd`
fails with a readable message instead of a dead transport.

```json
{
  "mcpServers": {
    "research expert": {
      "command": "ef",
      "args": ["run"],
      "cwd": "/abs/path/to/experts/research"
    }
  }
}
```

The pack is addressed by `cwd`, so moving or copying it only changes that one
line. Copy its `SKILL.md` to `~/.claude/skills/<name>-expert/SKILL.md` (or the
consuming project's `.claude/skills/`).

Tools: `search` (graph traversal), `read_source` (real text behind a node —
code, a fetched page, a paper, or a note), `neighbors` (callers, imports,
references), `corpus_info` (size, source composition, last reconciled).

## Keep it fresh

```bash
ef update research    # pull every refreshable source, then refresh the graph
ef sync research      # rewrite manifest and skill from the graph on disk
ef list               # every pack: nodes, size, last reconciled, composition
```

`ef update` fast-forwards each git source (refusing rather than discarding local
modifications), then picks a refresh path and prints which one and why:

- **noop** — nothing changed upstream.
- **ast** — only code changed. Cheap, no LLM.
- **semantic** — a doc, paper or image changed. graphify's AST-only update
  deliberately *preserves* existing semantic nodes, so a doc change has to force
  the expensive path or the graph keeps describing text that is no longer there.

Fetched pages and papers are snapshots with no refresh lifecycle; a changed
checksum is reported as information, not as a broken pack.

## Layout

- `src/ef/` — `workspace` (cwd-based pack resolution), `manifest`, `scoping`,
  `sources`, `extraction`, `skill`, `server`, `cli`
- `tests/` — pytest against real entry points and emitted artifacts; no test
  spends an LLM token
