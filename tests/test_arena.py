"""Unit tests for :mod:`core.arena`.

Covers the ``# Target Arena:`` directive parser, the conflict-resolved
:func:`build_arena_plan`, and the v3+ prefixed filename helpers.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.arena import (
    ArenaDirective,
    arena_filenames,
    arena_model_filename,
    build_arena_plan,
    parse_target_arena_directive,
    resolve_arena_dir,
)

# ---------------------------------------------------------------------------
# Directive parser
# ---------------------------------------------------------------------------


class TestParseDirective:
    def test_parses_standard_form(self) -> None:
        d = parse_target_arena_directive("# Target Arena: 006-AdminDashboard")
        assert d.number == 6
        assert d.name == "AdminDashboard"
        assert d.has_directive

    def test_no_directive(self) -> None:
        d = parse_target_arena_directive("Just some normal content here.")
        assert d.number is None
        assert d.name is None
        assert not d.has_directive

    def test_empty_text(self) -> None:
        assert parse_target_arena_directive("") == ArenaDirective()

    def test_only_whitespace(self) -> None:
        assert parse_target_arena_directive("   \n   \n   ") == ArenaDirective()

    def test_case_insensitive_prefix(self) -> None:
        d = parse_target_arena_directive("# target arena: 003-Hero")
        assert d.number == 3
        assert d.name == "Hero"

    def test_with_leading_whitespace_on_line(self) -> None:
        # Lstrip the line before matching prefix — the spec says first
        # non-empty line, then prefix is anchored on the stripped start.
        d = parse_target_arena_directive("   # Target Arena: 9-Foo")
        assert d.number == 9
        assert d.name == "Foo"

    def test_skips_blank_lines_before_directive(self) -> None:
        text = "\n\n# Target Arena: 010-Widget\nrest of file..."
        d = parse_target_arena_directive(text)
        assert d.number == 10
        assert d.name == "Widget"

    def test_directive_without_dash_separator(self) -> None:
        # Regex allows optional "-": `# Target Arena: 042` is valid.
        d = parse_target_arena_directive("# Target Arena: 042")
        assert d.number == 42
        assert d.name is None

    def test_malformed_number_returns_empty(self) -> None:
        # Hex digit rejected by isdigit() check.
        d = parse_target_arena_directive("# Target Arena: ABC-Foo")
        assert d.number is None

    def test_custom_prefix(self) -> None:
        d = parse_target_arena_directive("# Pin Arena: 7-Bar", prefix="# Pin Arena:")
        assert d.number == 7


# ---------------------------------------------------------------------------
# build_arena_plan
# ---------------------------------------------------------------------------


class TestBuildArenaPlan:
    def _paths(self, tmp_path: Path, names: list[str]) -> list[tuple[Path, str]]:
        return [(tmp_path / n, n[:-4]) for n in names]

    def test_implicit_only(self, tmp_path: Path) -> None:
        inputs = self._paths(tmp_path, ["a.txt", "b.txt"])
        assignments, warnings = build_arena_plan(inputs, {})
        assert len(assignments) == 2
        assert [a.arena_number for a in assignments] == [1, 2]
        assert warnings == []

    def test_explicit_number_honoured(self, tmp_path: Path) -> None:
        inputs = self._paths(tmp_path, ["alpha.txt", "beta.txt"])
        directives = {
            inputs[1][0]: ArenaDirective(number=7, name="Beta"),
        }
        assignments, _ = build_arena_plan(inputs, directives)
        # Beta got its explicit 7; alpha gets the next free number after 7.
        by_name = {a.arena_name: a for a in assignments}
        assert by_name["beta"].arena_number == 7
        assert by_name["alpha"].arena_number == 8

    def test_conflict_shifts_and_warns(self, tmp_path: Path) -> None:
        inputs = self._paths(tmp_path, ["a.txt", "b.txt"])
        directives = {
            inputs[0][0]: ArenaDirective(number=5, name="A"),
            inputs[1][0]: ArenaDirective(number=5, name="B"),
        }
        assignments, warnings = build_arena_plan(
            inputs, directives, on_conflict="warn_and_shift"
        )
        assert any("Conflict" in w for w in warnings)
        # First alphabetical wins 5; second gets shifted to 6.
        by_name = {a.arena_name: a for a in assignments}
        assert by_name["a"].arena_number == 5
        assert by_name["b"].arena_number == 6

    def test_conflict_silent_emits_no_warning(self, tmp_path: Path) -> None:
        inputs = self._paths(tmp_path, ["a.txt", "b.txt"])
        directives = {
            inputs[0][0]: ArenaDirective(number=5, name="A"),
            inputs[1][0]: ArenaDirective(number=5, name="B"),
        }
        assignments, warnings = build_arena_plan(
            inputs, directives, on_conflict="silent"
        )
        assert warnings == []
        by_name = {a.arena_name: a for a in assignments}
        assert by_name["b"].arena_number == 6

    def test_conflict_fail_raises(self, tmp_path: Path) -> None:
        inputs = self._paths(tmp_path, ["a.txt", "b.txt"])
        directives = {
            inputs[0][0]: ArenaDirective(number=5, name="A"),
            inputs[1][0]: ArenaDirective(number=5, name="B"),
        }
        with pytest.raises(RuntimeError, match="conflict"):
            build_arena_plan(inputs, directives, on_conflict="fail")

    def test_implicit_after_explicit_uses_next_free(self, tmp_path: Path) -> None:
        inputs = self._paths(tmp_path, ["a.txt", "b.txt", "c.txt"])
        directives = {
            inputs[0][0]: ArenaDirective(number=10, name="A"),
        }
        assignments, _ = build_arena_plan(inputs, directives)
        by_name = {a.arena_name: a for a in assignments}
        assert by_name["a"].arena_number == 10
        # b, c get 11 and 12.
        assert by_name["b"].arena_number == 11
        assert by_name["c"].arena_number == 12

    def test_returns_assignments_with_directive_attached(
        self, tmp_path: Path
    ) -> None:
        inputs = self._paths(tmp_path, ["a.txt"])
        d = ArenaDirective(number=2, name="A")
        directives = {inputs[0][0]: d}
        assignments, _ = build_arena_plan(inputs, directives)
        assert assignments[0].directive == d

    def test_max_iterations_exhausted_raises(self, tmp_path: Path) -> None:
        # Two conflicting directives that BOTH want #1 force a shift, which
        # calls ``_next_free``; with ``max_iterations=0`` the inner search
        # loop never runs and falls through to the RuntimeError.
        inputs = self._paths(tmp_path, ["a.txt", "b.txt"])
        directives = {
            inputs[0][0]: ArenaDirective(number=1, name="A"),
            inputs[1][0]: ArenaDirective(number=1, name="B"),  # collides
        }
        with pytest.raises(RuntimeError, match="exhausted"):
            build_arena_plan(inputs, directives, max_iterations=0)


# ---------------------------------------------------------------------------
# Filename helpers
# ---------------------------------------------------------------------------


class TestArenaFilenames:
    def test_md_output_format(self) -> None:
        arena_dir = Path("003-Hero")
        files = arena_filenames(arena_dir, output_format="md")
        assert files["input"] == Path("003-Hero/003-Hero.txt")
        assert files["context"] == Path("003-Hero/003-context.md")
        assert files["arena"] == Path("003-Hero/003-arena.md")
        assert files["prompt"] == Path("003-Hero/003-prompt.txt")

    def test_txt_output_format(self) -> None:
        arena_dir = Path("007-Admin")
        files = arena_filenames(arena_dir, output_format="txt")
        assert files["context"] == Path("007-Admin/007-context.txt")
        assert files["arena"] == Path("007-Admin/007-arena.txt")

    def test_unknown_format_defaults_to_md(self) -> None:
        arena_dir = Path("001-X")
        files = arena_filenames(arena_dir, output_format="yaml")
        assert files["context"].suffix == ".md"


class TestArenaModelFilename:
    def test_basic(self) -> None:
        p = arena_model_filename(Path("003-Hero"), "A")
        assert p == Path("003-Hero/003-A.txt")

    def test_different_letters(self) -> None:
        for letter in "ABCD":
            assert arena_model_filename(Path("003-Hero"), letter).name == f"003-{letter}.txt"


# ---------------------------------------------------------------------------
# resolve_arena_dir
# ---------------------------------------------------------------------------


class TestResolveArenaDir:
    def test_no_existing_returns_first(self, tmp_path: Path) -> None:
        out = tmp_path / "context_output"
        arena = resolve_arena_dir(out, "Hero")
        assert arena == out / "arenas" / "001-Hero"
        assert arena.is_dir()

    def test_reuses_existing_for_same_arena(self, tmp_path: Path) -> None:
        out = tmp_path / "context_output"
        first = resolve_arena_dir(out, "Hero")
        # Second call should reuse the same folder (max_match path).
        second = resolve_arena_dir(out, "Hero")
        assert second == first

    def test_new_arena_after_existing_uses_max_plus_one(self, tmp_path: Path) -> None:
        out = tmp_path / "context_output"
        resolve_arena_dir(out, "Hero")  # 001
        resolve_arena_dir(out, "Hero")  # still 001
        new = resolve_arena_dir(out, "OtherArena")
        assert new == out / "arenas" / "002-OtherArena"

    def test_preferred_number_overrides(self, tmp_path: Path) -> None:
        out = tmp_path / "context_output"
        arena = resolve_arena_dir(out, "Hero", preferred_number=42)
        assert arena == out / "arenas" / "042-Hero"

    def test_preferred_number_reuses_existing(self, tmp_path: Path) -> None:
        out = tmp_path / "context_output"
        a1 = resolve_arena_dir(out, "Hero", preferred_number=5)
        a2 = resolve_arena_dir(out, "Hero", preferred_number=5)
        assert a1 == a2
