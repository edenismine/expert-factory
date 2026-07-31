# Graph Report - /Users/eden.aragon/Projects/personal/expert-factory  (2026-07-31)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 404 nodes · 781 edges · 23 communities (20 shown, 3 thin omitted)
- Extraction: 98% EXTRACTED · 2% INFERRED · 0% AMBIGUOUS · INFERRED: 15 edges (avg confidence: 0.6)
- Token cost: 2,185 input · 275 output

## Graph Freshness
- Built from commit: `ec50b1e8`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- CLI Commands and Parsing
- Graph Extraction and Building
- Extraction Testing and Caching
- Manifest and Metadata
- Artifact Generation and Server
- Error Handling and Git Operations
- Scope and Gitignore Rules
- Server and File Access
- Source Acquisition and Adoption
- Manifest Reconciliation
- Pack Lifecycle Operations
- Workspace and Pack Resolution
- Graph Export and Features
- Update Operations
- Test Fixtures and Setup
- Skill Generation
- Graph Query Interface
- Git Commit Discipline
- System Architecture
- Pack Storage Layers
- Skill Definition
- Extraction Output Directory
- Expert Factory Tool

## God Nodes (most connected - your core abstractions)
1. `EfError` - 28 edges
2. `cmd_build()` - 23 edges
3. `cmd_update()` - 17 edges
4. `cmd_add()` - 14 edges
5. `_finish()` - 14 edges
6. `cmd_clone()` - 12 edges
7. `parser()` - 12 edges
8. `resolve_pack()` - 12 edges
9. `say()` - 11 edges
10. `cmd_new()` - 11 edges

## Surprising Connections (you probably didn't know these)
- `exa-researcher Agent - deep web research` --semantically_similar_to--> `expert-factory: CLI tool for building queryable experts`  [INFERRED] [semantically similar]
  .claude/agents/exa-researcher.md → README.md
- `cmd_update()` --calls--> `refreshable()`  [EXTRACTED]
  src/ef/cli.py → src/ef/manifest.py
- `test_pull_diffs_from_the_rev_the_graph_reflects()` --calls--> `git()`  [INFERRED]
  tests/test_sources.py → tests/conftest.py
- `moved_pack()` --calls--> `git()`  [INFERRED]
  tests/test_update.py → tests/conftest.py
- `expert-factory: CLI tool for building queryable experts` --cites--> `graphify - knowledge graph library`  [EXTRACTED]
  README.md → CLAUDE.md

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Pack content organization - four-layer model** — pack_repos_layer, pack_raw_layer, pack_notes_layer, pack_graph_layer [EXTRACTED 1.00]
- **ef CLI commands - full workflow** — ef_build_command, ef_run_command, ef_update_command [EXTRACTED 1.00]
- **graphify query tools - graph navigation** — graphify_query_tool, graphify_path_tool, graphify_explain_tool [EXTRACTED 1.00]
- **git discipline - three non-negotiables** — conventional_commits_pattern, atomic_commits_pattern, linear_history_pattern [EXTRACTED 1.00]
- **Extraction design principles - node/edge semantics** — extracted_vs_inferred_confidence, node_id_normalization, edge_direction_convention [EXTRACTED 1.00]

## Communities (23 total, 3 thin omitted)

### Community 0 - "CLI Commands and Parsing"
Cohesion: 0.10
Nodes (54): ArgumentParser, client_snippet(), cmd_add(), cmd_build(), cmd_clone(), cmd_delete(), cmd_list(), cmd_new() (+46 more)

### Community 1 - "Graph Extraction and Building"
Cohesion: 0.06
Nodes (46): ef build - extract corpus to graph, ef run - serve pack as MCP stdio, ef update - pull and refresh graph, graph.json - persistent knowledge graph, GRAPH_REPORT.md - extraction audit and analysis, Pack layer: graph/ - extracted knowledge graph, SKILL.md - generated agent skill, cluster() (+38 more)

