from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from ef import manifest


def git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True)


@pytest.fixture(name="git")
def git_fixture():
    """The same git runner conftest builds packs with, for tests that add commits."""
    return git


@pytest.fixture
def workspace_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An empty workspace, with the cwd pointed at it as every verb expects."""
    root = tmp_path / "ws"
    (root / "experts").mkdir(parents=True)
    monkeypatch.chdir(root)
    return root


@pytest.fixture
def pack(workspace_root: Path) -> Path:
    """A synthetic pack: a small fake clone, two raw/ files with frontmatter, a note.

    Every entry is manifested, so the pack reconciles clean and a test that wants
    a stray creates one itself.
    """
    home = workspace_root / "experts" / "demo"
    for layer in ("repos/acme/lib/src", "raw", "notes", "graph"):
        (home / layer).mkdir(parents=True)

    clone = home / "repos/acme/lib"
    (clone / "src/core.ts").write_text("export const answer = 42\n", encoding="utf-8")
    (clone / "README.md").write_text("# acme lib\n", encoding="utf-8")
    (clone / "docs").mkdir()
    (clone / "docs/guide.md").write_text("# guide\n", encoding="utf-8")
    git(clone, "init", "-q")
    git(clone, "add", "-A")
    git(clone, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init")

    (home / "raw/page.md").write_text(
        "---\n"
        "source_url: https://example.com/post\n"
        "type: webpage\n"
        "title: A Post\n"
        "captured_at: 2026-07-01T09:00:00Z\n"
        "contributor: eden\n"
        "---\n\n"
        "Body text.\n",
        encoding="utf-8",
    )
    (home / "raw/paper.pdf").write_bytes(b"%PDF-1.4 not a real pdf\n")
    (home / "notes/layer-memoization.md").write_text("Layers are memoized.\n", encoding="utf-8")

    data = manifest.blank("demo", "Demo Expert")
    rev = subprocess.run(
        ["git", "-C", str(clone), "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()
    data["sources"].append(
        manifest.git_entry(home, clone, "https://github.com/acme/lib", "main", rev)
    )
    for rel in ("raw/page.md", "raw/paper.pdf", "notes/layer-memoization.md"):
        layer = rel.split("/")[0]
        data["sources"].append(manifest.snapshot_entry(home, home / rel, layer))
    manifest.save(home, data)
    return home
