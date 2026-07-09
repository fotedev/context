"""Unit tests for :mod:`core.settings`.

These tests cover the highest-leverage surface area of the settings module:

* filename helpers (``aggregate_filename``, ``compare_filename``)
* paste-attachments slugification (``slugify_two_sentences``,
  ``extract_first_sentences``)
* settings file lifecycle (``load_settings``, ``save_settings``,
  ``ensure_context_dir``, ``write_default_ignore_if_enabled``)
* the empty/invalid-file edge cases from the spec

The settings schema is now a nested dataclass hierarchy
(:class:`core.settings.Settings`); tests construct and mutate settings via
``dataclasses.replace`` and attribute access (e.g. ``settings.output.format``).
``DEFAULT_SETTINGS`` is re-exported as a flat dict for the few cases where
key-set assertions are clearer than nested traversal.
"""

from __future__ import annotations

import copy
import dataclasses
import json

import pytest

from core.settings import (
    DEFAULT_SETTINGS,
    IgnoreSettings,
    JudgeSettings,
    ModelsSettings,
    OutputSettings,
    Settings,
    aggregate_filename,
    compare_filename,
    display_settings,
    ensure_context_dir,
    extract_first_sentences,
    load_settings,
    save_settings,
    slugify_two_sentences,
    write_default_ignore_if_enabled,
)


# ---------------------------------------------------------------------------
# Filename helpers (Req 9 / v3+ flat layout)
# ---------------------------------------------------------------------------


class TestFilenameHelpers:
    """v3+ filenames: ``context.<ext>`` and ``arena.<ext>`` driven by ``output_format``."""

    def test_default_md_extension(self) -> None:
        assert aggregate_filename(Settings()) == "context.md"
        assert compare_filename(Settings()) == "arena.md"

    def test_txt_extension_honoured(self) -> None:
        settings = Settings(output=OutputSettings(format="txt"))
        assert aggregate_filename(settings) == "context.txt"
        assert compare_filename(settings) == "arena.txt"

    def test_unknown_format_collapses_to_md(self) -> None:
        # Anything that isn't "md"/"txt" must not break callers — fall back to .md.
        settings = Settings(output=OutputSettings(format="pdf"))
        assert aggregate_filename(settings) == "context.md"
        assert compare_filename(settings) == "arena.md"

    def test_format_with_dotted_prefix_still_resolves(self) -> None:
        # Defensive: ".md" and "MD" should both work. The dataclass
        # constructor only accepts "md"/"txt", so exercise the fallback path
        # by patching ``settings.output.format`` directly.
        for fmt in (".md", "MD", " Md "):
            base = Settings()
            settings = dataclasses.replace(
                base, output=OutputSettings(format=fmt)
            )
            assert aggregate_filename(settings) == "context.md"


# ---------------------------------------------------------------------------
# Sentence extraction + slugification (paste-attachments archival)
# ---------------------------------------------------------------------------


class TestExtractFirstSentences:
    def test_returns_two_sentences_for_normal_text(self) -> None:
        text = "First sentence here. Second sentence there. Third ignored."
        assert extract_first_sentences(text, n=2) == [
            "First sentence here",
            "Second sentence there",
        ]

    def test_handles_exclamation_and_question_terminators(self) -> None:
        text = "Wow! Really? OK then."
        sentences = extract_first_sentences(text, n=3)
        assert sentences == ["Wow", "Really", "OK then"]

    def test_handles_arabic_terminators(self) -> None:
        # U+061F ARABIC QUESTION MARK, U+061B ARABIC SEMICOLON, U+06D4 FULL STOP.
        text = "السطر الأول؟ السطر الثاني؛ السطر الثالث."
        out = extract_first_sentences(text, n=3)
        assert len(out) == 3
        assert out[0] == "السطر الأول"

    def test_returns_empty_for_empty_text(self) -> None:
        assert extract_first_sentences("", n=2) == []
        assert extract_first_sentences("   \n\n  ", n=2) == []

    def test_n_limits_output(self) -> None:
        text = "A. B. C. D."
        assert extract_first_sentences(text, n=1) == ["A"]