### Community 2 - "Extraction Testing and Caching"
Cohesion: 0.08
Nodes (21): captured_argv(), MonkeyPatch, parametrize, Update-path branching and backend resolution: where the expensive mistake lives., The AST path preserves existing semantic nodes, so a rewritten doc leaves stale…, Record the argv extract() hands to graphify's sys.argv-driven CLI branch., A workspace gitignores its packs, and graphify walks up to the VCS root. Left…, graphify reads --force as "skip the semantic cache read". Passing it… (+13 more)

### Community 3 - "Manifest and Metadata"
Cohesion: 0.13
Nodes (26): adopt(), checksum(), classify(), git_entry(), irreplaceable_counts(), is_metadata(), kind_for_adoption(), now() (+18 more)

### Community 4 - "Artifact Generation and Server"
Cohesion: 0.13
Nodes (21): multi_source(), Path, The generated skill and the printed client-config snippet., An unquoted cd would split the path and strand the server in the wrong place., A stdio server is spawned as a child process; there is no port, url, or…, A table grows without bound, and a skill competes for the context budget it…, Reworded to cover all layers rather than "the code"., Claude Code ignores a `cwd` key, so the shell has to cd before exec'ing ef. (+13 more)

### Community 5 - "Error Handling and Git Operations"
Cohesion: 0.17
Nodes (19): Exception, EfError, ef — build and serve experts over packs of code, docs, papers and notes., A condition the user can fix. The CLI prints it and exits non-zero., adopt_path(), clone(), fetch(), git() (+11 more)

### Community 6 - "Scope and Gitignore Rules"
Cohesion: 0.15
Nodes (19): Path, Scope compilation, including one pass through graphify's own ignore matcher., The one place worth crossing the boundary: the semantics are subtle and…, A skill teaching an agent to query a corpus must not become a node in it., gitignore's parent-exclusion rule: a negation cannot rescue a file under an…, Extraction runs --no-gitignore, so the clone's own rules no longer guard these., The guard has to hold under graphify's real matcher, not just as text., A clone that ships its own graph.json would have it dispatched as a document:… (+11 more)

### Community 7 - "Server and File Access"
Cohesion: 0.16
Nodes (20): build_graph(), Path, Server preflight and read_source — the one tool ef invents rather than inherits., A crafted node id must not read the host filesystem., Being spawned in the wrong directory has to be diagnosable, not a silent failed…, The path a misconfigured client actually hits: `ef run` with no name, spawned…, PDFs have no char-offset model, so a line anchor has nothing behind it., test_a_line_window_anchors_on_the_source_location() (+12 more)

### Community 8 - "Source Acquisition and Adoption"
Cohesion: 0.14
Nodes (18): parametrize, Path, Acquisition: video rejection, owner/repo splitting, adoption, and pull refusal., Work forgotten in a clone is never discarded., A refresh that pulled but failed to extract must still be recoverable. The…, The fetched-versus-authored distinction stays visible in the layout., test_a_directory_holding_video_is_rejected_before_copying(), test_a_directory_is_adopted_recursively() (+10 more)

### Community 9 - "Manifest Reconciliation"
Cohesion: 0.18
Nodes (18): Path, Manifest reconciliation: the guarantee that a built graph has complete…, A rebuild must never see the previous build's output as unmanifested material., repos/ has one entry for the whole tree, not one per file., test_adopt_all_classifies_kind_and_lifecycle(), test_adopt_lifts_provenance_frontmatter(), test_authored_note_has_no_fetch_origin(), test_checksum_detects_a_mutated_snapshot() (+10 more)

### Community 10 - "Pack Lifecycle Operations"
Cohesion: 0.27
Nodes (17): delete_args(), new_args(), MonkeyPatch, Namespace, Path, ef new and ef delete — the ops that create and destroy a pack directory., test_delete_guards_on_a_dotfile_too(), test_delete_names_a_missing_pack() (+9 more)

### Community 11 - "Workspace and Pack Resolution"
Cohesion: 0.20
Nodes (16): MonkeyPatch, Path, Pack resolution and workspace scaffolding: the "wiring is right" tests., A stray parent manifest must not capture a subdirectory silently., Fetched material suffers link rot and notes are original work: neither rebuilds., test_a_gitignore_is_written_when_absent(), test_a_name_resolves_under_experts(), test_an_existing_gitignore_is_never_touched() (+8 more)

