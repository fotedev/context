"""Catppuccin Mocha dark palette and font setup for the GUI.

Centralising the theme constants here keeps the colour choices out of
the top-level application class — every Tkinter widget builder can
``from gui.theme import _BG, _ACCENT`` etc. without pulling in the
whole ``AggregatorGUI``.

The leading-underscore constants are preserved from the original
``aggregator_gui.py`` (they are module-private to the package's own
modules, not exposed as a public API).
"""

from __future__ import annotations

import tkinter as tk
from tkinter import font

# ── Catppuccin Mocha dark palette (legacy constants — kept verbatim) ────
_BG         = "#1e1e2e"   # base
_BG_PANEL   = "#181825"   # mantle
_BG_ENTRY   = "#313244"   # surface0
_BG_HOVER   = "#45475a"   # surface1
_FG         = "#cdd6f4"   # text
_FG_DIM     = "#6c7086"   # overlay0
_ACCENT     = "#89b4fa"   # blue
_GREEN      = "#a6e3a1"   # green
_YELLOW     = "#f9e2af"   # yellow
_ORANGE     = "#fab387"   # peach
_RED        = "#f38ba8"   # red
_MAUVE      = "#cba6f7"   # mauve
_TEAL       = "#94e2d5"   # teal
_BTN_TEXT   = "#1e1e2e"


def build_fonts() -> dict[str, font.Font]:
    """Construct the GUI's four Font objects in one place.

    Kept identical to the legacy ``_setup_fonts`` method so visual
    output is unchanged.
    """
    return {
        "ui":    font.Font(family="Segoe UI", size=10),
        "mono":  font.Font(family="Consolas", size=9),
        "title": font.Font(family="Segoe UI", size=11, weight="bold"),
        "small": font.Font(family="Segoe UI", size=8),
    }


def configure_log_tags(log: tk.Text) -> None:
    """Register the colour tags used by :class:`gui.log_panel.LogPanel`.

    Mirrors the legacy tag wiring that used to live inside
    ``_build_log_pane``.
    """
    log.tag_config("ok",    foreground=_GREEN)
    log.tag_config("warn",  foreground=_YELLOW)
    log.tag_config("error", foreground=_RED)
    log.tag_config("info",  foreground=_FG_DIM)
    log.tag_config("step",  foreground=_TEAL)
    log.tag_config("judge", foreground=_MAUVE)


__all__ = [
    "_BG",
    "_BG_PANEL",
    "_BG_ENTRY",
    "_BG_HOVER",
    "_FG",
    "_FG_DIM",
    "_ACCENT",
    "_GREEN",
    "_YELLOW",
    "_ORANGE",
    "_RED",
    "_MAUVE",
    "_TEAL",
    "_BTN_TEXT",
    "build_fonts",
    "configure_log_tags",
]
