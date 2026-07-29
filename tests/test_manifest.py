"""Manifest reconciliation: the guarantee that a built graph has complete provenance."""

from __future__ import annotations

from pathlib import Path

from ef import manifest


def test_clean_pack_reconciles(pack: Path) -> None:
    state = manifest.reconcile(pack, manifest.load(pack))
    assert state.ok
    assert state.strays == []
    assert state.orphans == []
    assert state.altered == []


def test_strays_are_all_listed(pack: Path) -> None:
    (pack / "raw/orphaned.md").write_text("no entry\n", encoding="utf-8")
    (pack / "notes/second.md").write_text("also no entry\n", encoding="utf-8")

    state = manifest.reconcile(pack, manifest.load(pack))

    assert not state.ok
    assert {p.name for p in state.strays} == {"orphaned.md", "second.md"}


def test_files_inside_a_clone_are_not_strays(pack: Path) -> None:
    """repos/ has one entry for the whole tree, not one per file."""
    (pack / "repos/acme/lib/src/extra.ts").write_text("export const x = 1\n", encoding="utf-8")
    assert manifest.reconcile(pack, manifest.load(pack)).ok


def test_adopt_all_classifies_kind_and_lifecycle(pack: Path) -> None:
    (pack / "raw/diagram.png").write_bytes(b"\x89PNG\r\n")
    (pack / "raw/spec.pdf").write_bytes(b"%PDF-1.4\n")
    (pack / "notes/finding.md").write_text("Research finding.\n", encoding="utf-8")
    data = manifest.load(pack)

    added = manifest.adopt(pack, data, manifest.reconcile(pack, data).strays)

    by_path = {e["path"]: e for e in added}
    assert by_path["raw/diagram.png"]["kind"] == "image"
    assert by_path["raw/spec.pdf"]["kind"] == "paper"
    assert by_path["notes/finding.md"]["kind"] == "note"
    assert all(e["lifecycle"] == "snapshot" for e in added)
    assert all(e["checksum"].startswith("sha256:") for e in added)
    assert manifest.reconcile(pack, data).ok


def test_adopt_lifts_provenance_frontmatter(pack: Path) -> None:
    (pack / "raw/fetched.md").write_text(
        "---\n"
        "source_url: https://arxiv.org/abs/2401.12345\n"
        "type: paper\n"
        "title: Structured Concurrency\n"
        "captured_at: 2026-07-21T09:00:00Z\n"
        "contributor: eden\n"
        "---\n\nAbstract.\n",
        encoding="utf-8",
    )
    data = manifest.load(pack)

    (entry,) = manifest.adopt(pack, data, manifest.reconcile(pack, data).strays)

    assert entry["name"] == "Structured Concurrency"
    assert entry["kind"] == "paper"
    assert entry["origin"] == {"type": "fetch", "url": "https://arxiv.org/abs/2401.12345"}
    assert entry["captured_at"] == "2026-07-21T09:00:00Z"
    assert entry["contributor"] == "eden"


def test_authored_note_has_no_fetch_origin(pack: Path) -> None:
    entry = manifest.snapshot_entry(pack, pack / "notes/layer-memoization.md", "notes")
    assert entry["origin"] == {"type": "authored"}
    assert entry["kind"] == "note"


def test_missing_file_is_an_orphan(pack: Path) -> None:
    (pack / "raw/page.md").unlink()

    state = manifest.reconcile(pack, manifest.load(pack))

    assert not state.ok
    assert state.orphans == ["raw/page.md"]


def test_missing_clone_is_an_orphan(pack: Path) -> None:
    import shutil

    shutil.rmtree(pack / "repos/acme/lib")

    state = manifest.reconcile(pack, manifest.load(pack))

    assert "repos/acme/lib" in state.orphans


def test_checksum_detects_a_mutated_snapshot(pack: Path) -> None:
    (pack / "raw/page.md").write_text("---\ntype: webpage\n---\n\nRewritten.\n", encoding="utf-8")

    state = manifest.reconcile(pack, manifest.load(pack))

    assert state.altered == ["raw/page.md"]
    assert state.ok, "an altered snapshot is information, not a broken pack"


def test_save_load_roundtrip_keeps_entries(pack: Path) -> None:
    data = manifest.load(pack)
    manifest.save(pack, data)
    assert manifest.load(pack)["sources"] == data["sources"]


def test_upsert_replaces_by_path(pack: Path) -> None:
    data = manifest.load(pack)
    before = len(data["sources"])

    manifest.upsert(data, {"path": "raw/page.md", "kind": "document", "name": "replaced"})

    assert len(data["sources"]) == before
    assert next(s for s in data["sources"] if s["path"] == "raw/page.md")["name"] == "replaced"


def test_sources_by_kind_counts_composition(pack: Path) -> None:
    counts = manifest.sources_by_kind(manifest.load(pack))
    assert counts == {"code": 1, "document": 1, "paper": 1, "note": 1}


def test_only_git_sources_are_refreshable(pack: Path) -> None:
    entries = manifest.refreshable(manifest.load(pack))
    assert [e["path"] for e in entries] == ["repos/acme/lib"]


def test_graph_output_is_not_reconciled(pack: Path) -> None:
    """A rebuild must never see the previous build's output as unmanifested material."""
    (pack / "graph/converted").mkdir(parents=True, exist_ok=True)
    (pack / "graph/converted/paper_abc12345.md").write_text("text\n", encoding="utf-8")
    assert manifest.reconcile(pack, manifest.load(pack)).ok
