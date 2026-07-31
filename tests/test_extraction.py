"""Update-path branching and backend resolution: where the expensive mistake lives."""

from __future__ import annotations

import pytest

from ef import EfError, extraction


def captured_argv(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Record the argv extract() hands to graphify's sys.argv-driven CLI branch."""
    seen: list[str] = []

    def fake_dispatch(argv: list[str], command: str) -> None:
        seen.extend(argv)

    monkeypatch.setattr(extraction, "_dispatch", fake_dispatch)
    return seen


def test_extraction_never_honors_vcs_ignore_files(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A workspace gitignores its packs, and graphify walks up to the VCS root.

    Left on, the very rule that keeps a pack out of git empties its corpus, and
    gitignore's parent-exclusion rule means no negation inside the pack wins it back.
    """
    argv = captured_argv(monkeypatch)
    extraction.extract(tmp_path, code_only=False, backend="openai")
    assert "--no-gitignore" in argv


def test_the_cheap_path_also_ignores_vcs_ignore_files(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    argv = captured_argv(monkeypatch)
    extraction.extract(tmp_path, code_only=True, backend=None)
    assert "--no-gitignore" in argv
    assert "--code-only" in argv


def test_extraction_does_not_force_by_default(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """graphify reads --force as "skip the semantic cache read".

    Passing it unconditionally re-dispatches every file in the pack on every
    refresh, so a one-file change re-pays for the whole corpus.
    """
    argv = captured_argv(monkeypatch)
    extraction.extract(tmp_path, code_only=False, backend="openai")
    assert "--force" not in argv


def test_forcing_is_the_callers_choice(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    argv = captured_argv(monkeypatch)
    extraction.extract(tmp_path, code_only=False, backend="openai", force=True)
    assert "--force" in argv


def test_no_changes_is_a_noop() -> None:
    decision = extraction.decide_update_path([])
    assert decision.kind == "noop"
    assert not decision.needs_llm


def test_code_only_changes_take_the_free_ast_path() -> None:
    decision = extraction.decide_update_path(
        ["repos/acme/lib/src/core.ts", "repos/acme/lib/src/other.py"]
    )
    assert decision.kind == "ast"
    assert not decision.needs_llm


def test_a_doc_change_forces_the_semantic_path() -> None:
    """The AST path preserves existing semantic nodes, so a rewritten doc leaves stale ones."""
    decision = extraction.decide_update_path(["repos/acme/lib/docs/guide.md"])
    assert decision.kind == "semantic"
    assert decision.needs_llm
    assert "guide.md" in decision.reason


@pytest.mark.parametrize("path", ["a/paper.pdf", "a/diagram.png", "a/notes.txt", "a/page.html"])
def test_every_prose_kind_forces_semantic(path: str) -> None:
    assert extraction.decide_update_path([path]).kind == "semantic"


def test_mixed_changes_take_the_semantic_path() -> None:
    decision = extraction.decide_update_path(["src/core.ts", "docs/guide.md"])
    assert decision.kind == "semantic"


def test_force_upgrades_an_empty_change_set() -> None:
    decision = extraction.decide_update_path([], force=True)
    assert decision.kind == "semantic"
    assert decision.reason == "forced"


def test_the_reason_names_the_files_that_drove_the_choice() -> None:
    decision = extraction.decide_update_path(["a.md", "b.md", "c.md", "d.md", "e.md"])
    assert "+2 more" in decision.reason


# --------------------------------------------------------------------------- #
# backend resolution


def test_a_cheap_path_needs_no_backend() -> None:
    assert extraction.resolve_backend({}, None, needs_llm=False) is None


def test_an_explicit_flag_overrides_the_persisted_backend() -> None:
    data = {"extraction": {"backend": "gemini"}}
    assert extraction.resolve_backend(data, "claude-cli", needs_llm=True) == "claude-cli"


def test_the_persisted_backend_is_reused_when_the_flag_is_absent() -> None:
    data = {"extraction": {"backend": "claude-cli"}}
    assert extraction.resolve_backend(data, None, needs_llm=True) == "claude-cli"


def test_no_backend_anywhere_names_claude_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("graphify.llm.detect_backend", lambda: None)

    with pytest.raises(EfError) as caught:
        extraction.resolve_backend({}, None, needs_llm=True)

    assert "claude-cli" in str(caught.value)
    assert "--code-only" in str(caught.value)


def test_auto_detection_is_the_last_resort(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("graphify.llm.detect_backend", lambda: "openai")
    assert extraction.resolve_backend({}, None, needs_llm=True) == "openai"


# --------------------------------------------------------------------------- #
# pre-build warnings


def test_code_only_explains_what_it_would_drop() -> None:
    hint = extraction.code_only_warning([{"kind": "paper"}, {"kind": "note"}])
    assert hint is not None
    assert "2 note/paper source(s)" in hint


def test_code_only_is_silent_on_a_pure_code_pack() -> None:
    assert extraction.code_only_warning([{"kind": "code"}]) is None


def test_images_need_a_vision_capable_backend() -> None:
    message = extraction.check_vision("deepseek", [{"kind": "image", "path": "raw/a.png"}])
    assert message is not None
    assert "vision" in message


def test_a_vision_backend_passes() -> None:
    assert extraction.check_vision("claude-cli", [{"kind": "image", "path": "raw/a.png"}]) is None


def test_no_images_means_no_vision_check() -> None:
    assert extraction.check_vision("deepseek", [{"kind": "code"}]) is None


def test_an_almost_empty_graph_over_prose_warns() -> None:
    facts = {"nodes": 3}
    assert extraction.hollow_warning(facts, [{"kind": "paper"}] * 3) is not None


def test_a_healthy_graph_does_not_warn() -> None:
    assert extraction.hollow_warning({"nodes": 400}, [{"kind": "paper"}] * 3) is None
