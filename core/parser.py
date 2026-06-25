"""Core parser module for the File Aggregator tool.
Handles file parsing, path resolution, tree generation, ignore patterns,
settings management, output directory resolution, and multi-file discovery.
"""
from __future__ import annotations

import sys
import fnmatch
import functools
import json
import re
from pathlib import Path
from typing import cast, Iterator

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
    "archive_dir": "ARCHIVE",
    "inputs_dir": ".context/inputs",
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


def initialize_environment(
    root: Path,
    model_count: int = 2,
    output_dir: Path | None = None,
) -> None:
    """Ensure required files and directories exist.

    Non-interactive by default (Req 4).  Creates ``files.txt`` in the
    current working directory.
    """
    # 1. Ensure files.txt exists (in CWD)
    files_txt = Path("files.txt")
    if not files_txt.exists():
        _ = files_txt.touch()
        print(f"Created {files_txt}")


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


@functools.lru_cache(maxsize=16384)
def _check_glob_match(path_str: str, patterns: frozenset[str]) -> bool:
    """Cached glob matching to reduce O(N*P) regex recompilation overhead."""
    return any(fnmatch.fnmatch(path_str, pat) for pat in patterns)


def should_ignore(path: Path, root: Path, patterns: frozenset[str]) -> bool:
    """Decide whether *path* matches any exclusion pattern.

    Matching is performed against:
    * The full POSIX relative path (e.g. ``src/utils/helper.py``).
    * Each individual path component (e.g. ``src``, ``utils``, ``helper.py``).

    Uses :func:`_check_glob_match` with LRU caching to avoid redundant
    regex compilations across repeated calls with the same pattern set.

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

    if _check_glob_match(rel_posix, patterns):
        return True

    for part in rel.parts:
        if _check_glob_match(part, patterns):
            return True

    return False


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

        if not resolved_path.exists():
            print(
                f"WARNING: Cross-platform path resolution failed for"
                f" {stripped}. Resolved to {resolved_path} which does not"
                f" exist. Falling back to normalized path.",
                file=sys.stderr,
            )
            return Path(normalized)

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
                start, end = int(m.group(1)), int(m.group(2))
                if start > end:
                    print(
                        f"WARNING: Reversed line range {start}-{end} for"
                        f" {path_part.rstrip()}, auto-corrected to {end}-{start}",
                        file=sys.stderr,
                    )
                    start, end = end, start
                ranges.append((start, end))
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
    
    # Try reading with utf-8-sig (handles BOM), fall back to utf-16 if needed
    try:
        with source_file.open("r", encoding="utf-8-sig") as fh:
            lines = fh.readlines()
    except UnicodeDecodeError:
        with source_file.open("r", encoding="utf-16") as fh:
            lines = fh.readlines()

    for line in lines:
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


def stream_file_content(
    path: Path, ranges: list[tuple[int, int]] | None
) -> Iterator[str]:
    """Yield lines from a file, efficiently stopping early if ranges allow."""
    try:
        with path.open("r", encoding="utf-8") as fh:
            if ranges is None:
                yield from fh
                return

            sorted_ranges = sorted(ranges, key=lambda r: r[0])

            current_line = 1
            last_end = 0
            hit_eof = False

            for start, end in sorted_ranges:
                if hit_eof:
                    break

                # Handle gap between non-contiguous ranges
                if last_end > 0 and start > last_end + 1:
                    yield "...\n"

                # Fast forward to start line
                while current_line < start:
                    line = fh.readline()
                    if not line:
                        hit_eof = True
                        break
                    current_line += 1

                if hit_eof:
                    break

                # Yield lines within the current range
                while current_line <= end:
                    line = fh.readline()
                    if not line:
                        hit_eof = True
                        break
                    yield line
                    current_line += 1

                # Warn if requested range exceeded file length
                if end >= current_line and hit_eof:
                    yield (
                        f"\n[WARNING: Reached EOF before fulfilling range"
                        f" {start}-{end} in {path.name}]\n"
                    )

                last_end = end

    except OSError as exc:
        print(f"ERROR reading {path}: {exc}", file=sys.stderr)
        yield f"\n[ERROR: Could not read file {path}]\n"
    except UnicodeDecodeError as exc:
        print(f"ERROR decoding {path}: {exc}", file=sys.stderr)
        yield f"\n[ERROR: Could not decode file {path} as UTF-8]\n"


def read_file_paths(source_file: Path) -> list[Path]:
    """Read one file path per line from a plain-text source file.

    Blank lines, lines consisting only of whitespace, and comment lines
    (starting with ``#``) are skipped.

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
    
    try:
        with source_file.open("r", encoding="utf-8-sig") as fh:
            lines = fh.readlines()
    except UnicodeDecodeError:
        with source_file.open("r", encoding="utf-16") as fh:
            lines = fh.readlines()

    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            paths.append(Path(stripped))

    return paths


def aggregate_files(
    entries: list[tuple[Path, list[tuple[int, int]] | None, bool]],
    output_file: Path,
    root: Path | None,
) -> None:
    """Write each file's contents (or snippets) to *output_file* with headers.

    Supports full files, line-range snippets, and "important" markers.
    File content is streamed to the output, ensuring minimal memory usage.

    Args:
        entries: Ordered list of (Path, line_ranges, is_important) tuples.
                 line_ranges is None for full files, or a list of (start, end).
        output_file: Destination file; created or truncated on open.
                     Parent directories are created automatically.
        root: Project root for :func:`get_display_path`, or ``None``.
    """
    # Ensure parent directory exists (Req 1 — output may be in a subfolder)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    print(
        f"Overwriting {output_file.name}. Note: The Judge evaluates"
        f" files in the models/ directory, not {output_file.name}.",
        file=sys.stderr,
    )

    with output_file.open("w", encoding="utf-8") as out:
        for path, line_ranges, is_important in entries:
            if not path.is_file():
                print(f"ERROR: Not a file: {path}", file=sys.stderr)
                continue

            display = get_display_path(path, root)

            if line_ranges is None:
                header = f"# --- FILE: {display} ---"
            elif is_important:
                range_str = ",".join(f"{s}-{e}" for s, e in line_ranges)
                header = f"# --- IMPORTANT STRUCTURE: {display} [{range_str}] ---"
            else:
                range_str = ",".join(f"{s}-{e}" for s, e in line_ranges)
                header = f"# --- SNIPPET: {display} [{range_str}] ---"

            out.write(header + "\n")
            
            for line in stream_file_content(path, line_ranges):
                out.write(line)
            
            # Ensure separation between files
            out.write("\n")


