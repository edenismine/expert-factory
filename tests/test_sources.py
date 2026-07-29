"""Acquisition: video rejection, owner/repo splitting, adoption, and pull refusal."""

from __future__ import annotations

from pathlib import Path

import pytest

from ef import EfError, sources


@pytest.mark.parametrize(
    "target",
    [
        "https://www.youtube.com/watch?v=abc123",
        "https://youtu.be/abc123",
        "https://vimeo.com/12345",
        "/tmp/talk.mp4",
        "clip.webm",
    ],
)
def test_video_is_rejected_with_a_not_supported_message(target: str) -> None:
    with pytest.raises(EfError, match="not supported yet"):
        sources.reject_video(target)


def test_video_rejection_writes_nothing_into_the_pack(pack: Path) -> None:
    before = sorted(p.relative_to(pack) for p in pack.rglob("*"))

    with pytest.raises(EfError, match="not supported yet"):
        sources.fetch(pack, "https://www.youtube.com/watch?v=abc123", None)

    assert sorted(p.relative_to(pack) for p in pack.rglob("*")) == before


def test_a_non_video_url_is_not_rejected() -> None:
    sources.reject_video("https://arxiv.org/abs/2401.12345")


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://github.com/effect-ts/effect", ("effect-ts", "effect")),
        ("https://github.com/effect-ts/effect.git", ("effect-ts", "effect")),
        ("https://github.com/effect-ts/effect/", ("effect-ts", "effect")),
        ("git@github.com:effect-ts/effect.git", ("effect-ts", "effect")),
    ],
)
def test_owner_repo_splitting(url: str, expected: tuple[str, str]) -> None:
    assert sources.owner_repo(url) == expected


def test_owner_repo_needs_two_segments() -> None:
    with pytest.raises(EfError, match="cannot derive owner/repo"):
        sources.owner_repo("https://example.com/lonely")


def test_a_non_url_target_is_not_fetched(pack: Path) -> None:
    with pytest.raises(EfError, match="not a fetchable URL"):
        sources.fetch(pack, "ftp://example.com/paper.pdf", None)


# --------------------------------------------------------------------------- #
# local adoption


def test_a_local_markdown_file_is_adopted_as_a_note(pack: Path, tmp_path: Path) -> None:
    mine = tmp_path / "finding.md"
    mine.write_text("Research finding.\n", encoding="utf-8")

    (adopted,) = sources.adopt_path(pack, mine)

    assert adopted == pack / "notes/finding.md"
    assert adopted.read_text(encoding="utf-8") == "Research finding.\n"


def test_a_local_pdf_is_adopted_into_raw(pack: Path, tmp_path: Path) -> None:
    """The fetched-versus-authored distinction stays visible in the layout."""
    mine = tmp_path / "paper.pdf"
    mine.write_bytes(b"%PDF-1.4\n")

    (adopted,) = sources.adopt_path(pack, mine)

    assert adopted == pack / "raw/paper.pdf"


def test_a_directory_is_adopted_recursively(pack: Path, tmp_path: Path) -> None:
    tree = tmp_path / "material"
    (tree / "deep").mkdir(parents=True)
    (tree / "a.md").write_text("a\n", encoding="utf-8")
    (tree / "deep/b.pdf").write_bytes(b"%PDF\n")

    adopted = sources.adopt_path(pack, tree)

    assert {p.relative_to(pack).as_posix() for p in adopted} == {
        "notes/a.md",
        "raw/deep/b.pdf",
    }


def test_adopting_a_missing_path_is_a_clear_error(pack: Path, tmp_path: Path) -> None:
    with pytest.raises(EfError, match="no such path"):
        sources.adopt_path(pack, tmp_path / "nope.md")


def test_a_directory_holding_video_is_rejected_before_copying(pack: Path, tmp_path: Path) -> None:
    tree = tmp_path / "material"
    tree.mkdir()
    (tree / "notes.md").write_text("fine\n", encoding="utf-8")
    (tree / "talk.mp4").write_bytes(b"\x00")

    with pytest.raises(EfError, match="not supported yet"):
        sources.adopt_path(pack, tree)

    assert not (pack / "notes/notes.md").exists(), "nothing is copied when any file is rejected"


# --------------------------------------------------------------------------- #
# pull


def test_pull_refuses_a_clone_with_local_modifications(pack: Path) -> None:
    """Work forgotten in a clone is never discarded."""
    (pack / "repos/acme/lib/src/core.ts").write_text("export const answer = 43\n", encoding="utf-8")

    with pytest.raises(EfError, match="local modifications"):
        sources.pull(pack, {"path": "repos/acme/lib"})


def test_pull_rejects_a_directory_that_is_not_a_checkout(pack: Path) -> None:
    with pytest.raises(EfError, match="not a git checkout"):
        sources.pull(pack, {"path": "raw"})
