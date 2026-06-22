"""Core parser module for the File Aggregator tool.
Handles file parsing, path resolution, tree generation, ignore patterns,
settings management, output directory resolution, and multi-file discovery.
"""
from __future__ import annotations

import sys
import fnmatch
import json
import re
from pathlib import Path
from typing import cast

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

_ROOT_MARKERS: frozenset[str] = frozenset(
    {"package.json", ".git", "requirements.txt", "pyproject.toml", "src"}
)
_DEFAULT_IGNORE: frozenset[str] = frozenset(
    {
        ".git",
        "node_modules",
        "dist",
        "build",
        ".windsurf",
        ".agents",
        ".speckit",
        ".specify",
        "venv",
        ".vercel",
        ".cursor",
        ".vscode",
        ".github",
        "compare_4.txt",
        "compare-template.bak",
        "compare_of_compare.txt",
        "scripts",
        "migrations.old",
        "__pycache__",
        ".next",
        ".venv",
        ".index_ignore",
        "*.pyc",
        ".DS_Store",
        "files.txt",
        "arena.txt",
        "structure.txt",
        "llm.txt",
        "compare.md",
        "compare.txt",
        "compare_*.md",
        "compare_*.txt",
        "files_*.txt",
        "arena_*.txt",
        "structure_*.txt",
        "models",
        ".pnpm-store",
        "desktop.ini",
        "models/old",
        "get-shit-done",
        "gifts",
        "agents",
        ".agent",
        # Output and configuration directories (Req 1, Req 8)
        "context_output",
        ".context",
    }
)
_MAX_TREE_DEPTH: int = 20

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
    "archive_dir": "models/ARCHIVE",
}

