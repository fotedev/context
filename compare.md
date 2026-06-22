# Model Comparison (LMArena Style - 4 Models)

## The Prompt
> <role>
You are a senior Python developer improving a CLI tool called "context" (arena-context skill). The tool aggregates source files for LMArena blind pairwise comparisons. You write clean, minimal Python code following existing patterns in the codebase.
</role>

<context>
The tool has three entry points: aggregator.py (CLI), aggregator_tui.py, aggregator_gui.py. The core logic lives in core/ (parser.py, counter.py, judge.py). Currently it reads a single files.txt, generates arena.txt (aggregated code), structure.txt (project tree), and compare.md (model comparison via Gemini judge).

Project root detection: find_project_root() in parser.py searches parent directories for markers (.git, package.json, pyproject.toml, requirements.txt, src). The first file path in files.txt is used as the starting point.

Compact mode in core/judge.py does: (1) removes "### Notes" sections, (2) collapses blank lines, (3) trims trailing whitespace. It's a token saver for LMArena.
</context>

<current_code>
<!-- NOTE: The actual source code of these files will be provided/appended to the context. Use these descriptions for context. -->
<file path="aggregator.py">
Main entry point. Reads files.txt → generates arena.txt, structure.txt, compare.md. Has hardcoded input() prompts for Gemini judge and compact mode.
</file>
<file path="core/parser.py">
File parsing, path resolution, tree generation, ignore patterns. _DEFAULT_IGNORE is a hardcoded frozenset. read_file_entries() skips blank lines and # comments.
</file>
<file path="core/counter.py">
Token counting using tiktoken.
</file>
<file path="core/judge.py">
Gemini AI judge integration. build_compare_markdown() accepts compact flag. collect_model_responses() reads from models/ dir.
</file>
</current_code>

<requirements>
<requirement id="1" priority="high">
OUTPUT ORGANIZATION: Create a dedicated output folder (context_output/) instead of dumping files in the current working directory (CWD). All generated files (e.g. arena.txt, structure.txt, compare.md, and their multi-file equivalents) must be written inside this folder. The output folder path must be configurable via the --output flag.
</requirement>

<requirement id="2" priority="high">
MULTI-FILE SUPPORT: Automatically discover and process ALL files*.txt files in the CWD matching the pattern files.txt and files_*.txt (e.g. files.txt, files_1.txt, files_02.txt). Each discovered input file must produce its own set of arena/structure/compare outputs with a matching suffix inside the output folder (e.g. files_1.txt produces context_output/arena_1.txt, context_output/structure_1.txt, and context_output/compare_1.md).
</requirement>

<requirement id="3" priority="medium">
FLEXIBLE files.txt FORMAT WITH WARNINGS: Support free text and comment lines before and after file path entries.
- Ignore lines starting with '#' (comments) and blank lines (separators).
- Any line that doesn't resolve to a valid existing file path must print a warning to stderr (e.g., "Warning: Invalid path skipped: [line content]"), but the tool must proceed to process the remaining valid paths instead of failing or silently ignoring typos.
</requirement>

<requirement id="4" priority="high">
NON-INTERACTIVE BY DEFAULT & RESOLUTION RULES:
- Remove all hardcoded input() prompts. The tool runs completely silently (non-interactively) by default.
- Configuration precedence rule:
  Command Line Flags > Interactive Prompts (if --interactive) > Settings File (.context/settings.json) > Hardcoded Defaults.
- Add an --interactive CLI flag. When interactive mode is enabled, prompt the user for options in this exact order (where pressing Enter selects the default/setting value, and Space + Enter enables/overrides the option):
  a. "Run Gemini auto-comparison? [Enter=skip, Space=run]: "
  b. "Reduce tokens? Compact mode [Enter=skip, Space=enable]: "
  c. "Archive model responses? [Enter=no, Space=archive]: "
  d. "How many models? [Enter=2, Space=4]: "
  e. "Output format? [Enter=.md, Space=.txt]: "
</requirement>

<requirement id="5" priority="high">
DETAILED ARCHIVING WORKFLOW: When archiving is enabled:
  1. For each model response file (e.g., A.txt, B.txt, etc.) currently in models/, move it to the archive directory (models/ARCHIVE/ by default) renamed with a timestamp in the pattern `<model_name>_<timestamp>.<ext>` (e.g., A_20260622_143022.txt).
  2. If the destination filename already exists, handle the collision by appending `_1`, `_2`, etc. before the extension (e.g. A_20260622_143022_1.txt).
  3. Clear the models/ directory of the active model responses (do not clear other unrelated files).
  4. Prompt for the new model count (Enter=2, Space=4) and auto-create fresh empty templates (e.g. A.txt, B.txt) in models/.
</requirement>

<requirement id="6" priority="medium">
AUTO NOTES: Look for optional model notes files in models/ (e.g. A_NOTES.md or A_NOTES.txt matching the chosen output format extension). If a notes file exists for a model, insert its content under a "### Notes" section below that model's response in the compare output. If no notes file exists, do not write a "### Notes" section.
</requirement>

<requirement id="7" priority="medium">
MODEL COUNT CHOICE & TEMPLATES: Detect existing model files (A.txt, B.txt, C.txt, D.txt). When model_count is configured to 4 but only A.txt and B.txt exist, auto-create empty C.txt and D.txt files and print: "Created empty C.txt and D.txt. Please paste their responses."
</requirement>

<requirement id="8" priority="medium">
MERGED CONFIGURATION DIRECTORY:
- Store all configurations in a single `.context/` directory in the project root.
- Read ignore patterns from `.context/ignore`. If missing, auto-create it with default patterns merged with built-in default ignore patterns (e.g. .git, node_modules, pycache, etc.). Add context_output/ and .context/ to the ignore patterns. Keep backwards compatibility: if `.contextignore` exists in the project root, read and merge its patterns as well.
- Store persistent settings at `.context/settings.json`. If missing, auto-create it with defaults.
</requirement>

<requirement id="9" priority="high">
PERSISTENT SETTINGS SCHEMA: The settings file (.context/settings.json) must conform to this schema:
{
  "output_dir": "context_output",
  "output_format": "md",
  "model_count": 2,
  "gemini_judge": false,
  "compact_mode": false,
  "archive": false,
  "archive_dir": "models/ARCHIVE"
}
</requirement>

<requirement id="10" priority="high">
SETTINGS CLI flag: Add a --settings CLI flag. When passed, the script must print the path to the active `.context/settings.json`, display its current JSON content, and print instructions/template explaining how to edit/create it. Then exit cleanly.
</requirement>
</requirements>

<edge_cases>
<case id="1" input="empty files.txt" action="Create empty templates (arena.txt, structure.txt, compare.md) in the output folder. Ensure they exist but are empty." />
<case id="2" input="invalid settings.json" action="Fall back to defaults. Print warning to stderr every run. If settings.json is completely empty, print: 'Use context skill with AI model to initialize preferences.'" />
<case id="3" input="model_count=4 but only 2 files" action="Auto-create empty C.txt, D.txt. Prompt user to paste content." />
<case id="4" input="archive timestamp collision" action="Append _1, _2, etc. (e.g. A_20260622_143022_1.txt) to prevent overwriting existing archives." />
<case id="5" input="context_output/ has old files" action="If in interactive mode: prompt 'Warn: Merge? [Enter=merge, Space=skip]'. If in non-interactive mode: default silently to auto-merging/overwriting." />
<case id="6" input="GEMINI_API_KEY not set" action="Print a warning to stderr and skip the Gemini judge step. Do not throw an error or crash. Note: the .env containing GEMINI_API_KEY lives in the tool's root directory, not the project root." />
<case id="7" input="notes extension mismatch" action="Only match notes files whose extensions match the chosen output extension (e.g. if output format is 'md', match A_NOTES.md, ignore A_NOTES.txt)." />
<case id="8" input="old files in CWD" action="If in interactive mode: prompt 'Warn: Clean? [Enter=clean, Space=skip]'. If in non-interactive mode: default silently to skipping cleaning (do nothing to protect user files)." />
</edge_cases>

<constraints>
- Maintain backwards compatibility: running the tool with no arguments must still work seamlessly.
- Accept an optional --output flag to override the output folder location.
- Automatically add the output folder (e.g. context_output/) and the configuration folder (.context/) to parser ignore patterns.
- Do not break the existing core/ module APIs or external integration assumptions.
</constraints>

<examples>
<example>
<files.txt>
# Bug in navbar layout
# CSS grid breaking on mobile < 768px

C:/proj/src/components/Navbar.tsx
C:/proj/src/components/Navbar.module.css
C:/proj/src/layouts/MainLayout.tsx:45-80

# TODO: check responsive breakpoints
</files.txt>
→ Parser extracts 3 valid paths, skips comment and blank lines, and prints warnings for any lines that are invalid paths (if any).
</example>

<example>
<settings.json>
{
  "output_dir": "context_output",
  "output_format": "txt",
  "model_count": 4,
  "gemini_judge": true,
  "compact_mode": true,
  "archive": true,
  "archive_dir": "models/ARCHIVE"
}
</settings.json>
→ Run uses these settings silently. If --interactive is passed, these settings act as the default choices.
</example>

<example>
<archive>
models/ARCHIVE/A_20260622_143022.txt exists → new file becomes A_20260622_143022_1.txt
</archive>
</example>
</examples>

<deliverable>
Implement this in two phases to ensure no code is truncated or skipped:

PHASE 1 (DO THIS NOW):
Update core/parser.py and core/judge.py according to the requirements. Provide the FULL, complete code for both files without omitting anything or using placeholders.

PHASE 2 (WAIT FOR MY CUE):
After you provide Phase 1, I will reply with "Continue to Phase 2", and then you will provide the complete, fully updated aggregator.py.

Follow these quality guidelines:
1. Write clean, idiomatic Python code.
2. Maintain documentation integrity. Keep comments and docstrings.
3. Validate user preferences defensively.
4. Perform self-checks against the edge cases checklist before concluding.
</deliverable>

---
## Model A
### Response
# Phase 1: `core/parser.py` and `core/judge.py`

---

## `core/parser.py`

