"""Slimmed core parser — path parsing, aggregation, tree, output migration.

After the Phase-#2 refactor (see ``REFACTOR_AND_STATUS_PLAN.md``), this module
keeps only the concerns that don't belong in the new ``core.settings``,
``core.arena``, or ``core.discovery`` modules. It also re-exports the public
names those modules now own so the four legacy caller files
(``aggregator.py``, ``aggregator_gui.py``, ``aggregator_tui.py``,
``renumber_arenas.py``) keep working without any import changes.
"""
from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path
from typing import Iterator

# Re-export from the new focused modules. These names exist precisely so
# `from core.parser import X` continues to work for every caller — do not
# delete any of them even if they appear "unused" inside this file.
from core.settings import (  # noqa: F401  (re-export)
    DEFAULT_SETTINGS,
    display_settings,
    ensure_context_dir,
    load_settings,
    save_settings,
    sync_paste_attachments,
)
from core.discovery import (  # noqa: F401  (re-export)
    discover_files_txt,
    discover_files_txt_with_directives,
    get_latest_state,
    load_ignore_patterns,
    should_ignore,
    write_state_breadcrumb,
)
from core.arena import (  # noqa: F401  (re-export)
    ArenaAssignment,
    ArenaDirective,
    build_arena_plan,
    resolve_arena_dir,
)

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

_ROOT_MARKERS: frozenset[str] = frozenset(
    {"package.json", ".git", "requirements.txt", "pyproject.toml", "src"}
)
_MAX_TREE_DEPTH: int = 20

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
# Directory-tree generation
# ---------------------------------------------------------------------------


def generate_tree(
    dir_path: Path,
    root: Path,
    patterns: frozenset[str],
    prefix: str = "",
    _depth: int = 0,
    output_dir: str = "context_output",
) -> list[str]:
    """Recursively build a visual directory tree.

    Symbolic-link directories are listed but not descended into, preventing
    infinite loops on circular links.  Traversal stops at ``_MAX_TREE_DEPTH``
    regardless of structure depth.

    The *output_dir* parameter is forwarded to :func:`should_ignore` so the
    structural arena-file rule can locate arena dirs even when the user has
    configured a custom output directory name.

    Args:
        dir_path: Directory to scan at the current recursion level.
        root: Project root, used by :func:`should_ignore`.
        patterns: Glob patterns identifying items to exclude.
        prefix: Accumulated indentation string (internal, set by recursion).
        _depth: Current recursion depth (internal, set by recursion).
        output_dir: Configured output directory name (default
            ``"context_output"``). Threaded down so the structural
            un-prefixed-arena-file rule can match correctly.

    Returns:
        Lines forming the visual tree, without a trailing newline each.
    """
    from core.counter import count_lines

    if _depth > _MAX_TREE_DEPTH:
        return [f"{prefix}... (max depth {_MAX_TREE_DEPTH} reached)"]

    try:
        items = sorted(
            dir_path.iterdir(),
            key=lambda p: (not p.is_dir(), p.name.lower()),
        )
        items = [i for i in items if not should_ignore(i, root, patterns, output_dir)]
    except PermissionError:
        return [f"{prefix}[Permission Denied]"]

    tree: list[str] = []
    for index, item in enumerate(items):
        is_last = index == len(items) - 1
        connector = "└── " if is_last else "├── "
        suffix = "/" if item.is_dir() else ""
        if item.is_file():
            line_count = count_lines(item)
            tree.append(f"{prefix}{connector}{item.name} ({line_count} lines)")
        else:
            tree.append(f"{prefix}{connector}{item.name}{suffix}")

        if item.is_dir() and not item.is_symlink():
            child_prefix = prefix + ("    " if is_last else "│   ")
            tree.extend(
                generate_tree(
                    item,
                    root,
                    patterns,
                    child_prefix,
                    _depth + 1,
                    output_dir,
                )
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
        /path/to/file.py:5-10,25-30   → (Path, [(5, 10), (30, 30)], False)
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
) -> int:
    """Write each file's contents (or snippets) to *output_file* with headers.

    Supports full files, line-range snippets, and "important" markers.
    File content is streamed to the output, ensuring minimal memory usage.

    Args:
        entries: Ordered list of (Path, line_ranges, is_important) tuples.
                 line_ranges is None for full files, or a list of (start, end).
        output_file: Destination file; created or truncated on open.
                     Parent directories are created automatically.
        root: Project root for :func:`get_display_path`, or ``None``.

    Returns:
        Total number of lines aggregated.
    """
    from core.counter import count_lines

    # Ensure parent directory exists (Req 1 — output may be in a subfolder)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    print(
        f"Overwriting {output_file.name}. Note: The Judge evaluates"
        f" files in the models/ directory, not {output_file.name}.",
        file=sys.stderr,
    )

    total_lines = 0

    with output_file.open("w", encoding="utf-8") as out:
        for path, line_ranges, is_important in entries:
            if not path.is_file():
                print(f"ERROR: Not a file: {path}", file=sys.stderr)
                continue

            display = get_display_path(path, root)
            line_count = count_lines(path, line_ranges)
            total_lines += line_count

            if line_ranges is None:
                header = f"# --- FILE: {display} ({line_count} lines) ---"
            elif is_important:
                range_str = ",".join(f"{s}-{e}" for s, e in line_ranges)
                header = f"# --- IMPORTANT STRUCTURE: {display} [{range_str}] ({line_count} lines) ---"
            else:
                range_str = ",".join(f"{s}-{e}" for s, e in line_ranges)
                header = f"# --- SNIPPET: {display} [{range_str}] ({line_count} lines) ---"

            out.write(header + "\n")

            for line in stream_file_content(path, line_ranges):
                out.write(line)

            # Ensure separation between files
            out.write("\n")

    return total_lines


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
# Only v1/v2 filenames — the v3+ names (``context.*``, ``arena.md``) are the
# canonical flat layout and MUST NOT be re-migrated from CWD or wrapped into
# per-file folders (see ``migrate_to_per_file_folders``).
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


