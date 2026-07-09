"""Misc pure helpers shared across the GUI modules.

Keep this module Tk-free so its functions are trivially testable.
"""

from __future__ import annotations

from pathlib import Path


def assert_writable(path: Path) -> None:
    """Raise :class:`OSError` if *path* cannot be opened for appending.

    Used as a fail-fast pre-flight check before the aggregation worker
    writes to a target arena / structure / compare file. Mirrors the
    legacy ``_assert_writable`` module-private function.
    """
    try:
        path.open("a").close()
    except OSError as exc:
        raise OSError(f"Output file not writable: {path}") from exc


__all__ = ["assert_writable"]
