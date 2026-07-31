"""ef — the CLI. Owns subcommand parsing and all human-readable reporting.

Dependency flow is one-directional: CLI -> orchestration -> leaf helpers. No leaf
module imports this one.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from . import EfError, extraction, manifest, scoping, skill, sources, workspace


def say(message: str) -> None:
    print(f"[ef] {message}")


def warn(message: str) -> None:
    print(f"[ef] warning: {message}", file=sys.stderr)


def relative_to_cwd(path: Path) -> Path | str:
    """Shorten a path for display, falling back to absolute when it is elsewhere."""
    try:
        return path.resolve().relative_to(Path.cwd().resolve())
    except ValueError:
        return str(path.resolve())


def client_snippet(pack: Path, name: str) -> str:
    """The MCP client config entry for a pack.

    `args: ["run"]` with the pack as `cwd` — rather than `["run", <name>]` with the
    workspace as cwd — keeps the pack self-describing: move or copy it and only
    `cwd` changes. `cwd` is absolute because a client resolves it against its own
    working directory, not the workspace.
    """
    entry = {
        f"{name} expert": {
            "command": "ef",
            "args": ["run"],
            "cwd": str(pack.resolve()),
        }
    }
    return json.dumps(entry, indent=2)


def report_snippet(pack: Path, name: str) -> None:
    say("mount it in an MCP client with:")
    for line in client_snippet(pack, name).splitlines():
        print(f"  {line}")


# --------------------------------------------------------------------------- #
# verbs


def cmd_clone(args: argparse.Namespace) -> None:
    pack = workspace.pack_for_build(args.name)
    data = (
        manifest.load(pack)
        if workspace.is_pack(pack)
        else manifest.blank(args.name or pack.name, args.title)
    )

    say(f"cloning {args.url}")
    clone, ref, rev = sources.clone(pack, args.url)
    entry = manifest.git_entry(pack, clone, args.url, ref, rev)
    if args.paths:
        entry["paths"] = args.paths
    manifest.upsert(data, entry)
    manifest.save(pack, data)

    say(f"{entry['name']} -> {entry['path']} at {rev[:7]} ({ref})")
    if args.paths:
        say(f"scoped to {', '.join(args.paths)}; the next build compiles that into .graphifyignore")
    say(f"next: ef build {pack.name}")


def cmd_add(args: argparse.Namespace) -> None:
    pack = workspace.pack_for_build(args.name)
    data = (
        manifest.load(pack)
        if workspace.is_pack(pack)
        else manifest.blank(args.name or pack.name, args.title)
    )

    local = Path(args.target).expanduser()
    if local.exists():
        adopted = sources.adopt_path(pack, local)
        say(f"adopted {len(adopted)} file(s) from {local}")
    else:
        adopted = [sources.fetch(pack, args.target, args.contributor)]
        say(f"fetched {args.target}")

    for path in adopted:
        layer = path.relative_to(pack).parts[0]
        entry = manifest.snapshot_entry(pack, path, layer)
        manifest.upsert(data, entry)
        print(f"  {entry['kind']:<9} {entry['path']}")

    manifest.save(pack, data)
    say(f"next: ef build {pack.name}")


def _reconcile_or_fail(pack: Path, data: dict, adopt_all: bool) -> None:
    state = manifest.reconcile(pack, data)

    if state.strays and adopt_all:
        added = manifest.adopt(pack, data, state.strays)
        manifest.save(pack, data)
        say(f"adopted {len(added)} unmanifested file(s)")
        state = manifest.reconcile(pack, data)

    if state.strays:
        print(
            f"[ef] {len(state.strays)} file(s) in the pack have no manifest entry:",
            file=sys.stderr,
        )
        for path in state.strays:
            print(f"  {path.relative_to(pack).as_posix()}", file=sys.stderr)
        raise EfError(
            "refusing to build: every file needs a recorded origin so the graph carries "
            "complete provenance. Re-run with --adopt-all to accept them all."
        )

    if state.orphans:
        print("[ef] manifest entries with no file on disk:", file=sys.stderr)
        for rel in state.orphans:
            print(f"  {rel}", file=sys.stderr)
        raise EfError(
            "refusing to build: a graph built from a manifest describing absent files "
            "would misreport its own coverage. Restore the files or drop the entries."
        )

    for rel in state.altered:
        warn(f"snapshot changed since capture: {rel}")


def _finish(pack: Path, data: dict, *, path_taken: str) -> dict:
    """Write manifest, skill and reconciliation stamp from the graph on disk."""
    facts = extraction.graph_facts(pack)
    data.setdefault("graph", {}).update(
        nodes=facts["nodes"], edges=facts["edges"], last_reconciled=manifest.now()
    )
    manifest.save(pack, data)
    skill.write(pack, data, facts)

    say(f"{data['name']}: {facts['nodes']:,} nodes, {facts['edges']:,} edges ({path_taken})")
    hollow = extraction.hollow_warning(facts, data["sources"])
    if hollow:
        warn(hollow)
    say(f"skill: {relative_to_cwd(pack / workspace.SKILL_NAME)}")
    return facts


def cmd_build(args: argparse.Namespace) -> None:
    pack = workspace.pack_for_build(args.name)
    if not workspace.is_pack(pack):
        if args.name is None:
            raise EfError(f"{pack} is not a pack: no {workspace.MANIFEST_NAME}")
        manifest.save(pack, manifest.blank(args.name, args.title))
    data = manifest.load(pack)
    if args.title:
        data["title"] = args.title

    if not data["sources"] and not manifest.pack_files(pack):
        raise EfError(
            f"{pack.name} has no sources. Add material with `ef clone`, `ef add`, or by "
            f"writing markdown into {(pack / 'notes').name}/."
        )

    _reconcile_or_fail(pack, data, args.adopt_all)

    scaffolded = workspace.scaffold_gitignore()
    if scaffolded:
        say(f"scaffolded {scaffolded.name} (clones and graphs ignored; raw/ and notes/ tracked)")

    scoping.write_ignore(pack, data["sources"])

    if args.code_only:
        hint = extraction.code_only_warning(data["sources"])
        if hint:
            warn(hint)

    backend = extraction.resolve_backend(data, args.backend, needs_llm=not args.code_only)
    vision = extraction.check_vision(backend, data["sources"])
    if vision:
        raise EfError(vision)

    extraction_data: dict[str, object] = {"code_only": bool(args.code_only)}
    if backend:
        extraction_data["backend"] = backend
    data["extraction"] = extraction_data
    manifest.save(pack, data)

    say(
        f"extracting {pack.name} ({'code-only, AST' if args.code_only else f'semantic via {backend}'})"
    )
    extraction.extract(pack, code_only=args.code_only, backend=backend, force=args.force)

    sidecars = extraction.write_pdf_sidecars(pack)
    if sidecars:
        say(f"wrote {len(sidecars)} PDF text sidecar(s)")

    say("naming communities and writing the graph report")
    extraction.cluster(pack, backend)

    _finish(pack, data, path_taken="code-only" if args.code_only else f"semantic/{backend}")
    report_snippet(pack, data["name"])


def cmd_update(args: argparse.Namespace) -> None:
    pack = workspace.resolve_pack(args.name)
    data = manifest.load(pack)

    refreshable = manifest.refreshable(data)
    if not refreshable:
        say("no refreshable sources; fetched pages and papers have no refresh lifecycle")
        return

    changed: list[str] = []
    pulled: list[tuple[dict, str]] = []
    for entry in refreshable:
        result = sources.pull(pack, entry)
        pulled.append((entry, result.after))
        if result.moved:
            count = len(result.changed)
            say(f"{entry['path']}: {result.before[:7]} -> {result.after[:7]} ({count} file(s))")
        else:
            say(f"{entry['path']}: up to date at {result.after[:7]}")
        changed += result.changed

    def record_revs() -> None:
        """Stamp the pulled revs only once the graph reflects them.

        Saving earlier would make a failed extraction unrecoverable: the manifest
        would claim a rev the graph was never built from, and the next update would
        see no changes and skip the work.
        """
        for entry, rev in pulled:
            entry["rev"] = rev
            entry["last_synced"] = manifest.now()
        manifest.save(pack, data)

    decision = extraction.decide_update_path(changed, force=args.force)
    say(f"path: {decision.kind} — {decision.reason}")

    if decision.kind == "noop":
        record_revs()
        return

    if decision.kind == "ast":
        say("updating graph (AST only, no LLM cost)")
        extraction.update_ast(pack)
    else:
        backend = extraction.resolve_backend(data, args.backend, needs_llm=True)
        vision = extraction.check_vision(backend, data["sources"])
        if vision:
            raise EfError(vision)
        data.setdefault("extraction", {})["backend"] = backend
        say(f"semantic re-extraction via {backend} (spends LLM tokens)")
        scoping.write_ignore(pack, data["sources"])
        extraction.extract(
            pack,
            code_only=data.get("extraction", {}).get("code_only", False),
            backend=backend,
            force=args.force,
        )
        extraction.write_pdf_sidecars(pack)
        say("naming communities and writing the graph report")
        extraction.cluster(pack, backend)

    record_revs()
    _finish(pack, data, path_taken=decision.kind)


def cmd_sync(args: argparse.Namespace) -> None:
    """Rewrite the manifest and skill from the graph already on disk."""
    pack = workspace.resolve_pack(args.name)
    data = manifest.load(pack)
    _finish(pack, data, path_taken="from graph on disk")


def cmd_list(args: argparse.Namespace) -> None:
    packs = workspace.list_packs()
    if not packs:
        say(f"no packs in {workspace.experts_dir()}")
        return
    for pack in packs:
        data = manifest.load(pack)
        graph = data.get("graph") or {}
        size = workspace.tree_bytes(pack) / 1e6
        kinds = manifest.sources_by_kind(data)
        composition = (
            ", ".join(f"{count} {kind}" for kind, count in sorted(kinds.items())) or "empty"
        )
        print(
            f"{data['name']:<16} {graph.get('nodes', 0):>8,} nodes  {size:>7.1f} MB  "
            f"{(graph.get('last_reconciled') or 'never')[:10]}  {composition}"
        )


def cmd_new(args: argparse.Namespace) -> None:
    pack = workspace.experts_dir() / args.name
    if workspace.is_pack(pack):
        raise EfError(f"{args.name} is already a pack ({pack})")
    workspace.pack_for_build(args.name)
    manifest.save(pack, manifest.blank(args.name, args.title))
    say(f"created {relative_to_cwd(pack)}")
    say(f"next: ef clone {args.name} <url>, or ef add {args.name} <path-or-url>")


#: The noun for one file in a layer — "raw" has no better name than the layer
#: itself, "notes" is pluralized already so its singular reads as "note".
_LAYER_NOUN = {"raw": "raw file", "notes": "note"}


def _describe_counts(counts: dict[str, int], sep: str) -> str:
    return sep.join(
        f"{n} {_LAYER_NOUN.get(layer, layer)}(s)" for layer, n in sorted(counts.items())
    )


def cmd_delete(args: argparse.Namespace) -> None:
    pack = workspace.resolve_pack(args.name)
    counts = manifest.irreplaceable_counts(pack)

    if counts and not args.force:
        raise EfError(
            f"{args.name} has irreplaceable content that cannot be rebuilt: "
            f"{_describe_counts(counts, ', ')}. Re-run with --force to delete anyway."
        )

    if counts:
        reply = input(
            f"[ef] '{args.name}' has {_describe_counts(counts, ' and ')} that cannot be "
            "rebuilt. Delete anyway? [y/N] "
        )
        if reply.strip().lower() != "y":
            say("aborted")
            return

    shutil.rmtree(pack)
    say(f"deleted {args.name}")


def cmd_run(args: argparse.Namespace) -> None:
    from . import server

    pack = workspace.resolve_pack(args.name)
    server.serve(pack)


# --------------------------------------------------------------------------- #


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        prog="ef",
        description=(
            "Build and serve experts over packs of code, docs, papers and notes. "
            "Packs live in ./experts/<name> relative to the current directory."
        ),
    )
    sub = root.add_subparsers(dest="command", required=True)

    def with_pack(command: argparse.ArgumentParser) -> argparse.ArgumentParser:
        command.add_argument(
            "name", nargs="?", help="pack under ./experts/ (default: the cwd, if it is a pack)"
        )
        return command

    new = sub.add_parser("new", help="scaffold an empty pack")
    new.add_argument("name", help="pack under ./experts/")
    new.add_argument("--title", help="human label used in the skill prose")
    new.set_defaults(func=cmd_new)

    clone = with_pack(sub.add_parser("clone", help="clone a git source into a pack"))
    clone.add_argument("url", help="git URL")
    clone.add_argument("--title", help="human label used in the skill prose")
    clone.add_argument(
        "--paths",
        nargs="+",
        metavar="PATH",
        help="graph only these paths inside the clone (e.g. content/docs)",
    )
    clone.set_defaults(func=cmd_clone)

    add = with_pack(sub.add_parser("add", help="fetch a URL, or adopt a local file or directory"))
    add.add_argument("target", help="URL to fetch, or a local path to adopt")
    add.add_argument("--title", help="human label used in the skill prose")
    add.add_argument("--contributor", help="recorded in the provenance frontmatter")
    add.set_defaults(func=cmd_add)

    build = with_pack(sub.add_parser("build", help="extract the whole pack into one graph"))
    build.add_argument("--title", help="human label used in the skill prose")
    build.add_argument(
        "--code-only",
        action="store_true",
        help="AST only, no LLM cost. Drops docs, papers and images from the semantic pass.",
    )
    build.add_argument("--backend", help="LLM backend for semantic extraction")
    build.add_argument(
        "--force",
        action="store_true",
        help="re-extract every file, ignoring the semantic cache and the incremental gate",
    )
    build.add_argument(
        "--adopt-all",
        action="store_true",
        help="create manifest entries for every unmanifested file in one pass",
    )
    build.set_defaults(func=cmd_build)

    update = with_pack(sub.add_parser("update", help="pull git sources and refresh the graph"))
    update.add_argument("--backend", help="LLM backend, if a semantic re-extract is needed")
    update.add_argument(
        "--force",
        action="store_true",
        help="re-extract from scratch even if nothing changed, ignoring the semantic cache",
    )
    update.set_defaults(func=cmd_update)

    sync = with_pack(
        sub.add_parser("sync", help="rewrite the manifest and skill from the graph on disk")
    )
    sync.set_defaults(func=cmd_sync)

    listing = sub.add_parser("list", help="show every pack in the workspace")
    listing.set_defaults(func=cmd_list)

    delete = sub.add_parser("delete", help="delete a pack")
    delete.add_argument("name", help="pack under ./experts/")
    delete.add_argument(
        "--force",
        action="store_true",
        help="delete even if raw/ or notes/ hold content that cannot be rebuilt",
    )
    delete.set_defaults(func=cmd_delete)

    run = with_pack(sub.add_parser("run", help="serve a pack over stdio for an MCP client"))
    run.set_defaults(func=cmd_run)

    return root


def main() -> None:
    args = parser().parse_args()
    try:
        args.func(args)
    except EfError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    except KeyboardInterrupt:
        raise SystemExit(130) from None


if __name__ == "__main__":
    main()
