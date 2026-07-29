# `ef` — expert-factory as an installable CLI over multi-source packs

## Problem Statement

I can raise an expert from a GitHub repo, and that works well — the Effect TS and
graphify experts both answer real questions against real graphs. But the tool only
knows one kind of knowledge: a git checkout of source code.

Most of what I actually want an expert to know is not in a repo I can clone. It is
a paper I read, a docs site whose markdown I want indexed without the app code
around it, an article I fetched before it rotted, and — most of all — the research
notes an agent wrote after digging through something for an hour. Today all of that
either goes nowhere or gets pasted into a CLAUDE.md that competes for context
budget and never gets queried. There is no way to say "here is a pile of typed
material about one topic; make it queryable."

The tool is also welded to its own output. `experts/` resolves from the script's own
location, the generated compose file builds an image from a path inside the tool's
source tree, and the volume mounts are relative to the tool's root. So the experts I
build live *inside* the tool's git repo. I cannot install the tool once and keep my
experts somewhere else, I cannot have a work workspace and a personal workspace, and
I cannot update the tool without touching the directory holding my graphs.

And serving is heavier than the thing being served. An expert is one graph file read
by one agent on this machine, and reaching it today costs an image build, a compose
file, a long-running container, and a port that has to be allocated, recorded, and
kept unique — so two workspaces on one machine would both hand out 8801 and the second
container would lose the race at start. Every MCP client I use can already launch a
local process and speak to it over stdio; that is exactly what `command`, `args`, and
`cwd` in a client config are for.

And the defaults are wrong for the material I care about. Extraction defaults to
`--code-only`, which is exactly the flag that discards every doc, paper, and image
from the semantic pass. Building a pack of papers with today's defaults would produce
a near-empty graph and no error. Meanwhile the generated SKILL.md tells the agent the
graph "reflects one commit" and names a single git SHA — a sentence that is simply
false about a pack of twelve papers and three notes.

## Solution

expert-factory becomes `ef`, a CLI installed once with pipx or uv. Experts become its
output rather than part of it: `experts/` resolves from the current working directory,
the same way `git` and `docker` are global tools that operate on a local workspace.
This repo keeps only the tool.

An expert becomes a **pack**: one directory, one graph, over a list of typed sources.
Inside a workspace:

```
experts/<name>/
  repos/<owner>/<repo>/     git clones — refreshable via git pull
  raw/                      immutable fetched material (md, pdf, images)
  notes/                    agent- or human-authored prose
  graph/                    GRAPHIFY_OUT; self-excludes from the scan
    converted/              PDF text sidecars, persisted at build
  expert.json               the manifest
  SKILL.md
```

Today's repo-experts are the single-git-source case of that shape. What is served is
still one graph behind one MCP server with one generated skill — but the server is now
a process, not a container.

`ef run` is that server. Run inside a pack directory it serves that pack over stdio,
the way `npm start` runs the project whose `package.json` is in the cwd. An MCP client
launches it with nothing more than:

```json
{
  "effect expert": {
    "command": "ef",
    "args": ["run"],
    "cwd": "~/projects/experts/effect"
  }
}
```

No image, no compose file, no daemon, no port. The pack directory is the unit of
identity — a valid pack is any directory with an `expert.json` and a graph, so an
expert is copyable, and serving one is the client's business rather than an
always-running cost.

I fill a pack with three verbs. `ef clone <name> <url>` puts a git source under
`repos/<owner>/<repo>/`. `ef add <name> <url>` fetches a page, paper, or image into
`raw/`, keeping the provenance frontmatter the fetch already writes. Agents put their
own research into `notes/` directly — no CLI verb, no orchestration; the next build
picks the files up. Then `ef build <name>` extracts the whole pack into one graph, writes
the manifest and the skill, and prints the client-config snippet that mounts it.

Semantic extraction becomes the default, because a prose pack is the point;
`--code-only` becomes the explicit cheap path for a code-only pack. `ef update <name>`
pulls each git source and then chooses its refresh path from what actually changed:
the free AST update when only code moved, a semantic re-extract when docs did — and
it says which it picked and why.

The manifest is authoritative. Every file in the pack has an entry, and `ef build`
refuses to build when it finds one that does not, listing the strays. That friction is
the feature: a graph that built is a graph whose every node traces to a recorded
origin.

## User Stories

1. As a developer, I want to install `ef` once with pipx or uv, so that I do not have
   to clone expert-factory to use it.
2. As a developer, I want `ef` to resolve `experts/` from my current working
   directory, so that the tool is global and my knowledge is local, the way git and
   docker already work.
3. As a developer, I want to keep expert-factory's own repo free of built experts, so
   that upgrading the tool never touches my graphs and my graphs never bloat its
   history.
4. As a developer, I want to keep a work workspace and a personal workspace on the
   same machine, so that client material and personal research never share a
   directory.
5. As a developer, I want `ef` to import graphify as a library rather than shelling
   out to a `graphify` binary on PATH, so that I stop hitting the interpreter split
   where one Python can import `graphify` and another can import `mcp`.
6. As a developer, I want `graphifyy[all]` to be a hard dependency of `ef`, so that a
   single install brings the entire extraction toolchain and I never get a
   "graphify not on PATH" failure halfway through a build.