# ---------------------------------------------------------------------------
# Per-file folder migration (v2 layout: arena/arena.txt, compare/compare.md, ...)
# ---------------------------------------------------------------------------

# Active (non-archived) output files that should live in their own folder.
# Each entry is (filename_pattern, target_subfolder).
# Patterns use ``.suffix`` matching so both ``compare.md`` and ``compare.txt``
# work without listing each.
#
# IMPORTANT: only v1/v2 flat filenames belong here. The v3+ canonical
# filenames (``context.*``, ``arena.md``) ARE the flat layout and must NOT
# be wrapped into per-file folders — ``migrate_to_flat_layout`` would then
# have to flatten them again on every run (round-trip).
_PER_FILE_TARGETS: tuple[tuple[str, str], ...] = (
    ("arena.txt", "arena"),
    ("compare.md", "compare"),
    ("compare.txt", "compare"),
    ("structure.txt", "structure"),
)


def _per_file_safe_dest(target_dir: Path, file_name: str) -> Path:
    """Pick a non-colliding destination inside ``target_dir``.

    If the target file already exists, append ``_v2``, ``_v3``... before the
    extension. Idempotent: if the existing target is byte-identical to the
    source, return the existing path (caller can skip the move).
    """
    candidate = target_dir / file_name
    if not candidate.exists():
        return candidate
    src = Path(file_name)
    i = 2
    while True:
        cand = target_dir / f"{src.stem}_v{i}{src.suffix}"
        if not cand.exists():
            return cand
        i += 1


