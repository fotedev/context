"""Tkinter widget builders.

One focused function per UI region (header, left panel, queue pane,
options pane, log pane, statusbar). Each builder takes the parent
widget and any state needed to wire callbacks, and returns the new
container.

Builders are pure construction — they don't subscribe to settings
changes, don't carry state, and don't run a scheduler. The
:class:`gui.app.AggregatorGUI` coordinator owns state and binds
callbacks when assembling the window.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import scrolledtext, ttk
from typing import Callable

from gui.log_panel import LogPanel
from gui.theme import (
    _ACCENT,
    _BG,
    _BG_ENTRY,
    _BG_PANEL,
    _BTN_TEXT,
    _FG,
    _FG_DIM,
    _GREEN,
    _ORANGE,
    _RED,
)

# Font-key constants used by builders; kept as a tiny lookup to mirror
# the legacy behaviour. ``build_fonts`` returns a dict mapping these
# keys to Font objects.
_FONT_KEYS = {"ui": "ui", "mono": "mono", "title": "title", "small": "small"}


# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------


def build_header(master: tk.Misc, fonts) -> None:
    """Top accent-coloured header bar with title + hint."""
    bar = tk.Frame(master, bg=_ACCENT, height=42)
    bar.pack(fill="x", side="top")
    bar.pack_propagate(False)

    tk.Label(
        bar,
        text="⚙  File Aggregator",
        bg=_ACCENT, fg=_BTN_TEXT,
        font=fonts["title"],
    ).pack(side="left", padx=16, pady=10)

    tk.Label(
        bar,
        text="★ = important structure   [n-m] = snippet range",
        bg=_ACCENT, fg=_BTN_TEXT,
        font=fonts["small"],
    ).pack(side="right", padx=16)


# ---------------------------------------------------------------------------
# Body (PanedWindow hosting left + right panels)
# ---------------------------------------------------------------------------


def build_body(master: tk.Misc, *, left, right) -> None:
    """Pack a horizontal PanedWindow holding *left* and *right*."""
    body = tk.PanedWindow(
        master, orient="horizontal", bg=_BG, sashwidth=5, sashrelief="flat"
    )
    body.pack(fill="both", expand=True, padx=10, pady=(8, 0))
    body.add(left, minsize=320)
    body.add(right, minsize=440)


# ---------------------------------------------------------------------------
# Left panel — project tree + search + add button
# ---------------------------------------------------------------------------


def build_left_panel(
    master: tk.Misc,
    *,
    fonts,
    project_name: str,
    tree_holder: dict[str, object],
    search_holder: dict[str, object],
    add_command: Callable[[], None],
    search_trace_command: Callable[[], None],
) -> tk.Frame:
    """Construct the project tree pane.

    Returns the new Frame. *tree_holder* / *search_holder* are updated
    in-place with the constructed Tk widgets so the calling class can
    rebind methods to them later.
    """
    frame = tk.Frame(master, bg=_BG_PANEL)

    title = tk.Label(
        frame,
        text=f"📁  {project_name}",
        bg=_BG_PANEL, fg=_ACCENT,
        font=fonts["title"], anchor="w",
    )
    title.pack(fill="x", padx=10, pady=(10, 4))
    tree_holder["title"] = title

    # Search bar
    search_frame = tk.Frame(frame, bg=_BG_PANEL)
    search_frame.pack(fill="x", padx=8, pady=(0, 4))

    tk.Label(
        search_frame, text="🔍", bg=_BG_PANEL, fg=_FG_DIM,
        font=fonts["ui"],
    ).pack(side="left", padx=(0, 4))

    search_var = tk.StringVar()
    search_var.trace_add("write", lambda *_: search_trace_command())
    tk.Entry(
        search_frame,
        textvariable=search_var,
        bg=_BG_ENTRY, fg=_FG,
        insertbackground=_FG,
        relief="flat",
        font=fonts["mono"],
    ).pack(fill="x", expand=True, ipady=3)
    search_holder["var"] = search_var

    # Tree widget
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
        font=fonts["mono"],
        borderwidth=0,
    )
    style.map(
        "Agg.Treeview",
        background=[("selected", _ACCENT)],
        foreground=[("selected", _BTN_TEXT)],
    )

    tree = ttk.Treeview(
        tree_wrap,
        style="Agg.Treeview",
        selectmode="extended",
        show="tree",
    )
    vsb = ttk.Scrollbar(tree_wrap, orient="vertical",   command=tree.yview)
    hsb = ttk.Scrollbar(tree_wrap, orient="horizontal", command=tree.xview)
    tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
    vsb.pack(side="right",  fill="y")
    hsb.pack(side="bottom", fill="x")
    tree.pack(fill="both", expand=True)
    tree_holder["widget"] = tree

    _ = tree.bind("<Double-1>", lambda _e: add_command())

    tk.Button(
        frame,
        text="＋  Add Selected to Queue",
        command=add_command,
        bg=_ACCENT, fg=_BTN_TEXT,
        relief="flat", font=fonts["ui"], cursor="hand2", pady=6,
    ).pack(fill="x", padx=10, pady=(4, 10))

    return frame


# ---------------------------------------------------------------------------
# Right panel — queue / options / log
# ---------------------------------------------------------------------------


def build_right_panel(
    master: tk.Misc, *, queue_frame, options_frame, log_frame
) -> tk.Frame:
    """Pack a vertical PanedWindow holding the three sub-panes."""
    frame = tk.Frame(master, bg=_BG)
    paned_v = tk.PanedWindow(
        frame, orient="vertical", bg=_BG, sashwidth=5, sashrelief="flat"
    )
    paned_v.pack(fill="both", expand=True)
    paned_v.add(queue_frame, minsize=160)
    paned_v.add(options_frame, minsize=140)
    paned_v.add(log_frame, minsize=140)
    return frame


def build_queue_pane(
    master: tk.Misc,
    *,
    fonts,
    queue_holder: dict[str, object],
    remove_command: Callable[[], None],
) -> tk.Frame:
    """Build the queue listbox pane."""
    frame = tk.Frame(master, bg=_BG_PANEL)

    title = tk.Label(
        frame,
        text="📋  Queue  (0 entries)",
        bg=_BG_PANEL, fg=_ACCENT,
        font=fonts["title"], anchor="w",
    )
    title.pack(fill="x", padx=10, pady=(10, 4))
    queue_holder["title"] = title

    list_wrap = tk.Frame(frame, bg=_BG_PANEL)
    list_wrap.pack(fill="both", expand=True, padx=5, pady=4)

    listbox = tk.Listbox(
        list_wrap,
        bg=_BG_ENTRY, fg=_FG,
        selectbackground=_ACCENT, selectforeground=_BTN_TEXT,
        font=fonts["mono"],
        relief="flat", borderwidth=0,
        activestyle="none", highlightthickness=0,
    )
    q_vsb = ttk.Scrollbar(list_wrap, orient="vertical",   command=listbox.yview)
    q_hsb = ttk.Scrollbar(list_wrap, orient="horizontal", command=listbox.xview)
    listbox.configure(yscrollcommand=q_vsb.set, xscrollcommand=q_hsb.set)
    q_vsb.pack(side="right",  fill="y")
    q_hsb.pack(side="bottom", fill="x")
    listbox.pack(fill="both", expand=True)
    queue_holder["listbox"] = listbox
    queue_holder["colours"] = {}

    tk.Button(
        frame,
        text="－  Remove Selected",
        command=remove_command,
        bg=_ORANGE, fg=_BTN_TEXT,
        relief="flat", font=fonts["ui"], cursor="hand2", pady=5,
    ).pack(fill="x", padx=10, pady=(4, 10))

    return frame


def build_options_pane(
    master: tk.Misc,
    *,
    fonts,
    judge_var: tk.BooleanVar,
    compact_var: tk.BooleanVar,
    archive_var: tk.BooleanVar,
    output_dir_var: tk.StringVar,
    model_count_var: tk.IntVar,
    output_format_var: tk.StringVar,
    api_key_holder: dict[str, object],
    prompt_api_key_command: Callable[[], None],
    on_output_dir_focusout: Callable[[object], None],
    api_key_status_provider: Callable[[], str],
) -> tk.Frame:
    """Build the options pane (Gemini Judge / Compact / Archive / etc)."""
    frame = tk.Frame(master, bg=_BG_PANEL)

    tk.Label(
        frame,
        text="⚙  Aggregation Options",
        bg=_BG_PANEL, fg=_ACCENT,
        font=fonts["title"], anchor="w",
    ).pack(fill="x", padx=10, pady=(6, 4))

    # Row 1: checkboxes
    row1 = tk.Frame(frame, bg=_BG_PANEL)
    row1.pack(fill="x", padx=12, pady=2)

    tk.Checkbutton(
        row1, text="🤖  Run Gemini Judge", variable=judge_var,
        bg=_BG_PANEL, fg=_FG,
        selectcolor=_BG_ENTRY,
        activebackground=_BG_PANEL, activeforeground=_FG,
        font=fonts["ui"],
    ).pack(side="left", padx=(0, 16))

    tk.Checkbutton(
        row1, text="📦  Compact mode", variable=compact_var,
        bg=_BG_PANEL, fg=_FG,
        selectcolor=_BG_ENTRY,
        activebackground=_BG_PANEL, activeforeground=_FG,
        font=fonts["ui"],
    ).pack(side="left", padx=(0, 16))

    tk.Checkbutton(
        row1, text="🗄️  Archive on run", variable=archive_var,
        bg=_BG_PANEL, fg=_FG,
        selectcolor=_BG_ENTRY,
        activebackground=_BG_PANEL, activeforeground=_FG,
        font=fonts["ui"],
    ).pack(side="left")

    # Row 2: entry / combobox
    row2 = tk.Frame(frame, bg=_BG_PANEL)
    row2.pack(fill="x", padx=12, pady=4)

    tk.Label(row2, text="Output Dir:", bg=_BG_PANEL, fg=_FG_DIM, font=fonts["ui"]).pack(
        side="left", padx=(0, 4)
    )

    out_dir_entry = tk.Entry(
        row2,
        textvariable=output_dir_var,
        bg=_BG_ENTRY, fg=_FG,
        insertbackground=_FG, relief="flat",
        font=fonts["mono"], width=16,
    )
    out_dir_entry.pack(side="left", padx=(0, 16))
    _ = out_dir_entry.bind("<FocusOut>", on_output_dir_focusout)
    _ = out_dir_entry.bind("<Return>", on_output_dir_focusout)

    tk.Label(row2, text="Models:", bg=_BG_PANEL, fg=_FG_DIM, font=fonts["ui"]).pack(
        side="left", padx=(0, 4)
    )

    ttk.Combobox(
        row2, textvariable=model_count_var,
        values=["2", "4"], state="readonly", width=3,
    ).pack(side="left", padx=(0, 16))

    tk.Label(row2, text="Format:", bg=_BG_PANEL, fg=_FG_DIM, font=fonts["ui"]).pack(
        side="left", padx=(0, 4)
    )

    ttk.Combobox(
        row2, textvariable=output_format_var,
        values=["md", "txt"], state="readonly", width=4,
    ).pack(side="left", padx=(0, 16))

    # Row 3: API key
    row3 = tk.Frame(frame, bg=_BG_PANEL)
    row3.pack(fill="x", padx=12, pady=(2, 6))

    api_key_label = tk.Label(
        row3,
        text=api_key_status_provider(),
        bg=_BG_PANEL, fg=_FG_DIM,
        font=fonts["small"], anchor="w",
    )
    api_key_label.pack(side="left", fill="x", expand=True)
    api_key_holder["label"] = api_key_label

    tk.Button(
        row3,
        text="🔑  Set / Update API Key",
        command=prompt_api_key_command,
        bg=_BG_ENTRY, fg=_FG,
        relief="flat", font=fonts["small"], cursor="hand2",
        padx=8, pady=1,
    ).pack(side="right")

    return frame


def build_log_pane(
    master: tk.Misc, *, fonts, log_panel: LogPanel
) -> tk.Frame:
    """Build the read-only coloured log pane and wire it to *log_panel*."""
    frame = tk.Frame(master, bg=_BG_PANEL)

    tk.Label(
        frame,
        text="📜  Activity Log",
        bg=_BG_PANEL, fg=_ACCENT,
        font=fonts["title"], anchor="w",
    ).pack(fill="x", padx=10, pady=(10, 4))

    log_widget = scrolledtext.ScrolledText(
        frame,
        bg=_BG_ENTRY, fg=_FG,
        font=fonts["mono"],
        relief="flat", borderwidth=0,
        state="disabled", wrap="word",
    )
    log_widget.pack(fill="both", expand=True, padx=5, pady=5)
    log_panel.attach_log_widget(log_widget)
    return frame


# ---------------------------------------------------------------------------
# Statusbar
# ---------------------------------------------------------------------------


def build_statusbar(
    master: tk.Misc,
    *,
    fonts,
    project_root_str: str,
    status_holder: dict[str, object],
    on_path_submit: Callable[[object], None],
    open_root_command: Callable[[], None],
    clear_queue_command: Callable[[], None],
    run_command: Callable[[], None],
    refresh_command: Callable[[], None],
    cancel_command: Callable[[], None],
) -> None:
    """Build the status bar; returns widgets via *status_holder*."""
    bar = tk.Frame(master, bg=_BG_PANEL, height=52)
    bar.pack(fill="x", side="bottom")
    bar.pack_propagate(False)

    tk.Label(
        bar, text="Root:", bg=_BG_PANEL, fg=_FG_DIM, font=fonts["ui"],
    ).pack(side="left", padx=(10, 4))

    project_path_var = tk.StringVar(value=project_root_str)
    project_path_entry = tk.Entry(
        bar,
        textvariable=project_path_var,
        bg=_BG_ENTRY, fg=_FG,
        insertbackground=_FG, relief="flat",
        font=fonts["mono"], width=50,
    )
    project_path_entry.pack(side="left", padx=(0, 6), pady=8, ipady=3)
    _ = project_path_entry.bind("<Return>", on_path_submit)
    status_holder["project_path_var"] = project_path_var
    status_holder["project_path_entry"] = project_path_entry

    tk.Button(
        bar, text="Apply",
        command=lambda: on_path_submit(None),
        bg=_ACCENT, fg=_BTN_TEXT,
        relief="flat", font=fonts["ui"], cursor="hand2", padx=10,
    ).pack(side="left", padx=(0, 6), pady=8)

    action_btns = [
        ("📂  Open Root",      open_root_command,      _FG_DIM),
        ("✕  Clear Queue",    clear_queue_command,    _ORANGE),
        ("▶  Run Aggregate",  run_command,            _GREEN),
        ("⟳  Refresh",        refresh_command,        _ACCENT),
    ]
    for label, cmd, colour in action_btns:
        tk.Button(
            bar, text=label, command=cmd,
            bg=colour, fg=_BTN_TEXT,
            relief="flat", font=fonts["ui"], cursor="hand2", padx=14,
        ).pack(side="right", padx=5, pady=8)

    cancel_btn = tk.Button(
        bar, text="⏹  Cancel", command=cancel_command,
        bg=_RED, fg=_BTN_TEXT,
        relief="flat", font=fonts["ui"], cursor="hand2", padx=14,
    )
    status_holder["cancel_btn"] = cancel_btn

    progress = ttk.Progressbar(bar, mode="indeterminate", length=120)
    status_holder["progress"] = progress

    status_var = tk.StringVar(value="Ready.")
    status_lbl = tk.Label(
        bar, textvariable=status_var,
        bg=_BG_PANEL, fg=_FG_DIM, font=fonts["ui"], anchor="e",
    )
    status_lbl.pack(side="right", padx=10)
    status_holder["status_var"] = status_var


__all__ = [
    "build_header",
    "build_body",
    "build_left_panel",
    "build_right_panel",
    "build_queue_pane",
    "build_options_pane",
    "build_log_pane",
    "build_statusbar",
]
