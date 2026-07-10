"""Unit tests for :mod:`core.counter`.

Both the tiktoken-backed exact path and the stdlib-fallback heuristic must
be exercised. We don't require tiktoken to be installed; the fallback is
the default and well-defined behaviour.
"""

from __future__ import annotations

from pathlib import Path

from core.counter import count_lines, count_tokens


class TestCountTokens:
    def test_empty_string_returns_zero(self) -> None:
        assert count_tokens("") == 0

    def test_short_text_returns_positive(self) -> None:
        n = count_tokens("hello world")
        assert n > 0

    def test_uses_tiktoken_when_available(self, monkeypatch) -> None:
        # Force the tiktoken path by injecting a fake module that always
        # reports 42 tokens regardless of input.
        import sys
        import types

        fake = types.ModuleType("tiktoken")

        class FakeEncoding:
            def encode(self, text: str) -> list[int]:
                return [1] * 42

        fake.get_encoding = lambda name: FakeEncoding()  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "tiktoken", fake)

        # Re-import to make sure the import inside count_tokens picks up the fake.
        from core import counter as counter_module

        counter_module.count_tokens.__globals__["tiktoken"] = fake
        n = counter_module.count_tokens("any text at all")
        assert n == 42

    def test_fallback_estimate_is_positive(self, monkeypatch) -> None:
        # Remove tiktoken from sys.modules to force the ImportError branch.
        monkeypatch.setitem(__import__("sys").modules, "tiktoken", None)

        from core import counter as counter_module

        counter_module.count_tokens.__globals__.pop("tiktoken", None)
        text = "The quick brown fox jumps over the lazy dog. " * 10
        n = counter_module.count_tokens(text)
        # Heuristic: max(char_count // 4, word_count * 1.3).
        assert n > 0


class TestCountLines:
    def test_full_file(self, tmp_path: Path) -> None:
        p = tmp_path / "sample.txt"
        p.write_text("a\nb\nc\nd\n", encoding="utf-8")
        assert count_lines(p) == 4

    def test_with_ranges(self, tmp_path: Path) -> None:
        p = tmp_path / "sample.txt"
        p.write_text("a\nb\nc\nd\ne\n", encoding="utf-8")
        # Lines 2-3 inclusive = "b", "c" → 2 lines.
        assert count_lines(p, ranges=[(2, 3)]) == 2

    def test_with_multiple_ranges(self, tmp_path: Path) -> None:
        p = tmp_path / "sample.txt"
        p.write_text("a\nb\nc\nd\ne\n", encoding="utf-8")
        # Lines 1 + 4-5 = 1 + 2 = 3.
        assert count_lines(p, ranges=[(1, 1), (4, 5)]) == 3

    def test_missing_file_returns_zero(self, tmp_path: Path) -> None:
        assert count_lines(tmp_path / "nope.txt") == 0

    def test_clamped_ranges(self, tmp_path: Path) -> None:
        p = tmp_path / "sample.txt"
        p.write_text("a\nb\nc\n", encoding="utf-8")
        # Range beyond end is clamped to actual size.
        assert count_lines(p, ranges=[(1, 100)]) == 3

    def test_inverted_range_returns_zero(self, tmp_path: Path) -> None:
        p = tmp_path / "sample.txt"
        p.write_text("a\nb\nc\n", encoding="utf-8")
        # start > end (truly inverted) → 0 lines.
        assert count_lines(p, ranges=[(3, 2)]) == 0

    def test_unreadable_returns_zero(self, tmp_path: Path) -> None:
        # A directory raises OSError when opened as a file → return 0.
        d = tmp_path / "is_a_dir"
        d.mkdir()
        assert count_lines(d) == 0
