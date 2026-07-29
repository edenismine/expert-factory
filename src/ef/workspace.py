"""Workspace and pack resolution.

The workspace is the current working directory, the way `git` and `docker`
operate on a local tree rather than on their own install location. Nothing here
derives a path from this module's location.
"""

from __future__ import annotations

from pathlib import Path

from . import GRAPH_DIR_NAME, EfError

MANIFEST_NAME = "expert.json"
SKILL_NAME = "SKILL.md"
IGNORE_NAME = ".graphifyignore"
EXPERTS_DIR = "experts"

LAYERS = ("repos", "raw", "notes")

GITIGNORE_TEMPLATE = """\
# Written by ef on first build. Clones and graphs are large and reconstructible
# from expert.json's source list. raw/ and notes/ are deliberately NOT ignored:
# fetched material suffers link rot and notes are original work, so neither can
# be rebuilt.
experts/*/repos/
experts/*/graph/
"""


def workspace_root() -> Path:
    return Path.cwd().resolve()


def experts_dir(root: Path | None = None) -> Path:
    return (root or workspace_root()) / EXPERTS_DIR


def is_pack(path: Path) -> bool:
    return (path / MANIFEST_NAME).is_file()


def graph_dir(pack: Path) -> Path:
    return pack / GRAPH_DIR_NAME


def graph_json(pack: Path) -> Path:
    return graph_dir(pack) / "graph.json"


def resolve_pack(name: str | None, root: Path | None = None) -> Path:
    """Resolve a pack directory from a name, or from the cwd when name is None.

    No upward search: a client config states an exact `cwd`, and walking up would
    let a stray parent manifest capture a subdirectory silently.
    """
    root = root or workspace_root()
    if name is None:
        if not is_pack(root):
            raise EfError(
                f"{root} is not a pack: no {MANIFEST_NAME}. "
                f"Name a pack (`ef <verb> <name>`) or run from inside a pack directory."
            )
        return root

    pack = experts_dir(root) / name
    if not pack.is_dir():
        raise EfError(f"no such pack: {name} (looked in {experts_dir(root)})")
    return pack


def pack_for_build(name: str | None, root: Path | None = None) -> Path:
    """Resolve a pack, creating the directory when a name is given.

    Only `build`, `clone` and `add` may bring a pack into existence; every other
    verb goes through resolve_pack and fails on a name that does not exist.
    """
    root = root or workspace_root()
    if name is None:
        return resolve_pack(None, root)
    pack = experts_dir(root) / name
    for layer in LAYERS:
        (pack / layer).mkdir(parents=True, exist_ok=True)
    return pack


def list_packs(root: Path | None = None) -> list[Path]:
    directory = experts_dir(root)
    if not directory.is_dir():
        return []
    return sorted(d for d in directory.iterdir() if is_pack(d))


def scaffold_gitignore(root: Path | None = None) -> Path | None:
    """Write a workspace .gitignore when absent. An existing one is never touched."""
    root = root or workspace_root()
    target = root / ".gitignore"
    if target.exists():
        return None
    target.write_text(GITIGNORE_TEMPLATE, encoding="utf-8")
    return target


def tree_bytes(path: Path) -> int:
    if not path.is_dir():
        return path.stat().st_size if path.is_file() else 0
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
