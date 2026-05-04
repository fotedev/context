"""File Aggregator — consolidates source files and generates project trees.

Outputs:
    arena.txt     — all file contents with relative-path headers
    structure.txt — visual directory tree of the detected project root
"""

import sys
import fnmatch
from pathlib import Path
from typing import List, Optional

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
        "__pycache__",
        ".next",
        ".index_ignore",
        "*.pyc",
        ".DS_Store",
    }
)
_MAX_TREE_DEPTH: int = 20


# ---------------------------------------------------------------------------
# Project root detection
# ---------------------------------------------------------------------------


def find_project_root(path: Path) -> Optional[Path]:
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
        if parent == current:       # filesystem root reached
            return None
        current = parent


# ---------------------------------------------------------------------------
# Display-path helpers
# ---------------------------------------------------------------------------


def get_display_path(path: Path, root: Optional[Path]) -> str:
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
# Ignore-pattern management
# ---------------------------------------------------------------------------


def load_ignore_patterns(root: Optional[Path]) -> frozenset[str]:
    """Load exclusion patterns from ``.index_ignore`` plus built-in defaults.

    Args:
        root: Project root to search for ``.index_ignore``.
              Falls back to the current working directory when ``None``.

    Returns:
        Immutable set of glob patterns identifying paths to exclude.
    """
    extra: set[str] = set()
    search_dir = root if root is not None else Path.cwd()
    ignore_file = search_dir / ".index_ignore"

    if ignore_file.is_file():
        with ignore_file.open("r", encoding="utf-8") as fh:
            for line in fh:
                stripped = line.strip()
                if stripped and not stripped.startswith("#"):
                    extra.add(stripped)

    return _DEFAULT_IGNORE | frozenset(extra)


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
        return False    # outside root — never auto-ignore

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
) -> List[str]:
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

    tree: List[str] = []
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
# File I/O
# ---------------------------------------------------------------------------


def read_file_paths(source_file: Path) -> List[Path]:
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

    paths: List[Path] = []
    with source_file.open("r", encoding="utf-8") as fh:
        for line in fh:
            stripped = line.strip()
            if stripped:
                paths.append(Path(stripped))

    return paths


def aggregate_files(
    paths: List[Path],
    output_file: Path,
    root: Optional[Path],
) -> None:
    """Write each file's contents to *output_file* under a section header.

    File content is read *before* any header is written, ensuring that a
    read failure never leaves an orphaned header in the output.

    Args:
        paths: Ordered source file paths to aggregate.
        output_file: Destination file; created or truncated on open.
        root: Project root for :func:`get_display_path`, or ``None``.
    """
    with output_file.open("w", encoding="utf-8") as out:
        for path in paths:
            try:
                if not path.is_file():
                    print(f"ERROR: Not a file: {path}", file=sys.stderr)
                    continue

                # Read content first — header is only written on success.
                content = path.read_text(encoding="utf-8")
                display = get_display_path(path, root)

                out.write(f"# --- FILE: {display} ---\n")
                out.write(content)
                if not content.endswith("\n"):
                    out.write("\n")
                out.write("\n")

            except PermissionError as exc:
                print(f"ERROR: Permission denied — {path}: {exc}", file=sys.stderr)
            except UnicodeDecodeError as exc:
                print(f"ERROR: Encoding error — {path}: {exc}", file=sys.stderr)
            except OSError as exc:
                print(f"ERROR: OS error — {path}: {exc}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def _assert_writable(path: Path) -> None:
    """Raise :exc:`OSError` if *path* cannot be opened for writing.

    Args:
        path: File path to probe.

    Raises:
        OSError: If the file cannot be opened in append mode.
    """
    try:
        path.open("a").close()
    except OSError as exc:
        raise OSError(f"Output file not writable: {path}") from exc


def main() -> None:
    """Orchestrate project-root detection, tree generation, and aggregation."""
    files_txt = Path("files.txt")
    arena_txt = Path("arena.txt")
    structure_txt = Path("structure.txt")

    try:
        paths = read_file_paths(files_txt)
        if not paths:
            print("No paths found in files.txt — nothing to do.")
            return

        # Fail fast if outputs are not writable.
        _assert_writable(arena_txt)
        _assert_writable(structure_txt)

        root = find_project_root(paths[0])
        patterns = load_ignore_patterns(root)

        # 1. Project tree
        if root:
            print(f"Project root detected: {root}")
            tree_lines = [f"Project Root: {root.name}/"] + generate_tree(
                root, root, patterns
            )
            structure_txt.write_text("\n".join(tree_lines), encoding="utf-8")
            print(f"Structure written → {structure_txt}")
        else:
            print("No project root detected — skipping structure.txt.", file=sys.stderr)

        # 2. File aggregation
        print(f"Aggregating {len(paths)} file(s) → {arena_txt} …")
        aggregate_files(paths, arena_txt, root)
        print("Aggregation complete.")

    except Exception as exc:          # noqa: BLE001 — last-resort guard in main
        print(f"CRITICAL ERROR: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