### Community 12 - "Graph Export and Features"
Cohesion: 0.13
Nodes (15): add-watch - fetch URLs and auto-rebuild, exports - wiki, Neo4j, FalkorDB, SVG, GraphML, MCP, benchmark, extraction-spec - JSON schema and node ID rules, hooks - post-commit and native CLAUDE.md integration, transcribe - video and audio to text, update - incremental re-extraction and cluster-only, graphify Skill - semantic extraction and graph building, Edge direction - source is ACTOR, target is ACTED-UPON (+7 more)

### Community 13 - "Update Operations"
Cohesion: 0.21
Nodes (14): moved_pack(), fixture, MonkeyPatch, Path, What `ef update` hands to graphify — the verb where a mistake costs real money., A pack whose clone has a doc commit the manifest rev predates. A prose change…, Drive cmd_update, recording the argv of every graphify command it dispatches., graphify reads --force as "skip the semantic cache read", so passing it on… (+6 more)

### Community 14 - "Test Fixtures and Setup"
Cohesion: 0.29
Nodes (10): git(), git_fixture(), pack(), fixture, MonkeyPatch, Path, The same git runner conftest builds packs with, for tests that add commits., An empty workspace, with the cwd pointed at it as every verb expects. (+2 more)

### Community 15 - "Skill Generation"
Cohesion: 0.36
Nodes (7): sources_by_kind(), freshness_line(), Path, Generate SKILL.md from graph facts and the manifest., One aggregate line covering all sources, never a per-source table. A table…, render(), write()

### Community 16 - "Graph Query Interface"
Cohesion: 0.40
Nodes (5): query - graph traversal and expansion, graphify explain - plain-language node explanation, graphify path - shortest path between concepts, graphify query - BFS/DFS graph traversal, Query vocabulary expansion - match graph labels before traversal

### Community 17 - "Git Commit Discipline"
Cohesion: 0.50
Nodes (4): Atomic commits - one logical change per commit, git-discipline Skill - conventional commits and linear history, Conventional Commits - commit message discipline, Linear history - ff-only merges, no fork commits

### Community 18 - "System Architecture"
Cohesion: 0.50
Nodes (4): exa-researcher Agent - deep web research, graphify - knowledge graph library, graphify MCP server, expert-factory: CLI tool for building queryable experts

### Community 19 - "Pack Storage Layers"
Cohesion: 0.50
Nodes (4): expert.json - authoritative pack manifest, Pack layer: notes/ - user markdown, Pack layer: raw/ - fetched pages, papers, images, Pack layer: repos/ - pristine clones

## Knowledge Gaps
- **20 isolated node(s):** `expert-factory`, `graphify Skill Definition`, `exa-researcher Agent - deep web research`, `exports - wiki, Neo4j, FalkorDB, SVG, GraphML, MCP, benchmark`, `github-and-merge - clone and cross-repo merging` (+15 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **3 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `EfError` connect `Error Handling and Git Operations` to `CLI Commands and Parsing`, `Graph Extraction and Building`, `Manifest and Metadata`?**
  _High betweenness centrality (0.080) - this node is a cross-community bridge._
- **Why does `cmd_build()` connect `CLI Commands and Parsing` to `Graph Extraction and Building`, `Manifest and Metadata`, `Error Handling and Git Operations`?**
  _High betweenness centrality (0.015) - this node is a cross-community bridge._
- **What connects `expert-factory`, `graphify Skill Definition`, `exa-researcher Agent - deep web research` to the rest of the system?**
  _20 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `CLI Commands and Parsing` be split into smaller, more focused modules?**
  _Cohesion score 0.09837092731829573 - nodes in this community are weakly interconnected._
- **Should `Graph Extraction and Building` be split into smaller, more focused modules?**
  _Cohesion score 0.06431372549019608 - nodes in this community are weakly interconnected._
- **Should `Extraction Testing and Caching` be split into smaller, more focused modules?**
  _Cohesion score 0.07807807807807808 - nodes in this community are weakly interconnected._
- **Should `Manifest and Metadata` be split into smaller, more focused modules?**
  _Cohesion score 0.12698412698412698 - nodes in this community are weakly interconnected._