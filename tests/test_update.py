"""What `ef update` hands to graphify — the verb where a mistake costs real money."""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from ef import cli, extraction, manifest


@pytest.fixture
def moved_pack(pack: Path, git) -> Path:
    """A pack whose clone has a doc commit the manifest rev predates.

    A prose change is what forces the expensive semantic path, so this is the
    fixture that exercises the paid branch.
    """
    clone = pack / "repos/acme/lib"
    (clone / "docs/guide.md").write_text("# guide, rewritten\n", encoding="utf-8")
    git(clone, "add", "-A")
    git(clone, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "docs")
    git(clone, "remote", "add", "origin", str(clone))
    return pack


def run_update(monkeypatch: pytest.MonkeyPatch, *, force: bool = False) -> list[list[str]]:
    """Drive cmd_update, recording the argv of every graphify command it dispatches."""
    dispatched: list[list[str]] = []
    monkeypatch.setattr(extraction, "_dispatch", lambda argv, command: dispatched.append(argv))
    monkeypatch.setattr(extraction, "write_pdf_sidecars", lambda pack: [])
    monkeypatch.setattr(
        extraction,
        "graph_facts",
        lambda pack: {"nodes": 900, "edges": 1200, "hubs": [], "extensions": []},
    )

    args = argparse.Namespace(name=None, backend="openai", force=force)
    cli.cmd_update(args)
    return dispatched


def test_a_refresh_reuses_the_semantic_cache(moved_pack: Path, monkeypatch) -> None:
    """graphify reads --force as "skip the semantic cache read", so passing it on
    every refresh re-dispatches the whole corpus to pay for a handful of changes."""
    monkeypatch.chdir(moved_pack)
    extract = run_update(monkeypatch)[0]

    assert extract[1] == "extract"
    assert "--force" not in extract


def test_forcing_a_refresh_bypasses_the_cache(moved_pack: Path, monkeypatch) -> None:
    monkeypatch.chdir(moved_pack)
    extract = run_update(monkeypatch, force=True)[0]

    assert "--force" in extract


def test_a_refresh_leaves_no_report_describing_the_old_graph(moved_pack: Path, monkeypatch) -> None:
    """extract detects communities but never names them or writes GRAPH_REPORT.md,
    so without a clustering pass the pack keeps the previous build's report."""
    monkeypatch.chdir(moved_pack)
    commands = [argv[1] for argv in run_update(monkeypatch)]

    assert commands == ["extract", "cluster-only"]


def test_a_refresh_records_the_rev_it_built_from(moved_pack: Path, monkeypatch) -> None:
    monkeypatch.chdir(moved_pack)
    before = manifest.load(moved_pack)["sources"][0]["rev"]

    run_update(monkeypatch)

    assert manifest.load(moved_pack)["sources"][0]["rev"] != before
