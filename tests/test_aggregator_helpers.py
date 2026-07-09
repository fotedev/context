"""Unit tests for the helper functions in :mod:`aggregator`.

These cover the small, pure helpers that don't require a full CLI run:

* :func:`_output_names` — names the (context, structure, arena) tuple
* :func:`_LEGACY_OUTPUT_NAMES` — the constants block
* The interactive prompt helpers — exercised via ``input`` monkeypatching
"""

from __future__ import annotations

from pathlib import Path

import pytest

import aggregator


# ---------------------------------------------------------------------------
# _output_names
# ---------------------------------------------------------------------------


class TestOutputNames:
    def test_empty_suffix_md(self) -> None:
        assert aggregator._output_names("", "md") == (
            "context.md",
            "structure.txt",
            "arena.md",
        )

    def test_empty_suffix_txt(self) -> None:
        assert aggregator._output_names("", "txt") == (
            "context.txt",
            "structure.txt",
            "arena.txt",
        )

    def test_numbered_suffix(self) -> None:
        assert aggregator._output_names("_1", "md") == (
            "context_1.md",
            "structure_1.txt",
            "arena_1.md",
        )

    def test_legacy_block_is_frozenset_like(self) -> None:
        # Spec uses a set literal — just sanity check it covers the well-known
        # legacy names so the merge prompt fires when expected.
        assert "arena.txt" in aggregator._LEGACY_OUTPUT_NAMES
        assert "context.md" in aggregator._LEGACY_OUTPUT_NAMES
        assert "structure.txt" in aggregator._LEGACY_OUTPUT_NAMES


# ---------------------------------------------------------------------------
# Prompt helpers
# ---------------------------------------------------------------------------


class TestPromptToggle:
    def test_enter_returns_default(self, monkeypatch) -> None:
        monkeypatch.setattr("builtins.input", lambda _: "")
        assert (
            aggregator._prompt_toggle("Q? [Enter=yes]: ", default_setting=True)
            is True
        )

    def test_space_returns_true(self, monkeypatch) -> None:
        monkeypatch.setattr("builtins.input", lambda _: " ")
        # Default was False; space flips to True.
        assert (
            aggregator._prompt_toggle("Q? [Enter=no]: ", default_setting=False)
            is True
        )

    def test_yes_returns_true(self, monkeypatch) -> None:
        monkeypatch.setattr("builtins.input", lambda _: "yes")
        assert (
            aggregator._prompt_toggle("Q?: ", default_setting=False) is True
        )

    def test_no_returns_false(self, monkeypatch) -> None:
        monkeypatch.setattr("builtins.input", lambda _: "n")
        assert (
            aggregator._prompt_toggle("Q?: ", default_setting=True) is False
        )

    def test_eoferror_returns_default(self, monkeypatch) -> None:
        def raise_eof(_: str) -> str:
            raise EOFError

        monkeypatch.setattr("builtins.input", raise_eof)
        assert (
            aggregator._prompt_toggle("Q?: ", default_setting=False) is False
        )


class TestPromptChoiceCount:
    def test_enter_keeps_default(self, monkeypatch) -> None:
        monkeypatch.setattr("builtins.input", lambda _: "")
        assert (
            aggregator._prompt_choice_count("Q?: ", default_count=2) == 2
        )

    def test_space_picks_4(self, monkeypatch) -> None:
        monkeypatch.setattr("builtins.input", lambda _: " ")
        assert (
            aggregator._prompt_choice_count("Q?: ", default_count=2) == 4
        )

    def test_typed_2(self, monkeypatch) -> None:
        monkeypatch.setattr("builtins.input", lambda _: "2")
        assert (
            aggregator._prompt_choice_count("Q?: ", default_count=4) == 2
        )

    def test_invalid_then_valid(self, monkeypatch) -> None:
        answers = iter(["7", "4"])
        monkeypatch.setattr("builtins.input", lambda _: next(answers))
        # First input invalid → loop continues → second input "4" wins.
        assert (
            aggregator._prompt_choice_count("Q?: ", default_count=2) == 4
        )


class TestPromptChoiceFormat:
    def test_enter_keeps_default(self, monkeypatch) -> None:
        monkeypatch.setattr("builtins.input", lambda _: "")
        assert (
            aggregator._prompt_choice_format("Q?: ", default_format="md") == "md"
        )

    def test_space_picks_txt(self, monkeypatch) -> None:
        monkeypatch.setattr("builtins.input", lambda _: " ")
        assert (
            aggregator._prompt_choice_format("Q?: ", default_format="md") == "txt"
        )

    def test_typed_md_with_dot_prefix(self, monkeypatch) -> None:
        monkeypatch.setattr("builtins.input", lambda _: ".md")
        assert (
            aggregator._prompt_choice_format("Q?: ", default_format="txt") == "md"
        )


class TestPromptUpdateStructure:
    def test_enter_means_update(self, monkeypatch) -> None:
        monkeypatch.setattr("builtins.input", lambda _: "")
        assert aggregator._prompt_update_structure("update? ") is True

    def test_space_means_keep(self, monkeypatch) -> None:
        monkeypatch.setattr("builtins.input", lambda _: " ")
        assert aggregator._prompt_update_structure("update? ") is False

    def test_eoferror_means_update(self, monkeypatch) -> None:
        def raise_eof(_: str) -> str:
            raise EOFError

        monkeypatch.setattr("builtins.input", raise_eof)
        assert aggregator._prompt_update_structure("update? ") is True


# ---------------------------------------------------------------------------
# _prompt_merge uses _prompt_toggle; just smoke-test the wire-up.
# ---------------------------------------------------------------------------


class TestPromptMerge:
    def test_default_merges(self, monkeypatch) -> None:
        monkeypatch.setattr("builtins.input", lambda _: "")
        assert aggregator._prompt_merge() is True

    def test_space_skips(self, monkeypatch) -> None:
        monkeypatch.setattr("builtins.input", lambda _: " ")
        assert aggregator._prompt_merge() is False