# ---------------------------------------------------------------------------
# Multi-file discovery (Req 2)
# ---------------------------------------------------------------------------


def discover_files_txt(
    cwd: Path, root: Path | None = None, settings: dict[str, object] | None = None
) -> list[tuple[Path, str]]:
    """Discover input files and return (file_path, arena_name) tuples.
    
    Primary: root/.context/inputs/*.txt
    Fallback: cwd/files.txt and cwd/files_*.txt
    """
    results: list[tuple[Path, str]] = []
    
    if root and settings:
        inputs_dir_str = cast(str, settings.get("inputs_dir", ".context/inputs"))
        inputs_dir = root / inputs_dir_str
        
        if inputs_dir.is_dir():
            for p in sorted(inputs_dir.glob("*.txt")):
                if p.is_file():
                    arena_name = p.stem
                    results.append((p, arena_name))
            if results:
                return results

    # Fallback to CWD
    main = cwd / "files.txt"
    if main.is_file():
        results.append((main, "files"))
        
    for p in sorted(cwd.glob("files_*.txt")):
        if p.is_file():
            suffix = p.name[len("files_") : -len(".txt")]
            results.append((p, f"files_{suffix}"))
            
    return results


# ---------------------------------------------------------------------------
# Output directory resolution (Req 1)
# ---------------------------------------------------------------------------


def resolve_arena_dir(output_dir: Path, arena_name: str) -> Path:
    """Resolve the NNN-<arena-name> directory inside context_output/arenas/.
    
    Reuses the highest sequence number for the same arena_name.
    """
    arenas_base = output_dir / "arenas"
    arenas_base.mkdir(parents=True, exist_ok=True)
    
    max_all = 0
    existing_match = None
    max_match = 0
    
    for d in arenas_base.iterdir():
        if d.is_dir() and "-" in d.name:
            parts = d.name.split("-", 1)
            if parts[0].isdigit():
                num = int(parts[0])
                if num > max_all:
                    max_all = num
                if parts[1] == arena_name:
                    if num > max_match:
                        max_match = num
                        existing_match = d

    if existing_match is not None:
        return existing_match
        
    next_num = max_all + 1
    next_dir = arenas_base / f"{next_num:03d}-{arena_name}"
    next_dir.mkdir(parents=True, exist_ok=True)
    return next_dir


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


# ---------------------------------------------------------------------------
# Canonical models directory (lives under the output dir)
# ---------------------------------------------------------------------------