```python
# core/parser.py
"""File parsing, path resolution, tree generation, and ignore-pattern management.

Supports:
- Project root detection via marker files
- Cross-platform path normalization
- Line-range and important-structure snippet syntax
- Ignore patterns from .context/ignore (+ legacy .contextignore + built-ins)
- .context/ configuration directory initialization
"""

import sys
import fnmatch
import json
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
        "files_*.txt",
        "arena.txt",
        "arena_*.txt",
        "structure.txt",
        "structure_*.txt",
        "llm.txt",
        "compare.md",
        "compare_*.md",
        "compare.txt",
        "compare_*.txt",
        "models",
        ".pnpm-store",
        "desktop.ini",
        "models\\old",
        "get-shit-done",
        "gifts",
        "agents",
        ".agents",
        ".agent",
        # New: output and config directories are always ignored in trees
        "context_output",
        ".context",
    }
)

_MAX_TREE_DEPTH: int = 20

# Default settings written to .context/settings.json on first run
_DEFAULT_SETTINGS: dict = {
    "output_dir": "context_output",
    "output_format": "md",
    "model_count": 2,
    "gemini_judge": False,
    "compact_mode": False,
    "archive": False,
    "archive_dir": "models/ARCHIVE",
}

# Default ignore patterns written to .context/ignore on first run
_DEFAULT_IGNORE_FILE_CONTENT: str = """\
# Context Tool — ignore patterns
# One glob pattern per line. Lines starting with # are comments.
# These are merged with the tool's built-in defaults.

.git
node_modules
dist
build
venv
.venv
__pycache__
*.pyc
.DS_Store
.next
.vercel
.vscode
.cursor
.github
.pnpm-store
desktop.ini

# Tool output — always ignored in project trees
context_output
.context
"""


# ---------------------------------------------------------------------------
# .context/ configuration directory management
# ---------------------------------------------------------------------------


def get_context_dir(root: Optional[Path] = None) -> Path:
    """Return the path to the .context/ directory.

    Args:
        root: Project root. Falls back to CWD when ``None``.

    Returns:
        Path to the .context/ directory (not guaranteed to exist).
    """
    base = root if root is not None else Path.cwd()
    return base / ".context"


def load_settings(root: Optional[Path] = None) -> dict:
    """Load settings from .context/settings.json, falling back to defaults.

    Behaviour:
    - Missing file → auto-create with defaults, print creation notice.
    - Empty file → warn and return defaults.
    - Invalid JSON → warn and return defaults.
    - Valid JSON → merge with defaults so new keys are always present.

    Args:
        root: Project root containing the .context/ directory.

    Returns:
        Merged settings dictionary guaranteed to contain all default keys.
    """
    context_dir = get_context_dir(root)
    settings_path = context_dir / "settings.json"

    if not settings_path.exists():
        _bootstrap_context_dir(root)
        return dict(_DEFAULT_SETTINGS)

    raw = settings_path.read_text(encoding="utf-8").strip()

    if not raw:
        print(
            "Use context skill with AI model to initialize preferences.",
            file=sys.stderr,
        )
        return dict(_DEFAULT_SETTINGS)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(
            f"Warning: .context/settings.json is invalid JSON ({exc}). "
            "Using defaults.",
            file=sys.stderr,
        )
        return dict(_DEFAULT_SETTINGS)

    if not isinstance(data, dict):
        print(
            "Warning: .context/settings.json must be a JSON object. Using defaults.",
            file=sys.stderr,
        )
        return dict(_DEFAULT_SETTINGS)

    # Merge: default values fill in any keys absent from the file
    merged = dict(_DEFAULT_SETTINGS)
    merged.update(data)
    return merged


def save_settings(settings: dict, root: Optional[Path] = None) -> None:
    """Persist *settings* to .context/settings.json.

    Args:
        settings: Dictionary conforming to the settings schema.
        root: Project root containing the .context/ directory.
    """
    context_dir = get_context_dir(root)
    context_dir.mkdir(parents=True, exist_ok=True)
    settings_path = context_dir / "settings.json"
    settings_path.write_text(
        json.dumps(settings, indent=2) + "\n", encoding="utf-8"
    )


def _bootstrap_context_dir(root: Optional[Path] = None) -> None:
    """Create .context/ with settings.json and ignore on first run.

    Args:
        root: Project root. Falls back to CWD.
    """
    context_dir = get_context_dir(root)
    context_dir.mkdir(parents=True, exist_ok=True)

    settings_path = context_dir / "settings.json"
    if not settings_path.exists():
        settings_path.write_text(
            json.dumps(_DEFAULT_SETTINGS, indent=2) + "\n", encoding="utf-8"
        )
        print(
            f"Created {settings_path} — edit your preferences or delete to reset."
        )

    ignore_path = context_dir / "ignore"
    if not ignore_path.exists():
        ignore_path.write_text(_DEFAULT_IGNORE_FILE_CONTENT, encoding="utf-8")
        print(f"Created {ignore_path} with default patterns.")


# ---------------------------------------------------------------------------
# Environment initialization
# ---------------------------------------------------------------------------


def initialize_environment(root: Path, model_count: int = 2) -> None:
    """Ensure required files and directories exist.

    - Bootstraps .context/ (settings.json + ignore file).
    - Creates files.txt in CWD if missing.
    - Creates models/ under *root* if missing.
    - If models/ has no model files, creates empty templates up to *model_count*.
    - Ensures models/prompt.txt exists.

    Args:
        root: Project root directory where ``models/`` will be created.
        model_count: Number of model template files to create when models/ is empty.
    """
    # 1. Bootstrap .context/ config directory
    _bootstrap_context_dir(root)

    # 2. Ensure files.txt exists (in CWD)
    files_txt = Path("files.txt")
    if not files_txt.exists():
        files_txt.touch()
        print(f"Created {files_txt}")

    # 3. Ensure models/ directory exists
    models_dir = root / "models"
    if not models_dir.is_dir():
        models_dir.mkdir(parents=True, exist_ok=True)
        print(f"Created {models_dir}/")

    # 4. Check for existing model files (excluding prompt.txt and ARCHIVE/)
    model_files = [
        f
        for f in models_dir.iterdir()
        if f.is_file()
        and f.name != "prompt.txt"
        and not f.name.endswith("_NOTES.md")
        and not f.name.endswith("_NOTES.txt")
    ]

    if not model_files:
        _create_model_templates(models_dir, model_count)

    # 5. Ensure prompt.txt exists in models/
    prompt_file = models_dir / "prompt.txt"
    if not prompt_file.exists():
        prompt_file.touch()
        print(f"Created {prompt_file}")


def _create_model_templates(models_dir: Path, count: int) -> None:
    """Create empty model response files A.txt … up to *count*.

    Args:
        models_dir: Path to the models/ directory.
        count: Number of template files to create (max 26).
    """
    count = max(0, min(count, 26))
    created = []
    for i in range(count):
        letter = chr(ord("A") + i)
        model_file = models_dir / f"{letter}.txt"
        if not model_file.exists():
            model_file.touch()
            created.append(model_file.name)

    if created:
        names = ", ".join(created)
        print(f"Created empty {names}. Please paste their responses.")


def ensure_model_count(models_dir: Path, model_count: int) -> None:
    """Auto-create missing model files to reach *model_count*.

    If model_count=4 but only A.txt and B.txt exist, creates C.txt and D.txt.

    Args:
        models_dir: Path to the models/ directory.
        model_count: Desired number of model files.
    """
    existing = {
        chr(ord("A") + i)
        for i in range(26)
        if (models_dir / f"{chr(ord('A') + i)}.txt").exists()
    }
    needed = [chr(ord("A") + i) for i in range(model_count)]
    missing = [letter for letter in needed if letter not in existing]

    if missing:
        created = []
        for letter in missing:
            path = models_dir / f"{letter}.txt"
            path.touch()
            created.append(path.name)
        names = ", ".join(created)
        print(f"Created empty {names}. Please paste their responses.")


# ---------------------------------------------------------------------------
# Project root detection
# ---------------------------------------------------------------------------


def find_project_root(path: Path) -> Optional[Path]:
    """Search parent directories for a recognised project-root marker.

    Traversal starts at the parent of *path* and walks toward the
    filesystem root. The search stops at the first directory that
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


def load_ignore_patterns(
    root: Optional[Path],
    extra_ignores: Optional[List[str]] = None,
) -> frozenset[str]:
    """Load exclusion patterns merging all sources.

    Sources (all merged together):
    1. Built-in ``_DEFAULT_IGNORE``.
    2. ``.context/ignore`` in the project root.
    3. Legacy ``.contextignore`` in the project root (backwards compatibility).
    4. Legacy ``.index_ignore`` in the project root (backwards compatibility).
    5. Any additional patterns passed via *extra_ignores*.

    Args:
        root: Project root to search for ignore files.
              Falls back to the current working directory when ``None``.
        extra_ignores: Additional patterns to merge (e.g. from CLI flags).

    Returns:
        Immutable set of glob patterns identifying paths to exclude.
    """
    extra: set[str] = set()
    search_dir = root if root is not None else Path.cwd()

    ignore_sources = [
        search_dir / ".context" / "ignore",
        search_dir / ".contextignore",
        search_dir / ".index_ignore",
    ]

    for ignore_file in ignore_sources:
        if ignore_file.is_file():
            with ignore_file.open("r", encoding="utf-8") as fh:
                for line in fh:
                    stripped = line.strip()
                    if stripped and not stripped.startswith("#"):
                        extra.add(stripped)

    if extra_ignores:
        extra.update(extra_ignores)

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
) -> List[str]:
    """Recursively build a visual directory tree.

    Symbolic-link directories are listed but not descended into, preventing
    infinite loops on circular links. Traversal stops at ``_MAX_TREE_DEPTH``
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
# Multi-file input discovery
# ---------------------------------------------------------------------------


def discover_input_files(cwd: Optional[Path] = None) -> List[Tuple[Path, str]]:
    """Discover all files*.txt inputs in *cwd* matching the naming convention.

    Matches:
    - ``files.txt``       → suffix ``""``
    - ``files_1.txt``     → suffix ``"_1"``
    - ``files_02.txt``    → suffix ``"_02"``
    - ``files_abc.txt``   → suffix ``"_abc"``

    Returns results sorted so that ``files.txt`` comes first, followed by
    ``files_*.txt`` in ascending lexicographic order.

    Args:
        cwd: Directory to scan. Defaults to ``Path.cwd()``.

    Returns:
        List of ``(path, suffix)`` tuples.
    """
    search = cwd if cwd is not None else Path.cwd()
    results: List[Tuple[Path, str]] = []

    base = search / "files.txt"
    if base.is_file():
        results.append((base, ""))

    for candidate in sorted(search.glob("files_*.txt")):
        if candidate.is_file():
            # Extract suffix: everything between "files" and ".txt"
            suffix = candidate.stem[len("files"):]  # e.g. "_1", "_02"
            results.append((candidate, suffix))

    return results


def output_paths_for_suffix(
    output_dir: Path, suffix: str, output_format: str = "md"
) -> Tuple[Path, Path, Path]:
    """Compute the three output file paths for a given input suffix.

    Args:
        output_dir: Base output directory (e.g. ``context_output/``).
        suffix: Input file suffix (``""`` for files.txt, ``"_1"`` for files_1.txt).
        output_format: ``"md"`` or ``"txt"`` for the compare file extension.

    Returns:
        Tuple of ``(arena_path, structure_path, compare_path)``.
    """
    arena = output_dir / f"arena{suffix}.txt"
    structure = output_dir / f"structure{suffix}.txt"
    compare = output_dir / f"compare{suffix}.{output_format}"
    return arena, structure, compare


# ---------------------------------------------------------------------------
# Path parsing with line ranges
# ---------------------------------------------------------------------------


def resolve_cross_platform_path(path_str: str) -> Path:
    """Resolve a path string which might be from a different OS.

    If the path exists as-is, returns it. Otherwise normalizes Windows
    separators and attempts a suffix-overlap match with the CWD.

    Args:
        path_str: Raw path string from files.txt.

    Returns:
        Best-effort :class:`~pathlib.Path` for the given string.
    """
    stripped = path_str.strip()
    if not stripped:
        return Path(stripped)

    p = Path(stripped)
    if p.exists():
        return p

    normalized = stripped.replace("\\", "/")
    p_norm = Path(normalized)
    if p_norm.exists():
        return p_norm

    normalized_clean = normalized
    if re.match(r"^[a-zA-Z]:", normalized):
        normalized_clean = normalized[2:]
    normalized_clean = normalized_clean.lstrip("/")

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

    return Path(normalized)


def parse_file_entry(
    line: str,
) -> Tuple[Path, Optional[List[Tuple[int, int]]], bool]:
    """Parse a files.txt entry into (path, line_ranges, is_important).

    Supported formats::

        /path/to/file.py              → (Path, None, False)
        /path/to/file.py:10-20        → (Path, [(10, 20)], False)
        /path/to/file.py:5-10,25-30   → (Path, [(5, 10), (25, 30)], False)
        !/path/to/file.py:1-5         → (Path, [(1, 5)], True)

    Args:
        line: A stripped, non-empty, non-comment input line from files.txt.

    Returns:
        A tuple of ``(Path, list of (start, end) ranges or None, is_important)``.
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
            return (
                resolve_cross_platform_path(path_part.rstrip()),
                ranges,
                is_important,
            )

    return resolve_cross_platform_path(stripped), None, is_important


def read_file_entries(
    source_file: Path,
) -> List[Tuple[Path, Optional[List[Tuple[int, int]]], bool]]:
    """Read and validate file entries from a files.txt input file.

    Rules:
    - Blank lines are skipped silently.
    - Lines starting with ``#`` are treated as comments and skipped silently.
    - Any non-blank, non-comment line that does not resolve to an existing file
      emits a warning to stderr but does **not** abort processing
      (Requirement 3).

    Args:
        source_file: Path to the files.txt (or files_N.txt) listing.

    Returns:
        Ordered list of ``(Path, line_ranges, is_important)`` tuples for
        all lines that resolved to existing files.

    Raises:
        FileNotFoundError: If *source_file* does not exist or is not a file.
    """
    if not source_file.is_file():
        raise FileNotFoundError(f"Source paths file not found: {source_file}")

    entries: List[Tuple[Path, Optional[List[Tuple[int, int]]], bool]] = []

    with source_file.open("r", encoding="utf-8") as fh:
        for raw_line in fh:
            stripped = raw_line.strip()

            # Skip blank lines and comments silently
            if not stripped or stripped.startswith("#"):
                continue

            path, ranges, is_important = parse_file_entry(stripped)

            if not path.is_file():
                print(
                    f"Warning: Invalid path skipped: {stripped}",
                    file=sys.stderr,
                )
                continue

            entries.append((path, ranges, is_important))

    return entries


def extract_lines(content: str, ranges: List[Tuple[int, int]]) -> str:
    """Extract specified line ranges from content.

    Args:
        content: Full file text.
        ranges: List of ``(start, end)`` tuples, 1-indexed, inclusive.

    Returns:
        The selected lines, with ``'...\\n'`` separator between non-contiguous
        ranges.
    """
    lines = content.splitlines(keepends=True)
    result = []
    last_end = 0

    for start, end in ranges:
        s = max(0, start - 1)
        e = min(len(lines), end)

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

    File content is read *before* any header is written, ensuring that a
    read failure never leaves an orphaned header in the output.

    Args:
        entries: Ordered list of ``(Path, line_ranges, is_important)`` tuples.
                 ``line_ranges`` is ``None`` for full files, or a list of
                 ``(start, end)`` pairs for snippets.
        output_file: Destination file; created or truncated on open.
        root: Project root for :func:`get_display_path`, or ``None``.
    """
    with output_file.open("w", encoding="utf-8") as out:
        for path, line_ranges, is_important in entries:
            try:
                if not path.is_file():
                    print(f"ERROR: Not a file: {path}", file=sys.stderr)
                    continue

                full_content = path.read_text(encoding="utf-8")
                display = get_display_path(path, root)

                if line_ranges is None:
                    content = full_content
                    header = f"# --- FILE: {display} ---"
                elif is_important:
                    content = extract_lines(full_content, line_ranges)
                    range_str = ",".join(f"{s}-{e}" for s, e in line_ranges)
                    header = f"# --- IMPORTANT STRUCTURE: {display} [{range_str}] ---"
                else:
                    content = extract_lines(full_content, line_ranges)
                    range_str = ",".join(f"{s}-{e}" for s, e in line_ranges)
                    header = f"# --- SNIPPET: {display} [{range_str}] ---"

                out.write(header + "\n")
                out.write(content)
                if not content.endswith("\n"):
                    out.write("\n")
                out.write("\n")

            except PermissionError as exc:
                print(
                    f"ERROR: Permission denied — {path}: {exc}", file=sys.stderr
                )
            except UnicodeDecodeError as exc:
                print(
                    f"ERROR: Encoding error — {path}: {exc}", file=sys.stderr
                )
            except OSError as exc:
                print(f"ERROR: OS error — {path}: {exc}", file=sys.stderr)
```

---

## `core/judge.py`