7. As a researcher, I want an expert whose corpus is a pile of papers rather than a
   repo, so that I can ask questions about a body of literature the same way I ask
   about a library.
8. As a researcher, I want one pack to mix code, docs, papers, notes, and images, so
   that a question can be answered from whichever kind of material actually holds the
   answer.
9. As a developer, I want my existing single-repo experts to be nothing more than the
   one-git-source case of a pack, so that I learn one model rather than two.
10. As a developer, I want `ef clone <name> <url>` to place a clone at
    `repos/<owner>/<repo>/`, so that a pack can hold several git sources without
    their names colliding.
11. As a developer, I want `ef add <name> <url>` to fetch an article or paper into
    `raw/`, so that I capture material before it link-rots.
12. As a researcher, I want the YAML provenance frontmatter written at fetch time —
    `source_url`, `type`, `title`, `captured_at`, `contributor` — to survive into the
    pack unmodified, so that a graph node can always be traced back to the page it
    came from.
13. As a developer, I want `ef add <name> <path>` to adopt a local file or directory
    into the pack, so that material I already have on disk joins a pack without a
    round trip through a URL.
14. As a developer, I want `ef add` to place adopted material in `raw/` or `notes/`
    according to its kind, so that the fetched-versus-authored distinction stays
    visible in the directory layout.
15. As an agent, I want to write my research findings straight into `notes/` as
    markdown, so that I contribute to a pack with the file tools I already have and no
    special protocol.
16. As a developer, I want `ef add` never to invoke a research agent, so that fetching
    stays a cheap, predictable, non-LLM operation.
17. As a developer, I want `ef build <name>` to extract the entire pack into one
    graph, so that a note about a library and the library's own source can be
    connected by a single query.
18. As a developer, I want semantic extraction to be the default on build, so that a
    prose pack is not silently reduced to a handful of file nodes and link edges.
19. As a developer, I want `--code-only` to remain available as an explicit flag, so
    that a purely code pack still costs nothing to index.
20. As a developer, I want `ef` to explain why `--code-only` is wrong for a pack that
    contains docs or papers, so that I understand the cost/coverage tradeoff at the
    moment I am choosing.
21. As a developer, I want `--backend` to be required only when an LLM is actually
    going to be called, so that cheap paths — `--code-only` builds and AST-only
    updates — need no credentials at all.
22. As a developer, I want the backend I chose to be remembered in the manifest, so
    that later semantic runs on the same pack do not silently switch models or fail
    for want of a flag.
23. As a developer, I want an explicit `--backend` on the command line to override the
    remembered one, so that I can move a pack to a different model without editing
    the manifest.
24. As a developer, I want `ef` to tell me that `claude-cli` must be named explicitly
    because it is deliberately excluded from graphify's backend auto-detection, so
    that I can deliberately choose the backend billed to my subscription instead of a
    metered API key.
25. As a developer, I want `ef update <name>` to pull every git source in the pack, so
    that refreshing a multi-repo pack is one command.
26. As a developer, I want `ef update` to run the free AST-only graph update when a
    pull changed only code, so that routine upkeep costs nothing.
27. As a developer, I want `ef update` to run a semantic re-extract when a pull
    changed docs or papers, so that I do not end up serving doc nodes that describe
    text no longer in the tree — the AST-only path deliberately preserves existing
    semantic nodes rather than regenerating them.
28. As a developer, I want `ef update` to print which path it took and what changed to
    make it choose that, so that an unexpected LLM bill is never a surprise.
29. As a developer, I want `ef update` to leave fetched pages and papers alone, so
    that a snapshot stays a snapshot and my corpus does not shift under me.
30. As a developer, I want `ef update` to refuse to refresh a git source with local
    modifications, so that work I forgot about in a clone is never discarded.
31. As a developer, I want `ef list` to show every pack in the workspace with its size
    and freshness, so that I can see what I have without starting anything.
32. As a developer, I want `ef sync <name>` to rewrite the manifest and skill from the
    graph already on disk, so that counts and freshness can be corrected without
    re-extracting.
33. As a developer, I want every file in `raw/` and `notes/` to have a manifest entry,
    so that a built graph always carries complete provenance.
34. As a developer, I want `ef build` to refuse to build when it finds unmanifested
    files, listing them, so that material never enters a graph without a recorded
    origin.
35. As a developer, I want `--adopt-all` to accept all the strays in one shot, so that
    the friction of full provenance is one flag rather than one edit per file.
36. As a researcher, I want a git source's manifest entry to carry its ref, revision,
    and last-synced time, so that I can tell exactly which revision the graph
    describes.
37. As a researcher, I want a fetched source's manifest entry to carry a captured-at
    time and a checksum, so that I can detect if an immutable snapshot was altered
    after capture.
38. As a developer, I want a git source to be able to declare that only some paths
    inside the clone should be graphed, so that a docs site's repo contributes its
    docs folder and not its application code.
39. As a developer, I want all sources' path scopes compiled into one generated ignore
    file at the pack root, so that scoping is a single reviewable artifact rather than
    per-directory rules scattered through the pack.
40. As a developer, I want the generated ignore file to use gitignore negation
    semantics — exclude the clone, re-include the wanted subtree — so that it behaves
    exactly as the last-match-wins rules I already know.
