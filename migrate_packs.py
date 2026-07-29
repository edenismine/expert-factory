#!/usr/bin/env python3
"""One-off: convert experts/<name>/repo/ into the pack layout. Delete after running.

    ./migrate_packs.py --dry-run
    ./migrate_packs.py

repo/ becomes repos/<owner>/<repo>/, derived from the checkout's origin remote, and
every repo-relative source_file in the graph gains that prefix so the already-paid-for
semantic extraction survives instead of being re-spent.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
EXPERTS = ROOT / "experts"

# Repo-relative path keys live in these graph-dir artifacts. cache/ast/ is keyed by
# content hash, not path, so it needs no rewrite.
PREFIXED_JSON = ("graph.json", "manifest.json")


def origin_slug(repo: Path) -> tuple[str, str]:
    url = subprocess.run(
        ["git", "-C", str(repo), "remote", "get-url", "origin"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    owner, name = url.removesuffix(".git").rstrip("/").rsplit("/", 2)[-2:]
    return owner, name


def rewrite_graph(path: Path, prefix: str) -> tuple[int, int]:
    data = json.loads(path.read_text(encoding="utf-8"))
    nodes = 0
    for node in data["nodes"]:
        source = node.get("source_file")
        if source and not source.startswith(prefix):
            node["source_file"] = prefix + source
            nodes += 1
    links = 0
    for link in data.get("links", data.get("edges", [])):
        source = link.get("source_file")
        if source and not source.startswith(prefix):
            link["source_file"] = prefix + source
            links += 1
    path.write_text(json.dumps(data), encoding="utf-8")
    return nodes, links


def rewrite_manifest(path: Path, prefix: str) -> int:
    data = json.loads(path.read_text(encoding="utf-8"))
    moved = {(k if k.startswith(prefix) else prefix + k): v for k, v in data.items()}
    path.write_text(json.dumps(moved, indent=2), encoding="utf-8")
    return len(moved)


def rewrite_stat_index(path: Path, prefix: str) -> int:
    if not path.is_file():
        return 0
    data = json.loads(path.read_text(encoding="utf-8"))
    moved = {(k if k.startswith(prefix) else prefix + k): v for k, v in data.items()}
    path.write_text(json.dumps(moved), encoding="utf-8")
    return len(moved)


def migrate(home: Path, dry_run: bool) -> None:
    name = home.name
    repo, graph = home / "repo", home / "graph"
    if not repo.is_dir():
        print(f"[{name}] no repo/ — already migrated, skipping")
        return

    owner, slug = origin_slug(repo)
    prefix = f"repos/{owner}/{slug}/"
    print(f"[{name}] repo/ -> {prefix}")

    if dry_run:
        graph_path = graph / "graph.json"
        data = json.loads(graph_path.read_text(encoding="utf-8"))
        pending = sum(
            1 for n in data["nodes"]
            if n.get("source_file") and not n["source_file"].startswith(prefix)
        )
        print(f"[{name}]   would prefix {pending:,} node paths (+ links, manifest, stat-index)")
        return

    target = home / "repos" / owner / slug
    target.parent.mkdir(parents=True, exist_ok=True)
    repo.rename(target)
    print(f"[{name}]   moved checkout")

    nodes, links = rewrite_graph(graph / "graph.json", prefix)
    print(f"[{name}]   graph.json: {nodes:,} nodes, {links:,} links prefixed")

    entries = rewrite_manifest(graph / "manifest.json", prefix)
    print(f"[{name}]   manifest.json: {entries:,} entries")

    indexed = rewrite_stat_index(graph / "cache" / "stat-index.json", prefix)
    if indexed:
        print(f"[{name}]   stat-index.json: {indexed:,} entries")

    # graphify records the scan root here; it now points at the pack, not the checkout.
    (graph / ".graphify_root").write_text(str(home) + "\n", encoding="utf-8")

    # Snapshot copies under graph/<date>/ are stale by construction once paths move.
    for dated in sorted(p for p in graph.iterdir() if p.is_dir() and p.name[:2] == "20"):
        shutil.rmtree(dated)
        print(f"[{name}]   dropped stale snapshot {dated.name}/")

    def git(*cmd: str) -> str:
        return subprocess.run(
            ["git", "-C", str(target), *cmd],
            capture_output=True, text=True, check=True,
        ).stdout.strip()

    rev = (graph / "synced_at").read_text(encoding="utf-8").strip()
    expert_path = home / "expert.json"
    expert = json.loads(expert_path.read_text(encoding="utf-8"))
    expert["sources"] = [
        {
            "name": f"{owner}/{slug}",
            "kind": "code",
            "path": prefix.rstrip("/"),
            "origin": {"type": "git", "url": git("remote", "get-url", "origin")},
            "lifecycle": "refreshable",
            "ref": git("rev-parse", "--abbrev-ref", "HEAD"),
            "rev": rev,
            # synced_at holds a commit, not a date, so the timestamp comes from that
            # commit's committer date.
            "last_synced": git("show", "-s", "--format=%cI", rev),
        }
    ]
    expert.pop("source", None)
    expert_path.write_text(json.dumps(expert, indent=2) + "\n", encoding="utf-8")
    print(f"[{name}]   wrote manifest entry")

    for layer in ("raw", "notes"):
        (home / layer).mkdir(exist_ok=True)

    (home / ".graphifyignore").write_text(
        "# Generated. Tool metadata is not corpus content.\n"
        "/expert.json\n/SKILL.md\n/.graphifyignore\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    homes = sorted(d for d in EXPERTS.iterdir() if (d / "expert.json").is_file())
    if not homes:
        sys.exit("no experts found")
    for home in homes:
        migrate(home, args.dry_run)


if __name__ == "__main__":
    main()
