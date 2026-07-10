"""Settings & configuration management.

This module owns:

* The nested ``Settings`` dataclass hierarchy (replaces the old 18-key flat dict).
* The ``.context/settings.json`` load/save/migrate lifecycle with **automatic
  flat-to-nested upgrade** of legacy on-disk files.
* The settings-driven paste-attachments archival feature.

Nested structure (formerly flat keys in parentheses):

* ``output``               — ``output_dir``, ``output_format``
* ``archive``              — ``archive``, ``archive_dir``
* ``models``               — ``model_count``
* ``judge``                — ``gemini_judge``
* ``compact``              — ``compact_mode``
* ``paste_attachments``    — 5 paste-attachments keys
* ``target_arena``         — ``respect_target_arena_directive``,
                             ``target_arena_directive_prefix``,
                             ``on_arena_number_conflict``
* ``ignore``               — ``use_default_ignore``
* ``inputs``               — ``inputs_dir`` (kept for legacy compatibility)

Migration strategy
------------------
``load_settings`` transparently accepts both:

1. Nested JSON (the new canonical form), e.g.::

       {"output": {"dir": "x"}, "judge": {"enabled": false}}

2. Flat JSON (legacy v1 form), e.g.::

       {"output_dir": "x", "gemini_judge": false}

When a legacy flat file is detected, ``_migrate_settings_file`` converts it to
the nested form **in-place** so the next ``save_settings`` writes the new
shape. The in-memory ``Settings`` object is always built from the nested form.
"""
from __future__ import annotations

import json
import logging
import re
import sys
from dataclasses import dataclass, field, fields, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, cast

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Nested settings schema
# ---------------------------------------------------------------------------


@dataclass
class OutputSettings:
    """Output directory + format."""

    dir: str = "context_output"
    format: str = "md"  # "md" or "txt"

    def __post_init__(self) -> None:
        if self.format not in ("md", "txt"):
            self.format = "md"


@dataclass
class ArchiveSettings:
    """Archive toggle + destination directory."""

    enabled: bool = False
    dir: str = "ARCHIVE"


@dataclass
class ModelsSettings:
    """How many model responses the arena expects (2 or 4)."""

    count: int = 2

    def __post_init__(self) -> None:
        if self.count not in (2, 4):
            self.count = 2


@dataclass
class JudgeSettings:
    """Whether to run the Gemini AI Judge step."""

    enabled: bool = False  # was: gemini_judge


@dataclass
class CompactSettings:
    """Compact compare output (fewer tokens)."""

    enabled: bool = False  # was: compact_mode


@dataclass
class PasteAttachmentsSettings:
    """Paste long-text files into smart-named copies under output_dir."""

    enabled: bool = False  # was: paste_attachments_enabled
    source_dir: str = "tmp/paste-attachments"  # was: paste_attachments_source_dir
    target_subdir: str = "tmp/paste-attachments"  # was: paste_attachments_target_subdir
    date_format: str = "%Y-%m-%d"  # was: paste_attachments_date_format
    copy_mode: str = "copy"  # was: paste_attachments_copy_mode

    def __post_init__(self) -> None:
        if self.copy_mode not in ("copy", "move"):
            self.copy_mode = "copy"


@dataclass
class TargetArenaSettings:
    """Target-arena directive handling (first-line ``# Target Arena: NNN-Name``)."""

    respect_directive: bool = True  # was: respect_target_arena_directive
    directive_prefix: str = "# Target Arena:"  # was: target_arena_directive_prefix
    on_number_conflict: str = "warn_and_shift"  # was: on_arena_number_conflict

    def __post_init__(self) -> None:
        if self.on_number_conflict not in ("warn_and_shift", "shift", "error"):
            self.on_number_conflict = "warn_and_shift"


@dataclass
class IgnoreSettings:
    """Auto-create ``.context/ignore`` with default template when enabled."""

    use_default: bool = True  # was: use_default_ignore


@dataclass
class InputsSettings:
    """Input file directory (legacy/deprecated but kept for compatibility)."""

    dir: str = ".context/inputs"  # was: inputs_dir