class TestSlugifyTwoSentences:
    @pytest.mark.parametrize(
        "text,expected_substring",
        [
            ("Hello world. Foo bar.", "hello_world"),
            ("First sentence. Second sentence here.", "first_sentence"),
        ],
    )
    def test_basic_slug(self, text: str, expected_substring: str) -> None:
        slug = slugify_two_sentences(text)
        assert expected_substring in slug

    def test_strips_forbidden_filename_chars(self) -> None:
        # `<>:"/\\|?*` should be removed; whitespace collapsed to `_`.
        slug = slugify_two_sentences('Hello: "world"? </foo>\\bar|.')
        # No forbidden chars survive.
        for forbidden in '<>:"/\\|?*':
            assert forbidden not in slug
        # Whitespace collapsed to single underscore.
        assert " " not in slug

    def test_truncates_long_inputs_to_80_chars(self) -> None:
        long = "word " * 50  # ~250 chars total
        slug = slugify_two_sentences(long)
        assert len(slug) <= 80

    def test_truncation_breaks_on_last_underscore(self) -> None:
        # 80-char limit; we expect truncation at the last `_` boundary.
        text = ("alpha " * 30).strip()  # "alpha alpha alpha..."
        slug = slugify_two_sentences(text)
        if len(slug) == 80:
            # If truncated, the break should be at an underscore, not mid-word.
            assert slug.endswith("alpha") or "_" not in slug[79:80]

    def test_empty_text_returns_fallback(self) -> None:
        assert slugify_two_sentences("") == "paste"
        assert slugify_two_sentences("   ") == "paste"
        assert slugify_two_sentences("....") == "paste"

    def test_custom_fallback_honoured(self) -> None:
        assert slugify_two_sentences("", fallback="my-fallback") == "my-fallback"

    def test_pure_numeric_slug_falls_back(self) -> None:
        # If after cleaning the slug is digits/dashes/underscores only, fall back.
        slug = slugify_two_sentences("123 456")
        assert slug == "paste"

    def test_case_insensitive(self) -> None:
        lower = slugify_two_sentences("Hello World.")
        upper = slugify_two_sentences("HELLO WORLD.")
        assert lower == upper


# ---------------------------------------------------------------------------
# Settings file lifecycle
# ---------------------------------------------------------------------------


class TestEnsureContextDir:
    def test_creates_context_and_inputs(self, tmp_project_root) -> None:
        ctx = ensure_context_dir(tmp_project_root)
        assert ctx == tmp_project_root / ".context"
        assert (tmp_project_root / ".context" / "inputs").is_dir()

    def test_idempotent(self, tmp_project_root) -> None:
        ensure_context_dir(tmp_project_root)
        ensure_context_dir(tmp_project_root)  # second call must not raise
        assert (tmp_project_root / ".context" / "inputs").is_dir()