def migrate_to_per_file_folders(output_dir: Path) -> list[Path]:
    """Reorganize flat outputs into per-file folders.

    New canonical layout produced by the tool:

        <output_dir>/
            arenas/<arena>/
                arena/arena.txt
                compare/compare.<md|txt>
                answers/A.txt, B.txt, prompt.txt   (already grouped)
                ARCHIVE/...                         (already grouped)
            structure/structure.txt
            models/
                A/A.txt, B/B.txt, prompt/prompt.txt
                ARCHIVE/...                         (already grouped)

    This function wraps any *flat* version of those files into the new
    folder layout. It is idempotent: re-running on an already-migrated
    tree is a no-op.

    Args:
        output_dir: Resolved output directory (e.g. ``context_output/``).

    Returns:
        List of new file paths that were created by the migration.
    """
    moved: list[Path] = []

    if not output_dir.is_dir():
        return moved

    arenas_dir = output_dir / "arenas"
    if arenas_dir.is_dir():
        for arena_dir in arenas_dir.iterdir():
            if not arena_dir.is_dir():
                continue
            for flat_name, sub in _PER_FILE_TARGETS:
                if sub in ("arena", "compare"):
                    src = arena_dir / flat_name
                    target = arena_dir / sub
                    if src.is_file() and src.parent.name != sub:
                        target.mkdir(parents=True, exist_ok=True)
                        dst = _per_file_safe_dest(target, src.name)
                        if dst.exists() and dst.read_bytes() == src.read_bytes():
                            continue
                        _ = shutil.move(str(src), str(dst))
                        moved.append(dst)

    # structure.txt at output_dir root
    structure_src = output_dir / "structure.txt"
    if structure_src.is_file():
        struct_dir = output_dir / "structure"
        struct_dir.mkdir(parents=True, exist_ok=True)
        dst = _per_file_safe_dest(struct_dir, "structure.txt")
        if not (dst.exists() and dst.read_bytes() == structure_src.read_bytes()):
            _ = shutil.move(str(structure_src), str(dst))
            moved.append(dst)

    # models/A.txt, B.txt, prompt.txt (active responses, not ARCHIVE/)
    models_dir = output_dir / "models"
    if models_dir.is_dir():
        for entry in list(models_dir.iterdir()):
            if not entry.is_file():
                continue
            name = entry.name
            if name == "ARCHIVE" or name.startswith("ARCHIVE"):
                continue
            if not (name.endswith(".txt") or name.endswith(".md")):
                continue
            stem = entry.stem
            target = models_dir / stem
            if target.is_dir() and (target / name).exists():
                continue
            target.mkdir(parents=True, exist_ok=True)
            dst = _per_file_safe_dest(target, name)
            if dst.exists() and dst.read_bytes() == entry.read_bytes():
                continue
            _ = shutil.move(str(entry), str(dst))
            moved.append(dst)

    if moved:
        rels = ", ".join(str(p.relative_to(output_dir)) for p in moved)
        print(f"Reorganized to per-file folders: {rels}")
    return moved


# ---------------------------------------------------------------------------
# Flat-layout migration (v3: arena.txt, compare.md, A.txt, ... directly in arena dir)
# ---------------------------------------------------------------------------

# v2 per-file-folder subfolders that need to be flattened.
# Each entry: (subfolder_name, child_filename_in_subfolder)
# If a file exists in arena_dir/<subfolder>/, move it up to arena_dir/.
_FLAT_LAYOUT_SOURCES: tuple[tuple[str, str], ...] = (
    ("arena", "arena.txt"),
    ("compare", "compare.md"),
    ("compare", "compare.txt"),
    ("answers", "prompt.txt"),
)

# Model-response files that lived in <arena>/answers/ in the v2 layout and
# need to move up to <arena>/<LETTER>.txt in the v3 layout.
_ANSWERS_MODEL_LETTERS = ("A", "B", "C", "D", "E", "F")


def _move_up_flat(arena_dir: Path, sub: str, fname: str, moved: list[Path]) -> None:
    """Move ``<arena_dir>/<sub>/<fname>`` up to ``<arena_dir>/<fname>`` if needed.

    Skips when the source doesn't exist, when the destination already exists
    with the same content, or when the subfolder itself is gone.
    """
    src = arena_dir / sub / fname
    if not src.is_file():
        return
    dst = arena_dir / fname
    if dst.exists():
        try:
            if dst.read_bytes() == src.read_bytes():
                return  # already migrated, identical content
        except OSError:
            pass
        # If the file already exists with different content, don't clobber.
        # Use a _v2 / _v3 suffix.
        stem = dst.stem
        suffix = dst.suffix
        i = 2
        while True:
            cand = arena_dir / f"{stem}_v{i}{suffix}"
            if not cand.exists():
                dst = cand
                break
            i += 1
    _ = shutil.move(str(src), str(dst))
    moved.append(dst)


