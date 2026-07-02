"""File discovery, ignore-pattern matching, and arena-state snapshotting.

This module owns:

* the built-in default ignore set,
* the user's ``.context/ignore``-driven pattern loader,
* the input-file discovery routines (``discover_files_txt``,
  ``discover_files_txt_with_directives``),
* the :func:`get_latest_state` helper that powers the ``--status`` flag.

It is the only module allowed to import across both ``core.settings`` and
``core.arena`` — those are its sole internal dependencies.
"""
from __future__ import annotations

import datetime as _dt
import fnmatch
import functools
import json
import re
import sys
from pathlib import Path
from typing import cast

from core.arena import ArenaDirective, _safe_read_directive
from core.settings import ensure_context_dir

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Ignore-pattern management (Req 8)
# ---------------------------------------------------------------------------


def load_ignore_patterns(root: Path | None) -> frozenset[str]:
    """Load exclusion patterns from the .context/ignore file.

    If ``.context/ignore`` does not exist, it is auto-created with a
    default template via :func:`ensure_context_dir`.

    Args:
        root: Project root to search for config files.
              Falls back to the current working directory when ``None``.

    Returns:
        Immutable set of glob patterns identifying paths to exclude.
    """
    patterns: set[str] = set()
    search_dir = root if root is not None else Path.cwd()

    # Ensure .context/ignore exists
    _ = ensure_context_dir(search_dir)

    # Read .context/ignore
    context_ignore = search_dir / ".context" / "ignore"
    if context_ignore.is_file():
        patterns.update(_read_pattern_file(context_ignore))

    return frozenset(patterns)


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
# Multi-file discovery (Req 2)
# ---------------------------------------------------------------------------


def discover_files_txt(
    cwd: Path, root: Path | None = None, settings: dict[str, object] | None = None
) -> list[tuple[Path, str]]:
    """Discover input files and return (file_path, arena_name) tuples.

    Primary: root/.context/inputs/*.txt
    Fallback: cwd/files.txt and cwd/files_*.txt

    The arena name is always derived from the filename (source of truth).
    The optional ``# Target Arena:`` directive is parsed lazily by callers
    via :func:`build_arena_plan` (passing a directive lookup built with
    :func:`_safe_read_directive`) so the legacy call sites keep their
    simple ``(Path, str)`` shape.
    """
    results: list[tuple[Path, str]] = []

    if root and settings:
        inputs_dir_str = cast(str, settings.get("inputs_dir", ".context/inputs"))
        inputs_dir = root / inputs_dir_str

        if inputs_dir.is_dir():
            # Use rglob to recursively scan all subdirectories for *.txt files
            for p in sorted(inputs_dir.rglob("*.txt")):
                if p.is_file():
                    try:
                        rel_path = p.relative_to(inputs_dir)
                        # Build a flat arena name: e.g. UI/AdminPage.txt -> UI-AdminPage
                        parts = list(rel_path.parent.parts) + [rel_path.stem]
                        # Filter out empty or '.' parts to handle files at the root of inputs_dir
                        parts = [part for part in parts if part and part != '.']
                        arena_name = "-".join(parts)
                    except ValueError:
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


def discover_files_txt_with_directives(
    cwd: Path,
    root: Path | None = None,
    settings: dict[str, object] | None = None,
) -> tuple[list[tuple[Path, str]], dict[Path, ArenaDirective]]:
    """Same as :func:`discover_files_txt` but also returns a directive lookup.

    Returns:
        Tuple of ``(results, directive_lookup)`` where ``results`` is the
        same ``(Path, arena_name)`` list and ``directive_lookup`` maps each
        filepath to its parsed :class:`ArenaDirective` (empty when no
        directive is present or decoding fails).
    """
    results = discover_files_txt(cwd, root, settings)
    directives: dict[Path, ArenaDirective] = {}
    for path, _name in results:
        directives[path] = _safe_read_directive(path)
    return results, directives


# ---------------------------------------------------------------------------
# State snapshot for AI agents (`--status` flag)
# ---------------------------------------------------------------------------


def get_latest_state(
    arenas_dir: Path,
    inputs_dir: Path | None = None,
) -> dict[str, object]:
    """Return a token-cheap snapshot of the arena state for AI agents.

    Numbering is derived SOLELY from the ``NNN-`` prefix of arena directories
    (deterministic across OS / git / copy). mtime is reported only as a
    secondary "when did this last change" hint.

    Args:
        arenas_dir: ``<output_dir>/arenas`` directory.
        inputs_dir: Optional ``.context/inputs`` directory; when provided, its
            ``.txt`` count and newest file are included.

    Returns:
        Dict with keys: last_arena, next_number, total_arenas,
        latest_activity_arena, latest_activity_time, total_inputs,
        latest_input, latest_input_time.
    """
    state: dict[str, object] = {
        "last_arena": None,
        "next_number": 0,
        "total_arenas": 0,
        "latest_activity_arena": None,
        "latest_activity_time": "",
        "total_inputs": 0,
        "latest_input": None,
        "latest_input_time": "",
    }

    arena_num_re = re.compile(r"^(\d+)-(.+)$")

    numbered: list[tuple[int, str, Path]] = []
    if arenas_dir.is_dir():
        for p in arenas_dir.iterdir():
            if not p.is_dir():
                continue
            m = arena_num_re.match(p.name)
            if m:
                numbered.append((int(m.group(1)), m.group(2), p))

    state["total_arenas"] = len(numbered)

    if numbered:
        numbered.sort(key=lambda t: t[0])
        top_num, top_name, _ = numbered[-1]
        state["last_arena"] = f"{top_num:03d}-{top_name}"
        state["next_number"] = top_num + 1

        # Secondary: most recently touched arena by mtime (info only).
        newest = max(numbered, key=lambda t: t[2].stat().st_mtime)
        state["latest_activity_arena"] = f"{newest[0]:03d}-{newest[1]}"
        try:
            state["latest_activity_time"] = _dt.datetime.fromtimestamp(
                newest[2].stat().st_mtime
            ).strftime("%Y-%m-%d %H:%M")
        except OSError:
            state["latest_activity_time"] = ""

    if inputs_dir is not None and inputs_dir.is_dir():
        txts = sorted(p for p in inputs_dir.glob("*.txt") if p.is_file())
        state["total_inputs"] = len(txts)
        if txts:
            newest_in = max(txts, key=lambda f: f.stat().st_mtime)
            state["latest_input"] = newest_in.name
            try:
                state["latest_input_time"] = _dt.datetime.fromtimestamp(
                    newest_in.stat().st_mtime
                ).strftime("%Y-%m-%d %H:%M")
            except OSError:
                state["latest_input_time"] = ""

    return state


def write_state_breadcrumb(
    context_dir: Path, arenas_dir: Path, inputs_dir: Path | None = None
) -> None:
    """Persist a one-line JSON snapshot of state into .context/last_arena.json.

    Safe to call every run; overwrites in place. Never raises — breadcrumb is
    best-effort only.
    """
    state = get_latest_state(arenas_dir, inputs_dir)
    state["updated_at"] = _dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    try:
        context_dir.mkdir(parents=True, exist_ok=True)
        (context_dir / "last_arena.json").write_text(
            json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    except OSError:
        pass