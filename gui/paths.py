"""Shared filesystem paths used across the ``gui/`` package.

The original ``aggregator_gui.py`` script computed ``_PROJECT_DIR`` as
``Path(__file__).resolve().parent``. When the GUI was broken up across
multiple modules in a ``gui/`` subpackage, every submodule would
compute a different ``PROJECT_DIR`` (= its own parent = the ``gui/``
directory). To preserve the original behaviour — ``.env`` loading and
``files.txt`` fallback targeting the project *root* — we expose a
single, identity-stable constant that always points at the directory
one level up from this file.

The leading underscore is dropped because this module is part of the
package's public surface now; consumers do ``from gui.paths import
PROJECT_DIR``.
"""

from __future__ import annotations

from pathlib import Path

#: Project root (parent of the ``gui/`` subpackage). All GUI helpers
#: resolve ``.env``, ``files.txt``, and ``prompt.txt`` against this path
#: to match the legacy single-file behaviour.
PROJECT_DIR: Path = Path(__file__).resolve().parent.parent


__all__ = ["PROJECT_DIR"]
