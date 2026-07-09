"""Tkinter GUI package for the File Aggregator.

Decomposition — replaces the original ``aggregator_gui.py`` God Object
(1,477 lines, one ``AggregatorGUI(tk.Tk)`` class with ~40 methods) with
focused modules grouped by concern:

* :mod:`gui.theme`              — Catppuccin Mocha dark palette + fonts.
* :mod:`gui.util`               — Misc pure helpers (``_assert_writable``).
* :mod:`gui.paths`              — Shared ``PROJECT_DIR`` constant.
* :mod:`gui.scanner`            — Pure file-scanner / tree-builder logic.
* :mod:`gui.queue_manager`      — Pure ``files.txt`` queue I/O helpers.
* :mod:`gui.aggregation_runner` — Background aggregation pipeline runner
                                   (no Tk dependencies; takes callables).
* :mod:`gui.api_key_dialog`     — ``_ApiKeyDialog`` Tk class + thread-safe
                                   key resolution.
* :mod:`gui.log_panel`          — Tk LogPanel widget (thread-safe writes).
* :mod:`gui.builders`           — UI panel / pane builders.
* :mod:`gui.app`                — :class:`AggregatorGUI` thin coordinator
                                   that wires the above modules together.

The public API (``main()`` and the ``AggregatorGUI`` class) is preserved
verbatim so ``python aggregator_gui.py`` and ``aggg`` aliases keep
working. :func:`main` lives in the project root ``aggregator_gui.py``
file (which is now a 30-line glue module) and forwards to
``gui.app.run_gui``.
"""

from __future__ import annotations

__all__: list[str] = []
