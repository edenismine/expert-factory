"""ef new and ef delete — the ops that create and destroy a pack directory."""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from ef import EfError, cli, manifest, workspace


def new_args(name: str, title: str | None = None) -> argparse.Namespace:
    return argparse.Namespace(name=name, title=title)


def delete_args(name: str, force: bool = False) -> argparse.Namespace:
    return argparse.Namespace(name=name, force=force)


def test_new_scaffolds_dirs_and_a_blank_manifest(workspace_root: Path) -> None:
    cli.cmd_new(new_args("demo"))

    home = workspace_root / "experts" / "demo"
    assert workspace.is_pack(home)
    for layer in workspace.LAYERS:
        assert (home / layer).is_dir()
    assert manifest.load(home)["sources"] == []


def test_new_applies_a_title(workspace_root: Path) -> None:
    cli.cmd_new(new_args("demo", title="Demo Expert"))

    data = manifest.load(workspace_root / "experts" / "demo")
    assert data["title"] == "Demo Expert"


def test_new_refuses_an_existing_pack(pack: Path) -> None:
    with pytest.raises(EfError, match="already a pack"):
        cli.cmd_new(new_args("demo"))


def test_new_adopts_a_directory_that_exists_but_is_not_yet_a_pack(workspace_root: Path) -> None:
    (workspace_root / "experts" / "demo").mkdir(parents=True)

    cli.cmd_new(new_args("demo"))

    assert workspace.is_pack(workspace_root / "experts" / "demo")


def test_delete_removes_a_pack_with_no_irreplaceable_content(workspace_root: Path) -> None:
    cli.cmd_new(new_args("demo"))

    cli.cmd_delete(delete_args("demo"))

    assert not (workspace_root / "experts" / "demo").exists()


def test_delete_refuses_raw_or_notes_content_without_force(pack: Path) -> None:
    with pytest.raises(EfError, match="irreplaceable"):
        cli.cmd_delete(delete_args("demo"))

    assert pack.exists()


def test_delete_names_the_actual_counts(pack: Path) -> None:
    with pytest.raises(EfError, match=r"1 note\(s\).*2 raw file\(s\)"):
        cli.cmd_delete(delete_args("demo"))


def test_delete_guards_on_a_dotfile_too(workspace_root: Path) -> None:
    cli.cmd_new(new_args("demo"))
    hidden = workspace_root / "experts" / "demo" / "notes" / ".hidden.md"
    hidden.write_text("secret note\n", encoding="utf-8")

    with pytest.raises(EfError, match="irreplaceable"):
        cli.cmd_delete(delete_args("demo"))

    assert hidden.exists()


def test_delete_prompts_and_aborts_on_no(pack: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("builtins.input", lambda _: "n")

    cli.cmd_delete(delete_args("demo", force=True))

    assert pack.exists()


def test_delete_prompts_and_proceeds_on_yes(pack: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("builtins.input", lambda _: "y")

    cli.cmd_delete(delete_args("demo", force=True))

    assert not pack.exists()


def test_delete_names_a_missing_pack(workspace_root: Path) -> None:
    with pytest.raises(EfError, match="no such pack"):
        cli.cmd_delete(delete_args("ghost"))
