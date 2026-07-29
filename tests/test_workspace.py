"""Pack resolution and workspace scaffolding: the "wiring is right" tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from ef import EfError, workspace


def test_a_name_resolves_under_experts(pack: Path, workspace_root: Path) -> None:
    assert workspace.resolve_pack("demo") == workspace_root / "experts" / "demo"


def test_an_unknown_name_is_a_clear_error(workspace_root: Path) -> None:
    with pytest.raises(EfError, match="no such pack: typo"):
        workspace.resolve_pack("typo")


def test_an_omitted_name_accepts_a_cwd_holding_a_manifest(
    pack: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(pack)
    assert workspace.resolve_pack(None) == pack


def test_an_omitted_name_rejects_a_non_pack_cwd(workspace_root: Path) -> None:
    with pytest.raises(EfError, match="is not a pack"):
        workspace.resolve_pack(None)


def test_resolution_never_walks_upward(pack: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A stray parent manifest must not capture a subdirectory silently."""
    inner = pack / "notes"
    monkeypatch.chdir(inner)

    with pytest.raises(EfError, match="is not a pack"):
        workspace.resolve_pack(None)


def test_pack_for_build_creates_the_layers(workspace_root: Path) -> None:
    created = workspace.pack_for_build("fresh")
    for layer in workspace.LAYERS:
        assert (created / layer).is_dir()


def test_list_packs_finds_only_directories_with_a_manifest(
    pack: Path, workspace_root: Path
) -> None:
    (workspace_root / "experts" / "half-built").mkdir()
    assert [p.name for p in workspace.list_packs()] == ["demo"]


# --------------------------------------------------------------------------- #
# scaffolding


def test_a_gitignore_is_written_when_absent(workspace_root: Path) -> None:
    written = workspace.scaffold_gitignore()
    assert written is not None
    assert written.read_text(encoding="utf-8") == workspace.GITIGNORE_TEMPLATE


def test_the_scaffolded_rules_ignore_clones_and_graphs(workspace_root: Path) -> None:
    text = workspace.scaffold_gitignore().read_text(encoding="utf-8")
    assert "experts/*/repos/" in text
    assert "experts/*/graph/" in text


def test_raw_notes_and_metadata_stay_tracked(workspace_root: Path) -> None:
    """Fetched material suffers link rot and notes are original work: neither rebuilds."""
    text = workspace.scaffold_gitignore().read_text(encoding="utf-8")
    for tracked in ("raw/", "notes/", "expert.json", "SKILL.md"):
        assert f"\n{tracked}" not in text
        assert not any(line.strip() == tracked for line in text.splitlines())


def test_an_existing_gitignore_is_never_touched(workspace_root: Path) -> None:
    mine = workspace_root / ".gitignore"
    mine.write_text("my own rules\n", encoding="utf-8")

    assert workspace.scaffold_gitignore() is None
    assert mine.read_text(encoding="utf-8") == "my own rules\n"
