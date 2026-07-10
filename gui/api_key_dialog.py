"""Tk-based API-key dialog + status helpers.

Isolates the modal ``_ApiKeyDialog`` Toplevel from the giant
``AggregatorGUI`` class so the GUI class can delegate ``_prompt_*``
calls to a focused module.

Visual styling and copy are preserved verbatim from the original file
— only the owning class changed.
"""

from __future__ import annotations

import os
import tkinter as tk

from gui.theme import (
    _ACCENT,
    _BG,
    _BG_ENTRY,
    _BTN_TEXT,
    _FG,
    _FG_DIM,
    _YELLOW,
)


class ApiKeyDialog(tk.Toplevel):
    """Modal dialog that collects the Gemini API key from the user.

    Public attributes
    -----------------
    result : str | None
        The entered key, or ``None`` when the user cancelled / skipped.
    save_to_env : bool
        Whether the user ticked "Save to .env".
    """

    def __init__(self, parent: tk.Tk) -> None:
        super().__init__(parent)
        _ = self.title("Gemini API Key Required")
        _ = self.configure(bg=_BG)
        _ = self.resizable(False, False)
        self.grab_set()  # modal
        self.result: str | None = None
        self.save_to_env: bool = False

        self._build()
        # Centre over parent
        self.update_idletasks()
        px = parent.winfo_rootx() + (parent.winfo_width() - self.winfo_width()) // 2
        py = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_height()) // 2
        _ = self.geometry(f"+{px}+{py}")
        self.wait_window()

    def _build(self) -> None:
        tk.Label(
            self,
            text="🔑  Gemini API Key not found in environment or .env file.",
            bg=_BG, fg=_YELLOW,
            font=("Segoe UI", 10, "bold"),
            wraplength=420, justify="left",
        ).pack(fill="x", padx=20, pady=8)

        tk.Label(
            self,
            text=(
                "Paste your GEMINI_API_KEY below, or leave blank "
                "to skip the AI Judge step."
            ),
            bg=_BG, fg=_FG_DIM,
            font=("Segoe UI", 9),
            wraplength=420, justify="left",
        ).pack(fill="x", padx=20, pady=(0, 4))

        # Key entry (show • while typing)
        self._key_var: tk.StringVar = tk.StringVar()
        entry = tk.Entry(
            self,
            textvariable=self._key_var,
            show="•",
            bg=_BG_ENTRY, fg=_FG,
            insertbackground=_FG,
            relief="flat",
            font=("Consolas", 10),
            width=52,
        )
        entry.pack(padx=20, pady=4, fill="x")
        entry.focus_set()
        _ = entry.bind("<Return>", lambda _e: self._confirm())

        # Save checkbox
        self._save_var: tk.BooleanVar = tk.BooleanVar(value=False)
        tk.Checkbutton(
            self,
            text="Save key to .env file in aggregator directory",
            variable=self._save_var,
            bg=_BG, fg=_FG,
            selectcolor=_BG_ENTRY,
            activebackground=_BG,
            activeforeground=_FG,
            font=("Segoe UI", 9),
        ).pack(anchor="w", padx=20, pady=(0, 8))

        # Buttons
        btn_row = tk.Frame(self, bg=_BG)
        btn_row.pack(fill="x", padx=20, pady=(0, 16))

        tk.Button(
            btn_row,
            text="Continue",
            command=self._confirm,
            bg=_ACCENT, fg=_BTN_TEXT,
            relief="flat", cursor="hand2",
            font=("Segoe UI", 10, "bold"),
            padx=18, pady=6,
        ).pack(side="left", padx=(0, 8))

        tk.Button(
            btn_row,
            text="Skip",
            command=self.destroy,
            bg=_BG_ENTRY, fg=_FG,
            relief="flat", cursor="hand2",
            font=("Segoe UI", 10),
            padx=18, pady=6,
        ).pack(side="left")

    def _confirm(self) -> None:
        key = self._key_var.get().strip()
        if key:
            self.result = key
            self.save_to_env = self._save_var.get()
        self.destroy()


# ---------------------------------------------------------------------------
# Status helpers
# ---------------------------------------------------------------------------


def api_key_status_text(
    project_dir, cwd: object | None = None
) -> str:
    """Return a one-line status string reflecting whether a key is loaded.

    Mirrors the legacy ``_api_key_status_text``. *project_dir* is the
    aggregator install dir (resolved by the caller).
    """
    from pathlib import Path

    from core.judge import load_dotenv

    load_dotenv(project_dir)
    if cwd is not None:
        load_dotenv(Path(cwd))
    key = os.environ.get("GEMINI_API_KEY", "")
    if key:
        if len(key) > 8:
            masked = key[:4] + "•" * (len(key) - 8) + key[-4:]
        else:
            masked = "••••"
        return f"API key loaded: {masked}"
    return "API key: not set  (Judge step will prompt)"


def save_api_key_to_env(env_path, key: str) -> None:
    """Append ``GEMINI_API_KEY=<key>`` to *env_path*. Best-effort."""
    try:
        with env_path.open("a", encoding="utf-8") as fh:
            fh.write(f"\nGEMINI_API_KEY={key}\n")
    except OSError as exc:  # noqa: BLE001
        # Surface via the GUI's log panel; we don't raise to keep the
        # dialog non-blocking.
        from gui.aggregation_runner import logger as _logger

        _logger.warning("Could not write .env at %s: %s", env_path, exc)


__all__ = [
    "ApiKeyDialog",
    "api_key_status_text",
    "save_api_key_to_env",
]