```python
# core/judge.py
"""Gemini AI judge integration and model-response collection.

Responsibilities:
- Load the GEMINI_API_KEY from .env / environment.
- Discover model response files from models/ (A.txt, B.txt, …).
- Optionally load per-model notes files (A_NOTES.md / A_NOTES.txt).
- Archive existing model files with timestamps to models/ARCHIVE/.
- Build the compare markdown document.
- Call the Gemini Flash API to generate an automated verdict.
"""

import os
import sys
import json
import shutil
import urllib.request
import re
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple


# ---------------------------------------------------------------------------
# .env loader
# ---------------------------------------------------------------------------


def load_dotenv(start_path: Path) -> None:
    """Simple parser to load .env file variables into os.environ.

    Walks parent directories from *start_path* upward until a .env is found
    or the filesystem root is reached.

    Args:
        start_path: Directory (or file) from which to begin the search.
    """
    current = start_path.resolve()
    # If a file was passed, start from its parent
    if current.is_file():
        current = current.parent

    while True:
        env_path = current / ".env"
        if env_path.is_file():
            try:
                with env_path.open("r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            key, val = line.split("=", 1)
                            os.environ.setdefault(
                                key.strip(),
                                val.strip().strip('"').strip("'"),
                            )
            except Exception as exc:
                print(
                    f"Warning: Failed to read .env at {env_path}: {exc}",
                    file=sys.stderr,
                )
            break
        parent = current.parent
        if parent == current:
            break
        current = parent


def get_api_key(root_dir: Optional[Path] = None) -> Optional[str]:
    """Retrieve GEMINI_API_KEY from environment or .env files.

    Search order:
    1. Already set in ``os.environ``.
    2. ``.env`` found by walking up from *root_dir*.
    3. ``.env`` found by walking up from CWD.
    4. ``.env`` found in the tool's own directory (aggregator root).

    If no key is found, a warning is printed to stderr and ``None`` is
    returned. The tool must not crash when the key is absent (Edge Case 6).

    Args:
        root_dir: Project root to search first.

    Returns:
        The API key string, or ``None`` if not found.
    """
    if root_dir:
        load_dotenv(root_dir)
    load_dotenv(Path.cwd())
    load_dotenv(Path(__file__).parent.parent)  # tool's own root

    api_key = os.environ.get("GEMINI_API_KEY")
    if api_key:
        return api_key

    print(
        "Warning: GEMINI_API_KEY not set. Skipping Gemini judge step.",
        file=sys.stderr,
    )
    return None


# ---------------------------------------------------------------------------
# Archive management
# ---------------------------------------------------------------------------


def _archive_timestamp() -> str:
    """Return current UTC timestamp formatted as ``YYYYMMDD_HHMMSS``."""
    return datetime.utcnow().strftime("%Y%m%d_%H%M%S")


def _safe_archive_path(archive_dir: Path, stem: str, ext: str) -> Path:
    """Compute a collision-free destination path inside *archive_dir*.

    If ``<stem>_<timestamp><ext>`` already exists, appends ``_1``, ``_2``,
    … until a free slot is found (Edge Case 4).

    Args:
        archive_dir: Directory where the file will be archived.
        stem: Original file stem (e.g. ``"A"``).
        ext: File extension including the dot (e.g. ``".txt"``).

    Returns:
        A :class:`~pathlib.Path` that does not yet exist.
    """
    ts = _archive_timestamp()
    base_name = f"{stem}_{ts}{ext}"
    candidate = archive_dir / base_name

    if not candidate.exists():
        return candidate

    counter = 1
    while True:
        name = f"{stem}_{ts}_{counter}{ext}"
        candidate = archive_dir / name
        if not candidate.exists():
            return candidate
        counter += 1


def archive_model_responses(
    models_dir: Path,
    archive_dir: Optional[Path] = None,
) -> List[Path]:
    """Move current model response files into *archive_dir* with timestamps.

    Only files matching the single-letter pattern (A.txt, B.txt … Z.txt) are
    archived. ``prompt.txt``, notes files, and subdirectories are left alone
    (Requirement 5).

    Args:
        models_dir: Path to the active models/ directory.
        archive_dir: Destination archive directory. Defaults to
                     ``models_dir / "ARCHIVE"``.

    Returns:
        List of destination paths where files were archived.
    """
    if archive_dir is None:
        archive_dir = models_dir / "ARCHIVE"

    archive_dir.mkdir(parents=True, exist_ok=True)

    archived: List[Path] = []
    model_pattern = re.compile(r"^[A-Z]$")  # single uppercase letter stems

    for f in sorted(models_dir.iterdir()):
        if not f.is_file():
            continue
        if not model_pattern.match(f.stem):
            continue  # skip prompt.txt, notes, etc.

        dest = _safe_archive_path(archive_dir, f.stem, f.suffix)
        shutil.move(str(f), str(dest))
        archived.append(dest)
        print(f"Archived {f.name} → {dest.relative_to(models_dir.parent)}")

    return archived


# ---------------------------------------------------------------------------
# Notes file support (Requirement 6)
# ---------------------------------------------------------------------------


def load_model_notes(
    models_dir: Path,
    model_stem: str,
    output_format: str = "md",
) -> Optional[str]:
    """Load notes for *model_stem* if a matching notes file exists.

    Only matches notes files whose extension matches *output_format*
    (Edge Case 7). E.g. if output_format is ``"md"``, looks for
    ``A_NOTES.md`` and ignores ``A_NOTES.txt``.

    Args:
        models_dir: Path to the models/ directory.
        model_stem: Stem of the model file (e.g. ``"A"``).
        output_format: ``"md"`` or ``"txt"``.

    Returns:
        Notes content as a string, or ``None`` if no notes file exists.
    """
    notes_file = models_dir / f"{model_stem}_NOTES.{output_format}"
    if notes_file.is_file():
        content = notes_file.read_text(encoding="utf-8").strip()
        return content if content else None
    return None


# ---------------------------------------------------------------------------
# Model response collection
# ---------------------------------------------------------------------------


def collect_model_responses(
    root: Optional[Path],
    output_format: str = "md",
) -> Tuple[str, List[dict]]:
    """Auto-discover model responses from models/ or fall back to llm.txt.

    Each entry in the returned list is a dict with keys:
    - ``"name"``     — display name (e.g. ``"Model A"``).
    - ``"stem"``     — raw file stem (e.g. ``"A"``), used for notes lookup.
    - ``"response"`` — response text.
    - ``"notes"``    — notes string or ``None``.

    Args:
        root: Project root. Falls back to CWD when ``None``.
        output_format: ``"md"`` or ``"txt"`` — controls notes file matching.

    Returns:
        ``(prompt_text, models_data)`` tuple.
    """
    target_root = root if root is not None else Path.cwd()
    models_dir = target_root / "models"
    llm_txt = target_root / "llm.txt"

    if models_dir.is_dir():
        prompt = ""
        prompt_file = models_dir / "prompt.txt"
        if prompt_file.is_file():
            prompt = prompt_file.read_text(encoding="utf-8").strip()

        models_data: List[dict] = []
        model_pattern = re.compile(r"^[A-Z]$")

        for f in sorted(models_dir.iterdir()):
            if not f.is_file():
                continue
            if not model_pattern.match(f.stem):
                continue  # skip prompt.txt, notes, ARCHIVE/ entries

            response = f.read_text(encoding="utf-8").strip()
            if not response:
                continue  # skip empty placeholders

            stem = f.stem
            notes = load_model_notes(models_dir, stem, output_format)

            models_data.append(
                {
                    "name": f"Model {stem}",
                    "stem": stem,
                    "response": response,
                    "notes": notes,
                }
            )

        if models_data:
            return prompt, models_data

    if llm_txt.is_file():
        return _parse_llm_file(llm_txt)

    return "", []


def _parse_llm_file(llm_file: Path) -> Tuple[str, List[dict]]:
    """Parse legacy llm.txt with ``===MARKER===`` syntax.

    Args:
        llm_file: Path to the legacy llm.txt file.

    Returns:
        ``(prompt_text, models_data)`` tuple compatible with the new schema.
    """
    content = llm_file.read_text(encoding="utf-8")
    prompt = ""
    models_data: List[dict] = []

    sections = re.split(r"^===([A-Z:]+)===\s*$", content, flags=re.MULTILINE)

    i = 1
    while i < len(sections):
        marker = sections[i].strip()
        body = sections[i + 1].strip() if i + 1 < len(sections) else ""

        if marker == "PROMPT":
            prompt = body
        elif marker.startswith("MODEL:"):
            raw_name = marker[len("MODEL:"):].strip()
            if not raw_name:
                raw_name = str(len(models_data) + 1)
            display = raw_name if raw_name.lower().startswith("model") else f"Model {raw_name}"
            models_data.append(
                {
                    "name": display,
                    "stem": raw_name,
                    "response": body,
                    "notes": None,
                }
            )

        i += 2

    return prompt, models_data


# ---------------------------------------------------------------------------
# Gemini API judge
# ---------------------------------------------------------------------------


def get_gemini_verdict(
    prompt: str, models_data: List[dict], api_key: str
) -> str:
    """Call Gemini Flash API to compare model responses.

    Args:
        prompt: The original user prompt from models/prompt.txt.
        models_data: List of model dicts (must have ``"name"`` and ``"response"``).
        api_key: Valid Gemini API key.

    Returns:
        Markdown-formatted evaluation string.

    Raises:
        RuntimeError: On any network or API error.
    """
    url = (
        "https://generativelanguage.googleapis.com/v1beta"
        f"/models/gemini-2.5-flash:generateContent?key={api_key}"
    )

    eval_prompt = (
        "You are an expert software engineer and AI model evaluator.\n"
        "Your task is to analyze the following user prompt and compare the "
        "responses from different AI models.\n"
        "Determine the winner, rank the model responses from best to worst, "
        "point out the strengths and weaknesses of each, and provide a clear, "
        "technical reason for your verdict.\n\n"
        f"[User Prompt]\n{prompt}\n"
    )

    for model in models_data:
        bar = "=" * 20
        name = model["name"].upper()
        eval_prompt += (
            f"\n\n{bar} RESPONSE FROM {name} {bar}\n"
            f"{model['response']}\n"
            f"{bar} END OF RESPONSE FROM {name} {bar}\n"
        )

    eval_prompt += """
Please output your evaluation in Markdown format. Your evaluation must include:
1. **Summary Table**: Compare models across key dimensions (correctness, completeness, formatting, explanation quality).
2. **Key Analysis**: Detailed review of differences in code, approach, or explanations.
3. **Winner & Ranking**: Clear winner (or "Tie"), ranked from best to worst with brief justifications.
4. **Optimal Merged Solution**: Blueprint combining all advantages while avoiding weaknesses.
5. **Prompt for the Coding Agent**: Copy-pasteable prompt instructing a coding agent to implement the combined optimal solution.

Output the markdown content directly. Do not wrap your response in an outer ```markdown block.
"""

    data = {
        "contents": [{"parts": [{"text": eval_prompt}]}]
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    print("Sending comparison request to Gemini Flash API...")
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            return res_data["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as exc:
        raise RuntimeError(f"Gemini API request failed: {exc}") from exc


# ---------------------------------------------------------------------------
# Compare document builder
# ---------------------------------------------------------------------------


def _apply_compact(content: str) -> str:
    """Apply compact-mode post-processing to reduce token count.

    Steps (matching the existing compact logic):
    1. Remove ``### Notes`` sections entirely.
    2. Collapse runs of blank lines to a single newline.
    3. Trim trailing whitespace from every line.

    Args:
        content: Raw markdown string.

    Returns:
        Compacted string.
    """
    # 1. Remove ### Notes sections (heading + all lines until next heading or ---)
    content = re.sub(
        r"### Notes\n(?:(?!###|---).*\n)*",
        "",
        content,
    )
    # 2. Collapse multiple blank lines
    content = re.sub(r"\n{3,}", "\n\n", content)
    # 3. Trim trailing whitespace per line
    content = re.sub(r"[ \t]+$", "", content, flags=re.MULTILINE)
    return content


def build_compare_markdown(
    prompt: str,
    models_data: List[dict],
    output_file: Path,
    verdict: Optional[str] = None,
    compact: bool = False,
    output_format: str = "md",
) -> None:
    """Build and write the compare document from parsed model data.

    Behaviour:
    - If a model has ``notes`` content **and** compact mode is off, a
      ``### Notes`` section is inserted below the response (Requirement 6).
    - If compact mode is on, notes sections are suppressed entirely.
    - The output extension is controlled by *output_file*'s suffix; callers
      are responsible for passing the correct path.

    Args:
        prompt: Original user prompt text.
        models_data: List of model dicts with keys ``name``, ``response``,
                     ``notes`` (may be ``None``).
        output_file: Destination path (created or overwritten).
        verdict: Optional Gemini verdict markdown string.
        compact: When ``True``, apply token-saving transformations.
        output_format: Informational only (``"md"`` or ``"txt"``); the actual
                       file extension is determined by *output_file*.
    """
    lines: List[str] = [
        f"# Model Comparison (LMArena Style — {len(models_data)} Models)",
        "",
        "## The Prompt",
        f"> {prompt}" if prompt else "> [No prompt provided]",
        "",
    ]

    for data in models_data:
        response = data["response"].strip()
        notes: Optional[str] = data.get("notes")

        lines.append("---")
        lines.append(f"## {data['name']}")
        lines.append("### Response")
        lines.append(response)
        lines.append("")

        # Append notes section only when notes exist and compact mode is off
        if notes and not compact:
            lines.append("### Notes")
            lines.append(notes)
            lines.append("")

    lines.append("---")
    lines.append("## Verdict")

    if verdict:
        lines.append(verdict)
    else:
        lines.append("- **Winner:** ")
        lines.append("- **Reasoning:** ")
        lines.append("  1. ")

    lines.append("")
    lines.append("---")
    lines.append("*Generated by File Aggregator Tool*")

    content = "\n".join(lines)

    if compact:
        content = _apply_compact(content)

    output_file.write_text(content, encoding="utf-8")


def generate_compare_template(output_file: Path) -> None:
    """Write a blank LMArena-style comparison template to *output_file*.

    Args:
        output_file: Destination path (extension determines format label).
    """
    template = """\
# Model Comparison (LMArena Style)

## Instructions
1. Use this document to compare outputs from different LLMs.
2. Paste the responses in the designated sections.
3. Vote for the winner based on accuracy, formatting, and instruction following.

---

## The Prompt
> [Paste your prompt here]

---

## Model A
### Response
[Paste Response from Model A]

### Notes
- 

---

## Model B
### Response
[Paste Response from Model B]

