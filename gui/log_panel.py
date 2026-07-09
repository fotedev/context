"""Tk LogPanel widget — thread-safe coloured output.

Replaces the trio of legacy methods on ``AggregatorGUI``:

* ``_log_write``  → :meth:`LogPanel.write`
* ``_step``       → :meth:`LogPanel.step`
* ``_set_status`` → :meth:`LogPanel.set_status`
* ``_stop_progress`` → :meth:`LogPanel.stop_progress`

The ``tk.after(0, ...)`` wrapping inside ``write`` makes every method
safe to call from a background thread (the aggregation worker).
"""

from __future__ import annotations

import tkinter as tk
from tkinter import scrolledtext, ttk
from typing import Optional

from gui.theme import _BG_ENTRY, _BG_PANEL, _FG, _FG_DIM, configure_log_tags


class LogPanel:
    """A bundled scrolled text view + status bar + progress bar.

    The instance owns three Tk widgets — a ScrolledText for log lines,
    a ttk.Progressbar for indeterminate run mode, and a tk.StringVar
    backing a label for the status message. The status-bar / cancel
    widgets live on the caller-supplied statusbar frame so the layout
    can be tuned externally.
    """

    def __init__(
        self,
        *,
        master: tk.Misc,
        log_widget: Optional[scrolledtext.ScrolledText] = None,
        status_var: Optional[tk.StringVar] = None,
        progress: Optional[ttk.Progressbar] = None,
    ) -> None:
        # If widgets are not supplied (most callers pre-create them in
        # the statusbar builder), just remember handles — the GUI can
        # still call ``configure_log_tags`` itself.
        self._log = log_widget
        self._status_var = status_var
        self._progress = progress
        self._master = master

    @property
    def log_widget(self) -> Optional[scrolledtext.ScrolledText]:
        return self._log

    @property
    def status_var(self) -> Optional[tk.StringVar]:
        return self._status_var

    @property
    def progress(self) -> Optional[ttk.Progressbar]:
        return self._progress

    # The standard ``gui.theme.configure_log_tags`` is what registers
    # the colour tags. We expose it through this class for convenience
    # so callers don't have to remember two names.
    def attach_log_widget(
        self, widget: scrolledtext.ScrolledText
    ) -> scrolledtext.ScrolledText:
        self._log = widget
        configure_log_tags(widget)
        return widget

    def attach_status(self, var: tk.StringVar) -> None:
        self._status_var = var

    def attach_progress(self, widget: ttk.Progressbar) -> None:
        self._progress = widget

    # ------------------------------------------------------------------
    # Thread-safe writers
    # ------------------------------------------------------------------

    def write(self, message: str, tag: str = "") -> None:
        """Append a coloured log line. Safe to call from any thread."""
        if self._log is None:
            return
        def _insert() -> None:
            self._log.configure(state="normal")
            self._log.insert("end", f"›  {message}\n", tag or "")
            self._log.see("end")
            self._log.configure(state="disabled")
        self._master.after(0, _insert)

    def step(self, message: str) -> None:
        """High-level "this pipeline step is happening" log line."""
        self.write(message, tag="step")
        self.set_status(message)

    def set_status(self, text: str) -> None:
        """Update the status-bar text."""
        if self._status_var is None:
            return
        self._master.after(0, lambda: self._status_var.set(text))

    def start_progress(self, *, interval_ms: int = 12) -> None:
        """Pack + start the indeterminate progress bar."""
        if self._progress is None:
            return
        self._master.after(
            0,
            lambda: (self._progress.pack(side="right", padx=6, pady=10),
                     self._progress.start(interval_ms)),
        )

    def stop_progress(self) -> None:
        """Stop the spinner and forget it (no widget, no CPU cycle)."""
        if self._progress is None:
            return
        self._master.after(
            0,
            lambda: (self._progress.stop(),
                     self._progress.pack_forget()),
        )


__all__ = ["LogPanel"]