def _rename_with_collision(
    src: Path, dst: Path, moved: list[Path]
) -> None:
    """Rename ``src`` → ``dst`` with collision detection (v3 → v3+ rename helper).

    Idempotent:
    * If ``src`` does not exist or ``src == dst``, no-op.
    * If ``dst`` exists with the same content, ``src`` is deleted (already migrated).
    * If ``dst`` exists with different content, ``dst`` gets a ``_v2`` suffix
      (we never clobber user data).
    """
    if not src.is_file() or src == dst:
        return
    if dst.exists():
        try:
            if dst.read_bytes() == src.read_bytes():
                _ = src.unlink()  # identical — drop the duplicate
                return
        except OSError:
            pass
        # Conflict — preserve the existing file, push the rename aside.
        stem, suffix = dst.stem, dst.suffix
        i = 2
        while True:
            cand = dst.parent / f"{stem}_v{i}{suffix}"
            if not cand.exists():
                dst = cand
                break
            i += 1
    try:
        _ = shutil.move(str(src), str(dst))
        moved.append(dst)
    except OSError as exc:
        print(
            f"Warning: could not rename {src} → {dst}: {exc}",
            file=sys.stderr,
        )


def _rename_v3_to_v3plus(
    arena_dir: Path,
    settings: dict[str, object],
    moved: list[Path],
) -> None:
    """Rename v3 flat filenames (``arena.txt``, ``compare.{ext}``) to v3+ names.

    v3 → v3+ mapping (defaults; the actual stems come from settings):

    ===================  ============================  ====================
    Old (v3)             New (v3+, default)            Role
    ===================  ============================  ====================
    ``arena.txt``        ``context.{ext}``              aggregate
    ``compare.md``       ``arena.md``                  compare (md format)
    ``compare.txt``      ``arena.txt``                  compare (txt format)
    ===================  ============================  ====================

    The extension on the new compare/aggregate comes from ``output_format`` via
    :func:`core.settings.aggregate_filename` and
    :func:`core.settings.compare_filename`.

    Order matters: ``arena.txt`` (old aggregate) is renamed FIRST so it frees
    the ``arena.txt`` slot for ``compare.txt`` (old compare) when
    ``output_format="txt"`` (where the new compare happens to be named
    ``arena.txt`` too).

    Stale ``compare.<other_ext>`` files (e.g. ``compare.md`` left over from a
    previous md-format run after switching to txt) are intentionally left
    alone — they belong to an older format and would otherwise overwrite the
    freshly-migrated ``arena.<ext>``. Users can clean them up manually.
    """
    from core.settings import aggregate_filename, compare_filename

    new_aggregate_name = aggregate_filename(settings)  # e.g. context.md
    new_compare_name = compare_filename(settings)      # e.g. arena.md
    new_ext = new_compare_name.rsplit(".", 1)[-1].lower()  # "md" or "txt"

    # 1. Old aggregate (always ``arena.txt`` in v3) → new aggregate
    old_aggregate = arena_dir / "arena.txt"
    new_aggregate_path = arena_dir / new_aggregate_name
    if old_aggregate.is_file():
        _rename_with_collision(old_aggregate, new_aggregate_path, moved)

    # 2. Old compare (``compare.md`` / ``compare.txt``) → new compare
    # Only rename the extension that matches the current ``output_format`` —
    # the other one is a stale orphan from a previous format.
    for old_ext in ("md", "txt"):
        if old_ext != new_ext:
            continue
        old_compare = arena_dir / f"compare.{old_ext}"
        if not old_compare.is_file():
            continue
        new_compare_path = arena_dir / new_compare_name
        _rename_with_collision(old_compare, new_compare_path, moved)