41. As a developer, I want the generated ignore file to exclude the pack's own
    metadata — the manifest, the skill, and itself — so that the instructions
    describing the corpus never become part of the corpus.
42. As a developer, I want the graph directory to stay out of its own scan, so that a
    rebuild never ingests the previous build's output.
43. As a developer, I want the generated ignore file clearly marked as generated, so
    that I do not hand-edit something the next build overwrites.
44. As a developer, I want code, documents, PDF papers, authored notes, and images all
    accepted as source kinds, so that a pack covers the material I actually collect.
45. As a developer, I want `ef` to tell me when an image source needs a
    vision-capable backend, so that I find out before spending a build rather than
    after.
46. As a developer, I want `ef add` to reject video with a clear "not supported yet",
    so that a YouTube URL fails loudly instead of being silently dropped or half
    downloaded.
47. As a developer, I want `ef run` inside a pack directory to serve that pack, so that
    an MCP client needs only a command and a `cwd` to mount an expert.
48. As a developer, I want `ef run` to speak stdio, so that serving an expert costs a
    process my client already knows how to launch rather than an image, a daemon, and a
    port.
49. As a developer, I want no container, compose file, or port anywhere in the pipeline,
    so that a built pack is immediately usable and nothing has to be running for it to
    be.
50. As a developer, I want `ef run <name>` from a workspace root to serve
    `experts/<name>`, so that the pack I want is reachable without a `cd`.
51. As a developer, I want `ef run` to refuse a directory that is not a valid pack and
    say what is missing, so that a wrong `cwd` in a client config is diagnosable
    instead of a silent failed handshake.
52. As a developer, I want `ef run` to fail before the MCP handshake when the graph is
    absent, so that an unbuilt pack tells me to build it rather than serving an empty
    expert.
53. As a developer, I want `ef run` to write nothing to the pack, so that serving is
    read-only in practice and an expert can live on read-only media or be served by two
    clients at once.
54. As a developer, I want `ef run` to keep diagnostics off stdout, so that log output
    can never corrupt the stdio JSON-RPC stream.
55. As a developer, I want the server to take the pack root as its one filesystem
    anchor, so that the process's view matches the pack-relative paths the graph
    actually stores.
56. As an agent consuming an expert, I want `read_source` to resolve a path from any
    layer of the pack, so that I can read a note or a paper with the same tool I use to
    read source code.
57. As an agent consuming an expert, I want `read_source` on a PDF-backed node to
    return readable text, so that a paper is as citable as a source file.
58. As a developer, I want PDF text extracted once at build and persisted as a sidecar
    next to the graph, so that serving needs no PDF library and the extraction is not
    repeated per request — the underlying extractor does not cache.
59. As an agent consuming an expert, I want line-window arguments to be meaningless
    rather than misleading on PDF-backed nodes, so that I do not chase a char offset
    that has no model behind it.
60. As a developer, I want `read_source` to refuse any path that escapes the pack root,
    so that a crafted node id cannot read the host filesystem.
61. As a developer, I want `ef` to scaffold a `.gitignore` on first build in a
    workspace that has none, so that I get sensible tracking without thinking about
    it.
62. As a developer, I want the scaffolded ignore rules to exclude clones and graphs,
    so that I do not commit multi-megabyte reconstructible artifacts.
63. As a developer, I want the scaffolded rules to keep `raw/`, `notes/`, the manifest,
    and the skill tracked, so that fetched material that has since rotted and notes
    that are original work are actually backed up.
64. As a developer, I want `ef` never to overwrite a `.gitignore` I already have, so
    that scaffolding cannot clobber my own rules.
65. As an agent consuming an expert, I want the generated skill to state freshness as
    one aggregate line covering all sources, so that I am not told a multi-source pack
    "reflects one commit".
66. As an agent consuming an expert, I want that line to name how many sources of each
    kind the pack holds and when it was last reconciled, so that I can judge staleness
    without a second tool call.
67. As an agent consuming an expert, I want the skill to stay short and omit a
    per-source table, so that it does not eat the context budget it is competing for.
68. As an agent consuming an expert, I want the skill to keep telling me to ground
    claims in the server rather than recollection, so that the behavior that makes
    experts useful survives the rewrite.
69. As a developer, I want a build to report node and edge counts and the chosen
    extraction path, so that I can tell at a glance whether the build did what I
    intended.
70. As a developer, I want a build to print the client config snippet for the pack it
    just built, so that mounting a fresh expert is a copy-paste rather than a recall of
    the config shape.
71. As a developer, I want a build over a pack whose semantic material would produce an
    almost-empty graph to warn me, so that I catch a mis-scoped ignore rule before I
    start querying a hollow expert.
72. As a developer, I want `ef` to work on a pack that has only `notes/` and nothing
    else, so that an agent's accumulated research is a legitimate expert on its own.
73. As a developer, I want a clear error when I name a pack that does not exist, so
    that a typo does not silently create an empty one.
74. As a developer, I want `ef build` to be safely re-runnable, so that interrupting a
    build and running it again converges rather than corrupting the pack.

## Implementation Decisions

### Packaging and workspace resolution

- The project becomes an installable, importable package exposing a console script
  named `ef`. The `package = false` setting that currently makes it a flat collection
  of loose scripts is removed, and the module previously living as a top-level script
  becomes the CLI entry point of a real package.