# Template written to .context/ignore when auto-created (Req 8)
_DEFAULT_IGNORE_TEMPLATE = """\
# Context Tool — Ignore Patterns
# One pattern per line.  # Comments and blank lines are ignored.
# These patterns are ADDITIONAL to the built-in defaults.
# Built-in defaults already cover: .git, node_modules, __pycache__, etc.
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

    # Auto-create ignore file if missing
    ignore_path = context_dir / "ignore"
    if not ignore_path.is_file():
        _ = ignore_path.write_text(
            _DEFAULT_IGNORE_TEMPLATE, encoding="utf-8"
        )
        print(f"Created {ignore_path}")

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
    settings_path = root / ".context" / "settings.json"

    # Ensure the file exists
    if not settings_path.is_file():
        _ = ensure_context_dir(root)
        return dict(DEFAULT_SETTINGS)

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
# Environment initialization
# ---------------------------------------------------------------------------


def initialize_environment(root: Path, model_count: int = 2) -> None:
    """Ensure required files and directories exist.

    Non-interactive by default (Req 4).  Creates ``files.txt`` in the
    current working directory and a ``models/`` folder under *root* when
    they are missing.  If the ``models/`` folder contains no model
    response files (excluding ``prompt.txt`` and ``*_NOTES.*`` files),
    empty template files (``A.txt``, ``B.txt``, …) are created based on
    *model_count*.

    Args:
        root: Project root directory where ``models/`` will be created.
        model_count: Number of model template files to create if none exist.
    """
    # 1. Ensure files.txt exists (in CWD)
    files_txt = Path("files.txt")
    if not files_txt.exists():
        _ = files_txt.touch()
        print(f"Created {files_txt}")

    # 2. Ensure models/ directory exists (under root)
    models_dir = root / "models"
    if not models_dir.is_dir():
        models_dir.mkdir(parents=True, exist_ok=True)
        print(f"Created {models_dir}/")

    # 3. Ensure prompt.txt exists in models/
    prompt_file = models_dir / "prompt.txt"
    if not prompt_file.exists():
        _ = prompt_file.touch()
        print(f"Created {prompt_file}")

    # 4. Ensure model template files exist if models/ is empty
    _ensure_model_files(models_dir, model_count)


def _ensure_model_files(models_dir: Path, model_count: int) -> None:
    """Create default model template files if no model responses exist.

    Args:
        models_dir: Path to the ``models/`` directory.
        model_count: Number of model files to create.
    """
    existing = [
        f
        for f in models_dir.iterdir()
        if f.is_file()
        and f.name != "prompt.txt"
        and not f.name.endswith("_NOTES.md")
        and not f.name.endswith("_NOTES.txt")
    ]

    if not existing and model_count > 0:
        for i in range(model_count):
            letter = chr(ord("A") + i)
            model_file = models_dir / f"{letter}.txt"
            _ = model_file.touch()
            print(f"Created {model_file}")


# ---------------------------------------------------------------------------
# Project root detection
# ---------------------------------------------------------------------------


def find_project_root(path: Path) -> Path | None:
    """Search parent directories for a recognised project-root marker.

    Traversal starts at the parent of *path* and walks toward the
    filesystem root.  The search stops at the first directory that
    contains any marker in ``_ROOT_MARKERS``.

    Args:
        path: Any file path whose project root is required.

    Returns:
        The nearest ancestor directory containing a root marker,
        or ``None`` if no marker is found.
    """
    current = path.resolve().parent

    while True:
        if any((current / marker).exists() for marker in _ROOT_MARKERS):
            return current
        parent = current.parent
        if parent == current:  # filesystem root reached
            return None
        current = parent


# ---------------------------------------------------------------------------
# Display-path helpers
# ---------------------------------------------------------------------------


def get_display_path(path: Path, root: Path | None) -> str:
    """Return the shortest unambiguous display string for *path*.

    Resolution order:
    1. Relative to *root* (preferred).
    2. Relative to the current working directory.
    3. Absolute POSIX path as a last resort.

    Args:
        path: Absolute path of the file being displayed.
        root: Detected project root, or ``None``.

    Returns:
        A forward-slash display string that uniquely identifies *path*.
    """
    abs_path = path.resolve()

    for anchor in filter(None, [root, Path.cwd()]):
        try:
            return abs_path.relative_to(anchor).as_posix()
        except ValueError:
            continue

    return abs_path.as_posix()


# ---------------------------------------------------------------------------
# Ignore-pattern management (Req 8)
# ---------------------------------------------------------------------------


def load_ignore_patterns(root: Path | None) -> frozenset[str]:
    """Load exclusion patterns from config files plus built-in defaults.

    Pattern sources (merged in order):
    1. Built-in ``_DEFAULT_IGNORE`` (always active).
    2. ``.context/ignore`` — user-managed patterns inside the config dir.
    3. ``.contextignore`` — legacy file at the project root (backwards compat).
    4. ``.index_ignore`` — older legacy file (backwards compat).

    If ``.context/ignore`` does not exist, it is auto-created with a
    default template via :func:`ensure_context_dir`.

    Args:
        root: Project root to search for config files.
              Falls back to the current working directory when ``None``.

    Returns:
        Immutable set of glob patterns identifying paths to exclude.
    """
    extra: set[str] = set()
    search_dir = root if root is not None else Path.cwd()

    # Ensure .context/ignore exists
    _ = ensure_context_dir(search_dir)

    # Read .context/ignore
    context_ignore = search_dir / ".context" / "ignore"
    if context_ignore.is_file():
        extra.update(_read_pattern_file(context_ignore))

    # Read .contextignore (legacy, backwards compat)
    contextignore = search_dir / ".contextignore"
    if contextignore.is_file():
        extra.update(_read_pattern_file(contextignore))

    # Read .index_ignore (older legacy, backwards compat)
    index_ignore = search_dir / ".index_ignore"
    if index_ignore.is_file():
        extra.update(_read_pattern_file(index_ignore))

    return _DEFAULT_IGNORE | frozenset(extra)


def _read_pattern_file(path: Path) -> set[str]:
    """Read ignore patterns from a text file, one per line.

    Lines starting with ``#`` and blank lines are skipped.

    Args:
        path: Path to the pattern file.

    Returns:
        Set of non-empty, non-comment pattern strings.
    """
    patterns: set[str] = set()
    try:
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                stripped = line.strip()
                if stripped and not stripped.startswith("#"):
                    patterns.add(stripped)
    except OSError as exc:
        print(f"Warning: Could not read {path}: {exc}", file=sys.stderr)
    return patterns


def should_ignore(path: Path, root: Path, patterns: frozenset[str]) -> bool:
    """Decide whether *path* matches any exclusion pattern.

    Matching is performed against:
    * The full POSIX relative path (e.g. ``src/utils/helper.py``).
    * Each individual path component (e.g. ``src``, ``utils``, ``helper.py``).

    Args:
        path: Path to evaluate.
        root: Project root used to compute the relative path.
        patterns: Compiled set of glob patterns.

    Returns:
        ``True`` if *path* should be excluded from processing.
    """
    try:
        rel = path.relative_to(root)
    except ValueError:
        return False  # outside root — never auto-ignore

    rel_posix = rel.as_posix()

    return any(
        fnmatch.fnmatch(rel_posix, pat)
        or any(fnmatch.fnmatch(part, pat) for part in rel.parts)
        for pat in patterns
    )


# ---------------------------------------------------------------------------
# Directory-tree generation
# ---------------------------------------------------------------------------


def generate_tree(
    dir_path: Path,
    root: Path,
    patterns: frozenset[str],
    prefix: str = "",
    _depth: int = 0,
) -> list[str]:
    """Recursively build a visual directory tree.

    Symbolic-link directories are listed but not descended into, preventing
    infinite loops on circular links.  Traversal stops at ``_MAX_TREE_DEPTH``
    regardless of structure depth.

    Args:
        dir_path: Directory to scan at the current recursion level.
        root: Project root, used by :func:`should_ignore`.
        patterns: Glob patterns identifying items to exclude.
        prefix: Accumulated indentation string (internal, set by recursion).
        _depth: Current recursion depth (internal, set by recursion).

    Returns:
        Lines forming the visual tree, without a trailing newline each.
    """
    if _depth > _MAX_TREE_DEPTH:
        return [f"{prefix}... (max depth {_MAX_TREE_DEPTH} reached)"]

    try:
        items = sorted(
            dir_path.iterdir(),
            key=lambda p: (not p.is_dir(), p.name.lower()),
        )
        items = [i for i in items if not should_ignore(i, root, patterns)]
    except PermissionError:
        return [f"{prefix}[Permission Denied]"]

    tree: list[str] = []
    for index, item in enumerate(items):
        is_last = index == len(items) - 1
        connector = "└── " if is_last else "├── "
        suffix = "/" if item.is_dir() else ""
        tree.append(f"{prefix}{connector}{item.name}{suffix}")

        if item.is_dir() and not item.is_symlink():
            child_prefix = prefix + ("    " if is_last else "│   ")
            tree.extend(
                generate_tree(item, root, patterns, child_prefix, _depth + 1)
            )

    return tree


# ---------------------------------------------------------------------------
# Path parsing with line ranges
# ---------------------------------------------------------------------------


def resolve_cross_platform_path(path_str: str) -> Path:
    """Resolve a path string which might be from a different OS.

    If the path exists as-is, returns it.  Otherwise, normalises
    separators and tries to find an overlapping suffix with the current
    working directory to map it to the current environment.
    """
    stripped = path_str.strip()
    if not stripped:
        return Path(stripped)

    # If the path already exists, just return it
    p = Path(stripped)
    if p.exists():
        return p

    # Normalize Windows separators
    normalized = stripped.replace("\\", "/")

    # If the normalized path exists, return it
    p_norm = Path(normalized)
    if p_norm.exists():
        return p_norm

    # Remove drive letter if present (e.g. C:/ or c:/)
    normalized_clean = normalized
    if re.match(r"^[a-zA-Z]:", normalized):
        normalized_clean = normalized[2:]

    # Strip leading slash to make it relative-friendly for suffix overlap
    normalized_clean = normalized_clean.lstrip("/")

    # Try to match suffix overlap with CWD
    path_parts = [part for part in normalized_clean.split("/") if part]

    cwd = Path.cwd().resolve()
    cwd_parts = [part for part in cwd.parts if part]

    overlap_len = 0
    for i in range(1, len(cwd_parts) + 1):
        suffix = cwd_parts[-i:]
        if len(path_parts) >= i and path_parts[:i] == suffix:
            overlap_len = i

    if overlap_len > 0:
        remaining_parts = path_parts[overlap_len:]
        resolved_path = cwd
        for part in remaining_parts:
            resolved_path = resolved_path / part
        return resolved_path

    # As a final fallback, return Path(normalized)
    return Path(normalized)


def parse_file_entry(
    line: str,
) -> tuple[Path, list[tuple[int, int]] | None, bool]:
    """Parse a files.txt entry into (path, line_ranges, is_important).

    Supported formats:
        /path/to/file.py              → (Path, None, False)
        /path/to/file.py:10-20        → (Path, [(10, 20)], False)
        /path/to/file.py:5-10,25-30   → (Path, [(5, 10), (25, 30)], False)
        !/path/to/file.py:1-5         → (Path, [(1, 5)], True)

    Args:
        line: A stripped, non-empty input line from files.txt.

    Returns:
        A tuple of (Path, list of (start, end) ranges or None, is_important flag).
        Line numbers are 1-indexed and inclusive.
    """
    stripped = line.strip()
    is_important = stripped.startswith("!")
    if is_important:
        stripped = stripped[1:]

    if ":" in stripped:
        path_part, range_part = stripped.rsplit(":", 1)
        ranges: list[tuple[int, int]] = []
        for segment in range_part.split(","):
            m = re.match(r"(\d+)\s*-\s*(\d+)", segment.strip())
            if m:
                ranges.append((int(m.group(1)), int(m.group(2))))
        if ranges:
            return (
                resolve_cross_platform_path(path_part.rstrip()),
                ranges,
                is_important,
            )

    return resolve_cross_platform_path(stripped), None, is_important


def read_file_entries(
    source_file: Path,
) -> list[tuple[Path, list[tuple[int, int]] | None, bool]]:
    """Read file entries (with optional line ranges) from files.txt.

    Blank lines and comment lines (starting with ``#``) are skipped.
    Any non-blank, non-comment line that does not resolve to a valid
    existing file path triggers a warning on stderr and is skipped
    (Req 3).

    Args:
        source_file: Path to the files.txt listing entries.

    Returns:
        Ordered list of (Path, line_ranges, is_important) tuples.
        Returns an empty list if source_file does not exist.

    Raises:
        FileNotFoundError: If source_file does not exist or is not a file.
    """
    if not source_file.is_file():
        raise FileNotFoundError(f"Source paths file not found: {source_file}")

    entries: list[tuple[Path, list[tuple[int, int]] | None, bool]] = []
    with source_file.open("r", encoding="utf-8") as fh:
        for line in fh:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            path, ranges, is_important = parse_file_entry(stripped)
            # Validate that the path resolves to an existing file (Req 3)
            if not path.is_file():
                print(
                    f"Warning: Invalid path skipped: {stripped}",
                    file=sys.stderr,
                )
                continue
            entries.append((path, ranges, is_important))

    return entries


def extract_lines(
    content: str, ranges: list[tuple[int, int]]
) -> str:
    """Extract specified line ranges from content.

    Args:
        content: Full file text.
        ranges: List of (start, end) tuples, 1-indexed, inclusive.

    Returns:
        The selected lines, with '...\\n' separator between non-contiguous ranges.
    """
    lines = content.splitlines(keepends=True)
    result: list[str] = []
    last_end = 0

    for start, end in ranges:
        s = max(0, start - 1)
        e = min(len(lines), end)

        # Add separator if there's a gap from previous range
        if result and s > last_end:
            result.append("...\n")

        result.extend(lines[s:e])
        last_end = e

    return "".join(result)


def read_file_paths(source_file: Path) -> list[Path]:
    """Read one file path per line from a plain-text source file.

    Blank lines and lines consisting only of whitespace are skipped.

    Args:
        source_file: Path to the text file listing source paths.

    Returns:
        Ordered list of :class:`~pathlib.Path` objects.

    Raises:
        FileNotFoundError: If *source_file* does not exist or is not a file.
    """
    if not source_file.is_file():
        raise FileNotFoundError(f"Source paths file not found: {source_file}")

    paths: list[Path] = []
    with source_file.open("r", encoding="utf-8") as fh:
        for line in fh:
            stripped = line.strip()
            if stripped:
                paths.append(Path(stripped))

    return paths


def aggregate_files(
    entries: list[tuple[Path, list[tuple[int, int]] | None, bool]],
    output_file: Path,
    root: Path | None,
) -> None:
    """Write each file's contents (or snippets) to *output_file* with headers.

    Supports full files, line-range snippets, and "important" markers.
    File content is read *before* any header is written, ensuring that a
    read failure never leaves an orphaned header in the output.

    Args:
        entries: Ordered list of (Path, line_ranges, is_important) tuples.
                 line_ranges is None for full files, or a list of (start, end).
        output_file: Destination file; created or truncated on open.
                     Parent directories are created automatically.
        root: Project root for :func:`get_display_path`, or ``None``.
    """
    # Ensure parent directory exists (Req 1 — output may be in a subfolder)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with output_file.open("w", encoding="utf-8") as out:
        for path, line_ranges, is_important in entries:
            try:
                if not path.is_file():
                    print(f"ERROR: Not a file: {path}", file=sys.stderr)
                    continue

                # Read content first — header is only written on success.
                full_content = path.read_text(encoding="utf-8")
                display = get_display_path(path, root)

                # Determine header type and content to write
                if line_ranges is None:
                    # Full file
                    content = full_content
                    header = f"# --- FILE: {display} ---"
                elif is_important:
                    # Important structure snippet
                    content = extract_lines(full_content, line_ranges)
                    range_str = ",".join(
                        f"{s}-{e}" for s, e in line_ranges
                    )
                    header = (
                        f"# --- IMPORTANT STRUCTURE: "
                        f"{display} [{range_str}] ---"
                    )
                else:
                    # Regular code snippet
                    content = extract_lines(full_content, line_ranges)
                    range_str = ",".join(
                        f"{s}-{e}" for s, e in line_ranges
                    )
                    header = (
                        f"# --- SNIPPET: "
                        f"{display} [{range_str}] ---"
                    )

                _ = out.write(header + "\n")
                _ = out.write(content)
                if not content.endswith("\n"):
                    _ = out.write("\n")
                _ = out.write("\n")

            except PermissionError as exc:
                print(
                    f"ERROR: Permission denied — {path}: {exc}",
                    file=sys.stderr,
                )
            except UnicodeDecodeError as exc:
                print(
                    f"ERROR: Encoding error — {path}: {exc}",
                    file=sys.stderr,
                )
            except OSError as exc:
                print(
                    f"ERROR: OS error — {path}: {exc}",
                    file=sys.stderr,
                )


# ---------------------------------------------------------------------------
# Multi-file discovery (Req 2)
# ---------------------------------------------------------------------------


def discover_files_txt(cwd: Path) -> list[tuple[Path, str]]:
    """Discover all ``files*.txt`` inputs in *cwd*.

    Matches ``files.txt`` and ``files_*.txt`` (e.g. ``files_1.txt``,
    ``files_02.txt``).  Each discovered input file produces its own set
    of arena/structure/compare outputs with a matching suffix.

    Args:
        cwd: Directory to scan for input files.

    Returns:
        List of ``(file_path, suffix)`` tuples, sorted.
        ``files.txt`` → suffix ``""``, ``files_1.txt`` → suffix ``"_1"``.
    """
    results: list[tuple[Path, str]] = []

    # Check for main files.txt
    main = cwd / "files.txt"
    if main.is_file():
        results.append((main, ""))

    # Check for files_*.txt
    for p in sorted(cwd.glob("files_*.txt")):
        if p.is_file():
            # Extract suffix: "files_1.txt" → "_1", "files_02.txt" → "_02"
            suffix = p.name[len("files") : -len(".txt")]
            results.append((p, suffix))

    return results


# ---------------------------------------------------------------------------
# Output directory resolution (Req 1)
# ---------------------------------------------------------------------------


def resolve_output_dir(
    root: Path,
    settings: dict[str, object],
    cli_output: str | None = None,
) -> Path:
    """Resolve the output directory.

    Precedence (Req 4): CLI ``--output`` flag > settings > default.

    Args:
        root: Project root directory.
        settings: Loaded settings dictionary.
        cli_output: Optional ``--output`` flag value from the command line.

    Returns:
        Path to the output directory (created if necessary).
    """
    dir_name = cli_output or settings.get("output_dir", "context_output")
    output_dir = root / str(dir_name)
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir
