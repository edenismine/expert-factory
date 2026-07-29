#!/usr/bin/env python3
"""Compile a repository into a runnable expert: graph + MCP server + skill.

    ./compile.py build <github-url|path> [--name NAME] [--port N] [--deep]
    ./compile.py list

Each expert lands in experts/<name>/ with a pristine checkout, an out-of-tree
graph, and a SKILL.md teaching agents to use the served tools. Compose wiring is
regenerated from the set of compiled experts.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
EXPERTS = ROOT / "experts"
BASE_PORT = 8801


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=True, text=True, **kwargs)


def graphify_bin() -> str:
    found = shutil.which("graphify")
    if not found:
        sys.exit("graphify not on PATH; the build step needs the full toolchain")
    return found


def derive_name(source: str) -> str:
    stem = source.rstrip("/").removesuffix(".git").rsplit("/", 1)[-1]
    cleaned = "".join(c if c.isalnum() or c in "-_" else "-" for c in stem).strip("-")
    return cleaned.lower() or "expert"


def load_expert(path: Path) -> dict:
    return json.loads((path / "expert.json").read_text(encoding="utf-8"))


def all_experts() -> list[dict]:
    if not EXPERTS.is_dir():
        return []
    found = [load_expert(d) for d in sorted(EXPERTS.iterdir()) if (d / "expert.json").is_file()]
    return found


def next_port() -> int:
    used = {e["port"] for e in all_experts()}
    port = BASE_PORT
    while port in used:
        port += 1
    return port


def prepare_checkout(source: str, repo_dir: Path) -> None:
    """Put a checkout at repo_dir, reusing an existing clone when possible."""
    if repo_dir.is_dir():
        print(f"[compile] reusing checkout at {repo_dir}")
        return

    local = Path(source).expanduser()
    if local.is_dir():
        if not (local / ".git").is_dir():
            sys.exit(f"{local} is not a git checkout; the maintainer needs git to refresh it")
        origin = subprocess.run(
            ["git", "-C", str(local), "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip()
        if not origin:
            sys.exit(f"{local} has no origin remote; cannot refresh later")
        print(f"[compile] cloning from local checkout ({origin})")
        run(["git", "clone", "--quiet", str(local), str(repo_dir)])
        run(["git", "-C", str(repo_dir), "remote", "set-url", "origin", origin])
        return

    print(f"[compile] cloning {source}")
    run(["git", "clone", "--quiet", source, str(repo_dir)])


def build_graph(repo_dir: Path, graph_dir: Path, deep: bool) -> None:
    """Extract into graph_dir, which sits outside the checkout so git stays clean."""
    # cwd=repo_dir: graphify stamps built_at_commit from `git rev-parse HEAD` in
    # its own cwd, not in the directory it was pointed at.
    env = {**os.environ, "GRAPHIFY_OUT": str(graph_dir)}
    if (graph_dir / "graph.json").is_file():
        print("[compile] graph exists; updating from source (AST only)")
        run([graphify_bin(), "update", str(repo_dir)], env=env, cwd=repo_dir)
        return

    cmd = [graphify_bin(), "extract", str(repo_dir)]
    if not deep:
        cmd.append("--code-only")
    print(f"[compile] extracting graph -> {graph_dir}")
    run(cmd, env=env, cwd=repo_dir)


def import_graph(existing: Path, graph_dir: Path) -> None:
    """Adopt an already-built graphify-out directory instead of re-extracting."""
    if (graph_dir / "graph.json").is_file():
        print(
            f"[compile] keeping the graph already at {graph_dir} (--reuse-graph would overwrite it)"
        )
        return
    graph_dir.mkdir(parents=True, exist_ok=True)
    for name in ("graph.json", "GRAPH_REPORT.md", "manifest.json", "cost.json"):
        src = existing / name
        if src.is_file():
            shutil.copy2(src, graph_dir / name)
    print(f"[compile] imported existing graph from {existing}")


def head_commit(repo_dir: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(repo_dir), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()


def graph_facts(graph_path: Path) -> dict:
    """Node/edge counts and top hubs, read without holding the graph in memory."""
    import collections

    data = json.loads(graph_path.read_text(encoding="utf-8"))
    degree: collections.Counter = collections.Counter()
    for link in data.get("links", data.get("edges", [])):
        degree[link["source"]] += 1
        degree[link["target"]] += 1
    labels = {n["id"]: n.get("label", n["id"]) for n in data["nodes"]}
    files = collections.Counter()
    for node in data["nodes"]:
        source = node.get("source_file") or ""
        if "." in source:
            files[source.rsplit(".", 1)[-1]] += 1
    return {
        "nodes": len(data["nodes"]),
        "edges": len(data.get("links", data.get("edges", []))),
        "built_at_commit": data.get("built_at_commit"),
        "hubs": [labels.get(i, i) for i, _ in degree.most_common(12)],
        "extensions": [ext for ext, _ in files.most_common(6)],
    }


SKILL_TEMPLATE = """---
name: {name}-expert
description: "{description}"
---

