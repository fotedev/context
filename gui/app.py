# ruff: noqa: E402 — core imports after sys.path manipulation
"""``AggregatorGUI`` Tk root class — thin coordinator.

Owns the live Tk state (widget handles, settings Tk-vars, busy flag)
and dispatches every action to one of the focused modules
(:mod:`gui.scanner`, :mod:`gui.queue_manager`, :mod:`gui.aggregation_runner`,
:mod:`gui.builders`, :mod:`gui.log_panel`, :mod:`gui.api_key_dialog`).

Before decomposition the file was a 1,477-line God Object with ~40
methods interleaving UI, file IO, and pipeline orchestration; it now
delegates most of the work and stays focused on widget state and
event wiring.

Public API (``AggregatorGUI(cmd_root, cmd_output)`` and the
``run_gui()`` entry point) is preserved verbatim so ``python
aggregator_gui.py`` and existing aliases keep working without
modification.
"""

from __future__ import annotations

import logging
import os
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Any, Callable, Optional, cast

# ── Encoding fix for Windows terminals (preserved from the legacy module)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# ── Project directory on sys.path so core/ is importable ---------------
_PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_DIR))

# ── Core imports -------------------------------------------------------
from core.parser import (  # pyright: ignore[reportMissingImports]
    find_project_root,
    initialize_environment,
    load_ignore_patterns,
    load_settings,
    read_file_paths,
    resolve_output_dir,
    save_settings,
)
from core.judge import (  # pyright: ignore[reportMissingImports]
    archive_model_responses,
    ensure_model_templates,
    GeminiJudge,
    load_dotenv,
)

# ── Decomposed GUI modules --------------------------------------------
from gui import aggregation_runner, builders, queue_manager, scanner
from gui.api_key_dialog import ApiKeyDialog, api_key_status_text, save_api_key_to_env
from gui.log_panel import LogPanel
from gui.paths import PROJECT_DIR
from gui.theme import build_fonts


logger = logging.getLogger("gui.app")

# Re-export some symbols the aggregator_gui.py entry-point may need
# (preserved for binary compatibility with downstream imports).
_FILES_TXT = PROJECT_DIR / "files.txt"


# ---------------------------------------------------------------------------
# Public API: AggregatorGUI
# ---------------------------------------------------------------------------