- Workspace root resolution moves from "the directory containing the tool's source"
  to "the current working directory". A single resolution helper owns this so no other
  module derives paths from module location. Commands that operate on a pack fail with
  a clear message when no `experts/` directory exists in the cwd rather than creating
  one implicitly outside of `build`/`clone`/`add`.
- The same helper owns the two ways a pack is named, and every verb uses it:
  `<name>` resolves to `<cwd>/experts/<name>`, and an omitted name means "the cwd is
  itself the pack", valid only when `<cwd>/expert.json` exists. No upward search — a
  client config states an exact `cwd`, and walking up would let a stray parent manifest
  capture a subdirectory silently.
- `graphifyy[all]` becomes a hard runtime dependency. `ef` calls graphify's Python
  API — its detection, ingestion, extraction, and update entry points — instead of
  locating a `graphify` executable on PATH. This removes the interpreter split
  documented in this repo's own CLAUDE.md, where the system Python and graphify's
  bundled interpreter cannot both satisfy `import graphify` and `import mcp`.
- Serving moves into the same package and the same install. `runtime/server.py` becomes
  a module of the `ef` package, invoked by `ef run` rather than by a container
  entrypoint, and `runtime/Dockerfile` and `runtime/requirements.txt` are deleted. The
  serving dependencies were `graphify --no-deps` plus `mcp` and `networkx`; all three
  are already inside `graphifyy[all]`, so folding serving in adds no dependency. The
  separate `--no-deps` install existed only to keep the image small, and there is no
  longer an image. One install now covers both building and serving, which is also what
  makes the client config as short as it is: `command: "ef"` with no path, no wrapper
  script, and no interpreter selection.
- Building and serving stay strictly separated in behavior even though they now share an
  install. `ef run` never extracts, never fetches, and never writes; extraction happens
  only under `build`, `update`, and `sync`. A server that could rebuild would make an
  agent's read-only query capable of spending money.

### Modules

The single compiler script is decomposed into a small set of modules with a
one-direction dependency flow (CLI → orchestration → leaf helpers). No leaf module
imports the CLI.

- **CLI/dispatch** — subcommand parsing and human-readable reporting for `clone`,
  `add`, `build`, `update`, `list`, `sync`, `run`. Owns all output formatting; owns no
  filesystem logic. `run` is the one verb that writes nothing and reports nothing on
  stdout: it validates, then hands the process to the server module.
- **Workspace** — resolves the workspace root and the pack directory for a name or for
  a cwd-is-pack invocation, validates that a directory is a pack, enumerates packs, and
  owns first-build `.gitignore` scaffolding.
- **Manifest** — load, validate, and write `expert.json`. Owns the source-entry schema
  below, the reconciliation between manifest entries and files on disk, and the
  classification of a path into a source kind. Pure functions over paths and dicts; no
  network, no subprocess, no LLM.
- **Sources** — per-kind acquisition. Git cloning and pulling, URL fetch delegated to
  graphify's ingestion (so provenance frontmatter is produced by the same code that
  produces it today), local-path adoption, and video rejection.
- **Scoping** — compiles the per-source `paths` scopes plus the metadata exclusions
  into the single generated ignore file at the pack root.
- **Extraction** — wraps graphify's extract and update entry points, decides the
  semantic-versus-AST path, resolves the effective backend, and persists PDF text
  sidecars.
- **Skill generation** — reads graph facts and the manifest, emits `SKILL.md`.
- **Server** (the existing runtime, moved into the package and modified) — stdio MCP
  server over one pack: pack-relative source resolution across all layers, sidecar-aware
  PDF reads, and pack-level `corpus_info`.

### The pack layout

Four content layers plus one output directory. Layer names are borrowed, not invented:

- `repos/<owner>/<repo>/` — git clones, the only layer with a refresh lifecycle. The
  owner/repo nesting matches graphify's own clone cache convention and prevents name
  collisions between two sources with the same repo name.
- `raw/` — immutable fetched material. Three independent precedents: graphify's own
  fetch command defaults its target directory to `./raw`; Cookiecutter Data Science
  uses `data/raw` for exactly the "never modify this" layer; several independent
  knowledge-base tools converged on the same name.
- `notes/` — authored prose, following knowledge-base tool practice.
- `graph/` — the graph output directory, pointed at by graphify's output environment
  variable. It self-excludes from the scan: graphify's skip-directory set includes both
  the literal default output name and the basename of the configured output path, so a
  build never ingests its own previous output.
- `graph/converted/` — PDF text sidecars, persisted at build.

A `derived/` layer was considered and rejected: graphify already owns its own
intermediates under its output directory (`converted/`, `memory/`), so a second
derived layer would compete with it for the same role.

Research established that no existing packaging standard encodes the
refreshable-versus-immutable distinction as a directory convention — BagIt, Frictionless
Data Package, Cookiecutter Data Science, and OAIS all stop short of it. DVC comes
closest but expresses it as a manifest field (a repo dependency with a pinned revision,
refreshed by an explicit update verb) rather than as a directory. So `ef` follows DVC:
the distinction lives in the manifest's lifecycle field, and the directory names are
borrowed for legibility only.

### Manifest schema