@dataclass
class Settings:
    """Root settings container — composes all nested groups.

    Use attribute access (``settings.judge.enabled``) — not dict-style.
    For dict-style legacy code that still uses ``settings["foo"]``,
    ``Settings.__getitem__`` proxies a single-segment key to the matching
    top-level group via its dict repr (best-effort compatibility).
    """

    output: OutputSettings = field(default_factory=OutputSettings)
    archive: ArchiveSettings = field(default_factory=ArchiveSettings)
    models: ModelsSettings = field(default_factory=ModelsSettings)
    judge: JudgeSettings = field(default_factory=JudgeSettings)
    compact: CompactSettings = field(default_factory=CompactSettings)
    paste_attachments: PasteAttachmentsSettings = field(
        default_factory=PasteAttachmentsSettings
    )
    target_arena: TargetArenaSettings = field(default_factory=TargetArenaSettings)
    ignore: IgnoreSettings = field(default_factory=IgnoreSettings)
    inputs: InputsSettings = field(default_factory=InputsSettings)

    # ---- dict I/O ---------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Serialize to nested-dict form (canonical on-disk shape)."""
        return _dataclass_to_dict(self)

    def to_flat_dict(self) -> dict[str, object]:
        """Serialize to the legacy flat dict shape.

        Useful for log lines, debug dumps, and tests that still expect flat keys.
        """
        return _to_flat_dict(self)

    # ---- limited backward-compat shims -----------------------------------

    def __getitem__(self, key: str) -> object:
        """Best-effort legacy support for ``settings['output_dir']`` etc.

        Tries, in order:
          1. Nested attribute access (``settings.output.dir`` → ``output_dir``)
          2. Flat key lookup via ``to_flat_dict()``
          3. ``KeyError`` if nothing matches.

        New code should use attribute access — this shim exists only to keep
        any straggling dict-style callers working during the transition.
        """
        # Try flat-key lookup first — covers the overwhelming majority of legacy
        # call sites (`settings["output_dir"]`, `settings.get("gemini_judge")`).
        flat = self.to_flat_dict()
        if key in flat:
            return flat[key]
        # Then try attribute access on the Settings object itself.
        if hasattr(self, key):
            return getattr(self, key)
        raise KeyError(key)

    def get(self, key: str, default: object | None = None) -> object | None:
        """Dict-style ``.get(key, default)`` legacy shim (see ``__getitem__``)."""
        try:
            return self[key]
        except KeyError:
            return default


# ---------------------------------------------------------------------------
# Dict ↔ dataclass helpers
# ---------------------------------------------------------------------------