def _flatten_answers(arena_dir: Path, moved: list[Path]) -> None:
    """Move ``<arena_dir>/answers/A.txt`` (etc.) up to ``<arena_dir>/A.txt``.

    Also moves any ``<letter>_NOTES.md``/``<letter>_NOTES.txt`` files.
    """
    answers_dir = arena_dir / "answers"
    if not answers_dir.is_dir():
        return
    for letter in _ANSWERS_MODEL_LETTERS:
        _move_up_flat(arena_dir, "answers", f"{letter}.txt", moved)
    # NOTES files: <letter>_NOTES.<ext>
    for f in list(answers_dir.iterdir()):
        if f.is_file() and re.match(r"^[A-Z]_NOTES\.(md|txt)$", f.name):
            target = arena_dir / f.name
            if target.exists():
                # If notes already at root, skip (likely already migrated).
                continue
            _ = shutil.move(str(f), str(target))
            moved.append(target)


def _cleanup_unprefixed_legacy_files(
    arena_dir: Path,
    settings: dict[str, object],
    removed: list[Path],
) -> None:
    """Reconcile unprefixed v3 leftovers against the canonical v3+ prefixed names.

    After the v2→v3→v3+ migration, an arena directory may be in one of two
    intermediate states:

    1. **Both versions present** — newer runs created ``<prefix>-arena.md``
       next to the legacy ``arena.md``, etc. The prefixed copy is the
       canonical v3+ file; the unprefixed copy is dead weight. When the
       two copies have byte-identical content the unprefixed file is
       deleted. When they differ, both are kept and a warning is printed
       (the user must resolve manually — divergent content is real data).

    2. **Only the unprefixed version present** — older arenas that were
       created with the v3 (unprefixed) layout and never re-aggregated.
       The unprefixed file is renamed in place to its prefixed v3+ name.
       This is a one-time conversion, idempotent on a re-run because the
       rename target already exists.

    Safety rules:

    * Prefixed files are NEVER deleted — they are the canonical v3+ files.
    * Unprefixed files are NEVER deleted when their prefixed counterpart
      is missing — instead they get renamed.
    * Unprefixed files are NEVER deleted when content differs — only
      removed when content is byte-identical.
    * Empty directories left behind after renames are NOT pruned here
      (none are expected — only files move).

    Args:
        arena_dir: Arena directory whose legacy files to reconcile.
        settings: Effective settings dict (used to resolve the canonical
            output extension from ``output_format``).
        removed: Mutable list that accumulates removed/renamed paths for
            the caller's reporting.
    """
    prefix, _, arena_name = arena_dir.name.partition("-")
    if not prefix.isdigit() or not arena_name:
        return  # arena dir name doesn't follow the NNN-<name> convention

    fmt = str(settings.get("output_format", "md")).lower().lstrip(".")
    ext = fmt if fmt in ("md", "txt") else "md"

    # (unprefixed_name, prefixed_name) pairs to reconcile. The unprefixed
    # name is the legacy v3 spelling; the prefixed name is the v3+
    # canonical spelling returned by :func:`core.arena.arena_filenames`
    # plus the model-response letters.
    pairs: list[tuple[str, str]] = [
        # Aggregate (context.{ext})
        (f"context.{ext}", f"{prefix}-context.{ext}"),
        # Compare (arena.{ext})
        (f"arena.{ext}", f"{prefix}-arena.{ext}"),
        # Prompt (answers/prompt.txt was moved up to arena root)
        ("prompt.txt", f"{prefix}-prompt.txt"),
        # Input legacy (ArenaName.txt → <prefix>-<ArenaName>.txt)
        (f"{arena_name}.txt", f"{prefix}-{arena_name}.txt"),
        # Compare legacy names — defensive, in case phase 2 left them
        # because the user had a stale extension.
        ("compare.md", f"{prefix}-compare.md"),
        ("compare.txt", f"{prefix}-compare.txt"),
    ]
    # Model-response files (A–F) — see ``_ANSWERS_MODEL_LETTERS``.
    for letter in _ANSWERS_MODEL_LETTERS:
        pairs.append((f"{letter}.txt", f"{prefix}-{letter}.txt"))

    for unprefixed_name, prefixed_name in pairs:
        unprefixed = arena_dir / unprefixed_name
        prefixed = arena_dir / prefixed_name
        if not unprefixed.is_file():
            continue  # nothing to reconcile for this pair

        if not prefixed.is_file():
            # State 2: only the unprefixed version exists. Rename it to the
            # v3+ prefixed name (idempotent — a re-run finds no source).
            try:
                _ = unprefixed.rename(prefixed)
                removed.append(unprefixed)
            except OSError as exc:
                print(
                    f"Warning: could not rename {unprefixed} → {prefixed}: {exc}",
                    file=sys.stderr,
                )
            continue

        # State 1: both exist. Compare content byte-for-byte.
        try:
            same = unprefixed.read_bytes() == prefixed.read_bytes()
        except OSError:
            same = False
        if same:
            try:
                _ = unprefixed.unlink()
                removed.append(unprefixed)
            except OSError as exc:
                print(
                    f"Warning: could not remove {unprefixed}: {exc}",
                    file=sys.stderr,
                )
        else:
            print(
                f"Note: kept both {unprefixed_name} and {prefixed_name} "
                f"in {arena_dir.name}/ (content differs — manual review "
                "needed).",
                file=sys.stderr,
            )


