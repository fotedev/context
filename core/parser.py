import sys
import fnmatch
from pathlib import Path
import re
from typing import List, Optional, Tuple

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
        "models",
        ".pnpm-store",
        "desktop.ini",
        "models\old",
        "get-shit-done",
        "gifts",
        "agents",
        ".agents",
        ".agent",
        "",
        "",

    }
)
_MAX_TREE_DEPTH: int = 20


# ---------------------------------------------------------------------------
# Environment initialization
# ---------------------------------------------------------------------------


def initialize_environment(root: Path) -> None:
    """Ensure required files and directories exist, prompting for model files if needed.

    Creates ``files.txt`` in the current working directory and a ``models/``
    folder under *root* when they are missing.  If the ``models/`` folder
    contains no model files (excluding ``prompt.txt``), the user is prompted
    to specify how many model files to generate (``A.txt``, ``B.txt``, …).

    Args:
        root: Project root directory where ``models/`` will be created.
    """
    # 1. Ensure files.txt exists (in CWD)
    files_txt = Path("files.txt")
    if not files_txt.exists():
        files_txt.touch()
        print(f"Created {files_txt}")

    # 2. Ensure models/ directory exists (under root)
    models_dir = root / "models"
    if not models_dir.is_dir():
        models_dir.mkdir(parents=True, exist_ok=True)
        print(f"Created {models_dir}/")

    # 3. Check if models/ has any model files (excluding prompt.txt)
    model_files = [
        f for f in models_dir.iterdir()
        if f.is_file() and f.name != "prompt.txt"
    ]
    if not model_files:
        while True:
            try:
                raw = input(
                    "How many model files to create? (e.g., 3 for A, B, C): "
                ).strip()
                if not raw:
                    count = 0
                    break
                count = int(raw)
                if count < 0:
                    print("Please enter a non-negative integer.")
                    continue
                break
            except ValueError:
                print("Invalid input. Please enter an integer.")

        for i in range(count):
            letter = chr(ord("A") + i)
            model_file = models_dir / f"{letter}.txt"
            model_file.touch()
            print(f"Created {model_file}")

    # 4. Ensure prompt.txt exists in models/
    prompt_file = models_dir / "prompt.txt"
    if not prompt_file.exists():
        prompt_file.touch()
        print(f"Created {prompt_file}")


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
# Path parsing with line ranges
# ---------------------------------------------------------------------------


def resolve_cross_platform_path(path_str: str) -> Path:
    """Resolve a path string which might be from a different OS (e.g. Windows paths on Linux/WSL).

    If the path exists as-is, returns it.
    Otherwise, normalizes it and tries to find an overlapping suffix with the current working directory
    to map it to the current environment.
    """
    stripped = path_str.strip()
    if not stripped:
        return Path(stripped)

    # If the path already exists, just return it
    p = Path(stripped)
    if p.exists():
        return p

    # Normalize Windows separators
    normalized = stripped.replace('\\', '/')

    # If the normalized path exists, return it
    p_norm = Path(normalized)
    if p_norm.exists():
        return p_norm

    # Remove drive letter if present (e.g. C:/ or c:/)
    normalized_clean = normalized
    if re.match(r'^[a-zA-Z]:', normalized):
        normalized_clean = normalized[2:]

    # Strip leading slash to make it relative-friendly for suffix overlap
    normalized_clean = normalized_clean.lstrip('/')

    # Try to match suffix overlap with CWD
    path_parts = [part for part in normalized_clean.split('/') if part]

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


def parse_file_entry(line: str) -> Tuple[Path, Optional[List[Tuple[int, int]]], bool]:
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
        ranges = []
        for segment in range_part.split(","):
            m = re.match(r"(\d+)\s*-\s*(\d+)", segment.strip())
            if m:
                ranges.append((int(m.group(1)), int(m.group(2))))
        if ranges:
            return resolve_cross_platform_path(path_part.rstrip()), ranges, is_important

    return resolve_cross_platform_path(stripped), None, is_important


def read_file_entries(source_file: Path) -> List[Tuple[Path, Optional[List[Tuple[int, int]]], bool]]:
    """Read file entries (with optional line ranges) from files.txt.

    Blank lines and comment lines (starting with #) are skipped.

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

    entries = []
    with source_file.open("r", encoding="utf-8") as fh:
        for line in fh:
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                entries.append(parse_file_entry(stripped))

    return entries


def extract_lines(content: str, ranges: List[Tuple[int, int]]) -> str:
    """Extract specified line ranges from content.

    Args:
        content: Full file text.
        ranges: List of (start, end) tuples, 1-indexed, inclusive.

    Returns:
        The selected lines, with '...\n' separator between non-contiguous ranges.
    """
    lines = content.splitlines(keepends=True)
    result = []
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
    entries: List[Tuple[Path, Optional[List[Tuple[int, int]]], bool]],
    output_file: Path,
    root: Optional[Path],
) -> None:
    """Write each file's contents (or snippets) to *output_file* with headers.

    Supports full files, line-range snippets, and "important" markers.
    File content is read *before* any header is written, ensuring that a
    read failure never leaves an orphaned header in the output.

    Args:
        entries: Ordered list of (Path, line_ranges, is_important) tuples.
                 line_ranges is None for full files, or a list of (start, end).
        output_file: Destination file; created or truncated on open.
        root: Project root for :func:`get_display_path`, or ``None``.
    """
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
                    range_str = ",".join(f"{s}-{e}" for s, e in line_ranges)
                    header = f"# --- IMPORTANT STRUCTURE: {display} [{range_str}] ---"
                else:
                    # Regular code snippet
                    content = extract_lines(full_content, line_ranges)
                    range_str = ",".join(f"{s}-{e}" for s, e in line_ranges)
                    header = f"# --- SNIPPET: {display} [{range_str}] ---"

                out.write(header + "\n")
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