def _dataclass_to_dict(obj: Any) -> dict[str, Any]:
    """Recursive ``dataclasses.asdict`` (works for nested dataclasses)."""
    if is_dataclass(obj) and not isinstance(obj, type):
        return {f.name: _dataclass_to_dict(getattr(obj, f.name)) for f in fields(obj)}
    if isinstance(obj, dict):
        return {k: _dataclass_to_dict(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_dataclass_to_dict(v) for v in obj]
    return obj


def _dataclass_from_dict(cls: type, data: dict[str, Any]) -> Any:
    """Build a dataclass of type ``cls`` from ``data``, ignoring unknown keys.

    Nested dataclass fields are detected by resolving the field's actual type
    via :func:`_resolve_field_type` (which works around ``from __future__
    import annotations`` making ``f.type`` a string). When a nested dataclass
    is found and the incoming *value* is a dict, recursion turns it into the
    correct nested instance — otherwise the raw *value* is passed through,
    letting dataclass ``__post_init__`` (or, ultimately, ``TypeError``) reject
    bogus shapes.
    """
    if not is_dataclass(cls):
        raise TypeError(f"{cls!r} is not a dataclass")
    kwargs: dict[str, Any] = {}
    for f in fields(cls):
        if f.name not in data:
            continue
        value = data[f.name]
        nested_cls = _resolve_field_type(cls, f.name)
        if (
            nested_cls is not None
            and is_dataclass(nested_cls)
            and isinstance(value, dict)
        ):
            kwargs[f.name] = _dataclass_from_dict(nested_cls, value)
            continue
        kwargs[f.name] = value
    return cls(**kwargs)


def _resolve_field_type(owner_cls: type, field_name: str) -> type | None:
    """Best-effort resolution of a nested dataclass type from the class.

    Works around ``from __future__ import annotations`` which makes
    ``dataclasses.field.type`` a string.
    """
    # Try the typing module first to get the actual class object.
    import typing

    hints = typing.get_type_hints(owner_cls)
    t = hints.get(field_name)
    if t is None:
        return None
    # Strip Optional[X] / Union[X, None]
    origin = getattr(t, "__origin__", None)
    if origin is not None:
        args = getattr(t, "__args__", ())
        for a in args:
            if a is not type(None):
                return a  # type: ignore[no-any-return]
        return None
    return t  # type: ignore[no-any-return]


def settings_from_dict(data: dict[str, Any]) -> Settings:
    """Build a ``Settings`` instance from a (possibly partial) nested dict."""
    return _dataclass_from_dict(Settings, data)


# ---------------------------------------------------------------------------
# Flat ↔ Nested migration tables
# ---------------------------------------------------------------------------


# Mapping from legacy flat key → nested dotted path.
# Used both for upgrading legacy on-disk files AND for the ``to_flat_dict()``
# reverse mapping (so legacy call sites using ``settings["output_dir"]`` keep
# working for the duration of the migration).
_FLAT_TO_NESTED: dict[str, tuple[str, str]] = {
    # (group_name, attribute_name)
    "output_dir": ("output", "dir"),
    "output_format": ("output", "format"),
    "archive": ("archive", "enabled"),
    "archive_dir": ("archive", "dir"),
    "model_count": ("models", "count"),
    "gemini_judge": ("judge", "enabled"),
    "compact_mode": ("compact", "enabled"),
    "paste_attachments_enabled": ("paste_attachments", "enabled"),
    "paste_attachments_source_dir": ("paste_attachments", "source_dir"),
    "paste_attachments_target_subdir": ("paste_attachments", "target_subdir"),
    "paste_attachments_date_format": ("paste_attachments", "date_format"),
    "paste_attachments_copy_mode": ("paste_attachments", "copy_mode"),
    "respect_target_arena_directive": ("target_arena", "respect_directive"),
    "target_arena_directive_prefix": ("target_arena", "directive_prefix"),
    "on_arena_number_conflict": ("target_arena", "on_number_conflict"),
    "use_default_ignore": ("ignore", "use_default"),
    "inputs_dir": ("inputs", "dir"),
}

# Keys we removed entirely from the schema. They are silently dropped on upgrade.
_DROPPED_FLAT_KEYS: set[str] = {
    "aggregate_filename",  # rejected intermediate-design keys
    "compare_filename",
}


# Subset of legacy-flat keys used to **detect** whether an on-disk file is in
# the legacy flat shape. Only keys whose *name* cannot collide with a nested
# group name are included — for instance, ``output_dir`` unambiguously points
# at the flat form (the nested form uses a top-level ``output`` object), but
# ``archive`` collides (it's both a flat key and a nested group name), so it
# is **not** a reliable detector and lives here in :data:`_AMBIGUOUS_FLAT_KEYS`
# instead. ``load_settings`` checks :data:`_LEGACY_FLAT_DETECTION_KEYS` to
# decide whether to run :func:`_flat_dict_to_nested`.
_LEGACY_FLAT_DETECTION_KEYS: set[str] = {
    "output_dir",
    "output_format",
    "model_count",
    "gemini_judge",
    "compact_mode",
    "paste_attachments_enabled",
    "paste_attachments_source_dir",
    "paste_attachments_target_subdir",
    "paste_attachments_date_format",
    "paste_attachments_copy_mode",
    "respect_target_arena_directive",
    "target_arena_directive_prefix",
    "on_arena_number_conflict",
    "use_default_ignore",
    "inputs_dir",
}


# Keys that **cannot** be used for flat-shape detection because their name
# also appears as a nested group name. We keep them in :data:`_FLAT_TO_NESTED`
# for the upgrade path, but the detector (the set above) ignores them —
# disambiguating them requires checking the value's type (a flat ``archive``
# value is a ``bool``; the nested ``archive`` is always a ``dict``), which we
# use :func:`_looks_like_flat_shape` for as a safety net.
_AMBIGUOUS_FLAT_KEYS: set[str] = {"archive", "archive_dir"}


def _looks_like_flat_shape(raw: dict[str, Any]) -> bool:
    """Decide whether *raw* (the parsed ``settings.json`` content) is legacy.

    A reliable positive signal is the presence of any unambiguous legacy flat
    key (e.g. ``"output_dir"``) at the top level — those names never appear in
    the nested form. As an extra safety net we also accept an *ambiguous* key
    such as ``"archive"`` if its value has the legacy ``bool``/``str`` shape
    instead of the nested ``dict`` shape — but we **only** do that when no
    other top-level key is a dict, to avoid false positives on partially-
    migrated or hand-crafted files.
    """
    if any(key in raw for key in _LEGACY_FLAT_DETECTION_KEYS):
        return True
    # Safety net for hand-rolled flat files with only ambiguous keys.
    ambiguous_match = any(key in raw for key in _AMBIGUOUS_FLAT_KEYS)
    if not ambiguous_match:
        return False
    nested_group_keys = {
        group_name for group_name, _ in _FLAT_TO_NESTED.values()
    }
    # If any *other* top-level key looks like a nested group (a dict), the
    # file is the nested form — the ambiguous key just happens to share a name.
    if any(
        isinstance(raw.get(k), dict) for k in (set(raw) & nested_group_keys)
    ):
        return False
    # No nested group present → treat as legacy flat.
    return True


def _flat_dict_to_nested(flat: dict[str, object]) -> dict[str, Any]:
    """Convert a flat settings dict to the nested dataclass input shape."""
    nested: dict[str, Any] = {}
    for key, value in flat.items():
        if key in _DROPPED_FLAT_KEYS:
            continue
        if key in _FLAT_TO_NESTED:
            group_name, attr_name = _FLAT_TO_NESTED[key]
            nested.setdefault(group_name, {})[attr_name] = value
        # Unknown keys are silently ignored — keeps forward-compatibility for
        # newly-added settings in newer versions without crashing older runs.
    return nested


def _to_flat_dict(settings: Settings) -> dict[str, object]:
    """Convert a ``Settings`` instance back to the legacy flat dict shape."""
    flat: dict[str, object] = {}
    for flat_key, (group_name, attr_name) in _FLAT_TO_NESTED.items():
        group = getattr(settings, group_name, None)
        if group is None:
            continue
        flat[flat_key] = getattr(group, attr_name)
    return flat


# Backward-compat alias — keep ``DEFAULT_SETTINGS`` importable so the rare
# external caller (e.g. CLI ``--settings`` schema dump) keeps working. We
# re-derive it from a fresh ``Settings()`` to keep one source of truth.
DEFAULT_SETTINGS: dict[str, object] = _to_flat_dict(Settings())


# ---------------------------------------------------------------------------
# .context/ignore template (unchanged from v1)
# ---------------------------------------------------------------------------

_DEFAULT_IGNORE_TEMPLATE = """\
# Context Tool — Ignore Patterns
# One pattern per line.  # Comments and blank lines are ignored.
# Edit this file to add or remove patterns. The tool ignores ONLY the patterns listed here.

# Version control
.git

# Dependency directories
node_modules
venv
.venv
.pnpm-store

# Editor & IDE files
.vscode
.idea
.cursor
.windsurf
.github
.agent
.agents
.speckit
.specify
desktop.ini
.DS_Store

# Temporary, cache, and build files
__pycache__
*.pyc
dist
build
.next
.vercel
.index_ignore
compare-template.bak
compare_4.txt
compare_of_compare.txt
migrations.old

# Tool inputs, outputs, and scripts
context_output
.context
files.txt
arena.txt
arena.md
context.txt
context.md
structure.txt
llm.txt
compare.md
compare.txt
compare_*.md
compare_*.txt
context_*.md
context_*.txt
files_*.txt
arena_*.txt
arena_*.md
structure_*.txt

# Un-prefixed (legacy v2 layout) files inside arena directories.
# The v3 flat layout prefixes every arena file with the arena's
# NNN- number (e.g. ``001-A.txt``, ``001-arena.md``). Files that
# don't carry the prefix (e.g. ``A.txt``, ``arena.md``, ``context.md``,
# ``prompt.txt``) are leftovers from the pre-prefix era and should
# never appear in ``structure.txt``. The tool also enforces this as
# a structural rule independent of this ignore file, but listing the
# patterns here keeps the contract visible and lets users who manage
# their own ignore file reproduce the same behaviour.
context_output/arenas/*/A.txt
context_output/arenas/*/B.txt
context_output/arenas/*/C.txt
context_output/arenas/*/D.txt
context_output/arenas/*/E.txt
context_output/arenas/*/F.txt
context_output/arenas/*/arena.md
context_output/arenas/*/arena.txt
context_output/arenas/*/context.md
context_output/arenas/*/context.txt
context_output/arenas/*/prompt.txt
context_output/arenas/*/structure.txt
context_output/arenas/*/llm.txt
context_output/arenas/*/compare.md
context_output/arenas/*/compare.txt

models
models/old
get-shit-done
gifts
agents
scripts
"""


# ---------------------------------------------------------------------------
# Configuration directory management (Req 8)
# ---------------------------------------------------------------------------


def ensure_context_dir(
    root: Path, settings: Settings | None = None
) -> Path:
    """Ensure the ``.context/`` directory exists.

    Always creates ``.context/`` and ``.context/inputs/``. The
    ``.context/settings.json`` and ``.context/ignore`` files are NOT
    auto-created here — they are owned by their respective loaders
    (:func:`load_settings` and :func:`core.discovery.load_ignore_patterns`)
    so the ``use_default_ignore`` toggle can be honored.

    Args:
        root: Project root directory.
        settings: Optional settings (reserved for future use).

    Returns:
        Path to the ``.context/`` directory.
    """
    _ = settings  # reserved for future use

    context_dir = root / ".context"
    context_dir.mkdir(parents=True, exist_ok=True)

    # Auto-create inputs directory if missing
    inputs_dir = context_dir / "inputs"
    inputs_dir.mkdir(parents=True, exist_ok=True)

    return context_dir


def write_default_ignore_if_enabled(
    root: Path, settings: Settings
) -> bool:
    """Write ``.context/ignore`` with the default template ONLY when enabled.

    Respects ``settings.ignore.use_default``:

    * ``True`` (default) — auto-creates ``.context/ignore`` with the built-in
      template if the file is missing, and also rewrites it if it still
      carries the legacy description
      ("These patterns are ADDITIONAL to the built-in defaults").
    * ``False`` — leaves ``.context/ignore`` entirely alone: never creates,
      writes, or overwrites it. The user has full control.

    Args:
        root: Project root directory.
        settings: Effective settings object.

    Returns:
        ``True`` if the file was written, ``False`` otherwise.
    """
    if not bool(settings.ignore.use_default):
        return False

    context_dir = root / ".context"
    # Defensive: ensure the parent dir exists (load_settings normally
    # already calls ensure_context_dir, but stay safe).
    context_dir.mkdir(parents=True, exist_ok=True)

    ignore_path = context_dir / "ignore"
    should_write = False
    if not ignore_path.is_file():
        should_write = True
    else:
        try:
            content = ignore_path.read_text(encoding="utf-8")
            if "These patterns are ADDITIONAL to the built-in defaults" in content:
                should_write = True
        except OSError:
            pass

    if should_write:
        _ = ignore_path.write_text(_DEFAULT_IGNORE_TEMPLATE, encoding="utf-8")
        logger.info("Created/Updated %s with default ignore patterns.", ignore_path)
        return True
    return False


# ---------------------------------------------------------------------------
# Settings I/O
# ---------------------------------------------------------------------------


def load_settings(root: Path) -> Settings:
    """Load settings from ``.context/settings.json``, falling back to defaults.

    On-disk format is the nested JSON shape (see module docstring). Legacy
    flat files are upgraded transparently on first load.

    Resolution strategy (Req 4 precedence — settings layer):
    * If the file is missing → auto-create with defaults (nested form),
      then honour the ``use_default_ignore`` toggle when deciding whether
      to write ``.context/ignore``.
    * If the file is empty → log a hint and return defaults (Edge case 2).
    * If the file contains invalid JSON → log a warning and return defaults.
    * Otherwise, parse and validate. A legacy flat dict is upgraded in-place
      to nested form before being merged with defaults.

    Args:
        root: Project root directory containing ``.context/``.

    Returns:
        A fully-populated :class:`Settings` instance.
    """
    # Ensure the configuration directory and inputs/ exist (ignore file is
    # NOT auto-created here — see ``write_default_ignore_if_enabled``).
    _ = ensure_context_dir(root)
    settings_path = root / ".context" / "settings.json"

    # First-run bootstrap: settings.json missing → create with defaults.
    if not settings_path.is_file():
        initial = Settings()
        save_settings(root, initial)
        logger.info(
            "Created %s — edit your preferences or delete to reset.",
            settings_path,
        )
        # Honour the toggle (True by default → write template).
        _ = write_default_ignore_if_enabled(root, initial)
        return initial

    try:
        content = settings_path.read_text(encoding="utf-8").strip()

        # Edge case 2: completely empty file
        if not content:
            logger.warning(
                "Use context skill with AI model to initialize preferences."
            )
            return Settings()

        raw = cast(dict[str, Any], json.loads(content))

        # Detect legacy flat shape. We use the safe predicate so we never
        # mis-classify a nested-form file as flat (which would corrupt the
        # "archive.enabled" key — see :func:`_looks_like_flat_shape`).
        is_flat = _looks_like_flat_shape(raw)

        if is_flat:
            nested_input = _flat_dict_to_nested(raw)
            # Persist the upgrade so future loads hit the fast path.
            try:
                _save_nested_dict(root, nested_input)
                logger.info(
                    "Upgraded legacy flat settings.json to nested form at %s.",
                    settings_path,
                )
            except OSError as exc:
                logger.warning(
                    "Could not persist nested settings upgrade: %s", exc
                )
        else:
            nested_input = cast(dict[str, Any], raw)

        # Build Settings (missing keys get dataclass defaults).
        settings = settings_from_dict(nested_input)
        _migrate_settings_file(root, settings)
        return settings

    except json.JSONDecodeError:
        logger.warning(
            "Invalid .context/settings.json — using defaults.",
        )
        return Settings()
    except (TypeError, ValueError) as exc:
        logger.warning(
            "Could not parse .context/settings.json (%s) — using defaults.",
            exc,
        )
        return Settings()
    except OSError as exc:
        logger.warning(
            "Could not read .context/settings.json (%s) — using defaults.",
            exc,
        )
        return Settings()


def save_settings(root: Path, settings: Settings) -> None:
    """Persist *settings* to ``.context/settings.json`` in nested form.

    Args:
        root: Project root directory.
        settings: Settings object to write.
    """
    context_dir = root / ".context"
    context_dir.mkdir(parents=True, exist_ok=True)
    context_dir / "settings.json"
    _save_nested_dict(root, settings.to_dict())


def _save_nested_dict(root: Path, data: dict[str, Any]) -> None:
    """Internal: write *data* as nested JSON to ``.context/settings.json``."""
    settings_path = root / ".context" / "settings.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    with settings_path.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
        _ = fh.write("\n")


def display_settings(root: Path) -> None:
    """Print the active settings path, current content, and help text.

    Used by the ``--settings`` CLI flag (Req 10). Kept as ``print()`` because
    this is a user-facing CLI command, not a server log.
    """
    context_dir = root / ".context"
    settings_path = context_dir / "settings.json"

    print(f"Settings file: {settings_path}")
    print()

    if settings_path.is_file():
        try:
            content = settings_path.read_text(encoding="utf-8")
            print("Current settings:")
            print(content)
        except OSError as exc:
            print(f"Error reading settings: {exc}", file=sys.stderr)
    else:
        print("No settings file found. It will be auto-created on next run.")

    print()
    print(
        "To edit settings, modify the JSON file above or delete it to reset to defaults."
    )
    print()
    print("Settings schema (nested form, default values):")
    print(json.dumps(Settings().to_dict(), indent=2))


# ---------------------------------------------------------------------------
# Output filename resolution (v3+ — context.<ext> and arena.<ext>)
# ---------------------------------------------------------------------------


def _resolve_ext(settings: Settings) -> str:
    """Return the canonical output extension from settings.

    ``settings.output.format`` is ``"md"`` or ``"txt"``. Anything else
    collapses to ``"md"`` so callers can always build a valid filename.

    The v3+ layout hard-codes the *stems* (``context`` and ``arena``) and
    derives only the extension from ``output.format``.
    """
    fmt = str(settings.output.format).lower().lstrip(".")
    return "txt" if fmt == "txt" else "md"


def aggregate_filename(settings: Settings) -> str:
    """Return the v3+ aggregate-output filename: ``context.<ext>``."""
    return f"context.{_resolve_ext(settings)}"


def compare_filename(settings: Settings) -> str:
    """Return the v3+ compare-output filename: ``arena.<ext>``."""
    return f"arena.{_resolve_ext(settings)}"


# ---------------------------------------------------------------------------
# Paste-attachments archival (long-text paste → smart-named copy in output)
# ---------------------------------------------------------------------------

# Forbidden filename characters on Windows; we strip these from slugs.
# (POSIX allows more, but cross-platform safety wins.)
_FORBIDDEN_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
# Punctuation-only / digits-only slugs fall back to a default stem.
_PURE_NUMERIC_OR_PUNCT = re.compile(r"^[\d._\-\s]+$")
# Sentence terminators (ASCII and Arabic/Persian/Urdu forms).
_SENTENCE_SPLIT_RE = re.compile(r"[.!?\u061f\u06d4\u061b\u061e\n\r]+")


def _read_text_safely(path: Path) -> str | None:
    """Read a text file with cascading encoding fallbacks.

    Tries (in order): utf-8-sig → utf-8 → utf-16 → latin-1.
    Returns the decoded text, or ``None`` when the file cannot be read at all.
    """
    for encoding in ("utf-8-sig", "utf-8", "utf-16", "latin-1"):
        try:
            return path.read_text(encoding=encoding)
        except (UnicodeDecodeError, OSError):
            continue
    return None


def extract_first_sentences(text: str, n: int = 2) -> list[str]:
    """Split *text* on sentence terminators (Latin + Arabic/Persian) and
    newlines, then return up to *n* non-empty trimmed sentences.
    """
    parts = _SENTENCE_SPLIT_RE.split(text)
    sentences: list[str] = []
    for raw in parts:
        cleaned = raw.strip()
        if cleaned:
            sentences.append(cleaned)
        if len(sentences) >= n:
            break
    return sentences[:n]


def slugify_two_sentences(text: str, fallback: str = "paste") -> str:
    """Build a safe filename stem from the first two sentences of *text*.

    Behaviour:
    * casefold() for case-insensitive matching (preserves Arabic letters).
    * Strips filesystem-forbidden characters (``<>:"/\\|?*`` + control chars).
    * Collapses whitespace to single ``_``; trims leading/trailing ``_`` and ``.``.
    * Truncates to 80 chars, breaking on the last ``_`` if available.
    * Falls back to *fallback* when the result is empty or digits/punct only.
    """
    sentences = extract_first_sentences(text, n=2)
    combined = " ".join(sentences) if sentences else ""
    if not combined.strip():
        return fallback

    slug = combined.casefold()
    slug = _FORBIDDEN_FILENAME_CHARS.sub("", slug)
    slug = re.sub(r"\s+", "_", slug.strip())
    slug = slug.strip("_.")

    if len(slug) > 80:
        truncated = slug[:80]
        last_underscore = truncated.rfind("_")
        slug = truncated[:last_underscore] if last_underscore > 0 else truncated

    slug = slug.strip("_.")
    if not slug or _PURE_NUMERIC_OR_PUNCT.match(slug):
        return fallback
    return slug


def _migrate_settings_file(root: Path, settings: Settings) -> None:
    """Add any missing keys to the user's nested settings file.

    Preserves every existing user value; only adds keys that were not present.
    Idempotent — a second call writes nothing because the diff becomes empty.
    """
    settings_path = root / ".context" / "settings.json"
    if not settings_path.is_file():
        return

    try:
        content = settings_path.read_text(encoding="utf-8").strip()
        if not content:
            return
        current = cast(dict[str, Any], json.loads(content))
    except (OSError, json.JSONDecodeError):
        return

    # Compute default-nested dict; diff with what's on disk.
    defaults = Settings().to_dict()
    added: list[str] = []

    def _merge(defaults_tree: dict[str, Any], disk_tree: dict[str, Any], path: str) -> None:
        for key, default_val in defaults_tree.items():
            dotted = f"{path}.{key}" if path else key
            if key not in disk_tree:
                disk_tree[key] = default_val
                added.append(dotted)
                continue
            if isinstance(default_val, dict) and isinstance(disk_tree[key], dict):
                _merge(default_val, disk_tree[key], dotted)

    if not isinstance(current, dict):
        return

    _merge(defaults, current, "")

    if not added:
        return

    try:
        save_settings(root, settings_from_dict(current))
        logger.info(
            "Added new settings to %s (defaults applied for: %s).",
            settings_path,
            ", ".join(sorted(added)),
        )
    except OSError as exc:
        logger.warning("Could not persist new settings keys: %s", exc)


def sync_paste_attachments(
    root: Path,
    output_dir: Path,
    settings: Settings,
) -> list[Path]:
    """Copy files from today's *paste-attachments* folder into *output_dir*.

    Each ``.txt`` file inside ``<root>/<source>/<today>/`` is copied (or moved,
    depending on ``paste_attachments.copy_mode``) into
    ``<output_dir>/<target>/<today>/`` under a slugified filename derived from
    the first two sentences of the file content.

    This makes manually-pasted long text files searchable / eyeballable inside
    the context output directory without flooding the aggregator's main input
    pipeline.

    Args:
        root: Project root (where ``paste_attachments.source_dir`` lives).
        output_dir: Resolved output directory (e.g. ``context_output/``).
        settings: Effective settings object.

    Returns:
        List of paths that were successfully written under ``output_dir``.
    """
    import shutil  # local import keeps top-of-file imports tidy

    paste = settings.paste_attachments
    if not bool(paste.enabled):
        return []

    source_subdir = paste.source_dir
    target_subdir = paste.target_subdir
    date_format = paste.date_format
    copy_mode = paste.copy_mode

    source_root = root / source_subdir
    if not source_root.is_dir():
        return []

    date_folder = datetime.now().strftime(date_format)
    source_today = source_root / date_folder
    if not source_today.is_dir():
        return []

    target_dir = output_dir / target_subdir / date_folder
    target_dir.mkdir(parents=True, exist_ok=True)

    sources = sorted(p for p in source_today.glob("*.txt") if p.is_file())
    if not sources:
        return []

    written: list[Path] = []
    for src_path in sources:
        text = _read_text_safely(src_path)
        if text is None:
            logger.warning("Could not decode %s — skipped.", src_path.name)
            continue

        # Use original file stem as slug fallback so empty/garbled pastes
        # still get a recognisable name.
        fallback = src_path.stem or "paste"
        slug = slugify_two_sentences(text, fallback=fallback) if text.strip() else fallback

        target_path = target_dir / f"{slug}.txt"
        if target_path.exists():
            # Idempotent re-runs: do NOT overwrite the user's named archive.
            logger.warning(
                "Skipping %s: target already exists at %s",
                src_path.name,
                target_path,
            )
            continue

        copied_ok = False
        if copy_mode == "move":
            try:
                _ = shutil.move(str(src_path), str(target_path))
                copied_ok = True
            except OSError as exc:
                # Cross-device move fails on Windows; fall back to copy+warn.
                logger.warning(
                    "Move failed for %s (%s); falling back to copy.",
                    src_path.name,
                    exc,
                )
        if not copied_ok:
            try:
                _ = shutil.copy2(str(src_path), str(target_path))
                copied_ok = True
            except OSError as exc:
                logger.error("Could not write %s: %s", target_path, exc)
                continue

        written.append(target_path)

    if written:
        logger.info(
            "Paste-attachments: archived %d file(s) → %s",
            len(written),
            target_dir,
        )
    return written


__all__ = [
    # Schema
    "Settings",
    "OutputSettings",
    "ArchiveSettings",
    "ModelsSettings",
    "JudgeSettings",
    "CompactSettings",
    "PasteAttachmentsSettings",
    "TargetArenaSettings",
    "IgnoreSettings",
    "InputsSettings",
    "settings_from_dict",
    # I/O
    "load_settings",
    "save_settings",
    "display_settings",
    "ensure_context_dir",
    "write_default_ignore_if_enabled",
    "sync_paste_attachments",
    # Filename helpers
    "aggregate_filename",
    "compare_filename",
    "slugify_two_sentences",
    "extract_first_sentences",
    # Legacy alias
    "DEFAULT_SETTINGS",
]