### Notes
- 

---

## Verdict
- **Winner:** [Model A / Model B / Tie]
- **Reasoning:** 
  1. 
  2. 

---
*Generated by File Aggregator Tool*
"""
    output_file.write_text(template, encoding="utf-8")
```

---

## Self-check against edge cases

| Edge Case | Handled? | Where |
|---|---|---|
| 1 — empty files.txt | ✅ | `read_file_entries` returns `[]`; caller creates empty outputs |
| 2 — invalid settings.json | ✅ | `load_settings` warns + returns defaults; empty → special message |
| 3 — model_count=4, 2 files | ✅ | `ensure_model_count` auto-creates C.txt, D.txt with message |
| 4 — archive timestamp collision | ✅ | `_safe_archive_path` appends `_1`, `_2`, … |
| 5 — old output files | ✅ | Logic delegated to aggregator.py (Phase 2); non-interactive = silent merge |
| 6 — GEMINI_API_KEY not set | ✅ | `get_api_key` prints warning, returns `None`; no crash |
| 7 — notes extension mismatch | ✅ | `load_model_notes` only opens `A_NOTES.{output_format}` |
| 8 — old CWD files | ✅ | Logic delegated to aggregator.py (Phase 2) |

---
## Model B
### Response
Here is **Phase 1** of the implementation. I have fully updated `core/parser.py` and `core/judge.py` to meet the infrastructure and underlying logic requirements (Req 3, Req 6, Req 7, Req 8, and the non-interactive requirements of Req 4 & Edge Case 6).

### Changes made in Phase 1:
1. **`core/parser.py`:**
   - Modified `_DEFAULT_IGNORE` and `load_ignore_patterns` to support `.context/ignore` and the legacy `.contextignore` while automatically ignoring `.context/` and `context_output/` directories.
   - Removed all `input()` prompts from `initialize_environment`. It now accepts `model_count` and automatically creates empty files up to the limit (e.g. `C.txt`, `D.txt`) and prints the required instructions (Req 7).
   - Updated `read_file_entries` to emit a stderr warning for invalid paths but continue processing the valid ones, while skipping `#` comments and blank lines (Req 3).

2. **`core/judge.py`:**
   - Removed all interactive `input()` prompts for the `GEMINI_API_KEY`. It now silently warns to `stderr` and skips if the key is missing (Req 4 / Edge Case 6).
   - Upgraded `collect_model_responses` to accept an `output_ext` argument. It now specifically seeks out matching `_NOTES.<ext>` files (e.g., `A_NOTES.md`) while skipping them as independent model files (Req 6 / Edge Case 7).
   - Updated `build_compare_markdown` to insert "### Notes" only when notes content exists, and explicitly drops notes entirely when `compact_mode` is enabled (Req 6 / Edge Case 7).

***

### 1. FILE: `core/parser.py`

```python
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
        ".contextignore",
        ".context",
        "context_output",
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
    }
)
_MAX_TREE_DEPTH: int = 20


# ---------------------------------------------------------------------------
# Environment initialization
# ---------------------------------------------------------------------------


def initialize_environment(root: Path, model_count: int = 2) -> None:
    """Ensure required files and directories exist, creating model files if needed.

    Creates ``files.txt`` in the current working directory and a ``models/``
    folder under *root* when they are missing. Auto-generates the requested
    number of model files (e.g. A.txt, B.txt) if they do not exist.

    Args:
        root: Project root directory where ``models/`` will be created.
        model_count: Number of models to auto-create templates for.
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

    # 3. Ensure required number of model files exist
    created_files = []
    for i in range(model_count):
        letter = chr(ord("A") + i)
        model_file = models_dir / f"{letter}.txt"
        if not model_file.exists():
            model_file.touch()
            created_files.append(model_file.name)

    if created_files:
        if len(created_files) == 1:
            names = created_files[0]
        elif len(created_files) == 2:
            names = " and ".join(created_files)
        else:
            names = ", ".join(created_files[:-1]) + f", and {created_files[-1]}"
        print(f"Created empty {names}. Please paste their responses.")

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
    """Load exclusion patterns from config directories plus built-in defaults.

    Args:
        root: Project root to search for config directories.
        Falls back to the current working directory when ``None``.

    Returns:
        Immutable set of glob patterns identifying paths to exclude.
    """
    extra: set[str] = set()
    search_dir = root if root is not None else Path.cwd()
    
    # Files to check for ignore patterns, in priority order
    ignore_files = [
        search_dir / ".context" / "ignore",
        search_dir / ".contextignore",
        search_dir / ".index_ignore"  # Legacy support
    ]

    for ignore_file in ignore_files:
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

    Blank lines, comment lines (starting with #), and unresolvable paths are skipped.
    Invalid paths generate a warning printed to stderr.

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
                path, ranges, is_important = parse_file_entry(stripped)
                if not path.exists():
                    print(f"Warning: Invalid path skipped: {stripped}", file=sys.stderr)
                    continue
                entries.append((path, ranges, is_important))

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
```

***

### 2. FILE: `core/judge.py`

```python
import os
import sys
import json
import urllib.request
import re
from pathlib import Path
from typing import List, Optional, Tuple

def load_dotenv(start_path: Path) -> None:
    """Simple parser to load .env file variables into os.environ."""
    current = start_path.resolve()
    while True:
        env_path = current / ".env"
        if env_path.is_file():
            try:
                with env_path.open("r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            key, val = line.split("=", 1)
                            os.environ[key.strip()] = val.strip().strip('"').strip("'")
            except Exception as e:
                print(f"Warning: Failed to read .env at {env_path}: {e}", file=sys.stderr)
            break
        parent = current.parent
        if parent == current:
            break
        current = parent

def get_api_key(root_dir: Optional[Path] = None) -> Optional[str]:
    """Retrieve GEMINI_API_KEY from environment or .env quietly."""
    if root_dir:
        load_dotenv(root_dir)
    load_dotenv(Path.cwd())
    load_dotenv(Path(__file__).parent.parent) # check aggregator folder
    
    api_key = os.environ.get("GEMINI_API_KEY")
    if api_key:
        return api_key

    # Warn quietly and fail gracefully (Non-interactive by default)
    print("Warning: GEMINI_API_KEY not found in environment or .env files. Skipping Gemini AI Judge.", file=sys.stderr)
    return None

def get_gemini_verdict(prompt: str, models_data: List[dict], api_key: str) -> str:
    """Call Gemini Flash API to compare the model responses and return evaluation markdown."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    
    eval_prompt = f"""You are an expert software engineer and AI model evaluator.
Your task is to analyze the following user prompt and compare the responses from different AI models.
Determine the winner, rank the model responses from best to worst, point out the strengths and weaknesses of each, and provide a clear, technical reason for your verdict.

[User Prompt]
{prompt}

"""
    for model in models_data:
        eval_prompt += f"\n\n==================== RESPONSE FROM {model['name'].upper()} ====================\n"
        eval_prompt += f"{model['response']}\n"
        eval_prompt += f"==================== END OF RESPONSE FROM {model['name'].upper()} ====================\n"

    eval_prompt += """
Please output your evaluation in Markdown format. Your evaluation must be thorough and include:
1. **Summary Table**: Compare the models across key dimensions (e.g. correctness, completeness, formatting, explanation quality).
2. **Key Analysis**: A detailed review of the differences in the code, approach, or explanations.
3. **Winner & Ranking**: Define a clear winner (or "Tie"), rank all the compared models from best to worst (e.g., 1st, 2nd, 3rd, etc.) with brief justifications, and explain why technically (e.g. why one code structure is better or handles edge cases better).
4. **Optimal Merged Solution**: Synthesize a blueprint/strategy that combines all the advantages and best practices of the compared models while avoiding all their weaknesses and edge cases.
5. **Prompt for the Coding Agent**: Write a precise, copy-pasteable prompt that the user can send to their AI coding agent (like Cursor, Windsurf, or Copilot) instructing it to implement the combined optimal solution based on the strengths of the analyzed models.

Output the markdown content directly. Do not wrap your response in an outer ```markdown block.
"""

    data = {
        "contents": [
            {
                "parts": [
                    {
                        "text": eval_prompt
                    }
                ]
            }
        ]
    }
    
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    
    try:
        print("Sending comparison request to Gemini Flash API...")
        with urllib.request.urlopen(req, timeout=45) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            verdict = res_data["candidates"][0]["content"]["parts"][0]["text"]
            return verdict
    except Exception as exc:
        raise RuntimeError(f"Gemini API request failed: {exc}")

def collect_model_responses(root: Optional[Path], output_ext: str = "md") -> Tuple[str, List[dict]]:
    """Auto-discover model responses and optional NOTES files from the models/ directory."""
    target_root = root if root is not None else Path.cwd()
    models_dir = target_root / "models"
    llm_txt = target_root / "llm.txt"

    if models_dir.is_dir():
        prompt = ""
        prompt_file = models_dir / "prompt.txt"
        if prompt_file.is_file():
            prompt = prompt_file.read_text(encoding="utf-8").strip()

        models_data: List[dict] = []
        for f in sorted(models_dir.iterdir()):
            if f.name == "prompt.txt" or not f.is_file():
                continue
            
            # Skip notes files during the primary iteration; they're tied to their models directly below
            if "_NOTES." in f.name:
                continue
            
            response = f.read_text(encoding="utf-8").strip()
            if not response:
                continue

            name = f.stem
            if not name.lower().startswith("model"):
                name = f"Model {name}"
            
            # Auto-discover NOTES file matching this model and output extension format
            notes = None
            notes_file = models_dir / f"{f.stem}_NOTES.{output_ext}"
            if notes_file.is_file():
                notes = notes_file.read_text(encoding="utf-8").strip()
            
            models_data.append({"name": name, "response": response, "notes": notes})

        if models_data:
            return prompt, models_data

    if llm_txt.is_file():
        return _parse_llm_file(llm_txt)

    return "", []

def _parse_llm_file(llm_file: Path) -> Tuple[str, List[dict]]:
    """Parse legacy llm.txt with === markers into (prompt, models_data)."""
    content = llm_file.read_text(encoding="utf-8")
    prompt = ""
    models_data: List[dict] = []

    sections = re.split(r"^===([A-Z:]+)===\s*$", content, flags=re.MULTILINE)

    i = 1
    while i < len(sections):
        marker = sections[i].strip()
        body = sections[i + 1].strip() if i + 1 < len(sections) else ""

        if marker == "PROMPT":
            prompt = body
        elif marker.startswith("MODEL:"):
            name = marker[len("MODEL:"):].strip()
            if not name:
                name = str(len(models_data) + 1)
            
            if not name.lower().startswith("model"):
                name = f"Model {name}"
                
            models_data.append({"name": name, "response": body, "notes": None})

        i += 2

    return prompt, models_data

def build_compare_markdown(
    prompt: str, models_data: List[dict], output_file: Path, verdict: Optional[str] = None, compact: bool = False
) -> None:
    """Build and write the compare.md from parsed LLM data with optional auto-merged Notes."""
    md = [f"# Model Comparison (LMArena Style - {len(models_data)} Models)", ""]
    md.append("## The Prompt")
    md.append(f"> {prompt}" if prompt else "> [No prompt provided]")
    
    if not compact:
        md.append("")

    for data in models_data:
        response = data["response"].strip()
        if compact:
            response = re.sub(r'\n\s*\n+', '\n', response)

        md.append("---")
        md.append(f"## {data['name']}")
        md.append("### Response")
        md.append(response)
        
        # Merge notes section if it exists and compact mode isn't enabled
        if not compact and data.get("notes"):
            md.append("")
            md.append("### Notes")
            md.append(data["notes"])
            md.append("")

    md.append("---")
    md.append("## Verdict")
    if verdict:
        md.append(verdict)
    else:
        md.append("- **Winner:** ")
        md.append("- **Reasoning:** ")
        md.append("  1. ")
    
    if not compact:
        md.append("")
    
    md.append("---")
    md.append("*Generated by File Aggregator Tool*")

    content = "\n".join(md)
    if compact:
        content = re.sub(r'\n---\n', '\n---\n', content)
        content = re.sub(r'\n+', '\n', content)
        content = re.sub(r'(\n---)', r'\n\1', content)
        content = re.sub(r'[ \t]+$', '', content, flags=re.MULTILINE)

    output_file.write_text(content, encoding="utf-8")

def generate_compare_template(output_file: Path) -> None:
    """Generate a markdown template for model comparison (LMArena style)."""
    template = """# Model Comparison (LMArena Style)

## Instructions
1. Use this document to compare outputs from different LLMs.
2. Paste the responses in the designated sections.
3. Vote for the winner based on accuracy, formatting, and instruction following.

---

## The Prompt
> [Paste your prompt here]

---

## Model A
### Response
[Paste Response from Model A]

---

## Model B
### Response
[Paste Response from Model B]

---

## Verdict
- **Winner:** [Model A / Model B / Tie]
- **Reasoning:** 
  1. 
  2. 

---
*Generated by File Aggregator Tool*
"""
    output_file.write_text(template, encoding="utf-8")
```

---
## Model C
### Response
# Phase 1: `core/parser.py` and `core/judge.py`

---

## `core/parser.py`

```python
# core/parser.py
"""File parsing, path resolution, tree generation, and ignore-pattern management.

Responsibilities:
    - Project-root detection via filesystem marker traversal.
    - Ignore-pattern loading from .context/ignore, .contextignore, and built-ins.
    - Directory-tree generation with depth and permission guards.
    - Cross-platform path resolution for files.txt entries.
    - File-entry parsing with line-range and importance-flag support.
    - File aggregation into a single arena output file.
    - Environment initialization (.context/, models/, files.txt).
    - Settings loading/saving from .context/settings.json.
"""

import sys
import fnmatch
import json
import re
from pathlib import Path
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
        "files_*.txt",
        "arena.txt",
        "arena_*.txt",
        "structure.txt",
        "structure_*.txt",
        "llm.txt",
        "compare.md",
        "compare.txt",
        "compare_*.md",
        "compare_*.txt",
        "models",
        ".pnpm-store",
        "desktop.ini",
        "models\\old",
        "get-shit-done",
        "gifts",
        "agents",
        ".agents",
        ".agent",
        # Configuration and output folders (added by req 8)
        ".context",
        "context_output",
    }
)

_MAX_TREE_DEPTH: int = 20

# ---------------------------------------------------------------------------
# Default settings schema (req 9)
# ---------------------------------------------------------------------------

_DEFAULT_SETTINGS: dict = {
    "output_dir": "context_output",
    "output_format": "md",
    "model_count": 2,
    "gemini_judge": False,
    "compact_mode": False,
    "archive": False,
    "archive_dir": "models/ARCHIVE",
}

# ---------------------------------------------------------------------------
# Settings management (req 8, 9, 10)
# ---------------------------------------------------------------------------


def get_context_dir(root: Optional[Path]) -> Path:
    """Return the .context/ directory path relative to the given root.

    Args:
        root: Project root, or CWD if None.

    Returns:
        Path to the .context/ directory (not necessarily created yet).
    """
    base = root if root is not None else Path.cwd()
    return base / ".context"


def load_settings(root: Optional[Path]) -> dict:
    """Load settings from .context/settings.json, creating it with defaults if absent.

    Validation rules:
    - If the file is missing → auto-create with defaults, return defaults.
    - If the file is completely empty → print special message, return defaults.
    - If the file contains invalid JSON → warn to stderr, return defaults.
    - Unknown keys are silently ignored; missing keys fall back to defaults.

    Args:
        root: Project root used to locate .context/settings.json.

    Returns:
        Merged settings dict (defaults overridden by valid file values).
    """
    context_dir = get_context_dir(root)
    settings_path = context_dir / "settings.json"

    if not settings_path.exists():
        _create_default_settings(settings_path)
        return dict(_DEFAULT_SETTINGS)

    raw = settings_path.read_text(encoding="utf-8").strip()

    if not raw:
        print(
            "Use context skill with AI model to initialize preferences.",
            file=sys.stderr,
        )
        return dict(_DEFAULT_SETTINGS)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(
            f"Warning: Invalid settings.json ({exc}). Falling back to defaults.",
            file=sys.stderr,
        )
        return dict(_DEFAULT_SETTINGS)

    if not isinstance(data, dict):
        print(
            "Warning: settings.json must be a JSON object. Falling back to defaults.",
            file=sys.stderr,
        )
        return dict(_DEFAULT_SETTINGS)

    # Merge: defaults first, then overlay with valid file values
    merged = dict(_DEFAULT_SETTINGS)
    for key, default_val in _DEFAULT_SETTINGS.items():
        if key in data:
            val = data[key]
            # Type-check against default type to catch corrupted values
            if isinstance(val, type(default_val)):
                merged[key] = val
            else:
                print(
                    f"Warning: settings.json key '{key}' has unexpected type "
                    f"(expected {type(default_val).__name__}). Using default.",
                    file=sys.stderr,
                )
    return merged


def _create_default_settings(settings_path: Path) -> None:
    """Write default settings.json to disk, creating parent dirs as needed.

    Args:
        settings_path: Full path to the settings file to create.
    """
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(
        json.dumps(_DEFAULT_SETTINGS, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"Created {settings_path} — edit your preferences or delete to reset."
    )


def save_settings(root: Optional[Path], settings: dict) -> None:
    """Persist settings dict to .context/settings.json.

    Args:
        root: Project root used to locate .context/settings.json.
        settings: Settings dict to write (should conform to schema).
    """
    context_dir = get_context_dir(root)
    settings_path = context_dir / "settings.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(
        json.dumps(settings, indent=2) + "\n", encoding="utf-8"
    )


def print_settings_info(root: Optional[Path]) -> None:
    """Print settings path, current content, and edit instructions. (req 10)

    Args:
        root: Project root used to locate .context/settings.json.
    """
    context_dir = get_context_dir(root)
    settings_path = context_dir / "settings.json"

    print(f"\nSettings file: {settings_path.resolve()}\n")

    if settings_path.exists():
        raw = settings_path.read_text(encoding="utf-8").strip()
        if raw:
            print("Current settings:")
            print(raw)
        else:
            print("(Settings file exists but is empty.)")
    else:
        print("(Settings file does not exist yet — will be created on next run.)")

    print(
        "\n--- How to configure ---\n"
        "Edit the JSON file above to change persistent defaults.\n"
        "All keys are optional; missing keys fall back to built-in defaults.\n"
        "\nTemplate:\n"
        + json.dumps(_DEFAULT_SETTINGS, indent=2)
        + "\n\nKey reference:\n"
        "  output_dir    : folder for generated files  (default: 'context_output')\n"
        "  output_format : 'md' or 'txt'               (default: 'md')\n"
        "  model_count   : 2 or 4                       (default: 2)\n"
        "  gemini_judge  : true / false                  (default: false)\n"
        "  compact_mode  : true / false                  (default: false)\n"
        "  archive       : true / false                  (default: false)\n"
        "  archive_dir   : path for archived responses  (default: 'models/ARCHIVE')\n"
    )


# ---------------------------------------------------------------------------
# Ignore-pattern management (req 8)
# ---------------------------------------------------------------------------


def load_ignore_patterns(root: Optional[Path]) -> frozenset[str]:
    """Load exclusion patterns merged from multiple sources.

    Sources (all merged together):
    1. Built-in ``_DEFAULT_IGNORE`` patterns.
    2. ``.context/ignore`` file (created with defaults if absent).
    3. ``.contextignore`` in the project root (legacy, backwards compat).

    The output folder and config folder are always included in the patterns
    via ``_DEFAULT_IGNORE``.

    Args:
        root: Project root to search for ignore files.
              Falls back to CWD when ``None``.

    Returns:
        Immutable set of glob patterns identifying paths to exclude.
    """
    search_dir = root if root is not None else Path.cwd()
    extra: set[str] = set()

    # Source 1: .context/ignore (req 8)
    context_ignore = search_dir / ".context" / "ignore"
    if not context_ignore.exists():
        _create_default_context_ignore(context_ignore)
    if context_ignore.is_file():
        extra.update(_read_pattern_file(context_ignore))

    # Source 2: legacy .contextignore (backwards compat, req 8)
    legacy_ignore = search_dir / ".contextignore"
    if legacy_ignore.is_file():
        extra.update(_read_pattern_file(legacy_ignore))

    # Source 3: legacy .index_ignore (original format, keep compat)
    index_ignore = search_dir / ".index_ignore"
    if index_ignore.is_file():
        extra.update(_read_pattern_file(index_ignore))

    return _DEFAULT_IGNORE | frozenset(extra)


def _read_pattern_file(path: Path) -> List[str]:
    """Read non-blank, non-comment lines from a pattern file.

    Args:
        path: Path to the ignore-pattern file.

    Returns:
        List of pattern strings.
    """
    patterns: List[str] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                patterns.append(stripped)
    return patterns


def _create_default_context_ignore(context_ignore: Path) -> None:
    """Create .context/ignore with built-in defaults and documentation header.

    Args:
        context_ignore: Path to the ignore file to create.
    """
    context_ignore.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# .context/ignore — patterns for the context tool's directory tree",
        "# One glob pattern per line. Lines starting with # are comments.",
        "# Built-in defaults are always active; add project-specific extras below.",
        "#",
        "# Examples:",
        "#   *.log",
        "#   temp/",
        "#   my_private_folder",
        "",
    ]
    context_ignore.write_text("\n".join(lines), encoding="utf-8")
    print(f"Created {context_ignore}")


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
# Environment initialization (req 7, 8, 9)
# ---------------------------------------------------------------------------


def initialize_environment(root: Path, settings: Optional[dict] = None) -> None:
    """Ensure required files and directories exist.

    Creates:
    - ``.context/`` directory with ``settings.json`` and ``ignore`` file.
    - ``files.txt`` in CWD if absent.
    - ``models/`` directory and ``prompt.txt`` under *root*.
    - Model template files (A.txt, B.txt, etc.) based on ``model_count`` setting
      when the models/ directory has no active model files.

    Args:
        root: Project root directory where ``models/`` will be created.
        settings: Pre-loaded settings dict. If None, settings are loaded here.
    """
    if settings is None:
        settings = load_settings(root)

    # 1. Ensure .context/ directory and config files exist
    context_dir = get_context_dir(root)
    context_dir.mkdir(parents=True, exist_ok=True)

    context_ignore = context_dir / "ignore"
    if not context_ignore.exists():
        _create_default_context_ignore(context_ignore)

    settings_path = context_dir / "settings.json"
    if not settings_path.exists():
        _create_default_settings(settings_path)

    # 2. Ensure files.txt exists in CWD
    files_txt = Path.cwd() / "files.txt"
    if not files_txt.exists():
        files_txt.touch()
        print(f"Created {files_txt}")

    # 3. Ensure models/ directory exists
    models_dir = root / "models"
    if not models_dir.is_dir():
        models_dir.mkdir(parents=True, exist_ok=True)
        print(f"Created {models_dir}/")

    # 4. Ensure prompt.txt exists in models/
    prompt_file = models_dir / "prompt.txt"
    if not prompt_file.exists():
        prompt_file.touch()
        print(f"Created {prompt_file}")

    # 5. Check for active model files (req 7)
    _ensure_model_files(models_dir, settings)


def _ensure_model_files(models_dir: Path, settings: dict) -> None:
    """Create or supplement model template files based on model_count setting.

    Active model files are single-uppercase-letter named files (A.txt, B.txt, etc.)
    or files with the configured output extension. ``prompt.txt`` and ``ARCHIVE/``
    are excluded from the count.

    If model_count=4 but only A.txt and B.txt exist, C.txt and D.txt are created.
    If no model files exist at all, all templates up to model_count are created.

    Args:
        models_dir: Path to the models/ directory.
        settings: Loaded settings dict containing model_count and output_format.
    """
    model_count: int = settings.get("model_count", 2)
    output_format: str = settings.get("output_format", "md")

    # Determine expected letter names
    expected_letters = [chr(ord("A") + i) for i in range(model_count)]

    # Discover existing model files (single uppercase letter stem)
    existing_stems = {
        f.stem.upper()
        for f in models_dir.iterdir()
        if f.is_file()
        and f.name != "prompt.txt"
        and not f.name.endswith("_NOTES.md")
        and not f.name.endswith("_NOTES.txt")
        and re.match(r"^[A-Z]$", f.stem.upper())
    }

    missing = [letter for letter in expected_letters if letter not in existing_stems]

    if not missing:
        return

    created = []
    for letter in missing:
        model_file = models_dir / f"{letter}.txt"
        model_file.touch()
        created.append(model_file.name)

    if created:
        names = ", ".join(created)
        print(f"Created empty {names}. Please paste their responses.")


# ---------------------------------------------------------------------------
# Multi-file discovery (req 2)
# ---------------------------------------------------------------------------


def discover_input_files(cwd: Optional[Path] = None) -> List[Tuple[Path, str]]:
    """Discover all files*.txt inputs in the given directory.

    Matches:
    - ``files.txt``          → suffix ``""``
    - ``files_1.txt``        → suffix ``"_1"``
    - ``files_02.txt``       → suffix ``"_02"``
    - ``files_foo.txt``      → suffix ``"_foo"``

    Files are sorted so that ``files.txt`` comes first, followed by
    ``files_*.txt`` in lexicographic order.

    Args:
        cwd: Directory to search. Defaults to ``Path.cwd()``.

    Returns:
        List of ``(path, suffix)`` tuples in processing order.
    """
    search_dir = cwd if cwd is not None else Path.cwd()
    results: List[Tuple[Path, str]] = []

    base = search_dir / "files.txt"
    if base.is_file():
        results.append((base, ""))

    # Glob for files_*.txt, sort for deterministic order
    for p in sorted(search_dir.glob("files_*.txt")):
        if p.is_file():
            # Extract suffix: everything between "files" and ".txt"
            suffix = p.stem[len("files"):]  # e.g. "_1", "_02"
            results.append((p, suffix))

    return results


# ---------------------------------------------------------------------------
# Project root detection
# ---------------------------------------------------------------------------


def find_project_root(path: Path) -> Optional[Path]:
    """Search parent directories for a recognised project-root marker.

    Traversal starts at the parent of *path* and walks toward the
    filesystem root. The search stops at the first directory that
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
    infinite loops on circular links. Traversal stops at ``_MAX_TREE_DEPTH``
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
    Otherwise, normalizes it and tries to find an overlapping suffix with
    the current working directory to map it to the current environment.

    Args:
        path_str: Raw path string, potentially from a foreign OS.

    Returns:
        Best-effort resolved :class:`~pathlib.Path`.
    """
    stripped = path_str.strip()
    if not stripped:
        return Path(stripped)

    p = Path(stripped)
    if p.exists():
        return p

    normalized = stripped.replace("\\", "/")
    p_norm = Path(normalized)
    if p_norm.exists():
        return p_norm

    normalized_clean = normalized
    if re.match(r"^[a-zA-Z]:", normalized):
        normalized_clean = normalized[2:]

    normalized_clean = normalized_clean.lstrip("/")
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

    return Path(normalized)


def parse_file_entry(line: str) -> Tuple[Path, Optional[List[Tuple[int, int]]], bool]:
    """Parse a files.txt entry into (path, line_ranges, is_important).

    Supported formats::

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


def read_file_entries(
    source_file: Path,
) -> List[Tuple[Path, Optional[List[Tuple[int, int]]], bool]]:
    """Read file entries (with optional line ranges) from a files*.txt input.

    Processing rules (req 3):
    - Blank lines are skipped silently.
    - Lines starting with ``#`` are treated as comments and skipped silently.
    - Any non-blank, non-comment line that does not resolve to an existing
      file path prints a warning to stderr but does NOT abort processing.

    Args:
        source_file: Path to the files*.txt listing entries.

    Returns:
        Ordered list of ``(Path, line_ranges, is_important)`` tuples for
        valid paths only.

    Raises:
        FileNotFoundError: If *source_file* does not exist or is not a file.
    """
    if not source_file.is_file():
        raise FileNotFoundError(f"Source paths file not found: {source_file}")

    entries: List[Tuple[Path, Optional[List[Tuple[int, int]]], bool]] = []

    with source_file.open("r", encoding="utf-8") as fh:
        for raw_line in fh:
            stripped = raw_line.strip()

            # Skip blank lines and comments
            if not stripped or stripped.startswith("#"):
                continue

            path, ranges, is_important = parse_file_entry(stripped)

            # Validate that the resolved path exists (req 3)
            if not path.exists():
                print(
                    f"Warning: Invalid path skipped: {stripped}",
                    file=sys.stderr,
                )
                continue

            entries.append((path, ranges, is_important))

    return entries


def extract_lines(content: str, ranges: List[Tuple[int, int]]) -> str:
    """Extract specified line ranges from content.

    Args:
        content: Full file text.
        ranges: List of (start, end) tuples, 1-indexed, inclusive.

    Returns:
        The selected lines, with ``...\\n`` separator between non-contiguous ranges.
    """
    lines = content.splitlines(keepends=True)
    result = []
    last_end = 0

    for start, end in ranges:
        s = max(0, start - 1)
        e = min(len(lines), end)

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
                     Parent directories are created automatically.
        root: Project root for :func:`get_display_path`, or ``None``.
    """
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with output_file.open("w", encoding="utf-8") as out:
        for path, line_ranges, is_important in entries:
            try:
                if not path.is_file():
                    print(f"ERROR: Not a file: {path}", file=sys.stderr)
                    continue

                full_content = path.read_text(encoding="utf-8")
                display = get_display_path(path, root)

                if line_ranges is None:
                    content = full_content
                    header = f"# --- FILE: {display} ---"
                elif is_important:
                    content = extract_lines(full_content, line_ranges)
                    range_str = ",".join(f"{s}-{e}" for s, e in line_ranges)
                    header = f"# --- IMPORTANT STRUCTURE: {display} [{range_str}] ---"
                else:
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
```

---

## `core/judge.py`

```python
# core/judge.py
"""Gemini AI judge integration and model-response collection.

Responsibilities:
    - Loading the GEMINI_API_KEY from environment / .env files.
    - Calling the Gemini Flash API to produce a structured comparison verdict.
    - Discovering model response files from the models/ directory.
    - Parsing the legacy llm.txt format.
    - Archiving model response files with timestamp-collision handling (req 5).
    - Auto-notes insertion per model (req 6).
    - Building compare.md / compare.txt output (req 6, compact mode).
    - Generating an empty compare template when no responses are present.
"""

import os
import sys
import json
import shutil
import urllib.request
import re
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple


# ---------------------------------------------------------------------------
# .env loading
# ---------------------------------------------------------------------------


def load_dotenv(start_path: Path) -> None:
    """Simple parser to load .env file variables into os.environ.

    Walks upward from *start_path* until a ``.env`` file is found or the
    filesystem root is reached.

    Args:
        start_path: Directory (or file) to begin the upward search from.
    """
    current = start_path.resolve()
    # If given a file, start from its parent
    if current.is_file():
        current = current.parent

    while True:
        env_path = current / ".env"
        if env_path.is_file():
            try:
                with env_path.open("r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            key, val = line.split("=", 1)
                            os.environ[key.strip()] = (
                                val.strip().strip('"').strip("'")
                            )
            except Exception as e:
                print(
                    f"Warning: Failed to read .env at {env_path}: {e}",
                    file=sys.stderr,
                )
            break
        parent = current.parent
        if parent == current:
            break
        current = parent


def get_api_key(root_dir: Optional[Path] = None) -> Optional[str]:
    """Retrieve GEMINI_API_KEY from environment or .env files.

    Search order:
    1. Current ``os.environ``.
    2. ``.env`` in *root_dir* (project root).
    3. ``.env`` in CWD.
    4. ``.env`` in the tool's own directory (aggregator folder).

    In non-interactive mode this returns ``None`` (with a stderr warning)
    if the key is not found. The caller decides whether to prompt the user.

    Args:
        root_dir: Project root to search for a ``.env`` file.

    Returns:
        The API key string, or ``None`` if not found.
    """
    if root_dir:
        load_dotenv(root_dir)
    load_dotenv(Path.cwd())
    load_dotenv(Path(__file__).parent.parent)  # tool root directory (edge case 6)

    api_key = os.environ.get("GEMINI_API_KEY")
    if api_key:
        return api_key

    # Key not found — caller handles the missing-key case
    return None


def prompt_for_api_key() -> Optional[str]:
    """Interactively prompt the user to enter a GEMINI_API_KEY.

    Offers to persist the key to the tool's .env file.

    Returns:
        The entered key string, or ``None`` if the user skips.
    """
    print("\n[Gemini AI Judge] GEMINI_API_KEY not found in environment or .env files.")
    try:
        key_input = input(
            "Please enter your GEMINI_API_KEY (or press Enter to skip): "
        ).strip()
        if not key_input:
            return None

        save_input = (
            input(
                "Save this key to the tool's .env file? [y/N]: "
            )
            .strip()
            .lower()
        )
        if save_input == "y":
            script_dir = Path(__file__).resolve().parent.parent
            env_path = script_dir / ".env"
            try:
                with env_path.open("a", encoding="utf-8") as f:
                    f.write(f"\nGEMINI_API_KEY={key_input}\n")
                print(f"API key saved to {env_path}")
            except Exception as e:
                print(f"Error saving to .env: {e}", file=sys.stderr)

        os.environ["GEMINI_API_KEY"] = key_input
        return key_input

    except (KeyboardInterrupt, EOFError):
        print("\nSkipping Gemini AI Judge.")
        return None


# ---------------------------------------------------------------------------
# Gemini API call
# ---------------------------------------------------------------------------


def get_gemini_verdict(
    prompt: str, models_data: List[dict], api_key: str
) -> str:
    """Call Gemini Flash API to compare model responses and return evaluation markdown.

    Args:
        prompt: The original user prompt shared with all models.
        models_data: List of dicts with keys ``"name"`` and ``"response"``.
        api_key: Valid Gemini API key.

    Returns:
        Markdown-formatted evaluation string from Gemini.

    Raises:
        RuntimeError: If the API request fails or returns an unexpected format.
    """
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-2.5-flash:generateContent?key={api_key}"
    )

    eval_prompt = (
        "You are an expert software engineer and AI model evaluator.\n"
        "Your task is to analyze the following user prompt and compare the "
        "responses from different AI models.\n"
        "Determine the winner, rank the model responses from best to worst, "
        "point out the strengths and weaknesses of each, and provide a clear, "
        "technical reason for your verdict.\n\n"
        f"[User Prompt]\n{prompt}\n"
    )

    for model in models_data:
        sep = "=" * 20
        eval_prompt += (
            f"\n\n{sep} RESPONSE FROM {model['name'].upper()} {sep}\n"
            f"{model['response']}\n"
            f"{sep} END OF RESPONSE FROM {model['name'].upper()} {sep}\n"
        )

    eval_prompt += (
        "\nPlease output your evaluation in Markdown format. Your evaluation "
        "must be thorough and include:\n"
        "1. **Summary Table**: Compare the models across key dimensions "
        "(e.g. correctness, completeness, formatting, explanation quality).\n"
        "2. **Key Analysis**: A detailed review of the differences in the code, "
        "approach, or explanations.\n"
        "3. **Winner & Ranking**: Define a clear winner (or \"Tie\"), rank all "
        "compared models from best to worst with brief justifications, and explain "
        "why technically.\n"
        "4. **Optimal Merged Solution**: Synthesize a blueprint/strategy that "
        "combines all the advantages and best practices of the compared models "
        "while avoiding their weaknesses.\n"
        "5. **Prompt for the Coding Agent**: Write a precise, copy-pasteable "
        "prompt the user can send to their AI coding agent (Cursor, Windsurf, "
        "Copilot) to implement the combined optimal solution.\n\n"
        "Output the markdown content directly. Do not wrap your response in an "
        "outer ```markdown block.\n"
    )

    data = {
        "contents": [{"parts": [{"text": eval_prompt}]}]
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        print("Sending comparison request to Gemini Flash API...")
        with urllib.request.urlopen(req, timeout=45) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            verdict = res_data["candidates"][0]["content"]["parts"][0]["text"]
            return verdict
    except Exception as exc:
        raise RuntimeError(f"Gemini API request failed: {exc}") from exc


# ---------------------------------------------------------------------------
# Model-response collection (req 6, 7)
# ---------------------------------------------------------------------------


def collect_model_responses(
    root: Optional[Path],
    output_format: str = "md",
) -> Tuple[str, List[dict]]:
    """Auto-discover model responses from the models/ directory.

    Reads ``prompt.txt`` as the shared prompt, then collects all single-
    uppercase-letter response files (A.txt, B.txt, …). Empty files are
    skipped. Notes files (A_NOTES.md / A_NOTES.txt) matching the chosen
    *output_format* are attached inline (req 6).

    Falls back to parsing ``llm.txt`` if no models/ directory exists.

    Args:
        root: Project root containing the ``models/`` directory.
        output_format: ``"md"`` or ``"txt"`` — controls which notes extension
                       is matched (req 6, edge case 7).

    Returns:
        ``(prompt_str, models_data)`` where each element of models_data is a
        dict with keys ``"name"``, ``"response"``, and optionally ``"notes"``.
    """
    target_root = root if root is not None else Path.cwd()
    models_dir = target_root / "models"
    llm_txt = target_root / "llm.txt"

    if models_dir.is_dir():
        prompt = ""
        prompt_file = models_dir / "prompt.txt"
        if prompt_file.is_file():
            prompt = prompt_file.read_text(encoding="utf-8").strip()

        models_data: List[dict] = []

        # Only pick single uppercase-letter files (A.txt, B.txt, C.txt, D.txt)
        for f in sorted(models_dir.iterdir()):
            if not f.is_file():
                continue
            if not re.match(r"^[A-Z]\.txt$", f.name):
                continue

            response = f.read_text(encoding="utf-8").strip()
            if not response:
                continue

            stem = f.stem  # "A", "B", etc.
            name = f"Model {stem}"

            # Auto-notes: look for matching notes file (req 6, edge case 7)
            notes_file = models_dir / f"{stem}_NOTES.{output_format}"
            notes: Optional[str] = None
            if notes_file.is_file():
                notes_content = notes_file.read_text(encoding="utf-8").strip()
                if notes_content:
                    notes = notes_content

            entry: dict = {"name": name, "response": response}
            if notes is not None:
                entry["notes"] = notes

            models_data.append(entry)

        if models_data:
            return prompt, models_data

    if llm_txt.is_file():
        return _parse_llm_file(llm_txt)

    return "", []


def _parse_llm_file(llm_file: Path) -> Tuple[str, List[dict]]:
    """Parse legacy llm.txt with ``===MARKER===`` delimiters.

    Args:
        llm_file: Path to the legacy llm.txt file.

    Returns:
        ``(prompt_str, models_data)`` in the same format as
        :func:`collect_model_responses`.
    """
    content = llm_file.read_text(encoding="utf-8")
    prompt = ""
    models_data: List[dict] = []

    sections = re.split(r"^===([A-Z:]+)===\s*$", content, flags=re.MULTILINE)

    i = 1
    while i < len(sections):
        marker = sections[i].strip()
        body = sections[i + 1].strip() if i + 1 < len(sections) else ""

        if marker == "PROMPT":
            prompt = body
        elif marker.startswith("MODEL:"):
            name = marker[len("MODEL:"):].strip()
            if not name:
                name = str(len(models_data) + 1)
            if not name.lower().startswith("model"):
                name = f"Model {name}"
            models_data.append({"name": name, "response": body})

        i += 2

    return prompt, models_data


# ---------------------------------------------------------------------------
# Archiving workflow (req 5)
# ---------------------------------------------------------------------------


def archive_model_responses(
    root: Optional[Path],
    archive_dir_setting: str = "models/ARCHIVE",
) -> None:
    """Move active model response files to the archive directory with timestamps.

    Workflow (req 5):
    1. For each single-uppercase-letter file (A.txt, B.txt, …) in models/,
       rename it to ``<letter>_<timestamp>.<ext>`` and move it to the archive dir.
    2. Handle filename collisions by appending ``_1``, ``_2``, … (edge case 4).
    3. Leave all other files (prompt.txt, notes files, subdirs) untouched.

    Args:
        root: Project root containing the ``models/`` directory.
        archive_dir_setting: Relative path (from *root*) to the archive folder.
                             Defaults to ``"models/ARCHIVE"``.
    """
    target_root = root if root is not None else Path.cwd()
    models_dir = target_root / "models"

    if not models_dir.is_dir():
        print("Warning: models/ directory not found — nothing to archive.", file=sys.stderr)
        return

    archive_dir = target_root / archive_dir_setting
    archive_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archived: List[str] = []

    for f in sorted(models_dir.iterdir()):
        if not f.is_file():
            continue
        # Only archive single uppercase-letter response files
        if not re.match(r"^[A-Z]\.txt$", f.name):
            continue

        stem = f.stem       # "A", "B", …
        ext = f.suffix      # ".txt"

        dest = _collision_safe_path(archive_dir, stem, timestamp, ext)
        shutil.move(str(f), str(dest))
        archived.append(f"{f.name} → {dest.name}")

    if archived:
        for entry in archived:
            print(f"Archived: {entry}")
    else:
        print("No active model files found to archive.")


def _collision_safe_path(
    directory: Path, stem: str, timestamp: str, ext: str
) -> Path:
    """Return a collision-free destination path in *directory*.

    Primary candidate: ``<stem>_<timestamp><ext>``
    On collision:      ``<stem>_<timestamp>_1<ext>``, ``_2``, … (edge case 4)

    Args:
        directory: Target directory for the archive file.
        stem: Original filename stem (e.g. ``"A"``).
        timestamp: Formatted timestamp string (e.g. ``"20260622_143022"``).
        ext: File extension including dot (e.g. ``".txt"``).

    Returns:
        A :class:`~pathlib.Path` that does not yet exist in *directory*.
    """
    candidate = directory / f"{stem}_{timestamp}{ext}"
    if not candidate.exists():
        return candidate

    counter = 1
    while True:
        candidate = directory / f"{stem}_{timestamp}_{counter}{ext}"
        if not candidate.exists():
            return candidate
        counter += 1


# ---------------------------------------------------------------------------
# Compare markdown/txt generation (req 6, compact mode)
# ---------------------------------------------------------------------------


def build_compare_markdown(
    prompt: str,
    models_data: List[dict],
    output_file: Path,
    verdict: Optional[str] = None,
    compact: bool = False,
) -> None:
    """Build and write the compare output file from parsed LLM data.

    Notes behaviour (req 6):
    - If a model dict contains a ``"notes"`` key, its value is written under
      a ``### Notes`` section below that model's response.
    - If no ``"notes"`` key is present, the ``### Notes`` section is omitted
      entirely (not a placeholder).
    - In compact mode, ``### Notes`` sections are suppressed globally and
      blank lines are collapsed.

    Args:
        prompt: The shared user prompt string.
        models_data: List of model dicts (keys: ``name``, ``response``,
                     optionally ``notes``).
        output_file: Destination path; parent directories are created if needed.
        verdict: Optional Gemini-generated markdown verdict string.
        compact: When True, removes Notes sections, collapses blank lines,
                 and trims trailing whitespace (token-saver mode).
    """
    output_file.parent.mkdir(parents=True, exist_ok=True)

    md: List[str] = [
        f"# Model Comparison (LMArena Style - {len(models_data)} Models)",
        "",
        "## The Prompt",
        f"> {prompt}" if prompt else "> [No prompt provided]",
    ]

    if not compact:
        md.append("")

    for data in models_data:
        response = data["response"].strip()
        if compact:
            response = re.sub(r"\n\s*\n+", "\n", response)

        md.append("---")
        md.append(f"## {data['name']}")
        md.append("### Response")
        md.append(response)

        # Auto-notes: only emit section if notes content exists (req 6)
        notes = data.get("notes")
        if notes and not compact:
            md.append("")
            md.append("### Notes")
            md.append(notes)

        if not compact:
            md.append("")

    md.append("---")
    md.append("## Verdict")

    if verdict:
        md.append(verdict)
    else:
        md.append("- **Winner:** ")
        md.append("- **Reasoning:** ")
        md.append("  1. ")

    if not compact:
        md.append("")

    md.append("---")
    md.append("*Generated by File Aggregator Tool*")

    content = "\n".join(md)

    if compact:
        # Collapse multiple blank lines → single newline
        content = re.sub(r"\n{3,}", "\n\n", content)
        # Trim trailing whitespace on every line
        content = re.sub(r"[ \t]+$", "", content, flags=re.MULTILINE)

    output_file.write_text(content, encoding="utf-8")


def generate_compare_template(output_file: Path) -> None:
    """Generate a markdown template for model comparison (LMArena style).

    Written when no model responses are found so the user has a ready-made
    scaffold to fill in manually.

    Args:
        output_file: Destination path; parent directories are created if needed.
    """
    output_file.parent.mkdir(parents=True, exist_ok=True)

    template = """\
# Model Comparison (LMArena Style)

## Instructions
1. Use this document to compare outputs from different LLMs.
2. Paste the responses in the designated sections.
3. Vote for the winner based on accuracy, formatting, and instruction following.

---

## The Prompt
> [Paste your prompt here]

---

## Model A
### Response
[Paste Response from Model A]

### Notes
- 
- 

---

## Model B
### Response
[Paste Response from Model B]

### Notes
- 
- 

---

## Verdict
- **Winner:** [Model A / Model B / Tie]
- **Reasoning:** 
  1. 
  2. 

---
*Generated by File Aggregator Tool*
"""
    output_file.write_text(template, encoding="utf-8")
```

---

## Self-Check Against Edge Cases

| Edge Case | Handled |
|---|---|
| **EC1** Empty files.txt | `read_file_entries` returns `[]`; caller writes empty templates via `aggregate_files` on an empty list + `generate_compare_template`. Implemented in Phase 2 (aggregator). |
| **EC2** Invalid settings.json | `load_settings` catches `JSONDecodeError`, warns stderr, returns defaults. Empty file prints special message. ✅ |
| **EC3** model_count=4, only 2 files | `_ensure_model_files` detects missing letters, creates them, prints message. ✅ |
| **EC4** Archive timestamp collision | `_collision_safe_path` appends `_1`, `_2`, … until free. ✅ |
| **EC5** Old files in context_output/ | Non-interactive: silently merges/overwrites. Interactive prompt in Phase 2 aggregator. |
| **EC6** GEMINI_API_KEY not set | `get_api_key` returns `None`; caller (aggregator Phase 2) prints stderr warning and skips judge. ✅ |
| **EC7** Notes extension mismatch | `collect_model_responses` constructs `f"{stem}_NOTES.{output_format}"` — only that exact extension is checked. ✅ |
| **EC8** Old files in CWD | Non-interactive: skip silently. Interactive prompt in Phase 2 aggregator. |

---
## Model D
### Response
# Phase 1: Updated `core/parser.py` and `core/judge.py`

## Self-check against requirements & edge cases before writing

| Req/Case | Covered in parser.py | Covered in judge.py |
|---|---|---|
| R1 Output folder | `resolve_output_dir()`, `_DEFAULT_IGNORE` additions | — |
| R2 Multi-file | `discover_files_txt()` | — |
| R3 Flexible files.txt + warnings | `read_file_entries()` updated | — |
| R4 Non-interactive | `initialize_environment()` rewritten | `get_api_key()` rewritten |
| R5 Archiving | — | `archive_model_responses()`, `_resolve_archive_path()` |
| R6 Auto notes | — | `collect_model_responses()`, `build_compare_markdown()` updated |
| R7 Model count/templates | `_ensure_model_files()` | `ensure_model_templates()` |
| R8 Merged config dir | `ensure_context_dir()`, `load_ignore_patterns()` updated | — |
| R9 Settings schema | `DEFAULT_SETTINGS`, `load_settings()`, `save_settings()` | — |
| R10 --settings flag | `display_settings()` | — |
| EC1 Empty files.txt | `read_file_entries()` returns `[]` naturally | — |
| EC2 Invalid settings | `load_settings()` fallback + warning | — |
| EC3 model_count=4 but 2 files | — | `ensure_model_templates()` |
| EC4 Archive collision | — | `_resolve_archive_path()` |
| EC6 No API key | — | `get_api_key()` returns `None` |
| EC7 Notes ext mismatch | — | `collect_model_responses()` filters by ext |

---

## core/parser.py

```python
"""Core parser module for the File Aggregator tool.

Handles file parsing, path resolution, tree generation, ignore patterns,
settings management, output directory resolution, and multi-file discovery.
"""

import sys
import fnmatch
import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

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
        "models\\old",
        "get-shit-done",
        "gifts",
        "agents",
        ".agents",
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

DEFAULT_SETTINGS: Dict[str, object] = {
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
        ignore_path.write_text(_DEFAULT_IGNORE_TEMPLATE, encoding="utf-8")
        print(f"Created {ignore_path}")

    return context_dir


# ---------------------------------------------------------------------------
# Settings management (Req 9, Req 10)
# ---------------------------------------------------------------------------


def load_settings(root: Path) -> Dict[str, object]:
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
        ensure_context_dir(root)
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

        user_settings = json.loads(content)

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
    except Exception as exc:
        print(
            f"Warning: Could not read .context/settings.json ({exc}) — using defaults.",
            file=sys.stderr,
        )
        return dict(DEFAULT_SETTINGS)


def save_settings(root: Path, settings: Dict[str, object]) -> None:
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
        fh.write("\n")


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
        except Exception as exc:
            print(f"Error reading settings: {exc}", file=sys.stderr)
    else:
        print("No settings file found. It will be auto-created on next run.")

    print()
    print("To edit settings, modify the JSON file above or delete it to reset to defaults.")
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
        files_txt.touch()
        print(f"Created {files_txt}")

    # 2. Ensure models/ directory exists (under root)
    models_dir = root / "models"
    if not models_dir.is_dir():
        models_dir.mkdir(parents=True, exist_ok=True)
        print(f"Created {models_dir}/")

    # 3. Ensure prompt.txt exists in models/
    prompt_file = models_dir / "prompt.txt"
    if not prompt_file.exists():
        prompt_file.touch()
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
            model_file.touch()
            print(f"Created {model_file}")


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
        if parent == current:  # filesystem root reached
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
# Ignore-pattern management (Req 8)
# ---------------------------------------------------------------------------


def load_ignore_patterns(root: Optional[Path]) -> frozenset[str]:
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
    ensure_context_dir(search_dir)

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
) -> Tuple[Path, Optional[List[Tuple[int, int]]], bool]:
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
            return (
                resolve_cross_platform_path(path_part.rstrip()),
                ranges,
                is_important,
            )

    return resolve_cross_platform_path(stripped), None, is_important


def read_file_entries(
    source_file: Path,
) -> List[Tuple[Path, Optional[List[Tuple[int, int]]], bool]]:
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

    entries: List[Tuple[Path, Optional[List[Tuple[int, int]]], bool]] = []
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


def extract_lines(content: str, ranges: List[Tuple[int, int]]) -> str:
    """Extract specified line ranges from content.

    Args:
        content: Full file text.
        ranges: List of (start, end) tuples, 1-indexed, inclusive.

    Returns:
        The selected lines, with '...\\n' separator between non-contiguous ranges.
    """
    lines = content.splitlines(keepends=True)
    result: List[str] = []
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


# ---------------------------------------------------------------------------
# Multi-file discovery (Req 2)
# ---------------------------------------------------------------------------


def discover_files_txt(cwd: Path) -> List[Tuple[Path, str]]:
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
    results: List[Tuple[Path, str]] = []

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
    settings: Dict[str, object],
    cli_output: Optional[str] = None,
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
```

---

## core/judge.py

```python
"""Core judge module for the File Aggregator tool.

Handles Gemini AI judge integration, model response collection, notes
discovery, archiving, and comparison output generation.
"""

import os
import sys
import json
import re
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# .env loading
# ---------------------------------------------------------------------------


def load_dotenv(start_path: Path) -> None:
    """Simple parser to load .env file variables into os.environ."""
    current = start_path.resolve()
    while True:
        env_path = current / ".env"
        if env_path.is_file():
            try:
                with env_path.open("r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            key, val = line.split("=", 1)
                            os.environ[key.strip()] = (
                                val.strip().strip('"').strip("'")
                            )
            except Exception as e:
                print(
                    f"Warning: Failed to read .env at {env_path}: {e}",
                    file=sys.stderr,
                )
            break
        parent = current.parent
        if parent == current:
            break
        current = parent


# ---------------------------------------------------------------------------
# API key retrieval (Req 4 — non-interactive, Edge case 6)
# ---------------------------------------------------------------------------


def get_api_key(root_dir: Optional[Path] = None) -> Optional[str]:
    """Retrieve GEMINI_API_KEY from environment or .env files.

    Non-interactive: returns ``None`` if the key is not found.
    The caller should handle the missing-key case (e.g. print a warning
    and skip the judge step) — Edge case 6.

    The ``.env`` file is searched in three locations:
    1. The project root (*root_dir*).
    2. The current working directory.
    3. The tool's own root directory (where aggregator.py lives).

    Args:
        root_dir: Optional project root to search for a ``.env`` file.

    Returns:
        The API key string, or ``None`` if not found.
    """
    if root_dir:
        load_dotenv(root_dir)
    load_dotenv(Path.cwd())
    load_dotenv(Path(__file__).parent.parent)  # tool root directory

    return os.environ.get("GEMINI_API_KEY")


# ---------------------------------------------------------------------------
# Gemini AI Judge
# ---------------------------------------------------------------------------


def get_gemini_verdict(
    prompt: str, models_data: List[dict], api_key: str
) -> str:
    """Call Gemini Flash API to compare the model responses.

    Returns evaluation markdown with summary table, key analysis,
    winner & ranking, optimal merged solution, and a prompt for the
    coding agent.

    Args:
        prompt: The user prompt that was sent to all models.
        models_data: List of dicts with ``name`` and ``response`` keys.
        api_key: Gemini API key.

    Returns:
        Markdown evaluation text from Gemini.

    Raises:
        RuntimeError: If the API request fails.
    """
    url = (
        "https://generativelanguage.googleapis.com/v1beta/"
        f"models/gemini-2.5-flash:generateContent?key={api_key}"
    )

    eval_prompt = (
        "You are an expert software engineer and AI model evaluator.\n"
        "Your task is to analyze the following user prompt and compare "
        "the responses from different AI models.\n"
        "Determine the winner, rank the model responses from best to worst, "
        "point out the strengths and weaknesses of each, and provide a clear, "
        "technical reason for your verdict.\n\n"
        f"[User Prompt]\n{prompt}\n\n"
    )

    for model in models_data:
        eval_prompt += (
            f"\n\n==================== RESPONSE FROM "
            f"{model['name'].upper()} ====================\n"
        )
        eval_prompt += f"{model['response']}\n"
        eval_prompt += (
            f"==================== END OF RESPONSE FROM "
            f"{model['name'].upper()} ====================\n"
        )

    eval_prompt += """
Please output your evaluation in Markdown format. Your evaluation must be thorough and include:
1. **Summary Table**: Compare the models across key dimensions (e.g. correctness, completeness, formatting, explanation quality).
2. **Key Analysis**: A detailed review of the differences in the code, approach, or explanations.
3. **Winner & Ranking**: Define a clear winner (or "Tie"), rank all the compared models from best to worst (e.g., 1st, 2nd, 3rd, etc.) with brief justifications, and explain why technically (e.g. why one code structure is better or handles edge cases better).
4. **Optimal Merged Solution**: Synthesize a blueprint/strategy that combines all the advantages and best practices of the compared models while avoiding all their weaknesses and edge cases.
5. **Prompt for the Coding Agent**: Write a precise, copy-pasteable prompt that the user can send to their AI coding agent (like Cursor, Windsurf, or Copilot) instructing it to implement the combined optimal solution based on the strengths of the analyzed models.

Output the markdown content directly. Do not wrap your response in an outer ```markdown block.
"""

    data = {
        "contents": [
            {"parts": [{"text": eval_prompt}]}
        ]
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        print("Sending comparison request to Gemini Flash API...")
        with urllib.request.urlopen(req, timeout=45) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            verdict = res_data["candidates"][0]["content"]["parts"][0]["text"]
            return verdict
    except Exception as exc:
        raise RuntimeError(f"Gemini API request failed: {exc}") from exc


# ---------------------------------------------------------------------------
# Model response collection (with notes support — Req 6, Edge case 7)
# ---------------------------------------------------------------------------


def collect_model_responses(
    root: Optional[Path],
    output_format: str = "md",
) -> Tuple[str, List[dict]]:
    """Auto-discover model responses and notes from the ``models/`` directory.

    For each model file found (e.g. ``A.txt``), also checks for a
    corresponding notes file whose extension matches *output_format*
    (e.g. ``A_NOTES.md`` when *output_format* is ``"md"``, ``A_NOTES.txt``
    when ``"txt"``).  Notes content is stored in the ``"notes"`` key of
    each model dict — Edge case 7.

    Falls back to parsing ``llm.txt`` if ``models/`` contains no
    non-empty responses.

    Args:
        root: Project root directory (or ``None`` for CWD).
        output_format: Extension for notes matching (``"md"`` or ``"txt"``).

    Returns:
        Tuple of ``(prompt_text, models_data)`` where each entry in
        *models_data* has keys ``name``, ``response``, and ``notes``.
    """
    target_root = root if root is not None else Path.cwd()
    models_dir = target_root / "models"
    llm_txt = target_root / "llm.txt"

    if models_dir.is_dir():
        prompt = ""
        prompt_file = models_dir / "prompt.txt"
        if prompt_file.is_file():
            prompt = prompt_file.read_text(encoding="utf-8").strip()

        models_data: List[dict] = []
        notes_ext = f".{output_format}"

        for f in sorted(models_dir.iterdir()):
            # Skip non-files and special files
            if f.name == "prompt.txt" or not f.is_file():
                continue
            # Skip notes files — they are loaded per-model below
            if re.match(r"^[A-Z]_NOTES\.(md|txt)$", f.name, re.IGNORECASE):
                continue

            response = f.read_text(encoding="utf-8").strip()
            if not response:
                continue

            name = f.stem
            if not name.lower().startswith("model"):
                name = f"Model {name}"

            # Look for notes file matching the output format (Req 6, EC7)
            notes = ""
            notes_file = models_dir / f"{f.stem}_NOTES{notes_ext}"
            if notes_file.is_file():
                notes = notes_file.read_text(encoding="utf-8").strip()

            models_data.append(
                {"name": name, "response": response, "notes": notes}
            )

        if models_data:
            return prompt, models_data

    if llm_txt.is_file():
        return _parse_llm_file(llm_txt)

    return "", []


def _parse_llm_file(llm_file: Path) -> Tuple[str, List[dict]]:
    """Parse legacy llm.txt with === markers into (prompt, models_data)."""
    content = llm_file.read_text(encoding="utf-8")
    prompt = ""
    models_data: List[dict] = []

    sections = re.split(r"^===([A-Z:]+)===\s*$", content, flags=re.MULTILINE)

    i = 1
    while i < len(sections):
        marker = sections[i].strip()
        body = sections[i + 1].strip() if i + 1 < len(sections) else ""

        if marker == "PROMPT":
            prompt = body
        elif marker.startswith("MODEL:"):
            name = marker[len("MODEL:") :].strip()
            if not name:
                name = str(len(models_data) + 1)

            if not name.lower().startswith("model"):
                name = f"Model {name}"

            models_data.append(
                {"name": name, "response": body, "notes": ""}
            )

        i += 2

    return prompt, models_data


# ---------------------------------------------------------------------------
# Compare output generation (Req 6 — notes, compact mode)
# ---------------------------------------------------------------------------


def build_compare_markdown(
    prompt: str,
    models_data: List[dict],
    output_file: Path,
    verdict: Optional[str] = None,
    compact: bool = False,
) -> None:
    """Build and write the compare output from parsed LLM data.

    **Notes** (Req 6): If a model dict contains a non-empty ``notes``
    value and *compact* is ``False``, a ``### Notes`` section is
    inserted below that model's response.  If no notes exist, the
    section is omitted entirely.

    **Compact mode**: Removes Notes sections, collapses blank lines,
    and trims trailing whitespace — token saver for LMArena.

    Args:
        prompt: The user prompt text.
        models_data: List of dicts with ``name``, ``response``, ``notes``.
        output_file: Destination file path.
        verdict: Optional Gemini AI judge verdict text.
        compact: If True, removes Notes sections, collapses blank lines,
                 and trims trailing whitespace.
    """
    md: List[str] = [
        f"# Model Comparison (LMArena Style - {len(models_data)} Models)",
        "",
    ]
    md.append("## The Prompt")
    md.append(f"> {prompt}" if prompt else "> [No prompt provided]")

    if not compact:
        md.append("")

    for data in models_data:
        response = data["response"].strip()
        notes = data.get("notes", "").strip()

        if compact:
            response = re.sub(r"\n\s*\n+", "\n", response)

        md.append("---")
        md.append(f"## {data['name']}")
        md.append("### Response")
        md.append(response)

        if not compact:
            md.append("")
            # Only include Notes section when notes content exists (Req 6)
            if notes:
                md.append("### Notes")
                md.append(notes)
                md.append("")

    md.append("---")
    md.append("## Verdict")
    if verdict:
        md.append(verdict)
    else:
        md.append("- **Winner:** ")
        md.append("- **Reasoning:** ")
        md.append("  1. ")

    if not compact:
        md.append("")

    md.append("---")
    md.append("*Generated by File Aggregator Tool*")

    content = "\n".join(md)

    if compact:
        # Compact: collapse consecutive blank lines, trim trailing whitespace
        content = re.sub(r"\n{2,}", "\n", content)
        content = re.sub(r"[ \t]+$", "", content, flags=re.MULTILINE)

    # Ensure output directory exists
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(content, encoding="utf-8")


def generate_compare_template(
    output_file: Path, model_count: int = 2
) -> None:
    """Generate a template for model comparison (LMArena style).

    Args:
        output_file: Destination file path.
        model_count: Number of model sections to include in the template.
    """
    lines: List[str] = [
        "# Model Comparison (LMArena Style)",
        "",
        "## Instructions",
        "1. Use this document to compare outputs from different LLMs.",
        "2. Paste the responses in the designated sections.",
        "3. Vote for the winner based on accuracy, formatting, "
        "and instruction following.",
        "",
        "---",
        "",
        "## The Prompt",
        "> [Paste your prompt here]",
        "",
    ]

    for i in range(model_count):
        letter = chr(ord("A") + i)
        lines.extend(
            [
                "---",
                "",
                f"## Model {letter}",
                "### Response",
                f"[Paste Response from Model {letter}]",
                "",
                "### Notes",
                "- ",
                "- ",
                "",
            ]
        )

    lines.extend(
        [
            "---",
            "",
            "## Verdict",
            "- **Winner:** [Model A / Model B / Tie]",
            "- **Reasoning:** ",
            "  1. ",
            "  2. ",
            "",
            "---",
            "*Generated by File Aggregator Tool*",
        ]
    )

    # Ensure output directory exists
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# Archiving workflow (Req 5, Edge case 4)
# ---------------------------------------------------------------------------


def archive_model_responses(
    root: Path,
    archive_dir: str = "models/ARCHIVE",
) -> List[Path]:
    """Archive current model responses with timestamps.

    For each model response file (e.g. ``A.txt``, ``B.txt``) currently
    in ``models/``, move it to the archive directory renamed with a
    timestamp in the pattern ``<name>_<YYYYMMDD_HHMMSS>.<ext>``.
    Corresponding notes files (``<name>_NOTES.md`` or
    ``<name>_NOTES.txt``) are also archived.

    If the destination filename already exists, a counter is appended
    before the extension (e.g. ``A_20260622_143022_1.txt``) — Edge case 4.

    Args:
        root: Project root directory.
        archive_dir: Relative path to archive directory from root.

    Returns:
        List of paths to the archived files.
    """
    models_dir = root / "models"
    archive_path = root / archive_dir
    archive_path.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archived: List[Path] = []

    # Find model response files (single uppercase letter + .txt)
    model_files = sorted(
        f
        for f in models_dir.iterdir()
        if f.is_file() and re.match(r"^[A-Z]\.txt$", f.name)
    )

    # Collect notes files for those models
    notes_files: List[Path] = []
    for mf in model_files:
        model_name = mf.stem  # e.g. "A"
        for notes_ext in (".md", ".txt"):
            notes_file = models_dir / f"{model_name}_NOTES{notes_ext}"
            if notes_file.is_file():
                notes_files.append(notes_file)

    all_files_to_archive = model_files + notes_files

    for src_file in all_files_to_archive:
        name = src_file.stem  # e.g. "A" or "A_NOTES"
        ext = src_file.suffix  # e.g. ".txt" or ".md"

        dest = _resolve_archive_path(archive_path, name, ext, timestamp)
        src_file.rename(dest)
        archived.append(dest)
        print(f"Archived {src_file.name} → {dest.name}")

    return archived


def _resolve_archive_path(
    archive_dir: Path, name: str, ext: str, timestamp: str
) -> Path:
    """Resolve archive destination with collision handling.

    Pattern: ``<name>_<timestamp>.<ext>``
    Collision: ``<name>_<timestamp>_1.<ext>``, ``<name>_<timestamp>_2.<ext>``, etc.

    Args:
        archive_dir: Archive directory path.
        name: File stem (e.g. ``"A"`` or ``"A_NOTES"``).
        ext: File extension including dot (e.g. ``".txt"``).
        timestamp: Timestamp string in ``YYYYMMDD_HHMMSS`` format.

    Returns:
        A path that does not collide with any existing file.
    """
    dest = archive_dir / f"{name}_{timestamp}{ext}"
    if not dest.exists():
        return dest

    counter = 1
    while True:
        dest = archive_dir / f"{name}_{timestamp}_{counter}{ext}"
        if not dest.exists():
            return dest
        counter += 1


# ---------------------------------------------------------------------------
# Model template management (Req 7, Edge case 3)
# ---------------------------------------------------------------------------


def ensure_model_templates(root: Path, model_count: int = 2) -> List[str]:
    """Ensure model template files exist for the given count.

    If *model_count* is 4 but only ``A.txt`` and ``B.txt`` exist,
    creates empty ``C.txt`` and ``D.txt`` files — Edge case 3.

    Args:
        root: Project root directory.
        model_count: Number of model files to ensure exist.

    Returns:
        List of newly created model names (e.g. ``['C', 'D']``).
    """
    models_dir = root / "models"
    if not models_dir.is_dir():
        models_dir.mkdir(parents=True, exist_ok=True)

    # Detect existing model response files
    existing: set[str] = set()
    for f in models_dir.iterdir():
        if f.is_file() and re.match(r"^[A-Z]\.txt$", f.name):
            existing.add(f.stem)

    created: List[str] = []
    for i in range(model_count):
        letter = chr(ord("A") + i)
        if letter not in existing:
            model_file = models_dir / f"{letter}.txt"
            model_file.touch()
            created.append(letter)

    if created:
        names = ", ".join(f"{c}.txt" for c in created)
        print(
            f"Created empty {names}. Please paste their responses."
        )

    return created
```

---

**Self-check summary:**

| Check | Status |
|---|---|
| All original functions preserved with same signatures | ✅ |
| `read_file_entries()` warns on invalid paths (Req 3) | ✅ |
| `initialize_environment()` is non-interactive (Req 4) | ✅ |
| `get_api_key()` is non-interactive, returns `None` if missing (Req 4, EC6) | ✅ |
| `collect_model_responses()` discovers notes with extension matching (Req 6, EC7) | ✅ |
| `build_compare_markdown()` includes Notes only when content exists (Req 6) | ✅ |
| Compact mode removes Notes, collapses blanks, trims whitespace | ✅ |
| `archive_model_responses()` handles timestamp collisions (Req 5, EC4) | ✅ |
| `ensure_model_templates()` auto-creates missing files (Req 7, EC3) | ✅ |
| `load_settings()` handles missing/empty/invalid JSON (EC2) | ✅ |
| `ensure_context_dir()` auto-creates `.context/` with defaults (Req 8) | ✅ |
| `load_ignore_patterns()` reads `.context/ignore`, `.contextignore`, `.index_ignore` (Req 8) | ✅ |
| `discover_files_txt()` finds `files.txt` + `files_*.txt` (Req 2) | ✅ |
| `resolve_output_dir()` respects CLI > settings > default (Req 1) | ✅ |
| `_DEFAULT_IGNORE` includes `context_output` and `.context` (Req 1, Req 8) | ✅ |
| `display_settings()` for `--settings` flag (Req 10) | ✅ |
| `generate_compare_template()` accepts `model_count` (Req 7) | ✅ |
| All output files get `parent.mkdir(parents=True, exist_ok=True)` (Req 1) | ✅ |
| Backwards compatibility: no breaking API changes | ✅ |

Ready for your "Continue to Phase 2" cue.

---
## Verdict
- **Winner:** 
- **Reasoning:** 
  1. 

---
*Generated by File Aggregator Tool*