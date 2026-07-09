"""Pure file-scanner + tree-builder logic.

Extracted from the original ``_refresh_tree`` and ``_populate_tree``
methods on :class:`gui.app.AggregatorGUI`. Kept Tk-free so the logic
can be unit-tested independently and so the GUI class can stay focused
on widget orchestration.

The scanner does three things and returns plain Python data structures
(no Tk widget references in the output):

* :func:`discover_tree` — walk *root* honouring ignore patterns and
  optionally a search filter; emit a flat list of
  ``(path, depth, is_dir)`` records.
* :func:`detect_initial_root` — re-implements the legacy bootstrap
  heuristic for picking a starting project root.
* :func:`list_commands` placeholder kept for future CLI-integration
  work (unused today).
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from core.parser import (
    find_project_root,
    load_ignore_patterns,
    read_file_paths,
    should_ignore,
)

# Local imports must keep working regardless of which module imports
# this one — same sys.path bootstrap the legacy script used.
from gui.paths import PROJECT_DIR as _PROJECT_DIR


logger = logging.getLogger("gui.scanner")


@dataclass(frozen=True)
class TreeNode:
    """One entry in a scanned project tree.

    Attributes:
        path: Absolute filesystem path.
        depth: 0 = root, +1 per directory level.
        is_dir: True for directories, False for files.
        in_queue: True if the resolved path is already queued
            (carried through from the GUI's queue so the tree can show
            ✔ markers).
    """

    path: Path
    depth: int
    is_dir: bool
    in_queue: bool


# Cap recursion to match the legacy behaviour (was ``depth > 8``).
_MAX_DEPTH = 8


def discover_tree(
    *,
    root: Path,
    settings,
    queued_paths: Iterable[Path],
    output_dir_name: str,
    filter_text: str = "",
    max_depth: int = _MAX_DEPTH,
) -> list[TreeNode]:
    """Walk *root* and return a flat list of :class:`TreeNode` records.

    Honours ``settings['output_dir']`` plus the ignore-pattern set
    produced by :func:`core.parser.load_ignore_patterns` for the
    *filtering rules* concern the decomposition brief calls out.
    The ``filter_text`` substring filter is applied per-file-name and
    only files (directories are always shown so the tree remains
    navigable).

    Args:
        root: Project root to walk.
        settings: Loaded settings dataclass / dict — used to read
            ``output_dir`` (mirrors legacy behaviour).
        queued_paths: Paths the user has already queued. Used to flip
            the ``in_queue`` flag on each node.
        output_dir_name: Settings ``output_dir`` string used by
            :func:`core.parser.should_ignore` to skip self-output.
        filter_text: Optional case-insensitive substring filter for
            file names. Empty string = no filter.
        max_depth: Recursion guard. Defaults to ``_MAX_DEPTH`` to match
            the legacy hard-coded ``8``.

    Returns:
        Flat list of :class:`TreeNode` ordered as a depth-first walk
        suitable for driving a :class:`ttk.Treeview` widget.
    """
    patterns = load_ignore_patterns(root, settings)
    queued_resolved = {p.resolve() for p in queued_paths}
    needle = filter_text.strip().lower()

    nodes: list[TreeNode] = []
    _walk(
        nodes,
        parent=root,
        root=root,
        patterns=patterns,
        queued=queued_resolved,
        filter_text=needle,
        output_dir_name=output_dir_name,
        depth=0,
        max_depth=max_depth,
    )
    return nodes


def _walk(
    out: list[TreeNode],
    *,
    parent: Path,
    root: Path,
    patterns: frozenset[str],
    queued: set[Path],
    filter_text: str,
    output_dir_name: str,
    depth: int,
    max_depth: int,
) -> None:
    """Recursive depth-first walker used by :func:`discover_tree`."""
    if depth > max_depth:
        return
    try:
        items = sorted(
            parent.iterdir(),
            key=lambda p: (not p.is_dir(), p.name.lower()),
        )
    except PermissionError:
        logger.debug("Permission denied while listing %s", parent)
        return

    for item in items:
        if should_ignore(item, root, patterns, output_dir_name):
            continue
        if filter_text and item.is_file() and filter_text not in item.name.lower():
            continue

        is_dir = item.is_dir() and not item.is_symlink()
        out.append(
            TreeNode(
                path=item,
                depth=depth,
                is_dir=is_dir,
                in_queue=item.resolve() in queued,
            )
        )
        if is_dir:
            _walk(
                out,
                parent=item,
                root=root,
                patterns=patterns,
                queued=queued,
                filter_text=filter_text,
                output_dir_name=output_dir_name,
                depth=depth + 1,
                max_depth=max_depth,
            )


def detect_initial_root(
    *,
    cwd: Optional[Path] = None,
    project_dir: Optional[Path] = None,
) -> Path:
    """Best-effort bootstrap for the GUI's project root.

    Mirrors the legacy :meth:`AggregatorGUI._detect_initial_root`:
    if either ``<cwd>/files.txt`` or ``<project_dir>/files.txt`` is
    readable and lists at least one path, use
    :func:`core.parser.find_project_root` to pick the root. Otherwise
    fall back to the CWD.

    Args:
        cwd: Current working directory (default: :func:`Path.cwd`).
        project_dir: Aggregator install dir (default: :data:`PROJECT_DIR`).

    Returns:
        Resolved Path to use as the project root.
    """
    candidates = [
        (cwd or Path.cwd()) / "files.txt",
        (project_dir or _PROJECT_DIR) / "files.txt",
    ]
    for candidate in candidates:
        if candidate.is_file():
            try:
                paths = read_file_paths(candidate)
            except Exception as exc:  # noqa: BLE001 — best effort
                logger.debug("read_file_paths(%s) failed: %s", candidate, exc)
                paths = []
            if paths:
                root = find_project_root(paths[0])
                if root:
                    return root
    return (cwd or Path.cwd()).resolve()


def iter_tree_rows(nodes: Iterable[TreeNode]) -> list[tuple[TreeNode, str]]:
    """Convert a flat :class:`TreeNode` list into rows ready for a Treeview.

    Helper for the GUI layer — labels ``📁`` for directories and
    ``✔ `` for queued files. Returns tuples of ``(node, display_text)``.
    The Treeview itself owns positioning and indent rendering.
    """
    rows: list[tuple[TreeNode, str]] = []
    for node in nodes:
        if node.is_dir:
            label = f"📁  {node.path.name}"
        else:
            marker = "✔  " if node.in_queue else "    "
            label = f"{marker}{node.path.name}"
        rows.append((node, label))
    return rows


# Convenience export expected by some tests / future TUI callers.
__all__ = [
    "TreeNode",
    "discover_tree",
    "detect_initial_root",
    "iter_tree_rows",
]


# Suppress noisy stdout from imported modules during initial load
# (mirrors legacy encoding fix-up).
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")
