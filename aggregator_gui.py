# aggregator_gui.py
"""Fully-integrated Tkinter GUI for the File Aggregator.

All backend logic from aggregator.py is wired into this GUI:
  • File tree browsing with ignore-pattern filtering
  • Queue management supporting full files, snippets (:start-end), and
    important structures (! prefix)
  • Background aggregation thread → arena.txt + structure.txt
  • Token counter shown after aggregation
  • Gemini AI Judge pipeline → compare.md
  • API key retrieval from env / .env / GUI dialog

Launch via:  aggg
No third-party dependencies required beyond the standard library.
"""

from __future__ import annotations

import os
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, font, messagebox, scrolledtext, simpledialog, ttk
from typing import Optional

# ── Encoding fix for Windows terminals ───────────────────────────────────────
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# ── Project directory on sys.path so core/ is importable ─────────────────────
_PROJECT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_PROJECT_DIR))

# ── Core imports ──────────────────────────────────────────────────────────────
from core.parser import (
    aggregate_files,
    find_project_root,
    generate_tree,
    load_ignore_patterns,
    read_file_entries,
    read_file_paths,
    should_ignore,
    initialize_environment,
)
from core.counter import count_tokens
from core.judge import (
    build_compare_markdown,
    collect_model_responses,
    generate_compare_template,
    get_api_key,
    get_gemini_verdict,
    load_dotenv,
)

# ── Fixed output paths (always relative to the aggregator project dir) ────────
_FILES_TXT    = _PROJECT_DIR / "files.txt"
_ARENA_TXT    = _PROJECT_DIR / "arena.txt"
_STRUCTURE_TXT = _PROJECT_DIR / "structure.txt"
_COMPARE_TXT  = _PROJECT_DIR / "compare.md"

# ── Catppuccin Mocha dark palette ─────────────────────────────────────────────
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


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _entry_display(path: Path, ranges, is_important: bool) -> str:
    """Return a human-readable queue label for a files.txt entry tuple.

    Examples
    --------
    Full file      →  /home/proj/main.py
    Snippet        →  /home/proj/main.py  [45-80]
    Multi-range    →  /home/proj/main.py  [5-10, 25-30]
    Important      →  ★ /home/proj/types.ts  [1-30]
    """
    base = str(path)
    if ranges:
        range_str = ", ".join(f"{s}-{e}" for s, e in ranges)
        base += f"  [{range_str}]"
    prefix = "★ " if is_important else "  "
    return f"{prefix}{base}"


def _assert_writable(path: Path) -> None:
    """Raise OSError if *path* cannot be opened for appending."""
    try:
        path.open("a").close()
    except OSError as exc:
        raise OSError(f"Output file not writable: {path}") from exc


# ─────────────────────────────────────────────────────────────────────────────
# GUI – API Key Dialog
# ─────────────────────────────────────────────────────────────────────────────

class _ApiKeyDialog(tk.Toplevel):
    """Modal dialog that collects the Gemini API key from the user.

    Attributes
    ----------
    result : str | None
        The entered key, or ``None`` when the user cancelled / skipped.
    save_to_env : bool
        Whether the user ticked "Save to .env".
    """

    def __init__(self, parent: tk.Tk) -> None:
        super().__init__(parent)
        self.title("Gemini API Key Required")
        self.configure(bg=_BG)
        self.resizable(False, False)
        self.grab_set()             # modal
        self.result: Optional[str] = None
        self.save_to_env: bool = False

        self._build()
        # Centre over parent
        self.update_idletasks()
        px = parent.winfo_rootx() + (parent.winfo_width()  - self.winfo_width())  // 2
        py = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{px}+{py}")
        self.wait_window()

    def _build(self) -> None:
        pad = {"padx": 20, "pady": 8}

        tk.Label(
            self,
            text="🔑  Gemini API Key not found in environment or .env file.",
            bg=_BG, fg=_YELLOW,
            font=("Segoe UI", 10, "bold"),
            wraplength=420, justify="left",
        ).pack(fill="x", **pad)

        tk.Label(
            self,
            text="Paste your GEMINI_API_KEY below, or leave blank to skip the AI Judge step.",
            bg=_BG, fg=_FG_DIM,
            font=("Segoe UI", 9),
            wraplength=420, justify="left",
        ).pack(fill="x", padx=20, pady=(0, 4))

        # Key entry (show * while typing)
        self._key_var = tk.StringVar()
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
        entry.bind("<Return>", lambda _e: self._confirm())

        # Save checkbox
        self._save_var = tk.BooleanVar(value=False)
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


# ─────────────────────────────────────────────────────────────────────────────
# Main Application Window
# ─────────────────────────────────────────────────────────────────────────────