def _prune_empty_subdirs(arena_dir: Path) -> None:
    """Remove the now-empty v2 subfolders from an arena directory.

    Best-effort: silently skip subdirs that still contain files (user has
    out-of-band content there we should never touch).
    """
    for sub in ("arena", "compare", "answers", "ARCHIVE"):
        # Don't touch ARCHIVE — it is preserved as-is in v3.
        if sub == "ARCHIVE":
            continue
        d = arena_dir / sub
        if d.is_dir():
            try:
                # Only remove if empty; if non-empty, leave it (user owns it).
                d.rmdir()
            except OSError:
                pass


def migrate_to_flat_layout(
    output_dir: Path,
    dry_run: bool = False,
    settings: dict[str, object] | None = None,
) -> list[Path]:
    """Migrate from the v2 per-file-folder layout to the v3+ flat layout.

    Phase 1 — v2 → v3 flat (flatten subfolders into the arena root):

        <output>/arenas/<NNN>-<name>/
            arena/arena.txt       ─→  arena.txt
            compare/compare.md    ─→  compare.md
            compare/compare.txt   ─→  compare.txt
            answers/A.txt         ─→  A.txt
            answers/prompt.txt    ─→  prompt.txt
            answers/ARCHIVE/      (preserved as-is)

    Phase 2 — v3 → v3+ rename (semantic filename cleanup):

        arena.txt              ─→  context.{ext}     (aggregate)
        compare.{ext}          ─→  arena.{ext}       (compare)

    The extension on the new compare/aggregate comes from the user's
    ``output_format`` setting (``md`` or ``txt``), resolved via
    :func:`core.settings.aggregate_filename` and
    :func:`core.settings.compare_filename`. The phase-2 rename is idempotent:
    a re-run on a fully v3+ arena is a no-op.

    Args:
        output_dir: Resolved output directory (e.g. ``context_output/``).
        dry_run: If True, only report what *would* move; make no changes.
        settings: Effective settings dict used to resolve the new aggregate /
            compare filenames. When ``None``, defaults are used
            (``context.md`` / ``arena.md``). Pass the live settings from
            :func:`core.settings.load_settings` to honour the user's
            ``output_format`` and any custom ``aggregate_filename`` /
            ``compare_filename`` overrides.

    Returns:
        List of paths that were created by the migration (phase 1 only —
        phase 2 rename destinations are reported by :func:`_plan_flatten`
        but not appended to ``moved`` in dry-run mode for stability of the
        existing print log).
    """
    if not output_dir.is_dir():
        return []

    eff_settings: dict[str, object] = settings or {}
    moved: list[Path] = []

    arenas_dir = output_dir / "arenas"
    if arenas_dir.is_dir():
        for arena_dir in arenas_dir.iterdir():
            if not arena_dir.is_dir():
                continue
            if dry_run:
                # Compute what would move without actually moving.
                planned = _plan_flatten(arena_dir, eff_settings)
                moved.extend(planned)
            else:
                # Phase 1: v2 → v3 flat (subfolder → arena root).
                for sub, fname in _FLAT_LAYOUT_SOURCES:
                    _move_up_flat(arena_dir, sub, fname, moved)
                _flatten_answers(arena_dir, moved)
                _prune_empty_subdirs(arena_dir)
                # Phase 2: v3 → v3+ rename (arena.txt → context.{ext},
                # compare.{ext} → arena.{ext}). Done after phase 1 so the
                # just-flattened arena.txt / compare.{ext} files are renamed.
                _rename_v3_to_v3plus(arena_dir, eff_settings, moved)
                # Phase 3: drop redundant unprefixed v3 leftovers when the
                # v3+ prefixed copy is present and byte-identical. Safe and
                # idempotent — never touches the prefixed files.
                _cleanup_unprefixed_legacy_files(arena_dir, eff_settings, moved)

    if moved and not dry_run:
        rels = ", ".join(str(p.relative_to(output_dir)) for p in moved[:10])
        suffix = " ..." if len(moved) > 10 else ""
        print(f"Flattened v2→v3+ layout: {rels}{suffix}")
    return moved