def resolve_models_dir(output_dir: Path) -> Path:
    """Return the canonical models directory: ``output_dir/models/``.

    The models directory is created if it does not already exist.

    Args:
        output_dir: Resolved output directory (e.g. ``context_output/``).

    Returns:
        Path to the models directory, guaranteed to exist.
    """
    models_dir = output_dir / "models"
    models_dir.mkdir(parents=True, exist_ok=True)
    return models_dir


# ---------------------------------------------------------------------------
# Legacy-output migration (replaces the old EC8 cleanup)
# ---------------------------------------------------------------------------

# Legacy output files written by older versions of the tool directly into CWD.
_LEGACY_OUTPUT_FILES: tuple[str, ...] = (
    "arena.txt",
    "structure.txt",
    "compare.md",
    "compare.txt",
)
_LEGACY_OUTPUT_GLOBS: tuple[str, ...] = (
    "arena_*.txt",
    "structure_*.txt",
    "compare_*.md",
    "compare_*.txt",
)


def _output_dir_already_populated(output_dir: Path) -> bool:
    """Return True if *output_dir* already holds a migrated ``models/`` dir.

    Only checks for ``models/`` — output files (arena, structure, compare)
    are regenerated each run and safe to overwrite.  The guard prevents
    double-moving ``root/models/`` when migration already ran.
    """
    models_dir = output_dir / "models"
    return models_dir.is_dir() and any(models_dir.iterdir())


def _resolve_migration_dest(output_dir: Path, name: str) -> Path:
    """Pick a non-colliding destination filename inside *output_dir*.

    Appends ``_migrated_N`` before the extension if the target already
    exists (e.g. ``arena_migrated_1.txt``).
    """
    dest = output_dir / name
    if not dest.exists():
        return dest
    stem = Path(name).stem
    suffix = Path(name).suffix
    counter = 1
    while True:
        candidate = output_dir / f"{stem}_migrated_{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def migrate_old_outputs(root: Path, output_dir: Path) -> list[Path]:
    """Move legacy CWD outputs and root ``models/`` into *output_dir*.

    Non-destructive migration that consolidates the pre-output-folder
    layout into the canonical ``output_dir/``:

    * Legacy output files (``arena.txt``, ``structure.txt``,
      ``compare.md``, ``compare.txt`` and their ``_*`` multi-file
      variants) are moved from the CWD into ``output_dir/``.
    * ``root/models/`` — if it exists — is moved in its entirety into
      ``output_dir/models/``, preserving any ``old/N`` history and the
      active response files.

    Files that are NOT touched: ``files*.txt``, ``.context/``, ``.env``,
    ``context.txt`` (not a tool output), ``llm.txt``.

    Safety guard: if *output_dir* already contains tool outputs or a
    non-empty ``models/`` directory, migration is skipped entirely to
    protect existing data (the caller may have already migrated).

    Args:
        root: Project root directory (where the legacy ``models/`` lives).
        output_dir: Resolved output directory to migrate INTO.

    Returns:
        List of paths that were moved (empty if nothing was migrated).
    """
    import shutil

    cwd = Path.cwd()
    moved: list[Path] = []

    # Guard: never migrate into an already-populated output dir.
    if _output_dir_already_populated(output_dir):
        return moved

    # 1. Move legacy output files from CWD → output_dir/.
    cwd_legacy: list[Path] = []
    for name in _LEGACY_OUTPUT_FILES:
        p = cwd / name
        if p.is_file():
            cwd_legacy.append(p)
    for glob in _LEGACY_OUTPUT_GLOBS:
        cwd_legacy.extend(p for p in cwd.glob(glob) if p.is_file())

    for src in cwd_legacy:
        dest = _resolve_migration_dest(output_dir, src.name)
        _ = shutil.move(str(src), str(dest))
        moved.append(dest)

    # 2. Move root/models/ → output_dir/models/ (whole tree, one move).
    root_models = root / "models"
    if root_models.is_dir():
        dest_models = output_dir / "models"
        if dest_models.exists():
            # Merge case: dest models/ exists but (per guard above) is
            # empty — move individual top-level entries instead.
            for entry in list(root_models.iterdir()):
                target = dest_models / entry.name
                if target.exists():
                    target = _resolve_migration_dest(dest_models, entry.name)
                _ = shutil.move(str(entry), str(target))
                moved.append(target)
            try:
                root_models.rmdir()
            except OSError:
                pass
        else:
            _ = shutil.move(str(root_models), str(dest_models))
            moved.append(dest_models)

    if moved:
        names = ", ".join(
            p.name if p.is_file() else f"{p.name}/" for p in moved
        )
        print(f"Migrated: {names} → {output_dir}/")

    return moved