class AggregatorGUI(tk.Tk):
    """Full-featured dark-mode GUI for the File Aggregator pipeline.

    Layout (left → right, top → bottom)
    ─────────────────────────────────────
    Header bar
    ┌─ Left panel ──────────┬─ Right panel ───────────────────────────────┐
    │  Project tree         │  ┌─ Queue ──────────────────────────────┐   │
    │  (filterable)         │  │  Entries (files / snippets / structs)│   │
    │                       │  └──────────────────────────────────────┘   │
    │                       │  ┌─ Options ────────────────────────────┐   │
    │                       │  │  ☑ Run Gemini Judge  ☑ Compact mode │   │
    │                       │  └──────────────────────────────────────┘   │
    │                       │  ┌─ Activity log ───────────────────────┐   │
    │                       │  │  Coloured, scrollable, read-only     │   │
    │                       │  └──────────────────────────────────────┘   │
    └───────────────────────┴─────────────────────────────────────────────┘
    Status / progress bar
    """

    def __init__(self) -> None:
        super().__init__()
        self.title("File Aggregator")
        self.geometry("1100x750")
        self.minsize(860, 560)
        self.configure(bg=_BG)

        # State
        self._project_root: Path = self._detect_initial_root()
        self._busy: bool = False          # True while a background thread runs

        # UI setup
        self._setup_fonts()
        self._build_ui()

        # Bootstrap: ensure files.txt / models/ / prompt.txt exist, then refresh
        self._initialize_env_silent()
        self._refresh_all()

    # ── Startup helpers ───────────────────────────────────────────────────────

    def _detect_initial_root(self) -> Path:
        """Guess project root from files.txt, falling back to the aggregator dir."""
        if _FILES_TXT.is_file():
            try:
                paths = read_file_paths(_FILES_TXT)
                if paths:
                    root = find_project_root(paths[0])
                    if root:
                        return root
            except Exception:
                pass
        return _PROJECT_DIR

    def _initialize_env_silent(self) -> None:
        """Call initialize_environment() without any blocking terminal prompts.

        The GUI creates the folder structure silently; model-file count is
        handled via the dedicated "Manage Model Files" workflow instead of
        stdin.
        """
        try:
            models_dir = self._project_root / "models"
            # Touch files.txt
            if not _FILES_TXT.exists():
                _FILES_TXT.touch()

            # Create models/ and prompt.txt if absent
            models_dir.mkdir(parents=True, exist_ok=True)
            prompt_file = models_dir / "prompt.txt"
            if not prompt_file.exists():
                prompt_file.touch()

            self._log_write("Environment initialised.", tag="info")
        except Exception as exc:
            self._log_write(f"Warning: could not initialise env: {exc}", tag="warn")

    # ── Font setup ────────────────────────────────────────────────────────────

    def _setup_fonts(self) -> None:
        self._font_ui    = font.Font(family="Segoe UI",  size=10)
        self._font_mono  = font.Font(family="Consolas",  size=9)
        self._font_title = font.Font(family="Segoe UI",  size=11, weight="bold")
        self._font_small = font.Font(family="Segoe UI",  size=8)

    # ─────────────────────────────────────────────────────────────────────────
    # UI Construction
    # ─────────────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        self._build_header()
        self._build_body()
        self._build_statusbar()

    # ── Header ────────────────────────────────────────────────────────────────

    def _build_header(self) -> None:
        bar = tk.Frame(self, bg=_ACCENT, height=42)
        bar.pack(fill="x", side="top")
        bar.pack_propagate(False)

        tk.Label(
            bar,
            text="⚙  File Aggregator",
            bg=_ACCENT, fg=_BTN_TEXT,
            font=self._font_title,
        ).pack(side="left", padx=16, pady=10)

        # Version / hint on the right
        tk.Label(
            bar,
            text="★ = important structure   [n-m] = snippet range",
            bg=_ACCENT, fg=_BTN_TEXT,
            font=self._font_small,
        ).pack(side="right", padx=16)

    # ── Body (paned: tree | queue+log) ───────────────────────────────────────

    def _build_body(self) -> None:
        body = tk.PanedWindow(
            self, orient="horizontal", bg=_BG, sashwidth=5, sashrelief="flat"
        )
        body.pack(fill="both", expand=True, padx=10, pady=(8, 0))

        body.add(self._build_left_panel(body),  minsize=320)
        body.add(self._build_right_panel(body), minsize=440)

    # ── Left: project tree ────────────────────────────────────────────────────

    def _build_left_panel(self, parent: tk.Widget) -> tk.Frame:
        frame = tk.Frame(parent, bg=_BG_PANEL)

        self._tree_title = tk.Label(
            frame,
            text=f"📁  {self._project_root.name}",
            bg=_BG_PANEL, fg=_ACCENT,
            font=self._font_title, anchor="w",
        )
        self._tree_title.pack(fill="x", padx=10, pady=(10, 4))

        # ── Search / filter bar ───────────────────────────────────────────────
        search_frame = tk.Frame(frame, bg=_BG_PANEL)
        search_frame.pack(fill="x", padx=8, pady=(0, 4))

        tk.Label(
            search_frame, text="🔍", bg=_BG_PANEL, fg=_FG_DIM,
            font=self._font_ui,
        ).pack(side="left", padx=(0, 4))

        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", lambda *_: self._refresh_tree())
        tk.Entry(
            search_frame,
            textvariable=self._search_var,
            bg=_BG_ENTRY, fg=_FG,
            insertbackground=_FG,
            relief="flat",
            font=self._font_mono,
        ).pack(fill="x", expand=True, ipady=3)

        # ── Tree widget ────────────────────────────────────────────────────────
        tree_wrap = tk.Frame(frame, bg=_BG_PANEL)
        tree_wrap.pack(fill="both", expand=True, padx=5, pady=4)

        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            "Agg.Treeview",
            background=_BG_ENTRY,
            fieldbackground=_BG_ENTRY,
            foreground=_FG,
            rowheight=24,
            font=self._font_mono,
            borderwidth=0,
        )
        style.map(
            "Agg.Treeview",
            background=[("selected", _ACCENT)],
            foreground=[("selected", _BTN_TEXT)],
        )

        self._tree = ttk.Treeview(
            tree_wrap,
            style="Agg.Treeview",
            selectmode="extended",
            show="tree",
        )
        vsb = ttk.Scrollbar(tree_wrap, orient="vertical",   command=self._tree.yview)
        hsb = ttk.Scrollbar(tree_wrap, orient="horizontal", command=self._tree.xview)
        self._tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.pack(side="right",  fill="y")
        hsb.pack(side="bottom", fill="x")
        self._tree.pack(fill="both", expand=True)

        # Double-click to add single file
        self._tree.bind("<Double-1>", lambda _e: self._add_selected())

        tk.Button(
            frame,
            text="＋  Add Selected to Queue",
            command=self._add_selected,
            bg=_ACCENT, fg=_BTN_TEXT,
            relief="flat", font=self._font_ui, cursor="hand2", pady=6,
        ).pack(fill="x", padx=10, pady=(4, 10))

        return frame

    # ── Right: queue + options + log ──────────────────────────────────────────

    def _build_right_panel(self, parent: tk.Widget) -> tk.Frame:
        frame = tk.Frame(parent, bg=_BG)
        paned_v = tk.PanedWindow(
            frame, orient="vertical", bg=_BG, sashwidth=5, sashrelief="flat"
        )
        paned_v.pack(fill="both", expand=True)

        paned_v.add(self._build_queue_pane(paned_v),   minsize=160)
        paned_v.add(self._build_options_pane(paned_v), minsize=80)
        paned_v.add(self._build_log_pane(paned_v),     minsize=140)

        return frame

    def _build_queue_pane(self, parent: tk.Widget) -> tk.Frame:
        frame = tk.Frame(parent, bg=_BG_PANEL)

        self._queue_title = tk.Label(
            frame,
            text="📋  Queue  (0 entries)",
            bg=_BG_PANEL, fg=_ACCENT,
            font=self._font_title, anchor="w",
        )
        self._queue_title.pack(fill="x", padx=10, pady=(10, 4))

        list_wrap = tk.Frame(frame, bg=_BG_PANEL)
        list_wrap.pack(fill="both", expand=True, padx=5, pady=4)

        self._queue_listbox = tk.Listbox(
            list_wrap,
            bg=_BG_ENTRY, fg=_FG,
            selectbackground=_ACCENT, selectforeground=_BTN_TEXT,
            font=self._font_mono,
            relief="flat", borderwidth=0,
            activestyle="none", highlightthickness=0,
        )
        q_vsb = ttk.Scrollbar(list_wrap, orient="vertical",   command=self._queue_listbox.yview)
        q_hsb = ttk.Scrollbar(list_wrap, orient="horizontal", command=self._queue_listbox.xview)
        self._queue_listbox.configure(
            yscrollcommand=q_vsb.set, xscrollcommand=q_hsb.set
        )
        q_vsb.pack(side="right",  fill="y")
        q_hsb.pack(side="bottom", fill="x")
        self._queue_listbox.pack(fill="both", expand=True)

        # Tag coloring for queue entries
        # (Listbox does not natively support per-item colours without hacks;
        #  we use a separate colour map keyed by listbox index instead)
        self._queue_colours: dict[int, str] = {}

        tk.Button(
            frame,
            text="－  Remove Selected",
            command=self._remove_selected,
            bg=_ORANGE, fg=_BTN_TEXT,
            relief="flat", font=self._font_ui, cursor="hand2", pady=5,
        ).pack(fill="x", padx=10, pady=(4, 10))

        return frame

    def _build_options_pane(self, parent: tk.Widget) -> tk.Frame:
        """Options panel: Gemini Judge toggle + compact mode toggle."""
        frame = tk.Frame(parent, bg=_BG_PANEL)

        tk.Label(
            frame,
            text="⚙  Aggregation Options",
            bg=_BG_PANEL, fg=_ACCENT,
            font=self._font_title, anchor="w",
        ).pack(fill="x", padx=10, pady=(10, 6))

        row = tk.Frame(frame, bg=_BG_PANEL)
        row.pack(fill="x", padx=12)

        # Gemini Judge toggle
        self._judge_var = tk.BooleanVar(value=True)
        tk.Checkbutton(
            row,
            text="🤖  Run Gemini AI Judge after aggregation",
            variable=self._judge_var,
            bg=_BG_PANEL, fg=_FG,
            selectcolor=_BG_ENTRY,
            activebackground=_BG_PANEL, activeforeground=_FG,
            font=self._font_ui,
        ).pack(side="left", padx=(0, 24))

        # Compact mode toggle
        self._compact_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            row,
            text="📦  Compact mode (strip Notes)",
            variable=self._compact_var,
            bg=_BG_PANEL, fg=_FG,
            selectcolor=_BG_ENTRY,
            activebackground=_BG_PANEL, activeforeground=_FG,
            font=self._font_ui,
        ).pack(side="left")

        # API key status label
        self._api_key_label = tk.Label(
            frame,
            text=self._api_key_status_text(),
            bg=_BG_PANEL, fg=_FG_DIM,
            font=self._font_small, anchor="w",
        )
        self._api_key_label.pack(fill="x", padx=12, pady=(4, 8))

        # "Set API Key" button
        tk.Button(
            frame,
            text="🔑  Set / Update API Key",
            command=self._prompt_api_key_gui,
            bg=_BG_ENTRY, fg=_FG,
            relief="flat", font=self._font_small, cursor="hand2",
            padx=10, pady=3,
        ).pack(anchor="w", padx=12, pady=(0, 10))

        return frame

    def _build_log_pane(self, parent: tk.Widget) -> tk.Frame:
        frame = tk.Frame(parent, bg=_BG_PANEL)

        tk.Label(
            frame,
            text="📜  Activity Log",
            bg=_BG_PANEL, fg=_ACCENT,
            font=self._font_title, anchor="w",
        ).pack(fill="x", padx=10, pady=(10, 4))

        self._log = scrolledtext.ScrolledText(
            frame,
            bg=_BG_ENTRY, fg=_FG,
            font=self._font_mono,
            relief="flat", borderwidth=0,
            state="disabled", wrap="word",
        )
        self._log.pack(fill="both", expand=True, padx=5, pady=5)

        # Colour tags for log lines
        self._log.tag_config("ok",    foreground=_GREEN)
        self._log.tag_config("warn",  foreground=_YELLOW)
        self._log.tag_config("error", foreground=_RED)
        self._log.tag_config("info",  foreground=_FG_DIM)
        self._log.tag_config("step",  foreground=_TEAL)
        self._log.tag_config("judge", foreground=_MAUVE)

        return frame

    # ── Status / progress bar ─────────────────────────────────────────────────

    def _build_statusbar(self) -> None:
        bar = tk.Frame(self, bg=_BG_PANEL, height=52)
        bar.pack(fill="x", side="bottom")
        bar.pack_propagate(False)

        # Project path label + entry
        tk.Label(
            bar, text="Root:",
            bg=_BG_PANEL, fg=_FG_DIM, font=self._font_ui,
        ).pack(side="left", padx=(10, 4))

        self._project_path_var = tk.StringVar(value=str(self._project_root))
        self._project_path_entry = tk.Entry(
            bar,
            textvariable=self._project_path_var,
            bg=_BG_ENTRY, fg=_FG,
            insertbackground=_FG, relief="flat",
            font=self._font_mono, width=50,
        )
        self._project_path_entry.pack(side="left", padx=(0, 6), pady=8, ipady=3)
        self._project_path_entry.bind("<Return>", self._on_path_submit)

        tk.Button(
            bar, text="Apply",
            command=lambda: self._on_path_submit(None),
            bg=_ACCENT, fg=_BTN_TEXT,
            relief="flat", font=self._font_ui, cursor="hand2",
            padx=10,
        ).pack(side="left", padx=(0, 6), pady=8)

        # Action buttons (right-to-left packing order)
        action_btns = [
            ("📂  Open Root",      self._open_root,      _FG_DIM),
            ("✕  Clear Queue",    self._clear_queue,    _ORANGE),
            ("▶  Run Aggregate",  self._run_aggregate,  _GREEN),
            ("⟳  Refresh",        self._refresh_all,    _ACCENT),
        ]
        for label, cmd, colour in action_btns:
            tk.Button(
                bar, text=label, command=cmd,
                bg=colour, fg=_BTN_TEXT,
                relief="flat", font=self._font_ui, cursor="hand2",
                padx=14,
            ).pack(side="right", padx=5, pady=8)

        # Progress bar (hidden until busy)
        self._progress = ttk.Progressbar(
            bar, mode="indeterminate", length=120,
        )
        # Status text
        self._status_var = tk.StringVar(value="Ready.")
        self._status_lbl = tk.Label(
            bar,
            textvariable=self._status_var,
            bg=_BG_PANEL, fg=_FG_DIM, font=self._font_ui, anchor="e",
        )
        self._status_lbl.pack(side="right", padx=10)

    # ─────────────────────────────────────────────────────────────────────────
    # API Key helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _api_key_status_text(self) -> str:
        """Return a one-line status string reflecting whether a key is loaded."""
        # Load .env files the same way core.judge does
        load_dotenv(_PROJECT_DIR)
        load_dotenv(Path.cwd())
        key = os.environ.get("GEMINI_API_KEY", "")
        if key:
            masked = key[:4] + "•" * (len(key) - 8) + key[-4:] if len(key) > 8 else "••••"
            return f"API key loaded: {masked}"
        return "API key: not set  (Judge step will prompt)"

    def _prompt_api_key_gui(self) -> None:
        """Open the API key dialog and store the result in the environment."""
        dlg = _ApiKeyDialog(self)
        if dlg.result:
            os.environ["GEMINI_API_KEY"] = dlg.result
            if dlg.save_to_env:
                self._save_api_key_to_env(dlg.result)
            self._api_key_label.configure(text=self._api_key_status_text())
            self._log_write("API key updated.", tag="ok")

    def _save_api_key_to_env(self, key: str) -> None:
        """Append GEMINI_API_KEY to the aggregator-directory .env file."""
        env_path = _PROJECT_DIR / ".env"
        try:
            with env_path.open("a", encoding="utf-8") as fh:
                fh.write(f"\nGEMINI_API_KEY={key}\n")
            self._log_write(f"API key saved → {env_path}", tag="ok")
        except Exception as exc:
            self._log_write(f"Could not save .env: {exc}", tag="warn")

    # ─────────────────────────────────────────────────────────────────────────
    # Project root management
    # ─────────────────────────────────────────────────────────────────────────

    def _change_root(self, new_root: Path) -> None:
        """Update internal root, clear queue, refresh everything."""
        self._project_root = new_root
        self._project_path_var.set(str(new_root))
        # Clear queue when switching projects
        _FILES_TXT.write_text("", encoding="utf-8")
        self._initialize_env_silent()
        self._log_write(f"Root → {new_root}", tag="info")
        self._refresh_all()

    def _on_path_submit(self, _event: object) -> None:
        raw = self._project_path_var.get().strip()
        if not raw:
            self._log_write("Path field is empty.", tag="warn")
            return
        candidate = Path(raw).expanduser()
        try:
            candidate = candidate.resolve()
        except Exception:
            pass
        if not candidate.is_dir():
            self._log_write(f"Not a directory: {raw}", tag="error")
            return
        self._change_root(candidate)

    def _open_root(self) -> None:
        chosen = filedialog.askdirectory(
            title="Select Project Root",
            initialdir=str(self._project_root),
        )
        if chosen:
            self._change_root(Path(chosen).resolve())

    # ─────────────────────────────────────────────────────────────────────────
    # Tree (left panel)
    # ─────────────────────────────────────────────────────────────────────────

    def _refresh_tree(self) -> None:
        """Rebuild the file-system tree from the current project root."""
        self._tree.delete(*self._tree.get_children())
        root = self._project_root
        patterns = load_ignore_patterns(root)
        queued_resolved = {p.resolve() for p, _r, _i in self._current_queue_entries()}
        filter_text = self._search_var.get().strip().lower()

        self._tree_title.configure(text=f"📁  {root}")
        self._populate_tree("", root, root, patterns, queued_resolved, filter_text)
        self._log_write(f"Tree loaded: {root}", tag="info")

    def _populate_tree(
        self,
        parent_iid: str,
        dir_path: Path,
        root: Path,
        patterns: frozenset[str],
        queued: set[Path],
        filter_text: str,
        depth: int = 0,
    ) -> None:
        """Recursively insert directory contents into the Treeview widget."""
        if depth > 8:
            return
        try:
            items = sorted(
                dir_path.iterdir(),
                key=lambda p: (not p.is_dir(), p.name.lower()),
            )
        except PermissionError:
            return

        for item in items:
            if should_ignore(item, root, patterns):
                continue

            # Apply search filter to file names (directories always shown)
            if filter_text and item.is_file():
                if filter_text not in item.name.lower():
                    continue

            if item.is_dir() and not item.is_symlink():
                iid = self._tree.insert(
                    parent_iid, "end",
                    text=f"📁  {item.name}",
                    open=False,
                    values=[str(item)],
                )
                self._populate_tree(
                    iid, item, root, patterns, queued, filter_text, depth + 1
                )
            elif item.is_file():
                in_queue = item.resolve() in queued
                marker = "✔  " if in_queue else "    "
                self._tree.insert(
                    parent_iid, "end",
                    text=f"{marker}{item.name}",
                    values=[str(item)],
                )

    # ─────────────────────────────────────────────────────────────────────────
    # Queue management  (files.txt read / write in full-entry format)
    # ─────────────────────────────────────────────────────────────────────────

    def _current_queue_entries(self) -> list:
        """Read files.txt and return the parsed entry list (may be empty)."""
        if not _FILES_TXT.is_file():
            return []
        try:
            return read_file_entries(_FILES_TXT)
        except Exception:
            return []

    def _write_queue_lines(self, lines: list[str]) -> None:
        """Overwrite files.txt with *lines* (one entry per line)."""
        content = "\n".join(lines) + ("\n" if lines else "")
        _FILES_TXT.write_text(content, encoding="utf-8")

    def _refresh_queue(self) -> None:
        """Repopulate the queue Listbox from files.txt."""
        self._queue_listbox.delete(0, "end")

        if not _FILES_TXT.is_file():
            self._queue_title.configure(text="📋  Queue  (0 entries)")
            return

        # Read raw lines so the display preserves the exact syntax
        # (snippet ranges, ! prefix) without re-serialising through Path
        raw_lines = [
            l.strip()
            for l in _FILES_TXT.read_text(encoding="utf-8").splitlines()
            if l.strip() and not l.strip().startswith("#")
        ]

        for line in raw_lines:
            self._queue_listbox.insert("end", line)

        # Colour code by type
        for idx, line in enumerate(raw_lines):
            if line.startswith("!"):
                self._queue_listbox.itemconfigure(idx, foreground=_MAUVE)
            elif re.search(r":\d+-\d+", line):
                self._queue_listbox.itemconfigure(idx, foreground=_TEAL)
            else:
                self._queue_listbox.itemconfigure(idx, foreground=_FG)

        self._queue_title.configure(
            text=f"📋  Queue  ({len(raw_lines)} {'entry' if len(raw_lines) == 1 else 'entries'})"
        )

    def _add_selected(self) -> None:
        """Add tree-selected files to files.txt as full-file entries."""
        selection = self._tree.selection()
        if not selection:
            self._log_write("No items selected in the tree.", tag="warn")
            return

        # Read existing raw lines to avoid duplicates while preserving order
        existing_lines: list[str] = []
        if _FILES_TXT.is_file():
            existing_lines = [
                l.strip()
                for l in _FILES_TXT.read_text(encoding="utf-8").splitlines()
                if l.strip() and not l.strip().startswith("#")
            ]

        # Build a set of already-queued absolute paths (ignoring range suffixes)
        def _bare_path(line: str) -> str:
            line = line.lstrip("!")
            # Strip range suffix  (e.g. "file.py:10-20" → "file.py")
            if re.search(r":\d+-\d+", line):
                line = line.rsplit(":", 1)[0]
            return line

        existing_bare = {_bare_path(l) for l in existing_lines}

        added = 0
        new_lines = list(existing_lines)

        for iid in selection:
            values = self._tree.item(iid, "values")
            if not values:
                continue
            item = Path(values[0])
            if not item.is_file():
                continue
            abs_str = str(item.resolve())
            if abs_str not in existing_bare:
                new_lines.append(abs_str)
                added += 1

        self._write_queue_lines(new_lines)

        tag = "ok" if added else "warn"
        msg = f"Added {added} file(s) to queue." if added else "All selected files already in queue."
        self._log_write(msg, tag=tag)
        self._refresh_all()

    def _remove_selected(self) -> None:
        """Remove highlighted entries from the queue Listbox (and files.txt)."""
        indices = list(self._queue_listbox.curselection())
        if not indices:
            self._log_write("No entries selected in the queue.", tag="warn")
            return

        existing_lines = [
            l.strip()
            for l in _FILES_TXT.read_text(encoding="utf-8").splitlines()
            if l.strip() and not l.strip().startswith("#")
        ]
        indices_set = set(indices)
        new_lines = [l for i, l in enumerate(existing_lines) if i not in indices_set]

        self._write_queue_lines(new_lines)
        self._log_write(f"Removed {len(indices)} entry/entries from queue.", tag="warn")
        self._refresh_all()

    def _clear_queue(self) -> None:
        if not messagebox.askyesno("Confirm", "Clear all entries from the queue?"):
            return
        _FILES_TXT.write_text("", encoding="utf-8")
        self._log_write("Queue cleared.", tag="warn")
        self._refresh_all()

    # ─────────────────────────────────────────────────────────────────────────
    # Refresh helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _refresh_all(self) -> None:
        self._refresh_tree()
        self._refresh_queue()
        # Refresh API key status in case env changed
        self._api_key_label.configure(text=self._api_key_status_text())

    # ─────────────────────────────────────────────────────────────────────────
    # Aggregation pipeline  (runs entirely in a background thread)
    # ─────────────────────────────────────────────────────────────────────────

    def _run_aggregate(self) -> None:
        """Guard against double-clicks then launch the worker thread."""
        if self._busy:
            self._log_write("Already running — please wait.", tag="warn")
            return
        self._busy = True
        self._progress.pack(side="right", padx=6, pady=10)
        self._progress.start(12)
        threading.Thread(target=self._aggregate_worker, daemon=True).start()

    def _aggregate_worker(self) -> None:
        """Full aggregation pipeline executed on a background thread.

        Steps
        -----
        1.  Read & validate entries from files.txt.
        2.  Detect project root + load ignore patterns.
        3.  Write structure.txt (directory tree).
        4.  Write arena.txt   (aggregated content).
        5.  Count tokens and report.
        6.  Collect model responses from models/.
        7.  Optionally call Gemini AI Judge.
        8.  Write compare.md.
        """
        try:
            # ── Step 1: read entries ──────────────────────────────────────────
            self._step("Reading files.txt …")
            entries = read_file_entries(_FILES_TXT)
            if not entries:
                self._log_write("Queue is empty — nothing to aggregate.", tag="warn")
                self._set_status("Empty queue.")
                return

            # Count entry types for reporting
            n_full      = sum(1 for _, r, _i in entries if r is None)
            n_snippets  = sum(1 for _, r,  i in entries if r is not None and not i)
            n_important = sum(1 for _, r,  i in entries if r is not None and i)

            summary_parts = []
            if n_full:      summary_parts.append(f"{n_full} file(s)")
            if n_snippets:  summary_parts.append(f"{n_snippets} snippet(s)")
            if n_important: summary_parts.append(f"{n_important} structure(s)")
            self._log_write(f"Queue: {' + '.join(summary_parts)}", tag="info")

            # ── Step 2: detect root ───────────────────────────────────────────
            self._step("Detecting project root …")
            root = find_project_root(entries[0][0]) or self._project_root
            patterns = load_ignore_patterns(root)
            self._log_write(f"Root: {root}", tag="info")

            # ── Writable checks (fail fast) ───────────────────────────────────
            for out_path in (_ARENA_TXT, _STRUCTURE_TXT, _COMPARE_TXT):
                _assert_writable(out_path)

            # ── Step 3: project tree ──────────────────────────────────────────
            self._step("Generating project tree …")
            tree_lines = [f"Project Root: {root.name}/"] + generate_tree(
                root, root, patterns
            )
            _STRUCTURE_TXT.write_text("\n".join(tree_lines), encoding="utf-8")
            self._log_write(f"structure.txt written  ({root.name}/)", tag="ok")

            # ── Step 4: aggregate ─────────────────────────────────────────────
            self._step("Aggregating files …")
            aggregate_files(entries, _ARENA_TXT, root)
            self._log_write("arena.txt written.", tag="ok")

            # ── Step 5: token count ───────────────────────────────────────────
            self._step("Counting tokens …")
            try:
                arena_content = _ARENA_TXT.read_text(encoding="utf-8")
                token_count   = count_tokens(arena_content)
                char_count    = len(arena_content)
                # Traffic-light status
                if token_count >= 128_000:
                    tok_tag = "error"
                    tok_icon = "🔴"
                elif token_count >= 80_000:
                    tok_tag = "warn"
                    tok_icon = "🟡"
                else:
                    tok_tag = "ok"
                    tok_icon = "🟢"
                self._log_write(
                    f"{tok_icon}  {char_count:,} chars | ~{token_count:,} tokens",
                    tag=tok_tag,
                )
                self._set_status(f"~{token_count:,} tokens")
            except Exception as exc:
                self._log_write(f"Token count warning: {exc}", tag="warn")
                token_count = None

            # ── Step 6: collect model responses ──────────────────────────────
            self._step("Checking models/ directory …")
            prompt, models_data = collect_model_responses(root)

            if not models_data:
                # No model files → write blank template and stop
                generate_compare_template(_COMPARE_TXT)
                self._log_write(
                    "No model responses found — blank compare.md template written.",
                    tag="warn",
                )
                self._set_status("Done (no models).")
                return

            self._log_write(
                f"Found {len(models_data)} model response(s) in models/", tag="ok"
            )

            # ── Step 7: Gemini AI Judge (optional) ───────────────────────────
            verdict: Optional[str] = None
            if self._judge_var.get():
                self._step("Running Gemini AI Judge …")
                api_key = self._resolve_api_key_for_thread(root)

                if api_key:
                    try:
                        verdict = get_gemini_verdict(prompt, models_data, api_key)
                        self._log_write("Gemini verdict received ✓", tag="judge")
                    except Exception as exc:
                        self._log_write(
                            f"Gemini API error: {exc}  (falling back to manual template)",
                            tag="error",
                        )
                else:
                    self._log_write("No API key — skipping Gemini Judge.", tag="warn")
            else:
                self._log_write("Gemini Judge disabled by user.", tag="info")

            # ── Step 8: write compare.md ──────────────────────────────────────
            self._step("Writing compare.md …")
            compact = self._compact_var.get()
            build_compare_markdown(
                prompt, models_data, _COMPARE_TXT,
                verdict=verdict, compact=compact,
            )
            src       = "models/" if (root / "models").is_dir() else "llm.txt"
            mode_str  = " [COMPACT]" if compact else ""
            judge_str = " + Gemini Judge" if verdict else ""
            self._log_write(
                f"compare.md written from {src}  ({len(models_data)} models){mode_str}{judge_str}",
                tag="ok",
            )

            # ── Final status ──────────────────────────────────────────────────
            final = f"Done — {len(entries)} entries"
            if token_count is not None:
                final += f", ~{token_count:,} tokens"
            self._set_status(final)
            self._log_write("─" * 48, tag="info")
            self._log_write("Aggregation complete ✓", tag="ok")

        except FileNotFoundError as exc:
            self._log_write(f"File not found: {exc}", tag="error")
            self._set_status("Error — see log.")
        except OSError as exc:
            self._log_write(f"OS error: {exc}", tag="error")
            self._set_status("Error — see log.")
        except Exception as exc:
            self._log_write(f"Unexpected error: {exc}", tag="error")
            self._set_status("Error — see log.")
        finally:
            # Always stop the spinner and release the busy lock
            self.after(0, self._stop_progress)
            self._busy = False

    def _resolve_api_key_for_thread(self, root: Path) -> Optional[str]:
        """Retrieve the API key without blocking the background thread.

        If the key is already in the environment we return it immediately.
        Otherwise we schedule a GUI dialog on the main thread and block
        until the user responds (using a threading.Event).
        """
        # Try env / .env files first (no dialog needed)
        load_dotenv(root)
        load_dotenv(_PROJECT_DIR)
        load_dotenv(Path.cwd())
        key = os.environ.get("GEMINI_API_KEY", "").strip()
        if key:
            return key

        # Need to ask the user — must run on main thread
        result_holder: list[Optional[str]] = [None]
        ready = threading.Event()

        def _show_dialog() -> None:
            dlg = _ApiKeyDialog(self)
            if dlg.result:
                os.environ["GEMINI_API_KEY"] = dlg.result
                if dlg.save_to_env:
                    self._save_api_key_to_env(dlg.result)
                result_holder[0] = dlg.result
            ready.set()

        self.after(0, _show_dialog)
        ready.wait(timeout=120)   # wait up to 2 min for user input
        return result_holder[0]

    # ─────────────────────────────────────────────────────────────────────────
    # Thread-safe UI helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _log_write(self, message: str, tag: str = "") -> None:
        """Append a coloured log line — safe to call from any thread."""
        def _insert() -> None:
            self._log.configure(state="normal")
            self._log.insert("end", f"›  {message}\n", tag or "")
            self._log.see("end")
            self._log.configure(state="disabled")
        self.after(0, _insert)

    def _step(self, message: str) -> None:
        """Log a pipeline step with the 'step' colour and update status bar."""
        self._log_write(message, tag="step")
        self._set_status(message)

    def _set_status(self, text: str) -> None:
        self.after(0, lambda: self._status_var.set(text))

    def _stop_progress(self) -> None:
        self._progress.stop()
        self._progress.pack_forget()


# ─────────────────────────────────────────────────────────────────────────────
# Missing import needed by _refresh_queue colour logic
# ─────────────────────────────────────────────────────────────────────────────
import re   # noqa: E402  (already in core.parser but needed directly here)


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    app = AggregatorGUI()
    app.mainloop()


if __name__ == "__main__":
    main()