# {title} expert

Answers about {title} are grounded in a knowledge graph built from its source at
commit `{commit_short}` ({nodes:,} nodes, {edges:,} edges), served by the
`{server}` MCP server over HTTP at `{url}`. Ground every non-trivial claim in that
server rather than in recollection, and keep the mechanism out of user-facing prose.

## Tools

Exposed as `mcp__{server}__<tool>`:

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

Prominent areas in this corpus: {hub_list}.
Indexed file types: {ext_list}.

The graph reflects one commit. When a consuming project has its own copy of this
dependency, that copy and its type checker win — the graph may describe a
different revision. Say so when a version difference could matter.

If `{server}` is unreachable, say the expert is unavailable and fall back to the
consuming project's installed source instead of guessing.
"""


def write_skill(path: Path, expert: dict, facts: dict) -> None:
    title = expert["title"]
    commit = facts.get("built_at_commit") or expert["built_at_commit"] or "unknown"
    skill = SKILL_TEMPLATE.format(
        name=expert["name"],
        title=title,
        server=expert["server"],
        url=expert["url"],
        description=(
            f"{title} questions, implementation, debugging, and review, grounded in a "
            f"knowledge graph of the {title} source tree. Use when the task involves "
            f"{title} APIs, internals, or idioms."
        ),
        commit_short=commit[:7],
        nodes=facts["nodes"],
        edges=facts["edges"],
        hub_list=", ".join(facts["hubs"][:10]) or "n/a",
        ext_list=", ".join(facts["extensions"]) or "n/a",
    )
    (path / "SKILL.md").write_text(skill, encoding="utf-8")


def write_compose() -> None:
    experts = all_experts()
    if not experts:
        return
    lines = ["# Generated by compile.py; edits are overwritten on the next build.", "services:"]
    for e in experts:
        lines += [
            f"  {e['name']}:",
            "    build: ./runtime",
            f"    container_name: expert-{e['name']}",
            "    restart: unless-stopped",
            f'    ports: ["{e["port"]}:{e["port"]}"]',
            "    environment:",
            f"      EXPERT_NAME: {e['name']}",
            "      EXPERT_GRAPH: /graph/graph.json",
            # source_file values are pack-relative, so the whole pack is mounted
            # rather than a single checkout.
            "      EXPERT_PACK: /pack",
            f'      EXPERT_PORT: "{e["port"]}"',
            "    volumes:",
            f"      - ./experts/{e['name']}:/pack:ro",
            f"      - ./experts/{e['name']}/graph:/graph:ro",
            "",
        ]
    (ROOT / "docker-compose.yml").write_text("\n".join(lines), encoding="utf-8")
    print(f"[compile] wrote docker-compose.yml ({len(experts)} expert(s))")


def cmd_build(args: argparse.Namespace) -> None:
    name = args.name or derive_name(args.source)
    home = EXPERTS / name
    repo_dir, graph_dir = home / "repo", home / "graph"
    home.mkdir(parents=True, exist_ok=True)

    prepare_checkout(args.source, repo_dir)

    adopt = Path(args.source).expanduser() / "graphify-out"
    if args.reuse_graph and (adopt / "graph.json").is_file():
        import_graph(adopt, graph_dir)
    else:
        build_graph(repo_dir, graph_dir, args.deep)

    graph_path = graph_dir / "graph.json"
    if not graph_path.is_file():
        sys.exit(f"no graph produced at {graph_path}")

    facts = graph_facts(graph_path)
    port = (
        args.port
        or next((e["port"] for e in all_experts() if e["name"] == name), None)
        or next_port()
    )

    expert = {
        "name": name,
        "title": args.title or name,
        "server": f"{name}-expert",
        "port": port,
        "url": f"http://127.0.0.1:{port}/mcp",
        "source": args.source,
        "built_at_commit": facts.get("built_at_commit") or head_commit(repo_dir),
        "nodes": facts["nodes"],
        "edges": facts["edges"],
    }
    (home / "expert.json").write_text(json.dumps(expert, indent=2) + "\n", encoding="utf-8")
    # What maintain.sh compares against HEAD. Tracked separately from
    # built_at_commit, which graphify only rewrites when topology changes. Seeded
    # from the graph's own commit so an adopted --reuse-graph graph built at an
    # older revision than this checkout reports as needing a refresh.
    (graph_dir / "synced_at").write_text(expert["built_at_commit"] + "\n", encoding="utf-8")
    write_skill(home, expert, facts)
    write_compose()

    dirty = subprocess.run(
        ["git", "-C", str(repo_dir), "status", "--porcelain"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    print(f"\n[compile] {name}: {facts['nodes']:,} nodes, {facts['edges']:,} edges, port {port}")
    print(f"[compile] checkout {'DIRTY - graph leaked into it' if dirty else 'clean'}")
    print(f"[compile] skill: {home / 'SKILL.md'}")
    print(f"[compile] start:  docker compose up -d {name}")


def cmd_sync(args: argparse.Namespace) -> None:
    """Rewrite expert.json and SKILL.md from the graph on disk, after a refresh."""
    home = EXPERTS / args.name
    if not (home / "expert.json").is_file():
        sys.exit(f"unknown expert: {args.name}")

    graph_path = home / "graph" / "graph.json"
    facts = graph_facts(graph_path)
    expert = load_expert(home)
    expert.update(
        built_at_commit=facts.get("built_at_commit") or head_commit(home / "repo"),
        nodes=facts["nodes"],
        edges=facts["edges"],
    )
    (home / "expert.json").write_text(json.dumps(expert, indent=2) + "\n", encoding="utf-8")
    write_skill(home, expert, facts)
    print(f"[compile] synced {args.name}: {facts['nodes']:,} nodes, {facts['edges']:,} edges")


def cmd_list(_: argparse.Namespace) -> None:
    experts = all_experts()
    if not experts:
        print("no experts compiled yet")
        return
    for e in experts:
        print(f"{e['name']:<16} {e['url']:<30} {e['nodes']:>7,} nodes  {e['built_at_commit'][:7]}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build", help="compile a repo into an expert")
    build.add_argument("source", help="github url, or path to an existing checkout")
    build.add_argument("--name", help="expert name (default: repo name)")
    build.add_argument("--title", help="human label used in the skill prose")
    build.add_argument("--port", type=int, help="HTTP port (default: next free)")
    build.add_argument("--deep", action="store_true", help="semantic extraction (costs LLM tokens)")
    build.add_argument(
        "--reuse-graph",
        action="store_true",
        help="adopt an existing graphify-out/ next to the source instead of extracting",
    )
    build.set_defaults(func=cmd_build)

    sync = sub.add_parser("sync", help="rewrite expert.json + SKILL.md from the graph on disk")
    sync.add_argument("name")
    sync.set_defaults(func=cmd_sync)

    listing = sub.add_parser("list", help="show compiled experts")
    listing.set_defaults(func=cmd_list)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
