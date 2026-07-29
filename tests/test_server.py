"""Server preflight and read_source — the one tool ef invents rather than inherits."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ef import EfError, extraction, server


def build_graph(pack: Path) -> None:
    (pack / "graph").mkdir(exist_ok=True)
    (pack / "graph/graph.json").write_text(json.dumps({"nodes": [], "links": []}), encoding="utf-8")


def test_preflight_rejects_a_non_pack_directory(tmp_path: Path) -> None:
    """A bad cwd in a client config has to be diagnosable, not a silent failed handshake."""
    with pytest.raises(EfError) as caught:
        server.preflight(tmp_path)

    assert "expert.json" in str(caught.value)
    assert "cwd" in str(caught.value)


def test_preflight_rejects_a_pack_with_no_graph(pack: Path) -> None:
    with pytest.raises(EfError, match="run `ef build`"):
        server.preflight(pack)


def test_preflight_passes_on_a_built_pack(pack: Path) -> None:
    build_graph(pack)
    assert server.preflight(pack) == pack / "graph/graph.json"


# --------------------------------------------------------------------------- #
# read_source across every layer


def test_reads_a_file_from_the_repos_layer(pack: Path) -> None:
    result = server.read_material(pack, "repos/acme/lib/src/core.ts", None, 0, 10)
    assert "answer = 42" in result["text"]
    assert result["file"] == "repos/acme/lib/src/core.ts"


def test_reads_a_fetched_page_from_the_raw_layer(pack: Path) -> None:
    result = server.read_material(pack, "raw/page.md", None, 0, 20)
    assert "Body text." in result["text"]


def test_reads_an_authored_note_from_the_notes_layer(pack: Path) -> None:
    result = server.read_material(pack, "notes/layer-memoization.md", None, 0, 10)
    assert "memoized" in result["text"]


def test_a_line_window_anchors_on_the_source_location(pack: Path) -> None:
    long_file = pack / "notes/long.md"
    long_file.write_text("\n".join(f"line {i}" for i in range(1, 101)), encoding="utf-8")

    result = server.read_material(pack, "notes/long.md", "50-55", 2, 3)

    assert result["start_line"] == 48
    assert result["text"].startswith("line 48")
    assert result["truncated"]


def test_a_pdf_is_served_from_its_sidecar_with_lines_reported_inapplicable(pack: Path) -> None:
    """PDFs have no char-offset model, so a line anchor has nothing behind it."""
    sidecar = pack / "graph/converted" / extraction.sidecar_name(pack, pack / "raw/paper.pdf")
    sidecar.parent.mkdir(parents=True, exist_ok=True)
    sidecar.write_text("<!-- converted from paper.pdf -->\n\nPaper body.\n", encoding="utf-8")

    result = server.read_material(pack, "raw/paper.pdf", "12", 5, 60)

    assert "Paper body." in result["text"]
    assert "no char-offset model" in result["lines_not_applicable"]
    assert "start_line" not in result


def test_a_pdf_with_no_sidecar_says_to_rebuild(pack: Path) -> None:
    result = server.read_material(pack, "raw/paper.pdf", None, 0, 10)
    assert "re-run `ef build`" in result["error"]


def test_a_path_escaping_the_pack_root_is_refused(pack: Path) -> None:
    """A crafted node id must not read the host filesystem."""
    result = server.read_material(pack, "../../../../etc/passwd", None, 0, 10)
    assert result["error"] == "path escapes the pack root"


def test_a_symlink_out_of_the_pack_is_refused(pack: Path) -> None:
    outside = pack.parent.parent / "secret.txt"
    outside.write_text("secret\n", encoding="utf-8")
    (pack / "notes/link.md").symlink_to(outside)

    result = server.read_material(pack, "notes/link.md", None, 0, 10)

    assert result["error"] == "path escapes the pack root"


def test_a_missing_file_is_reported_as_absent(pack: Path) -> None:
    result = server.read_material(pack, "notes/nope.md", None, 0, 10)
    assert "not present in the pack" in result["error"]
