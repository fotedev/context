"""Settings & configuration management + paste-attachments archival.

Holds the DEFAULT_SETTINGS schema, the .context/settings.json load/save/migrate
lifecycle, and the settings-driven paste-attachments archival feature.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import cast

# ---------------------------------------------------------------------------
# Default settings schema (Req 9)
# ---------------------------------------------------------------------------

DEFAULT_SETTINGS: dict[str, object] = {
    "output_dir": "context_output",
    "output_format": "md",
    "model_count": 2,
    "gemini_judge": False,
    "compact_mode": False,
    "archive": False,
    "archive_dir": "ARCHIVE",
    "inputs_dir": ".context/inputs",
    # Paste-attachments archival (paste long text into a file in
    # tmp/paste-attachments/<date>/; tool renames + copies into output dir on run).
    "paste_attachments_enabled": False,
    "paste_attachments_source_dir": "tmp/paste-attachments",
    "paste_attachments_target_subdir": "tmp/paste-attachments",
    "paste_attachments_date_format": "%Y-%m-%d",
    "paste_attachments_copy_mode": "copy",
    # Target-arena directive (first-line `# Target Arena: 006-AdminDashboard`
    # in an input file pins the arena number; filename remains source-of-truth
    # for the arena name).
    "respect_target_arena_directive": True,
    "target_arena_directive_prefix": "# Target Arena:",
    "on_arena_number_conflict": "warn_and_shift",
}

# Template written to .context/ignore when auto-created (Req 8)
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
structure.txt
llm.txt
compare.md
compare.txt
compare_*.md
compare_*.txt
files_*.txt
arena_*.txt
structure_*.txt
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


def ensure_context_dir(root: Path) -> Path:
    """Ensure the ``.context/`` directory exists with default config files.

    Creates ``.context/``, ``.context/settings.json``, and ``.context/ignore``
    if they are missing.  Existing files are never overwritten.

    Args:
        root: Project root directory.

    Returns:
        Path to the ``.context/`` directory.
    """
    context_dir = root / ".context"
    context_dir.mkdir(parents=True, exist_ok=True)

    # Auto-create settings.json if missing
    settings_path = context_dir / "settings.json"
    if not settings_path.is_file():
        save_settings(root, dict(DEFAULT_SETTINGS))
        print(
            f"Created {settings_path} — edit your preferences or delete to reset."
        )

    # Auto-create ignore file if missing or update if it contains the legacy template description
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
        _ = ignore_path.write_text(
            _DEFAULT_IGNORE_TEMPLATE, encoding="utf-8"
        )
        print(f"Created/Updated {ignore_path} with default ignore patterns.")

    # Auto-create inputs directory if missing
    inputs_dir = context_dir / "inputs"
    inputs_dir.mkdir(parents=True, exist_ok=True)

    return context_dir


# ---------------------------------------------------------------------------
# Settings management (Req 9, Req 10)
# ---------------------------------------------------------------------------


def load_settings(root: Path) -> dict[str, object]:
    """Load settings from ``.context/settings.json``, falling back to defaults.

    Resolution strategy (Req 4 precedence — settings layer):
    * If the file is missing → auto-create with defaults and return them.
    * If the file is empty → print a hint and return defaults (Edge case 2).
    * If the file contains invalid JSON → print a warning every run and
      return defaults (Edge case 2).
    * Otherwise, merge user values on top of ``DEFAULT_SETTINGS`` so that
      new keys introduced in future versions are always present.

    Args:
        root: Project root directory containing ``.context/``.

    Returns:
        A settings dictionary guaranteed to contain every key from
        ``DEFAULT_SETTINGS``.
    """
    # Ensure the configuration directory and files exist (including .context/inputs)
    _ = ensure_context_dir(root)
    settings_path = root / ".context" / "settings.json"

    try:
        content = settings_path.read_text(encoding="utf-8").strip()

        # Edge case 2: completely empty file
        if not content:
            print(
                "Use context skill with AI model to initialize preferences.",
                file=sys.stderr,
            )
            return dict(DEFAULT_SETTINGS)

        user_settings = cast(dict[str, object], json.loads(content))

        # Merge: user values override defaults, new keys get defaults
        merged = dict(DEFAULT_SETTINGS)
        merged.update(user_settings)
        _migrate_settings_file(root, merged)
        return merged

    except json.JSONDecodeError:
        # Edge case 2: invalid JSON — warn every run
        print(
            "Warning: Invalid .context/settings.json — using defaults.",
            file=sys.stderr,
        )
        return dict(DEFAULT_SETTINGS)

    except OSError as exc:
        print(
            f"Warning: Could not read .context/settings.json ({exc}) — using defaults.",
            file=sys.stderr,
        )
        return dict(DEFAULT_SETTINGS)


def save_settings(root: Path, settings: dict[str, object]) -> None:
    """Persist *settings* to ``.context/settings.json``.

    The ``.context/`` directory is created if necessary.

    Args:
        root: Project root directory.
        settings: Complete settings dictionary to write.
    """
    context_dir = root / ".context"
    context_dir.mkdir(parents=True, exist_ok=True)
    settings_path = context_dir / "settings.json"
    with settings_path.open("w", encoding="utf-8") as fh:
        json.dump(settings, fh, indent=2)
        _ = fh.write("\n")


def display_settings(root: Path) -> None:
    """Print the active settings path, current content, and help text.

    Used by the ``--settings`` CLI flag (Req 10).
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
    print("Settings schema:")
    print(json.dumps(DEFAULT_SETTINGS, indent=2))


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
    A successful ``latin-1`` decode after a UTF failure usually means the file
    is garbage; callers should treat that as user error rather than crash.
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