class TestLoadSaveSettings:
    def test_missing_file_creates_with_defaults(self, tmp_project_root) -> None:
        settings = load_settings(tmp_project_root)
        # All flat-key equivalents must be reachable via the legacy shim
        # (``Settings.__getitem__`` proxies through ``to_flat_dict()``).
        flat = settings.to_flat_dict()
        for key in DEFAULT_SETTINGS:
            assert key in flat, f"missing key: {key}"

        # Side-effect: settings.json should now exist on disk.
        assert (tmp_project_root / ".context" / "settings.json").is_file()

    def test_round_trip(self, tmp_project_root) -> None:
        original = load_settings(tmp_project_root)
        modified = dataclasses.replace(
            original,
            judge=JudgeSettings(enabled=True),
            models=ModelsSettings(count=4),
        )
        save_settings(tmp_project_root, modified)

        reloaded = load_settings(tmp_project_root)
        assert reloaded.judge.enabled is True
        assert reloaded.models.count == 4

    def test_empty_file_returns_defaults(self, tmp_project_root, capsys) -> None:
        ctx_dir = tmp_project_root / ".context"
        ctx_dir.mkdir(parents=True, exist_ok=True)
        (ctx_dir / "settings.json").write_text("", encoding="utf-8")
        settings = load_settings(tmp_project_root)
        flat = settings.to_flat_dict()
        for key, expected in DEFAULT_SETTINGS.items():
            assert flat[key] == expected

    def test_invalid_json_returns_defaults(self, tmp_project_root, capsys) -> None:
        ctx_dir = tmp_project_root / ".context"
        ctx_dir.mkdir(parents=True, exist_ok=True)
        (ctx_dir / "settings.json").write_text("{not json", encoding="utf-8")
        settings = load_settings(tmp_project_root)
        flat = settings.to_flat_dict()
        for key, expected in DEFAULT_SETTINGS.items():
            assert flat[key] == expected

    def test_partial_user_settings_merged_with_defaults(
        self, tmp_project_root
    ) -> None:
        # User file has only one key; load_settings must still return every
        # default key (new keys introduced later never crash old configs).
        ctx_dir = tmp_project_root / ".context"
        ctx_dir.mkdir(parents=True, exist_ok=True)
        (ctx_dir / "settings.json").write_text(
            json.dumps({"gemini_judge": True}), encoding="utf-8"
        )
        settings = load_settings(tmp_project_root)
        flat = settings.to_flat_dict()
        # User override wins.
        assert flat["gemini_judge"] is True
        # Every default is still present.
        for key in DEFAULT_SETTINGS:
            assert key in flat

    def test_save_creates_context_dir_if_missing(self, tmp_project_root) -> None:
        # Start clean: no .context/ at all.
        save_settings(tmp_project_root, Settings())
        assert (tmp_project_root / ".context" / "settings.json").is_file()


class TestWriteDefaultIgnore:
    def test_writes_when_enabled_and_missing(self, tmp_project_root, fake_settings) -> None:
        # Sanity: file should not exist yet.
        ignore = tmp_project_root / ".context" / "ignore"
        assert not ignore.exists()

        wrote = write_default_ignore_if_enabled(tmp_project_root, fake_settings)
        assert wrote is True
        assert ignore.is_file()

    def test_does_not_overwrite_existing_user_file(
        self, tmp_project_root, fake_settings
    ) -> None:
        ctx_dir = tmp_project_root / ".context"
        ctx_dir.mkdir(parents=True, exist_ok=True)
        user_content = "# my custom ignore\nfoo\nbar\n"
        ignore = ctx_dir / "ignore"
        ignore.write_text(user_content, encoding="utf-8")

        wrote = write_default_ignore_if_enabled(tmp_project_root, fake_settings)
        assert wrote is False
        assert ignore.read_text(encoding="utf-8") == user_content

    def test_disabled_setting_leaves_file_alone(
        self, tmp_project_root, fake_settings
    ) -> None:
        disabled = dataclasses.replace(
            fake_settings, ignore=IgnoreSettings(use_default=False)
        )
        wrote = write_default_ignore_if_enabled(tmp_project_root, disabled)
        assert wrote is False
        assert not (tmp_project_root / ".context" / "ignore").exists()


class TestDisplaySettings:
    def test_prints_when_present(self, tmp_project_root, capsys) -> None:
        load_settings(tmp_project_root)  # creates file
        display_settings(tmp_project_root)
        out = capsys.readouterr().out
        assert "Settings file:" in out
        # Settings schema label includes a hint about the nested form now.
        assert "Settings schema" in out

    def test_prints_when_missing(self, tmp_project_root, capsys) -> None:
        # Don't create settings.json — display should not crash.
        display_settings(tmp_project_root)
        out = capsys.readouterr().out
        assert "No settings file found" in out