The manifest is authoritative over pack contents. Field names borrow from Frictionless
Data's Resource descriptor (`name`, `path`, `sources`) and DVC's dependency-with-revision
lifecycle shape. Inlined because the entry shape encodes the lifecycle and provenance
decisions more precisely than prose:

```json
{
  "name": "effect",
  "title": "Effect TS",
  "extraction": { "code_only": false, "backend": "claude-cli" },
  "graph": {
    "nodes": 27729,
    "edges": 45530,
    "last_reconciled": "2026-07-29T10:12:03Z"
  },
  "sources": [
    {
      "name": "effect-ts/effect",
      "kind": "code",
      "path": "repos/effect-ts/effect",
      "origin": { "type": "git", "url": "https://github.com/effect-ts/effect" },
      "lifecycle": "refreshable",
      "ref": "main",
      "rev": "951d06b83d459d3e8fa9024e727a5db1662d3322",
      "last_synced": "2026-07-29T10:04:11Z",
      "paths": ["content/docs"]
    },
    {
      "name": "structured-concurrency-2024",
      "kind": "paper",
      "path": "raw/arxiv_org_abs_2401_12345.pdf",
      "origin": { "type": "fetch", "url": "https://arxiv.org/abs/2401.12345" },
      "lifecycle": "snapshot",
      "captured_at": "2026-07-21T09:00:00Z",
      "checksum": "sha256:1f0c…",
      "contributor": "eden"
    },
    {
      "name": "layer-memoization",
      "kind": "note",
      "path": "notes/layer-memoization.md",
      "origin": { "type": "authored" },
      "lifecycle": "snapshot",
      "captured_at": "2026-07-24T14:31:00Z",
      "checksum": "sha256:9ab3…",
      "contributor": "claude-code"
    }
  ]
}
```

Decisions the shape encodes:

- `kind` ∈ {`code`, `document`, `paper`, `note`, `image`}. `video` is a recognized
  token only so it can be rejected with a specific message.
- `lifecycle` ∈ {`refreshable`, `snapshot`}. Only `refreshable` entries participate in
  `ef update`. Only git sources are `refreshable`.
- `ref`/`rev`/`last_synced` appear only on `refreshable` entries; `captured_at` and
  `checksum` only on `snapshot` entries. The checksum exists so an "immutable"
  snapshot that changed can be detected.
- `paths` is optional and meaningful only on git sources; it is what the scoping module
  compiles into the generated ignore file.
- `extraction.backend` is the persisted backend, mirroring how graphify persists
  corpus-shaping options (its excludes and gitignore settings) into a build config and
  reuses them when the flag is absent. An explicit flag replaces the persisted value.
- `graph.last_reconciled` replaces the current per-pack `synced_at` sidecar and the
  single `built_at_commit` field. Reconciliation is a pack-level event across all
  sources, not a property of one commit.
- The current `server`, `port`, and `url` fields are dropped. They existed to name a
  compose service and address a container; a stdio server is addressed by the `cwd` its
  client launches it in, and `name` and `title` are the only identity a pack needs. The
  manifest describes the corpus, never a network location.

### Extraction defaults

- Semantic extraction is the default; `--code-only` is opt-out. The reason is
  mechanical: `--code-only` collects the doc, paper, and image sets and then empties
  all of them before the semantic pass, printing what it skipped. Markdown that does
  not go through the semantic pass gets only a free AST link-scan that mints file nodes
  and link edges. A prose pack built under `--code-only` would therefore be a
  near-empty graph with no error — the exact opposite of what a pack is for.
- `--backend` is required only when an LLM will actually be invoked. `--code-only`
  builds and AST-only updates require none. The effective backend is: explicit flag,
  else the persisted manifest value, else graphify's own auto-detection.
- `claude-cli` is deliberately excluded from graphify's backend auto-detection and must
  be named explicitly. `ef` surfaces this in its "no backend" error, because it is the
  one backend that bills a Claude subscription rather than a metered API key.
- Extraction runs with the pack directory as the scan root, so `source_file` values in
  the graph are pack-relative (`repos/effect-ts/effect/src/Effect.ts`,
  `notes/layer-memoization.md`). This is what makes one `read_source` implementation
  able to serve every layer.
- Images require a vision-capable backend. When the pack contains image sources and the
  effective backend has no vision support, `ef` says so before extracting rather than
  letting the images degrade silently.

### Update lifecycle

`ef update <name>` is a two-phase operation:

1. **Pull.** For every `refreshable` source: refuse if the clone has local
   modifications, fast-forward only, and record the before/after revisions. Snapshot
   sources are never re-fetched.
2. **Branch on what changed.** From the diff of changed paths across all pulled
   sources, classify each into code versus doc/paper/image using the same
   classification the manifest module uses:
   - nothing changed and no force → report up to date, do nothing.
   - only code changed → graphify's AST-only update path. Free.
   - any doc, paper, or image changed → semantic re-extract, which requires a backend.

The branch exists because the AST-only path deliberately *preserves* existing semantic
nodes rather than regenerating them: it identifies which doc files are backed by
semantic nodes in the prior graph and keeps them out of the rebuild targets so their
nodes are not wiped. That is correct for graphify's own incremental model, but it means
a pull that rewrote a markdown file leaves stale doc nodes present and unflagged.
`ef update` therefore treats a doc change as requiring the expensive path, and reports
which path it chose and which changed files drove the choice. Fetched pages and papers
have no refresh lifecycle at all.