class AggregatorGUI(tk.Tk):
    """Full-featured dark-mode GUI for the File Aggregator pipeline.

    Constructor signature is identical to the legacy class so
    ``python aggregator_gui.py [root] [--output DIR]`` and
    ``run_gui()`` both keep working without any change at the call
    sites.
    """

    def __init__(
        self,
        cmd_root: Optional[Path] = None,
        cmd_output: Optional[str] = None,
    ) -> None:
        super().__init__()
        _ = self.title("File Aggregator")
        _ = self.geometry("1100x750")
        _ = self.minsize(860, 560)
        from gui.theme import _BG
        _ = self.configure(bg=_BG)

        # ----- runtime state -----------------------------------------
        self._cmd_output: Optional[str] = cmd_output
        self._project_root: Path = (
            cmd_root if cmd_root is not None
            else scanner.detect_initial_root(cwd=Path.cwd(), project_dir=PROJECT_DIR)
        )
        self._busy: bool = False
        self._cancel_requested: bool = False
        self._settings: dict[str, object] = {}
        self._suppress_settings_save: bool = False

        # ----- Tk variables ------------------------------------------
        self._judge_var = tk.BooleanVar(value=True)
        self._compact_var = tk.BooleanVar(value=False)
        self._archive_var = tk.BooleanVar(value=False)
        self._output_dir_var = tk.StringVar(value="context_output")
        self._model_count_var = tk.IntVar(value=2)
        self._output_format_var = tk.StringVar(value="md")

        # ----- fonts -------------------------------------------------
        self._fonts = build_fonts()

        # ----- placeholder handles for builder output ----------------
        self._tree_holder: dict[str, Any] = {}
        self._search_holder: dict[str, Any] = {}
        self._queue_holder: dict[str, Any] = {}
        self._api_key_holder: dict[str, Any] = {}
        self._status_holder: dict[str, Any] = {}

        # ----- log panel (initialised when widgets are built) --------
        self._log_panel = LogPanel(master=self)

        # ----- bootstrap ---------------------------------------------
        self._load_and_apply_settings()
        for var in (
            self._judge_var,
            self._compact_var,
            self._archive_var,
            self._model_count_var,
            self._output_format_var,
        ):
            _ = var.trace_add("write", self._save_current_settings)

        self._build_ui()
        self._initialize_env_silent()
        self._refresh_all()

    # ── Startup helpers ────────────────────────────────────────────────

    @property
    def files_txt_path(self) -> Path:
        return queue_manager.files_txt_path(self._project_root)

    def _detect_initial_root(self) -> Path:
        """Legacy method preserved as a thin delegator."""
        return scanner.detect_initial_root(
            cwd=Path.cwd(), project_dir=PROJECT_DIR
        )

    def _load_and_apply_settings(self) -> None:
        self._settings = load_settings(self._project_root)
        self._suppress_settings_save = True
        try:
            self._judge_var.set(bool(self._settings.get("gemini_judge", False)))
            self._compact_var.set(bool(self._settings.get("compact_mode", False)))
            self._archive_var.set(bool(self._settings.get("archive", False)))
            if self._cmd_output:
                self._output_dir_var.set(self._cmd_output)
            else:
                self._output_dir_var.set(
                    str(self._settings.get("output_dir", "context_output"))
                )
            try:
                count = int(str(self._settings.get("model_count", 2)))
                if count not in (2, 4):
                    count = 2
            except (ValueError, TypeError):
                count = 2
            self._model_count_var.set(count)

            fmt = str(self._settings.get("output_format", "md"))
            fmt = fmt.strip().lower().lstrip(".")
            if fmt not in ("md", "txt"):
                fmt = "md"
            self._output_format_var.set(fmt)
        finally:
            self._suppress_settings_save = False

    def _save_current_settings(self, *args) -> None:
        if self._suppress_settings_save:
            return
        self._settings["gemini_judge"] = self._judge_var.get()
        self._settings["compact_mode"] = self._compact_var.get()
        self._settings["archive"] = self._archive_var.get()
        self._settings["output_dir"] = (
            self._output_dir_var.get().strip() or "context_output"
        )
        try:
            self._settings["model_count"] = int(self._model_count_var.get())
        except ValueError:
            self._settings["model_count"] = 2
        self._settings["output_format"] = self._output_format_var.get()
        try:
            save_settings(self._project_root, self._settings)
        except Exception as exc:
            self._log_panel.write(f"Could not save settings: {exc}", tag="warn")

    def _initialize_env_silent(self) -> None:
        try:
            if not self.files_txt_path.exists():
                self.files_txt_path.touch()
            output_dir = resolve_output_dir(self._project_root, self._settings)
            model_count = self._model_count_var.get()
            initialize_environment(
                self._project_root, model_count=model_count, output_dir=output_dir
            )
            self._log_panel.write("Environment initialised.", tag="info")
        except Exception as exc:
            self._log_panel.write(
                f"Warning: could not initialise env: {exc}", tag="warn"
            )

    # ───────────────────────────────────────────────────────────────────
    # UI Construction
    # ───────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        builders.build_header(self, self._fonts)
        # Body is built in two passes: left + right, both composed via
        # builders. The left and right frames need to exist before
        # ``build_body`` can add them to the PanedWindow.
        left_frame = builders.build_left_panel(
            self,
            fonts=self._fonts,
            project_name=self._project_root.name,
            tree_holder=self._tree_holder,
            search_holder=self._search_holder,
            add_command=self._add_selected,
            search_trace_command=self._refresh_tree,
        )
        queue_frame = builders.build_queue_pane(
            self,
            fonts=self._fonts,
            queue_holder=self._queue_holder,
            remove_command=self._remove_selected,
        )
        options_frame = builders.build_options_pane(
            self,
            fonts=self._fonts,
            judge_var=self._judge_var,
            compact_var=self._compact_var,
            archive_var=self._archive_var,
            output_dir_var=self._output_dir_var,
            model_count_var=self._model_count_var,
            output_format_var=self._output_format_var,
            api_key_holder=self._api_key_holder,
            prompt_api_key_command=self._prompt_api_key_gui,
            on_output_dir_focusout=self._save_current_settings,
            api_key_status_provider=self._api_key_status_text,
        )
        log_frame = builders.build_log_pane(
            self, fonts=self._fonts, log_panel=self._log_panel
        )
        right_frame = builders.build_right_panel(
            self,
            queue_frame=queue_frame,
            options_frame=options_frame,
            log_frame=log_frame,
        )
        builders.build_body(self, left=left_frame, right=right_frame)
        builders.build_statusbar(
            self,
            fonts=self._fonts,
            project_root_str=str(self._project_root),
            status_holder=self._status_holder,
            on_path_submit=self._on_path_submit,
            open_root_command=self._open_root,
            clear_queue_command=self._clear_queue,
            run_command=self._run_aggregate,
            refresh_command=self._refresh_all,
            cancel_command=self._cancel_run,
        )
        self._log_panel.attach_status(self._status_holder["status_var"])
        self._log_panel.attach_progress(self._status_holder["progress"])

    # ───────────────────────────────────────────────────────────────────
    # API Key helpers
    # ───────────────────────────────────────────────────────────────────

    def _api_key_status_text(self) -> str:
        return api_key_status_text(PROJECT_DIR)

    def _prompt_api_key_gui(self) -> None:
        dlg = ApiKeyDialog(self)
        if dlg.result:
            os.environ["GEMINI_API_KEY"] = dlg.result
            if dlg.save_to_env:
                env_path = PROJECT_DIR / ".env"
                save_api_key_to_env(env_path, dlg.result)
            self._log_panel.write("API key updated.", tag="ok")
            self._api_key_holder["label"].configure(
                text=self._api_key_status_text()
            )
            self._log_panel.write("API key updated.", tag="ok")

    # ───────────────────────────────────────────────────────────────────
    # Project root management
    # ───────────────────────────────────────────────────────────────────

    def _change_root(self, new_root: Path) -> None:
        self._project_root = new_root
        self._status_holder["project_path_var"].set(str(new_root))
        self._load_and_apply_settings()
        self._initialize_env_silent()
        self._log_panel.write(f"Root → {new_root}", tag="info")
        self._refresh_all()

    def _on_path_submit(self, _event: object) -> None:
        raw = self._status_holder["project_path_var"].get().strip()
        if not raw:
            self._log_panel.write("Path field is empty.", tag="warn")
            return
        candidate = Path(raw).expanduser()
        try:
            candidate = candidate.resolve()
        except Exception:
            pass
        if not candidate.is_dir():
            self._log_panel.write(f"Not a directory: {raw}", tag="error")
            return
        self._change_root(candidate)

    def _open_root(self) -> None:
        chosen = filedialog.askdirectory(
            title="Select Project Root",
            initialdir=str(self._project_root),
        )
        if chosen:
            self._change_root(Path(chosen).resolve())

    # ───────────────────────────────────────────────────────────────────
    # Tree (left panel)
    # ───────────────────────────────────────────────────────────────────

    def _refresh_tree(self) -> None:
        tree: ttk.Treeview = self._tree_holder["widget"]  # type: ignore[assignment]
        title: tk.Label = self._tree_holder["title"]  # type: ignore[assignment]
        tree.delete(*tree.get_children())

        root = self._project_root
        settings = load_settings(root)
        patterns = load_ignore_patterns(root, settings)

        # Collect currently-queued resolved paths so the tree can show
        # ✔ markers; preserve the existing behaviour.
        queued_resolved = {
            p.resolve()
            for p, _r, _i in queue_manager.read_entries(self.files_txt_path)
        }

        filter_text = self._search_holder["var"].get().strip().lower()
        output_dir = str(settings.get("output_dir", "context_output"))

        title.configure(text=f"📁  {root}")

        # Scan the tree.
        nodes = scanner.discover_tree(
            root=root,
            settings=settings,
            queued_paths=queued_resolved,
            output_dir_name=output_dir,
            filter_text=filter_text,
        )

        # Insert as a flat ordering with depth indentation (Tk
        # Treeview handles indent automatically when ``open=False``
        # children are inserted under the parent, but the legacy
        # implementation used a recursive insert. We honour that here
        # by reconstructing the parent / child relationship from
        # consecutive depth changes).
        prev_depth_to_iid: dict[int, str] = {0: ""}
        prev_node: Optional[scanner.TreeNode] = None
        for node in nodes:
            label = (
                f"📁  {node.path.name}" if node.is_dir
                else (f"✔  {node.path.name}" if node.in_queue else f"    {node.path.name}")
            )
            parent_iid = ""
            if node.depth == 0:
                parent_iid = ""
            elif node.depth <= (prev_node.depth if prev_node else 0):
                # Going up — use the last iid at parent depth.
                parent_iid = prev_depth_to_iid.get(node.depth - 1, "")
            else:
                # Going deeper — parent is the previous node's iid.
                # Tk doesn't allow this directly from
                # ``prev_depth_to_iid`` because we haven't recorded
                # the previous leaf's iid; capture it as the last
                # child of the previous depth.
                parent_iid = prev_depth_to_iid.get(prev_node.depth if prev_node else 0, "")
            iid = tree.insert(
                parent_iid, "end",
                text=label, open=False,
                values=[str(node.path)],
            )
            prev_depth_to_iid[node.depth] = iid
            prev_node = node

        self._log_panel.write(f"Tree loaded: {root}", tag="info")

    # ───────────────────────────────────────────────────────────────────
    # Queue management
    # ───────────────────────────────────────────────────────────────────

    def _refresh_queue(self) -> None:
        listbox: tk.Listbox = self._queue_holder["listbox"]
        title: tk.Label = self._queue_holder["title"]
        listbox.delete(0, "end")

        if not self.files_txt_path.is_file():
            title.configure(text="📋  Queue  (0 files)")
            return

        raw_lines = queue_manager.read_lines(self.files_txt_path)
        for line in raw_lines:
            listbox.insert("end", line)

        for idx, line in enumerate(raw_lines):
            cls = queue_manager.classify_line(line)
            color_map = {
                "comment":   "#6c7086",  # _FG_DIM
                "important": "#cba6f7",  # _MAUVE
                "snippet":   "#94e2d5",  # _TEAL
                "file":      "#cdd6f4",  # _FG
            }
            listbox.itemconfigure(idx, foreground=color_map[cls])

        file_count = queue_manager.count_files(raw_lines)
        noun = "file" if file_count == 1 else "files"
        title.configure(text=f"📋  Queue  ({file_count} {noun})")

    def _add_selected(self) -> None:
        tree: ttk.Treeview = self._tree_holder["widget"]  # type: ignore[assignment]
        selection = tree.selection()
        if not selection:
            self._log_panel.write("No items selected in the tree.", tag="warn")
            return

        paths: list[Path] = []
        for iid in selection:
            values = tree.item(iid, "values")
            if not values:
                continue
            candidate = Path(values[0])
            if candidate.is_file():
                paths.append(candidate)
        added, _ = queue_manager.add_paths(self.files_txt_path, paths)
        if added:
            self._log_panel.write(
                f"Added {added} file(s) to queue.", tag="ok"
            )
        else:
            self._log_panel.write(
                "All selected files already in queue.", tag="warn"
            )
        self._refresh_all()

    def _remove_selected(self) -> None:
        listbox: tk.Listbox = self._queue_holder["listbox"]
        indices = list(listbox.curselection())
        if not indices:
            self._log_panel.write("No entries selected in the queue.", tag="warn")
            return
        removed = queue_manager.remove_indices(self.files_txt_path, indices)
        self._log_panel.write(
            f"Removed {removed} entry/entries from queue.", tag="warn"
        )
        self._refresh_all()

    def _clear_queue(self) -> None:
        if not messagebox.askyesno("Confirm", "Clear all entries from the queue?"):
            return
        queue_manager.clear(self.files_txt_path)
        self._log_panel.write("Queue cleared.", tag="warn")
        self._refresh_all()

    # ───────────────────────────────────────────────────────────────────
    # Refresh helpers
    # ───────────────────────────────────────────────────────────────────

    def _refresh_all(self) -> None:
        self._refresh_tree()
        self._refresh_queue()
        self._api_key_holder["label"].configure(text=self._api_key_status_text())

    # ───────────────────────────────────────────────────────────────────
    # Aggregation pipeline (background thread)
    # ───────────────────────────────────────────────────────────────────

    def _run_aggregate(self) -> None:
        if self._busy:
            self._log_panel.write("Already running — please wait.", tag="warn")
            return
        self._busy = True
        self._cancel_requested = False
        self._log_panel.start_progress()
        self._status_holder["cancel_btn"].pack(side="right", padx=5, pady=8)

        log = self._log_panel.write
        step = self._log_panel.step
        set_status = self._log_panel.set_status
        cancel_fn = lambda: self._cancel_requested  # noqa: E731

        def _api_key_prompt_blocking() -> Optional[str]:
            """Resolve the API key — blocking on a thread-safe UI dialog."""
            result_holder: list[Optional[str]] = [None]
            ready = threading.Event()

            def _show() -> None:
                dlg = ApiKeyDialog(self)
                if dlg.result:
                    os.environ["GEMINI_API_KEY"] = dlg.result
                    if dlg.save_to_env:
                        env_path = PROJECT_DIR / ".env"
                        save_api_key_to_env(env_path, dlg.result)
                    result_holder[0] = dlg.result
                ready.set()

            self.after(0, _show)
            ready.wait(timeout=120)
            return result_holder[0]

        def _worker() -> None:
            try:
                aggregation_runner.run_aggregation(
                    project_root=self._project_root,
                    tool_root=PROJECT_DIR,
                    cwd=Path.cwd(),
                    log=log,
                    step=step,
                    set_status=set_status,
                    cancel_requested=cancel_fn,
                    api_key_provider=_api_key_prompt_blocking,
                    api_key_save=lambda k: save_api_key_to_env(
                        PROJECT_DIR / ".env", k
                    ),
                )
            finally:
                self.after(0, self._stop_progress)
                self._busy = False

        threading.Thread(target=_worker, daemon=True).start()

    def _cancel_run(self) -> None:
        if self._busy:
            self._cancel_requested = True
            self._log_panel.write(
                "Cancellation requested — finishing current step …", tag="warn"
            )
            self._log_panel.set_status("Cancelling …")

    def _stop_progress(self) -> None:
        self._log_panel.stop_progress()
        self._status_holder["cancel_btn"].pack_forget()


# ---------------------------------------------------------------------------
# Entry point helper (the module-level ``main`` lives in aggregator_gui.py)
# ---------------------------------------------------------------------------


def run_gui(
    cmd_root: Optional[Path] = None,
    cmd_output: Optional[str] = None,
) -> None:
    """Construct :class:`AggregatorGUI` and enter the Tk main loop."""
    app = AggregatorGUI(cmd_root=cmd_root, cmd_output=cmd_output)
    app.mainloop()


__all__ = ["AggregatorGUI", "run_gui"]
