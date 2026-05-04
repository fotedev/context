"""Lightweight Tkinter GUI for the File Aggregator.

Launch via:  aggg
No third-party dependencies required.
"""

from __future__ import annotations

import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, font, messagebox, scrolledtext, ttk
from typing import Optional

# Resolve project directory and import core engine
_PROJECT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_PROJECT_DIR))

from aggregator import (  # noqa: E402
    aggregate_files,
    find_project_root,
    generate_tree,
    load_ignore_patterns,
    read_file_paths,
    should_ignore,
)

_FILES_TXT = _PROJECT_DIR / "files.txt"
_ARENA_TXT = _PROJECT_DIR / "arena.txt"
_STRUCTURE_TXT = _PROJECT_DIR / "structure.txt"

# Catppuccin-inspired Dark Theme
_BG = "#1e1e2e"
_BG_PANEL = "#181825"
_BG_ENTRY = "#313244"
_FG = "#cdd6f4"
_FG_DIM = "#6c7086"
_ACCENT = "#89b4fa"
_SUCCESS = "#a6e3a1"
_WARNING = "#fab387"
_ERROR = "#f38ba8"
_BTN_PRIMARY = "#89b4fa"
_BTN_TEXT = "#1e1e2e"


class AggregatorGUI(tk.Tk):
    """Tkinter GUI providing project browsing, queue management, and aggregation."""

    def __init__(self) -> None:
        super().__init__()
        self.title("File Aggregator")
        self.geometry("1000x700")
        self.minsize(800, 500)
        self.configure(bg=_BG)

        self._project_root: Path = self._detect_root()
        self._setup_fonts()
        self._build_ui()
        self._refresh_all()

    def _detect_root(self) -> Path:
        """Return project root inferred from files.txt or current directory."""
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

    def _setup_fonts(self) -> None:
        self._font_ui = font.Font(family="Segoe UI", size=10)
        self._font_mono = font.Font(family="Consolas", size=9)
        self._font_title = font.Font(family="Segoe UI", size=11, weight="bold")

    def _build_ui(self) -> None:
        """Build the overall application layout."""
        self._build_header()
        self._build_body()
        self._build_statusbar()

    def _build_header(self) -> None:
        bar = tk.Frame(self, bg=_ACCENT, height=40)
        bar.pack(fill="x", side="top")
        bar.pack_propagate(False)

        tk.Label(
            bar,
            text="⚙  File Aggregator",
            bg=_ACCENT,
            fg=_BTN_TEXT,
            font=self._font_title,
        ).pack(side="left", padx=15, pady=8)

    def _build_body(self) -> None:
        body = tk.PanedWindow(self, orient="horizontal", bg=_BG, sashwidth=4)
        body.pack(fill="both", expand=True, padx=10, pady=10)

        # Left: Project Tree
        left = tk.Frame(body, bg=_BG_PANEL)
        body.add(left, minsize=300)

        self._tree_title = tk.Label(
            left,
            text=f"📁 Project: {self._project_root.name}",
            bg=_BG_PANEL,
            fg=_ACCENT,
            font=self._font_title,
            anchor="w",
        )
        self._tree_title.pack(fill="x", padx=10, pady=(10, 5))

        tree_frame = tk.Frame(left, bg=_BG_PANEL)
        tree_frame.pack(fill="both", expand=True, padx=5, pady=5)

        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            "Custom.Treeview",
            background=_BG_ENTRY,
            fieldbackground=_BG_ENTRY,
            foreground=_FG,
            rowheight=24,
            font=self._font_mono,
            borderwidth=0,
        )
        style.map(
            "Custom.Treeview",
            background=[("selected", _ACCENT)],
            foreground=[("selected", _BTN_TEXT)],
        )

        self._tree = ttk.Treeview(
            tree_frame,
            style="Custom.Treeview",
            selectmode="extended",
            show="tree",
        )
        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self._tree.yview)
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal", command=self._tree.xview)
        self._tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        vsb.pack(side="right", fill="y")
        hsb.pack(side="bottom", fill="x")
        self._tree.pack(fill="both", expand=True)

        tk.Button(
            left,
            text="＋ Add Selected to Queue",
            command=self._add_selected,
            bg=_BTN_PRIMARY,
            fg=_BTN_TEXT,
            relief="flat",
            font=self._font_ui,
            cursor="hand2",
            pady=5,
        ).pack(fill="x", padx=10, pady=10)

        # Right: Queue and Log
        right = tk.Frame(body, bg=_BG)
        body.add(right, minsize=400)

        paned_v = tk.PanedWindow(right, orient="vertical", bg=_BG, sashwidth=4)
        paned_v.pack(fill="both", expand=True)

        # Queue panel
        queue_frame = tk.Frame(paned_v, bg=_BG_PANEL)
        paned_v.add(queue_frame, minsize=200)

        self._queue_title = tk.Label(
            queue_frame,
            text="📋  Queue  (0 files)",
            bg=_BG_PANEL,
            fg=_ACCENT,
            font=self._font_title,
            anchor="w",
        )
        self._queue_title.pack(fill="x", padx=10, pady=(10, 5))

        self._queue_listbox = tk.Listbox(
            queue_frame,
            bg=_BG_ENTRY,
            fg=_FG,
            selectbackground=_ACCENT,
            selectforeground=_BTN_TEXT,
            font=self._font_mono,
            relief="flat",
            borderwidth=0,
            activestyle="none",
            highlightthickness=0,
        )
        q_vsb = ttk.Scrollbar(
            queue_frame, orient="vertical", command=self._queue_listbox.yview
        )
        self._queue_listbox.configure(yscrollcommand=q_vsb.set)
        q_vsb.pack(side="right", fill="y")
        self._queue_listbox.pack(fill="both", expand=True, padx=5, pady=5)

        tk.Button(
            queue_frame,
            text="－ Remove Selected from Queue",
            command=self._remove_selected,
            bg=_WARNING,
            fg=_BTN_TEXT,
            relief="flat",
            font=self._font_ui,
            cursor="hand2",
            pady=5,
        ).pack(fill="x", padx=10, pady=10)

        # Log panel
        log_frame = tk.Frame(paned_v, bg=_BG_PANEL)
        paned_v.add(log_frame, minsize=150)

        tk.Label(
            log_frame,
            text="📜 Activity Log",
            bg=_BG_PANEL,
            fg=_ACCENT,
            font=self._font_title,
            anchor="w",
        ).pack(fill="x", padx=10, pady=(10, 5))

        self._log = scrolledtext.ScrolledText(
            log_frame,
            bg=_BG_ENTRY,
            fg=_FG,
            font=self._font_mono,
            relief="flat",
            borderwidth=0,
            state="disabled",
            wrap="word",
        )
        self._log.pack(fill="both", expand=True, padx=5, pady=5)

        self._log.tag_config("ok", foreground=_SUCCESS)
        self._log.tag_config("warn", foreground=_WARNING)
        self._log.tag_config("error", foreground=_ERROR)
        self._log.tag_config("info", foreground=_FG_DIM)

    def _build_statusbar(self) -> None:
        bar = tk.Frame(self, bg=_BG_PANEL, height=45)
        bar.pack(fill="x", side="bottom")
        bar.pack_propagate(False)

        btns = [
            ("⟳  Refresh All", self._refresh_all, _BTN_PRIMARY),
            ("▶  Run Aggregate", self._run_aggregate, _SUCCESS),
            ("✕  Clear Queue", self._clear_queue, _WARNING),
            ("📂 Open Root", self._open_root, _FG_DIM),
        ]
        for label, cmd, colour in btns:
            tk.Button(
                bar,
                text=label,
                command=cmd,
                bg=colour,
                fg=_BTN_TEXT,
                relief="flat",
                font=self._font_ui,
                cursor="hand2",
                padx=15,
            ).pack(side="left", padx=5, pady=6)

        self._status_var = tk.StringVar(value="Ready.")
        tk.Label(
            bar,
            textvariable=self._status_var,
            bg=_BG_PANEL,
            fg=_FG_DIM,
            font=self._font_ui,
            anchor="e",
        ).pack(side="right", padx=15)

    def _refresh_all(self) -> None:
        """Refresh tree and queue lists."""
        self._refresh_tree()
        self._refresh_queue()

    def _refresh_tree(self) -> None:
        self._tree.delete(*self._tree.get_children())
        root = self._project_root
        patterns = load_ignore_patterns(root)
        queued_paths = self._current_queue_paths()

        self._tree_title.configure(text=f"📁 Project: {root}")
        self._populate_tree("", root, root, patterns, queued_paths)
        self._log_write(f"Tree loaded from: {root}", tag="info")

    def _populate_tree(
        self,
        parent_iid: str,
        dir_path: Path,
        root: Path,
        patterns: frozenset[str],
        queued: set[Path],
        depth: int = 0,
    ) -> None:
        if depth > 8:
            return

        try:
            items = sorted(
                dir_path.iterdir(),
                key=lambda p: (not p.is_dir(), p.name.lower()),
            )
        except PermissionError:
            return

        queued_resolved = {p.resolve() for p in queued}

        for item in items:
            if should_ignore(item, root, patterns):
                continue

            if item.is_dir() and not item.is_symlink():
                iid = self._tree.insert(
                    parent_iid,
                    "end",
                    text=f"📁 {item.name}",
                    open=False,
                    values=[str(item)],
                )
                self._populate_tree(iid, item, root, patterns, queued, depth + 1)
            elif item.is_file():
                marker = "✔ " if item.resolve() in queued_resolved else "  "
                self._tree.insert(
                    parent_iid, "end", text=f"{marker}{item.name}", values=[str(item)]
                )

    def _current_queue_paths(self) -> set[Path]:
        if not _FILES_TXT.is_file():
            return set()
        try:
            return set(read_file_paths(_FILES_TXT))
        except Exception:
            return set()

    def _refresh_queue(self) -> None:
        self._queue_listbox.delete(0, "end")
        paths = sorted(self._current_queue_paths(), key=lambda p: str(p))
        for path in paths:
            self._queue_listbox.insert("end", str(path))
        self._queue_title.configure(text=f"📋  Queue  ({len(paths)} files)")

    def _write_queue(self, paths: set[Path]) -> None:
        """Save path set to files.txt."""
        ordered = sorted({p.resolve() for p in paths}, key=lambda p: str(p))
        _FILES_TXT.write_text(
            "\n".join(str(p) for p in ordered) + ("\n" if ordered else ""),
            encoding="utf-8",
        )

    def _add_selected(self) -> None:
        selection = self._tree.selection()
        if not selection:
            self._log_write("No items selected in tree.", tag="warn")
            return

        current = self._current_queue_paths()
        added = 0
        current_resolved = {p.resolve() for p in current}

        for iid in selection:
            values = self._tree.item(iid, "values")
            if not values:
                continue
            path = Path(values[0])
            if path.is_file() and path.resolve() not in current_resolved:
                current.add(path.resolve())
                added += 1

        self._write_queue(current)
        self._log_write(f"Added {added} file(s) to queue.", tag="ok")
        self._refresh_all()

    def _remove_selected(self) -> None:
        indices = self._queue_listbox.curselection()
        if not indices:
            self._log_write("No items selected in queue.", tag="warn")
            return

        current = {p.resolve() for p in self._current_queue_paths()}
        to_remove = {Path(self._queue_listbox.get(i)).resolve() for i in indices}
        current -= to_remove

        self._write_queue(current)
        self._log_write(f"Removed {len(to_remove)} file(s) from queue.", tag="warn")
        self._refresh_all()

    def _clear_queue(self) -> None:
        if not messagebox.askyesno(
            "Confirm Clear", "Clear all files from the queue?"
        ):
            return
        _FILES_TXT.write_text("", encoding="utf-8")
        self._log_write("Queue cleared.", tag="warn")
        self._refresh_all()

    def _open_root(self) -> None:
        chosen = filedialog.askdirectory(title="Select Project Root")
        if not chosen:
            return
        self._project_root = Path(chosen).resolve()
        _FILES_TXT.write_text("", encoding="utf-8")
        self._log_write(f"Root changed to: {self._project_root}", tag="info")
        self._refresh_all()

    def _run_aggregate(self) -> None:
        threading.Thread(target=self._aggregate_worker, daemon=True).start()

    def _aggregate_worker(self) -> None:
        self._set_status("Aggregating…")
        self._log_write("Starting aggregation…", tag="info")

        try:
            paths = read_file_paths(_FILES_TXT)
            if not paths:
                self._log_write("Nothing to aggregate (queue empty).", tag="warn")
                self._set_status("Empty queue.")
                return

            root = find_project_root(paths[0]) or self._project_root
            patterns = load_ignore_patterns(root)

            # Generate tree
            tree_lines = [f"Project Root: {root.name}/"] + generate_tree(
                root, root, patterns
            )
            _STRUCTURE_TXT.write_text("\n".join(tree_lines), encoding="utf-8")
            self._log_write(f"structure.txt written ({root.name})", tag="ok")

            # Aggregate
            aggregate_files(paths, _ARENA_TXT, root)
            self._log_write(f"arena.txt written ({len(paths)} file(s)).", tag="ok")
            self._set_status(f"Done - {len(paths)} files.")

        except Exception as exc:
            self._log_write(f"Error: {exc}", tag="error")
            self._set_status("Error.")

    def _log_write(self, message: str, tag: str = "") -> None:
        def _insert() -> None:
            self._log.configure(state="normal")
            self._log.insert("end", f"› {message}\n", tag or "")
            self._log.see("end")
            self._log.configure(state="disabled")

        self.after(0, _insert)

    def _set_status(self, text: str) -> None:
        self.after(0, lambda: self._status_var.set(text))


def main() -> None:
    app = AggregatorGUI()
    app.mainloop()


if __name__ == "__main__":
    main()