### Per-source scoping

`ef` generates exactly one ignore file at the pack root, marked as generated, and
regenerates it on every build. It contains:

- For each git source with a `paths` scope: an exclusion of the clone's contents
  followed by re-inclusions of the wanted subtrees, using gitignore negation. graphify
  evaluates these with last-match-wins semantics and enforces gitignore's
  parent-exclusion rule (a negation cannot re-include a file whose ancestor directory
  is excluded), so the exclusion must be written against the clone's *contents* and the
  re-inclusions must name each ancestor directory of the wanted subtree.
- Exclusions for the pack's own metadata: the manifest, the skill, and the generated
  ignore file itself. Without this, the pack's instructions about its corpus become
  part of its corpus.

Per-directory ignore files inside clones are honored by graphify already and are left
alone. The graph directory needs no rule: it self-excludes via graphify's
skip-directory set.

### Manifest reconciliation

`ef build` reconciles the manifest against the files on disk before extracting:

- Files present in `raw/` or `notes/` with no manifest entry are **strays**. The build
  refuses, lists them, and suggests `--adopt-all`.
- `--adopt-all` creates entries for every stray in one pass, classifying each by
  extension, lifting `captured_at`/`contributor`/`source_url` from provenance
  frontmatter when present, and computing a checksum.
- Manifest entries whose path is missing on disk are reported as **orphans** and also
  block the build, since a graph built from a manifest that describes absent files
  would misreport its own coverage.
- Auto-adoption was explicitly rejected in favor of this friction: the guarantee that a
  built graph has complete provenance is worth one extra flag.

### Runtime and serving

- Serving is `ef run`: one process, stdio transport, one pack. No image, no compose
  file, no port, no daemon. The compose generation and the local-registry image tag are
  removed rather than reworked, because both existed only to address a container.
- `ef run` resolves its pack the same way every other verb does — a name argument, or
  the cwd when the name is omitted. Before the MCP handshake it validates that the
  directory has an `expert.json` and that the graph named by it exists on disk, and
  exits non-zero naming what is missing. A failed handshake gives an MCP client almost
  nothing to report, so the error has to happen before the transport starts.
- The pack root is the server's single filesystem anchor, replacing the container's
  mount point. This is required by pack-root extraction: `source_file` values are
  pack-relative, so the server needs one root containing all layers. `ef run` passes it
  in-process; the environment-variable configuration (`EXPERT_NAME`, `EXPERT_GRAPH`,
  `EXPERT_PACK`, `EXPERT_PORT`, `EXPERT_TRANSPORT`) existed so one image could serve any
  expert and is no longer how the server is configured.
- Read-only-ness is no longer enforced by a mount flag, so the server module simply has
  no write path — it opens the graph and source files for reading and nothing else. This
  keeps two clients able to serve the same pack concurrently and keeps a pack usable on
  read-only media.
- Anything the server needs to say goes to stderr. On stdio, stdout is the JSON-RPC
  framing, and a stray print corrupts the stream. graphify's own extraction chatter is
  a real hazard here, so the server does no extraction and any library output it cannot
  suppress must be redirected off stdout.
- `read_source` generalizes to resolve pack-relative paths across `repos/`, `raw/`, and
  `notes/`, keeping its existing containment check, now against the pack root. Note that
  graphify's own MCP server has no source-reading tool at all — its seven tools
  (`query_graph`, `get_node`, `get_neighbors`, `get_community`, `god_nodes`,
  `graph_stats`, `shortest_path`) are pure graph operations, because graphify assumes it
  runs inside an agent that already has a filesystem Read tool. `read_source` is
  expert-factory's own invention. Dropping the container weakens but does not remove its
  justification: a stdio-launched agent does have a filesystem, but it does not know
  where the pack lives, the graph's paths are pack-relative and resolve against nothing
  in the agent's own cwd, and a PDF node's text sits in a sidecar whose name the agent
  cannot derive. `read_source` keeps the pack layout an implementation detail, so a node
  id stays the only thing an agent has to hold.
- For a PDF-backed node, `read_source` reads the persisted text sidecar rather than the
  PDF. `ef build` writes those sidecars into the graph's `converted/` directory,
  mirroring graphify's own Office-document sidecar pattern (stable name derived from the
  scan-root-relative path, rewritten only when the source is newer). graphify's PDF text
  extractor does *not* cache, so this persistence is `ef`'s own addition. It now buys
  per-request speed and a serving path that never needs to parse a PDF, rather than a
  smaller image.
- Line-window arguments are not applied to PDF-backed nodes: graphify's own slicing
  module states plainly that PDFs and images "have no char-offset model" and are never
  sliced, so line anchors are meaningless for them. The response says so rather than
  returning a misleading window.
- `corpus_info` reports pack-level facts — source counts by kind and last reconciled —
  instead of a single build commit.

### Client wiring

Mounting an expert is a client-config entry, and `ef build` prints the exact one for
the pack it just built:

```json
{
  "effect expert": {
    "command": "ef",
    "args": ["run"],
    "cwd": "/Users/eden/projects/experts/effect"
  }
}
```

