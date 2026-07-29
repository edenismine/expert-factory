"""The generated skill and the printed client-config snippet."""

from __future__ import annotations

import json
from pathlib import Path

from ef import cli, manifest, skill

FACTS = {"nodes": 27729, "edges": 45530, "hubs": ["Effect", "Layer"], "extensions": ["ts", "md"]}


def multi_source() -> dict:
    data = manifest.blank("effect", "Effect TS")
    data["graph"] = {"nodes": 27729, "edges": 45530, "last_reconciled": "2026-07-29T10:12:03Z"}
    data["sources"] = (
        [{"kind": "code"}, {"kind": "code"}] + [{"kind": "paper"}] * 12 + [{"kind": "note"}] * 3
    )
    return data


def test_freshness_is_one_aggregate_line() -> None:
    line = skill.freshness_line(multi_source())
    assert line == "Built from 17 sources (2 git, 12 papers, 3 notes), last reconciled 2026-07-29."
    assert "\n" not in line


def test_a_single_source_pack_reads_naturally() -> None:
    data = manifest.blank("demo")
    data["graph"] = {"last_reconciled": "2026-07-29T10:00:00Z"}
    data["sources"] = [{"kind": "code"}]
    assert skill.freshness_line(data) == "Built from 1 source (1 git), last reconciled 2026-07-29."


def test_the_skill_never_claims_to_reflect_one_commit() -> None:
    text = skill.render(multi_source(), FACTS)
    assert "one commit" not in text
    assert "built_at_commit" not in text


def test_the_skill_carries_no_per_source_table() -> None:
    """A table grows without bound, and a skill competes for the context budget it saves."""
    text = skill.render(multi_source(), FACTS)
    assert "|" not in text


def test_the_skill_keeps_the_ground_claims_framing() -> None:
    text = skill.render(multi_source(), FACTS)
    assert "Ground every" in text
    assert "rather than in recollection" in text


def test_read_source_is_described_across_all_layers() -> None:
    """Reworded to cover all layers rather than "the code"."""
    collapsed = " ".join(skill.render(multi_source(), FACTS).split())
    assert "source code, a fetched page, a paper, or a note" in collapsed
    assert "On a PDF-backed node the line arguments do not apply" in collapsed


def test_the_skill_reports_counts_and_scope() -> None:
    text = skill.render(multi_source(), FACTS)
    assert "27,729 nodes, 45,530 edges" in text
    assert "Effect, Layer" in text
    assert "ts, md" in text


def test_the_skill_says_stdio_not_http() -> None:
    text = skill.render(multi_source(), FACTS)
    assert "over stdio" in text
    assert "http://" not in text


def test_the_skill_is_written_with_frontmatter(tmp_path: Path) -> None:
    written = skill.write(tmp_path, multi_source(), FACTS)
    assert written.read_text(encoding="utf-8").startswith("---\nname: effect-expert\n")


# --------------------------------------------------------------------------- #
# the client-config snippet


def test_the_snippet_mounts_the_pack_by_cwd(tmp_path: Path) -> None:
    entry = json.loads(cli.client_snippet(tmp_path, "effect"))
    (config,) = entry.values()

    assert config["command"] == "ef"
    assert config["args"] == ["run"]
    assert config["cwd"] == str(tmp_path.resolve())


def test_the_snippet_cwd_is_absolute(pack: Path, monkeypatch) -> None:
    """A client resolves cwd against its own working directory, not the workspace."""
    monkeypatch.chdir(pack)
    entry = json.loads(cli.client_snippet(Path("."), "demo"))
    (config,) = entry.values()

    assert Path(config["cwd"]).is_absolute()
    assert config["cwd"] == str(pack.resolve())


def test_the_snippet_names_no_port_or_url(tmp_path: Path) -> None:
    """A stdio server is addressed by its cwd; there is no port, url, or transport type."""
    (config,) = json.loads(cli.client_snippet(tmp_path, "effect")).values()
    assert set(config) == {"command", "args", "cwd"}