def _plan_flatten(
    arena_dir: Path, settings: dict[str, object] | None = None
) -> list[Path]:
    """Compute (without applying) the list of files that ``migrate_to_flat_layout``
    *would* move out of the v2 subfolders into the arena root, plus the v3 →
    v3+ rename destinations.
    """
    eff_settings: dict[str, object] = settings or {}
    planned: list[Path] = []
    for sub, fname in _FLAT_LAYOUT_SOURCES:
        src = arena_dir / sub / fname
        if src.is_file():
            planned.append(arena_dir / fname)
    answers_dir = arena_dir / "answers"
    if answers_dir.is_dir():
        for letter in _ANSWERS_MODEL_LETTERS:
            src = answers_dir / f"{letter}.txt"
            if src.is_file():
                planned.append(arena_dir / f"{letter}.txt")
        for f in answers_dir.iterdir():
            if f.is_file() and re.match(r"^[A-Z]_NOTES\.(md|txt)$", f.name):
                planned.append(arena_dir / f.name)
    # Phase 2 rename destinations (used by dry-run for visibility).
    planned.extend(_plan_v3_to_v3plus_rename(arena_dir, eff_settings))
    return planned


def _plan_v3_to_v3plus_rename(
    arena_dir: Path, settings: dict[str, object]
) -> list[Path]:
    """Plan v3 → v3+ rename destinations without applying them.

    Mirrors :func:`_rename_v3_to_v3plus` so ``dry_run`` accurately reports
    what *would* be renamed. Stale-ext compare files are intentionally
    skipped here too (matching the apply-side filter).
    """
    from core.settings import aggregate_filename, compare_filename

    planned: list[Path] = []
    new_aggregate_name = aggregate_filename(settings)
    new_compare_name = compare_filename(settings)
    new_ext = new_compare_name.rsplit(".", 1)[-1].lower()

    old_aggregate = arena_dir / "arena.txt"
    if old_aggregate.is_file() and old_aggregate.name != new_aggregate_name:
        planned.append(arena_dir / new_aggregate_name)

    for old_ext in ("md", "txt"):
        if old_ext != new_ext:
            continue
        old_compare = arena_dir / f"compare.{old_ext}"
        if old_compare.is_file() and old_compare.name != new_compare_name:
            planned.append(arena_dir / new_compare_name)

    return planned