`ef` writes no client configuration itself. Client config files are user-owned, live in
different places per client, and are hand-edited; generating into them would mean
merging someone else's file. Printing the snippet gives the whole benefit at none of
that cost. `cwd` is emitted absolute, since a client resolves it against its own working
directory, not the workspace.

The `args: ["run"]` form — rather than `["run", "effect"]` with the workspace as `cwd` —
is the one to print, because it keeps the pack directory self-describing: move or copy
the pack and only `cwd` changes.

### Workspace scaffolding

On first build in a workspace with no `.gitignore`, `ef` writes one ignoring
`experts/*/repos/` and `experts/*/graph/` — large and reconstructible — while leaving
`raw/`, `notes/`, `expert.json`, and `SKILL.md` tracked, because fetched content
suffers link rot and notes are original work. An existing `.gitignore` is never
modified.

### Skill generation

The hardcoded single-commit provenance is replaced by one aggregate freshness line
naming the source composition and the last reconciliation date (for example: "Built
from 4 sources (2 git, 12 papers, 3 notes), last reconciled 2026-07-29"). A per-source
table was explicitly rejected: skills compete for context budget, and a table grows
without bound as a pack grows. The tool descriptions, working method, and
ground-claims-in-the-server framing carry over, with `read_source` reworded to cover
all layers rather than "the code".

## Testing Decisions

This repo has **no test suite at all** — no test files, no test directory, no pytest
configuration in `pyproject.toml`, no test dependency group. So the decisions below
propose seams rather than citing prior art in this codebase. The nearest prior art is
upstream graphify's own suite, which is instructive on style: it is
pytest-with-tmp-path, drives the CLI's real entry points against synthetic corpora, and
asserts on emitted artifacts rather than on internal call sequences.

**What makes a good test here.** Tests assert on externally observable behavior: the
files `ef` writes, the exit status and message it produces, and the arguments it hands
to graphify. They do not assert on private helper names, call ordering, or intermediate
data structures. A test that would break under a refactor that preserved every written
artifact is a bad test.

**Prefer the fewest, highest seams.** The boundary between `ef` and graphify is the
natural one. Everything below it — AST extraction, semantic extraction, clustering,
ignore-pattern evaluation — is graphify's own, already tested upstream, and expensive
or LLM-dependent to exercise. `ef`'s job is deciding *what* to hand graphify and
*what* to write afterwards. That is what gets tested.

**Modules tested, in priority order:**

1. **Manifest reconciliation** — the highest-value target and the cheapest. Pure
   functions over a directory tree and a manifest dict. Build a temporary pack, assert
   that strays block the build and are all listed, that `--adopt-all` produces entries
   with the right kind and lifecycle, that provenance frontmatter is lifted into the
   entry, that missing-on-disk entries are reported as orphans, and that checksums
   detect a mutated snapshot. No graphify call, no network, no LLM.
2. **Update-path branching** — the decision function that maps a set of changed paths
   to `noop` / `ast` / `semantic` is extracted as a pure function taking classified
   change lists and returning a path plus a reason. Tested directly over synthetic
   change sets: code-only, doc-only, mixed, empty, forced. This is where the expensive
   mistake lives, and it must be testable without a pull or an extraction.
3. **Scope compilation** — the per-source `paths` list to generated ignore-file
   transformation is a pure string function. Assert the negation shape for a nested
   subtree (including the ancestor re-inclusions gitignore's parent-exclusion rule
   requires), that metadata paths are excluded, and that regeneration is idempotent. A
   second, narrower test feeds the generated file through graphify's own
   ignore-matching to confirm the intended files survive — this is the one place worth
   crossing the boundary, because the semantics are subtle and borrowed.
4. **Backend resolution** — the flag / persisted / auto-detected precedence, and the
   rule that a cheap path needs no backend. A pure function over a manifest dict, an
   optional flag, and a "needs LLM" boolean. No credentials in tests.
5. **Pack resolution and `run` preflight** — the resolver is a pure function over a cwd
   and an optional name: a name resolves under `experts/`, an omitted name accepts a cwd
   holding `expert.json` and rejects one that does not, and no case walks upward. The
   preflight is asserted by exit status and stderr message: a non-pack directory and a
   pack with no graph each fail before any transport starts, naming what is missing.
   This replaces port assignment as the "wiring is right" test, and it is the one that
   catches a bad `cwd` in a client config.
6. **Generated artifacts** — the skill and the printed client-config snippet are
   asserted as text snapshots over a fixture manifest: the single aggregate freshness
   line, the absence of any per-source table or single commit SHA, and a snippet whose
   `cwd` is absolute and whose `args` are exactly `["run"]`.
7. **Workspace scaffolding** — the ignore file is written when absent, is never
   modified when present, and covers clones and graphs while leaving `raw/` and
   `notes/` tracked.
8. **Video rejection** — a video URL exits non-zero with a "not supported yet" message
   and writes nothing into the pack.

**Explicitly not tested by this suite:** real extraction quality, real LLM calls, and
real network fetches. Graphify invocation is verified by asserting the arguments passed
at the seam, with graphify itself substituted. `ef add`'s fetch is tested against a local
file source and a substituted fetch, never against the live internet. `ef run` is tested
only up to its preflight — the served MCP session itself is not driven, because the tool
bodies are thin wrappers over graphify's query functions and a real session would need a
real graph. The tool that is `ef`'s own, `read_source`, is instead tested directly as a
function: pack-relative resolution across each layer, a PDF-backed node served from its
sidecar with line arguments reported as inapplicable, and a path escaping the pack root
refused.

**Infrastructure:** a pytest dev dependency group and a minimal pytest configuration,
plus one shared fixture that builds a synthetic pack (a small fake clone, a couple of
`raw/` files with frontmatter, a note) in a temporary directory. Every test above runs
off that fixture. No test spends an LLM token.

## Out of Scope

- **Video sources.** They need graphify's video extra (faster-whisper, yt-dlp, ffmpeg)
  and agent-orchestrated Whisper prompt composition from corpus god nodes. `ef add`
  rejects video with a clear "not supported yet"; nothing else about video is built.
- **Migrating the two existing experts.** Moving the current `repo/`-shaped experts to
  the pack layout is a one-off throwaway script, deliberately not a CLI verb. `ef`
  gains no migration command and no backward-compatibility path for the old layout.
- **Containers, compose, and images.** `ef run` is a stdio process. The Dockerfile, the
  runtime requirements file, compose generation, and the local-registry image tag are
  deleted rather than kept as an alternative path. No public registry either — there is
  no image to publish.
- **HTTP transport.** stdio only. A `--http` mode would bring back the port allocation,
  the bindability probing, and the two-workspaces-collide problem that dropping the
  container removed, to serve a case — an expert reachable across a network — that is not
  one I have.
- **Writing client configuration.** `ef` prints the config snippet and never edits a
  client's config file. Those files are user-owned, per-client, and hand-maintained.
- **Process supervision.** Nothing daemonizes, restarts, health-checks, or tracks a
  running expert. The MCP client owns the process lifecycle, which is the whole point of
  stdio.
- **Research orchestration.** `ef add` never invokes an agent. Agents author into
  `notes/` themselves with their own tools; `ef` only notices the files on the next
  build.
- **Re-fetching snapshots.** `ef update` never re-fetches a page or paper. If a
  snapshot should be refreshed, that is a new `ef add`.
- **Multi-pack or global graphs.** One pack, one graph. graphify's global-graph and
  graph-merging features are not wired in.
- **Server-side write paths.** `ef run` never mutates a pack. Refreshing is `ef update`,
  run deliberately from a shell.
- **A workspace `init` verb.** Scaffolding happens on first build; there is no separate
  initialization command.

## Further Notes

- The layer names are deliberately borrowed rather than invented. `raw/` has three
  independent precedents — graphify's own fetch default, Cookiecutter Data Science's
  `data/raw`, and multiple knowledge-base tools that converged on it — and `notes/`
  follows knowledge-base practice. The thing that is genuinely novel here is the
  refreshable-versus-immutable lifecycle distinction, and research confirmed no
  existing standard (BagIt, Frictionless Data Package, CCDS, OAIS) captures it as a
  directory convention. DVC comes closest and encodes it as a manifest field, which is
  the precedent `ef` follows. So the directories are conventional and legible, and the
  one novel idea lives in the manifest where it can be validated.
- Two of the flipped defaults are flipped for the same underlying reason: graphify's
  incremental and code-only paths are both optimized for a code corpus where docs are
  incidental. `--code-only` empties the doc set entirely; the AST-only update preserves
  doc nodes rather than regenerating them. Both are correct for graphify's primary use
  case and both are wrong for a prose pack, which is why `ef` has to make the opposite
  choice at each point and explain itself when it does.
- The generated ignore file doing double duty — per-source scoping *and* excluding the
  pack's own metadata — is worth noting as a small but real correctness fix. Today's
  single-source experts keep the graph outside the checkout, so the tool's metadata was
  never in scan range. At pack root it would be, and a skill teaching an agent how to
  query a corpus becoming a node in that corpus is a self-reference worth preventing
  deliberately rather than by accident.
- `read_source` is the one tool expert-factory invents rather than inherits. graphify's
  server is pure graph operations because it assumes an agent that can already read the
  files the graph points at. An expert cannot assume that: the graph's paths are
  pack-relative, the agent's cwd is its own project, and PDF text lives in a sidecar with
  a derived name. Generalizing it across pack layers is what makes a paper or a note as
  citable as a line of source, and keeps the pack layout something an agent never has to
  learn.
- Dropping the container is a subtraction, not a redesign, and that is the argument for
  it. Extraction already ran on the host; the container only ever held a graph read and
  four tool functions. What it added was an image build, a compose file, a persistent
  process, and a port — and the port was the one piece that could not be made correct in
  isolation, since bindability is a machine-wide fact that no amount of manifest-scanning
  can settle. `ef run` deletes the whole class of problem rather than solving it: the
  ports module, the `port_base` setting, the probing, the compose regeneration, and three
  manifest fields all go away, and what replaces them is a `cwd` in a config file the
  client already reads.
- The pack directory becoming the unit of identity is the quiet consequence. Under
  compose, an expert was only real as an entry in a workspace-level file, so it could not
  be moved without rewriting that file. A pack with a manifest and a graph is now
  self-contained: copy the directory, point a `cwd` at it, and it serves. The workspace
  stays useful as a place to keep packs and as the scope for `ef list`, but it is no
  longer load-bearing for serving.
