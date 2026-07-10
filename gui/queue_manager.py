"""Pure queue management for the GUI.

Wraps the read / write / mutate lifecycle of ``files.txt`` in plain
functions so the Tk widget layer doesn't have to know the on-disk
syntax. The legacy ``_current_queue_entries``, ``_write_queue_lines``,
``_add_selected``, ``_remove_selected``, ``_clear_queue`` methods on
``AggregatorGUI`` all collapse into imports from this module — the GUI
class then just renders the results.

The on-disk format is intentional: one entry per line, comments start
with ``#``, snippets carry ``path:start-end`` ranges, important
structures carry a ``!`` prefix. :func:`read_lines` preserves those
textually instead of round-tripping through
:func:`core.parser.read_file_entries`, so the queue Listbox always
displays the user's literal text.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from core.parser import read_file_entries

logger = logging.getLogger("gui.queue")

#: Substring that identifies snippet-range entries (e.g. ``file.py:10-20``).
_RANGE_RE = re.compile(r":\d+-\d+")


# ---------------------------------------------------------------------------
# Low-level raw-line helpers (mirror of the legacy methods)
# ---------------------------------------------------------------------------


def files_txt_path(project_root: Path) -> Path:
    """Resolve the canonical ``files.txt`` location for *project_root*."""
    return project_root / "files.txt"


def read_lines(files_txt: Path) -> list[str]:
    """Read ``files_txt`` and return non-empty stripped lines.

    Returns an empty list when the file is missing or unreadable.
    """
    if not files_txt.is_file():
        return []
    try:
        return [
            line.strip()
            for line in files_txt.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except OSError as exc:
        logger.warning("Could not read %s: %s", files_txt, exc)
        return []


def write_lines(files_txt: Path, lines: Sequence[str]) -> None:
    """Overwrite ``files_txt`` with *lines* (one per line, trailing newline)."""
    content = "\n".join(lines) + ("\n" if lines else "")
    files_txt.write_text(content, encoding="utf-8")


def clear(files_txt: Path) -> None:
    """Wipe *files_txt* to zero bytes (the equivalent of *clear_queue*)."""
    files_txt.write_text("", encoding="utf-8")


def read_entries(files_txt: Path) -> list[Any]:
    """Parse ``files_txt`` through :func:`core.parser.read_file_entries`.

    Returns an empty list when the file is missing — matches the legacy
    behaviour of ``_current_queue_entries``.
    """
    if not files_txt.is_file():
        return []
    try:
        return read_file_entries(files_txt)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not parse entries: %s", exc)
        return []


# ---------------------------------------------------------------------------
# Higher-level mutators
# ---------------------------------------------------------------------------


def _bare_path(line: str) -> str:
    """Strip the ``!`` / range suffix to expose the queue key (abs path)."""
    line = line.lstrip("!")
    if _RANGE_RE.search(line):
        line = line.rsplit(":", 1)[0]
    return line


def add_paths(
    files_txt: Path, paths: Sequence[Path]
) -> tuple[int, int]:
    """Append *paths* to ``files_txt`` as full-file entries.

    Duplicates (compared via :func:`_bare_path` key) are skipped. The
    line order is preserved.

    Returns:
        ``(added, skipped)`` tuple for downstream logging.
    """
    existing = read_lines(files_txt)
    bare_set = {_bare_path(line) for line in existing if not line.startswith("#")}
    new_lines = list(existing)

    added = 0
    skipped = 0
    for path in paths:
        try:
            abs_str = str(path.resolve())
        except OSError as exc:
            logger.warning("Could not resolve %s: %s", path, exc)
            skipped += 1
            continue
        if abs_str not in bare_set:
            new_lines.append(abs_str)
            bare_set.add(abs_str)
            added += 1
        else:
            skipped += 1

    write_lines(files_txt, new_lines)
    return added, skipped


def remove_indices(files_txt: Path, indices: Sequence[int]) -> int:
    """Drop the listed line *indices* from ``files_txt``.

    Indices are interpreted against the current read_lines() ordering
    (matching the Listbox indices shown to the user). Unknown indices
    are silently skipped.

    Returns:
        Number of lines actually removed.
    """
    existing = read_lines(files_txt)
    drop = set(indices)
    kept = [line for idx, line in enumerate(existing) if idx not in drop]
    write_lines(files_txt, kept)
    return len(existing) - len(kept)


# ---------------------------------------------------------------------------
# Display helpers (carry-over from the legacy _refresh_queue method)
# ---------------------------------------------------------------------------


def classify_line(line: str) -> str:
    """Classify a queue line for colour-coding.

    Returns one of:
        ``"comment"``    — starts with ``#``
        ``"important"``  — starts with ``!``
        ``"snippet"``    — has a ``:n-m`` range
        ``"file"``       — anything else
    """
    if line.startswith("#"):
        return "comment"
    if line.startswith("!"):
        return "important"
    if _RANGE_RE.search(line):
        return "snippet"
    return "file"


def count_files(lines: Sequence[str]) -> int:
    """Count non-comment lines for the queue title."""
    return sum(1 for line in lines if not line.startswith("#"))


__all__ = [
    "files_txt_path",
    "read_lines",
    "write_lines",
    "clear",
    "read_entries",
    "add_paths",
    "remove_indices",
    "classify_line",
    "count_files",
]