def _migrate_settings_file(root: Path, merged: dict[str, object]) -> None:
    """Add any missing keys (paste-attachments + arena-directive) to the
    user's settings file.

    Preserves every existing user value; only adds keys that were not present.
    Idempotent — a second call writes nothing because ``missing`` becomes empty.
    """
    new_keys = {
        "paste_attachments_enabled",
        "paste_attachments_source_dir",
        "paste_attachments_target_subdir",
        "paste_attachments_date_format",
        "paste_attachments_copy_mode",
        "respect_target_arena_directive",
        "target_arena_directive_prefix",
        "on_arena_number_conflict",
    }
    settings_path = root / ".context" / "settings.json"
    if not settings_path.is_file():
        return

    try:
        content = settings_path.read_text(encoding="utf-8").strip()
        if not content:
            return
        current = cast(dict[str, object], json.loads(content))
    except (OSError, json.JSONDecodeError):
        return

    missing = new_keys - set(current.keys())
    if not missing:
        return

    for key in missing:
        current[key] = merged.get(key)

    try:
        save_settings(root, current)
        print(
            "Added new settings to "
            f"{settings_path} (defaults applied for: "
            + ", ".join(sorted(missing))
            + ")."
        )
    except OSError as exc:
        print(f"Warning: Could not persist new settings keys: {exc}", file=sys.stderr)


def sync_paste_attachments(
    root: Path,
    output_dir: Path,
    settings: dict[str, object],
) -> list[Path]:
    """Copy files from today's *paste-attachments* folder into *output_dir*.

    Each ``.txt`` file inside ``<root>/<source>/<today>/`` is copied (or moved,
    depending on ``paste_attachments_copy_mode``) into
    ``<output_dir>/<target>/<today>/`` under a slugified filename derived from
    the first two sentences of the file content.

    This makes manually-pasted long text files searchable / eyeballable inside
    the context output directory without flooding the aggregator's main input
    pipeline.

    Args:
        root: Project root (where ``paste_attachments_source_dir`` lives).
        output_dir: Resolved output directory (e.g. ``context_output/``).
        settings: Effective settings dict (must include the five new keys).

    Returns:
        List of paths that were successfully written under ``output_dir``.
    """
    import shutil  # local import keeps top-of-file imports tidy

    if not bool(settings.get("paste_attachments_enabled", False)):
        return []

    source_subdir = str(
        settings.get("paste_attachments_source_dir", "tmp/paste-attachments")
    )
    target_subdir = str(
        settings.get("paste_attachments_target_subdir", "tmp/paste-attachments")
    )
    date_format = str(settings.get("paste_attachments_date_format", "%Y-%m-%d"))
    copy_mode = str(settings.get("paste_attachments_copy_mode", "copy")).lower()

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
            print(
                f"Warning: Could not decode {src_path.name} — skipped.",
                file=sys.stderr,
            )
            continue

        # Use original file stem as slug fallback so empty/garbled pastes
        # still get a recognisable name.
        fallback = src_path.stem or "paste"
        slug = slugify_two_sentences(text, fallback=fallback) if text.strip() else fallback

        target_path = target_dir / f"{slug}.txt"
        if target_path.exists():
            # Idempotent re-runs: do NOT overwrite the user's named archive.
            print(
                f"Skipping {src_path.name}: target already exists at {target_path}",
                file=sys.stderr,
            )
            continue

        copied_ok = False
        if copy_mode == "move":
            try:
                _ = shutil.move(str(src_path), str(target_path))
                copied_ok = True
            except OSError as exc:
                # Cross-device move fails on Windows; fall back to copy+warn.
                print(
                    f"Note: move failed for {src_path.name} ({exc}); "
                    "falling back to copy.",
                    file=sys.stderr,
                )
        if not copied_ok:
            try:
                _ = shutil.copy2(str(src_path), str(target_path))
                copied_ok = True
            except OSError as exc:
                print(
                    f"Error: Could not write {target_path}: {exc}",
                    file=sys.stderr,
                )
                continue

        written.append(target_path)

    if written:
        print(
            f"Paste-attachments: archived {len(written)} file(s) → {target_dir}"
        )
    return written