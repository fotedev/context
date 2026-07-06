"""Terminal User Interface for the File Aggregator.

Launch via:  aggt
Requires:    pip install textual
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import ClassVar

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    Checkbox,
    Footer,
    Header,
    Input,
    Label,
    RichLog,
    Static,
)

# Resolve project directory and import core engine
_PROJECT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_PROJECT_DIR))

from core.parser import (  # noqa: E402
    aggregate_files,
    find_project_root,
    generate_tree,
    load_ignore_patterns,
    load_settings,
    read_file_entries,
    read_file_paths,
    should_ignore,
)
from core.arena import arena_filenames, arena_model_filename  # noqa: E402
from core.counter import count_tokens
from core.judge import (
    archive_model_responses,
    build_compare_markdown,
    collect_model_responses,
    ensure_model_templates,
    generate_compare_template,
)

_FILES_TXT = _PROJECT_DIR / "files.txt"
_ENV_FILE = _PROJECT_DIR / ".env"

_CSS = """
Screen {
    layout: vertical;
}

#path-bar {
    height: 3;
    layout: horizontal;
    align: left middle;
    padding: 0 1;
    background: $surface;
}

#path-label {
    width: 14;
}

#path-input {
    width: 1fr;
}

#btn-set-root {
    margin-left: 1;
}

#btn-clear-root {
    margin-left: 1;
}

#body {
    layout: horizontal;
    height: 1fr;
}

#tree-panel {
    width: 40%;
    border: solid $primary;
    padding: 0 1;
}

#tree-title {
    background: $primary;
    color: $text;
    text-align: center;
    padding: 0 1;
}

#tree-scroll {
    height: 1fr;
}

#right-panel {
    width: 60%;
    layout: vertical;
}

#queue-panel {
    height: 50%;
    border: solid $accent;
    padding: 0 1;
}

#queue-title {
    background: $accent;
    color: $text;
    text-align: center;
    padding: 0 1;
}

#queue-scroll {
    height: 1fr;
}

#log-panel {
    height: 50%;
    border: solid $surface;
    padding: 0 1;
}

#controls {
    height: 3;
    layout: horizontal;
    align: center middle;
    padding: 0 1;
    background: $surface;
}

Button {
    margin: 0 1;
}

TreeEntry {
    height: 1;
    padding: 0;
    margin: 0;
    border: none;
    text-wrap: nowrap;
    text-overflow: ellipsis;
}

APIKeyModal {
    align: center middle;
}

#api-key-dialog {
    grid-size: 2;
    grid-gutter: 1 2;
    grid-rows: 1fr 3;
    padding: 0 1;
    width: 60;
    height: 11;
    border: thick $background 80%;
    background: $surface;
}

#api-key-label {
    column-span: 2;
    height: 1fr;
    width: 1fr;
    content-align: center middle;
}

#api-key-input {
    column-span: 2;
}

#btn-submit-key, #btn-cancel-key {
    width: 100%;
}
"""


class APIKeyModal(ModalScreen[str | type(None)]):
    """Modal dialog to request the Gemini API key."""

    def compose(self) -> ComposeResult:
        with Vertical(id="api-key-dialog"):
            yield Label("GEMINI_API_KEY is missing.\nPlease enter it below to run the AI Judge:", id="api-key-label")
            yield Input(placeholder="AIza...", id="api-key-input", password=True)
            yield Button("Submit", variant="success", id="btn-submit-key")
            yield Button("Cancel", variant="error", id="btn-cancel-key")

    @on(Button.Pressed, "#btn-submit-key")
    def submit_key(self) -> None:
        key = self.query_one("#api-key-input", Input).value.strip()
        self.dismiss(key if key else None)

    @on(Button.Pressed, "#btn-cancel-key")
    def cancel_key(self) -> None:
        self.dismiss(None)


class TreeEntry(Checkbox):
    """Selectable file entry in the project tree."""

    file_path: Path

    BINDINGS = [
        Binding("up", "focus_previous", "Previous", show=False),
        Binding("down", "focus_next", "Next", show=False),
        Binding("pageup", "page_up", "Page Up", show=False),
        Binding("pagedown", "page_down", "Page Down", show=False),
        Binding("tab", "skip_tree_forward", "Skip Forward", show=False),
        Binding("shift+tab", "skip_tree_backward", "Skip Backward", show=False),
    ]

    def __init__(self, label: str, file_path: Path, value: bool = False) -> None:
        super().__init__(label, value=value)
        self.file_path = file_path

    def action_focus_previous(self) -> None:
        self.app.action_focus_previous()

    def action_focus_next(self) -> None:
        self.app.action_focus_next()

    def action_page_up(self) -> None:
        for _ in range(10):
            self.app.action_focus_previous()

    def action_page_down(self) -> None:
        for _ in range(10):
            self.app.action_focus_next()

    def action_skip_tree_forward(self) -> None:
        self.app.query_one("#btn-refresh", Button).focus()

    def action_skip_tree_backward(self) -> None:
        self.app.query_one("#path-input", Input).focus()


class AggregatorTUI(App[None]):
    """Interactive TUI for browsing, selecting, and aggregating project files."""

    TITLE: str = "File Aggregator"
    CSS: str = _CSS

    BINDINGS = [
        Binding("r", "refresh", "Refresh Tree", show=True),
        Binding("a", "aggregate", "Aggregate", show=True),
        Binding("c", "clear", "Clear Queue", show=True),
        Binding("q", "quit", "Quit", show=True),
    ]

    _queue_count: reactive[int] = reactive(0)

    def __init__(self) -> None:
        super().__init__()
        self._suppress_checkbox_events: bool = False
        self._manual_root: Path | None = None

    def on_mount(self) -> None:
        """Populate tree and queue on startup."""
        self._load_tree()
        self._load_queue()

    def compose(self) -> ComposeResult:
        yield Header()

        with Horizontal(id="path-bar"):
            yield Static("Project Path:", id="path-label")
            yield Input(placeholder="Paste absolute path and press Enter", id="path-input")
            yield Button("Set", id="btn-set-root", variant="primary")
            yield Button("Clear", id="btn-clear-root", variant="warning")

        with Horizontal(id="body"):
            with Vertical(id="tree-panel"):
                yield Static("📁  Project Tree  (click to queue)", id="tree-title")
                with ScrollableContainer(id="tree-scroll"):
                    pass

            with Vertical(id="right-panel"):
                with Vertical(id="queue-panel"):
                    yield Static("📋  Queue  (0 files)", id="queue-title")
                    with ScrollableContainer(id="queue-scroll"):
                        pass

                with Vertical(id="log-panel"):
                    yield RichLog(id="activity-log", auto_scroll=True, markup=True)

        with Horizontal(id="controls"):
            yield Button("⟳  Refresh", id="btn-refresh", variant="default")
            yield Button("▶  Aggregate", id="btn-aggregate", variant="primary")
            yield Button("✕  Clear", id="btn-clear", variant="warning")
            yield Button("⏻  Quit", id="btn-quit", variant="error")
            yield Checkbox("Run AI Judge", id="cb-judge", value=False)
            yield Checkbox("Compact Mode", id="cb-compact", value=False)

        yield Footer()

    def log_message(self, message: str, level: str = "info") -> None:
        """Write a formatted message to the RichLog."""
        log = self.query_one("#activity-log", RichLog)
        color_map = {
            "info": "cyan",
            "success": "green",
            "warning": "yellow",
            "error": "red",
            "action": "magenta",
        }
        color = color_map.get(level, "white")
        formatted = f"[{color}]{message}[/{color}]"
        import threading
        if not hasattr(self, "_thread_id") or self._thread_id == threading.get_ident():
            log.write(formatted)
        else:
            self.call_from_thread(log.write, formatted)


    def _detect_root(self) -> Path:
        """Return project root inferred from files.txt or current directory."""
        if self._manual_root is not None:
            return self._manual_root
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

    def _set_manual_root_from_raw(self, raw: str) -> None:
        if not raw:
            self._manual_root = None
            self.action_refresh()
            self.log_message("[tree] Manual path cleared.", "info")
            return

        candidate = Path(raw).expanduser()
        try:
            candidate = candidate.resolve()
        except Exception:
            pass

        if not candidate.exists() or not candidate.is_dir():
            self.log_message(f"[error] Invalid directory: {raw}", "error")
            return

        self._manual_root = candidate
        self.action_refresh()
        self.log_message(f"[tree] Manual root set: {candidate}", "success")

    @on(Input.Submitted, "#path-input")
    def handle_path_submitted(self, event: Input.Submitted) -> None:
        self._set_manual_root_from_raw(event.value.strip())

    @on(Button.Pressed, "#btn-set-root")
    def handle_set_root_pressed(self) -> None:
        raw = self.query_one("#path-input", Input).value.strip()
        self._set_manual_root_from_raw(raw)

    @on(Button.Pressed, "#btn-clear-root")
    def handle_clear_root_pressed(self) -> None:
        path_input = self.query_one("#path-input", Input)
        path_input.value = ""
        self._set_manual_root_from_raw("")

    def _load_tree(self) -> None:
        """Scan project directory and rebuild the tree panel."""
        scroll = self.query_one("#tree-scroll", ScrollableContainer)
        scroll.remove_children()

        root = self._detect_root()
        path_input = self.query_one("#path-input", Input)
        if self._manual_root is not None:
            path_input.value = str(self._manual_root)
        elif not path_input.value:
            path_input.value = str(root)
        settings = load_settings(root)
        patterns = load_ignore_patterns(root, settings)
        output_dir = str(settings.get("output_dir", "context_output"))

        self._populate_tree(scroll, root, root, patterns, output_dir)
        self.log_message(f"[tree] Loaded from: {root}", "info")

    def _populate_tree(
        self,
        container: ScrollableContainer,
        dir_path: Path,
        root: Path,
        patterns: frozenset[str],
        output_dir: str = "context_output",
        depth: int = 0,
    ) -> None:
        """Recursively mount TreeEntry widgets for files and Labels for directories."""
        if depth > 6:
            return

        try:
            items = sorted(
                dir_path.iterdir(),
                key=lambda p: (not p.is_dir(), p.name.lower()),
            )
        except PermissionError:
            return

        # Pre-resolve queued paths for faster checking
        queued_paths = set()
        if _FILES_TXT.is_file():
            try:
                queued_paths = {p.resolve() for p in read_file_paths(_FILES_TXT)}
            except Exception:
                pass

        for item in items:
            if should_ignore(item, root, patterns, output_dir):
                continue

            indent = "  " * depth
            if item.is_dir() and not item.is_symlink():
                container.mount(Label(f"{indent}📁 {item.name}/"))
                self._populate_tree(
                    container, item, root, patterns, output_dir, depth + 1
                )
            elif item.is_file():
                entry = TreeEntry(
                    f"{indent}  {item.name}",
                    file_path=item.resolve(),
                    value=item.resolve() in queued_paths,
                )
                container.mount(entry)

    def _load_queue(self) -> None:
        """Rebuild the queue panel from files.txt."""
        scroll = self.query_one("#queue-scroll", ScrollableContainer)
        title = self.query_one("#queue-title", Static)

        scroll.remove_children()

        if not _FILES_TXT.is_file():
            self._queue_count = 0
            title.update("📋  Queue  (0 files | ~0 tokens | ~0 chars)")
            return

        try:
            paths = read_file_paths(_FILES_TXT)
        except Exception as exc:
            self.log_message(f"[error] Could not read files.txt: {exc}", "error")
            return

        for path in paths:
            scroll.mount(Label(str(path)))

        self._queue_count = len(paths)
        
        # Trigger async token estimation
        self._async_estimate_queue_tokens()

    @work(thread=True, exclusive=True)
    def _async_estimate_queue_tokens(self) -> None:
        """Estimate tokens and chars for the current queue."""
        if not _FILES_TXT.is_file():
            return
            
        try:
            entries = read_file_entries(_FILES_TXT)
        except Exception:
            return

        total_chars = 0
        
        for path, line_ranges, _ in entries:
            try:
                if not path.is_file():
                    continue
                content = path.read_text(encoding="utf-8")
                
                if line_ranges is not None:
                    from core.parser import stream_file_content
                    content = "".join(stream_file_content(path, line_ranges))
                    
                total_chars += len(content)
            except Exception:
                pass

        total_tokens = count_tokens("a" * total_chars) if total_chars else 0
        
        title = self.query_one("#queue-title", Static)
        self.call_from_thread(title.update, f"📋  Queue  ({self._queue_count} files | ~{total_tokens:,} tokens | ~{total_chars:,} chars)")

    @on(Checkbox.Changed)
    def handle_checkbox(self, event: Checkbox.Changed) -> None:
        """Add or remove a file from files.txt when checked/unchecked."""
        if self._suppress_checkbox_events:
            return
            
        # Ignore non-TreeEntry checkboxes (like our new controls)
        if not isinstance(event.checkbox, TreeEntry):
            return

        entry = event.checkbox

        self._update_files_txt(entry.file_path, add=event.value)
        action = "Added" if event.value else "Removed"
        self.log_message(f"[queue] {action}: {entry.file_path.name}", "action")
        self._load_queue()

    @on(Button.Pressed, "#btn-refresh")
    def handle_refresh(self) -> None:
        self.action_refresh()

    @on(Button.Pressed, "#btn-aggregate")
    def handle_aggregate(self) -> None:
        self.action_aggregate()

    @on(Button.Pressed, "#btn-clear")
    def handle_clear(self) -> None:
        self.action_clear()

    @on(Button.Pressed, "#btn-quit")
    async def handle_quit(self) -> None:
        await self.action_quit()

    def action_refresh(self) -> None:
        """Manual refresh of tree and queue."""
        self._load_tree()
        self._load_queue()

    @work(thread=True)
    def action_aggregate(self) -> None:
        """Run aggregation in a background thread."""
        self.log_message("[run] Starting aggregation…", "action")

        try:
            paths = read_file_paths(_FILES_TXT)
            if not paths:
                self.log_message("[warn] files.txt is empty — nothing to aggregate.", "warning")
                return

            root = find_project_root(paths[0])
            resolved_root = root or self._detect_root() or _PROJECT_DIR

            # Resolve arena directory
            from core.parser import load_settings, resolve_output_dir, resolve_arena_dir
            from core.parser import migrate_to_per_file_folders, migrate_to_flat_layout
            settings = load_settings(resolved_root)
            patterns = load_ignore_patterns(resolved_root, settings)
            output_dir = resolve_output_dir(resolved_root, settings)
            output_format = str(settings.get("output_format", "md"))
            # Flatten v2 → v3+ layout (idempotent if already flat).
            migrate_to_per_file_folders(output_dir)
            migrate_to_flat_layout(output_dir, settings=settings)
            arena_dir = resolve_arena_dir(output_dir, _FILES_TXT.stem)

            # v3-prefixed flat layout: every file lives directly in
            # arena_dir and carries the arena's NNN- prefix.
            filenames = arena_filenames(arena_dir, output_format)
            arena_path = filenames["context"]
            structure_txt = output_dir / "structure" / "structure.txt"

            if root:
                tree_lines = [f"Project Root: {root.name}/"] + generate_tree(
                    root, root, patterns
                )
                structure_txt.write_text("\n".join(tree_lines), encoding="utf-8")
                self.log_message(f"[ok] structure written to {structure_txt.name}", "success")

            entries = read_file_entries(_FILES_TXT)
            aggregate_files(entries, arena_path, root)
            self.log_message(f"[ok] arena written ({len(paths)} file(s)) to {arena_path.name}.", "success")

            # v3-prefixed flat layout: prompt/A/B live directly in arena_dir.
            prompt_file = filenames["prompt"]
            if not prompt_file.exists():
                prompt_file.touch()
            model_count = settings.get("model_count", 2)
            _ = ensure_model_templates(arena_dir, model_count)
            
            run_judge = self.query_one("#cb-judge", Checkbox).value
            if run_judge:
                self._check_and_run_judge(root, arena_dir)

        except FileNotFoundError:
            self.log_message("[error] files.txt not found — add files first.", "error")
        except Exception as exc:
            self.log_message(f"[error] {exc}", "error")

    def _check_and_run_judge(self, root: Path | None, arena_dir: Path) -> None:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            # Check env file in aggregator dir
            from core.judge import load_dotenv
            if root:
                load_dotenv(root)
            load_dotenv(Path.cwd())
            load_dotenv(_PROJECT_DIR)
            api_key = os.environ.get("GEMINI_API_KEY")
            
        if not api_key:
            self.call_from_thread(self._prompt_for_key_and_run, root, arena_dir)
        else:
            self._run_judge_thread(root, api_key, arena_dir)

    def _prompt_for_key_and_run(self, root: Path | None, arena_dir: Path) -> None:
        def check_key(key: str | None) -> None:
            if key:
                os.environ["GEMINI_API_KEY"] = key
                try:
                    with _ENV_FILE.open("a", encoding="utf-8") as f:
                        f.write(f"\\nGEMINI_API_KEY={key}\\n")
                    self.log_message("[key] API key saved to .env", "success")
                except Exception as e:
                    self.log_message(f"[error] Failed to save key: {e}", "warning")
                    
                self._run_judge_thread(root, key, arena_dir)
            else:
                self.log_message("[judge] API key is required to run the AI Judge.", "warning")
                
        self.app.push_screen(APIKeyModal(), check_key)

    @work(exclusive=True)
    async def _run_judge_thread(self, root: Path | None, api_key: str, arena_dir: Path) -> None:
        self.log_message("[judge] Collecting model responses...", "action")
        try:
            from core.parser import load_settings
            resolved_root = root or self._detect_root() or _PROJECT_DIR
            settings = load_settings(resolved_root)
            output_format = settings.get("output_format", "md")
            filenames = arena_filenames(arena_dir, output_format)
            compare_file = filenames["arena"]

            model_count = settings.get("model_count", 2)
            prompt, models_data = collect_model_responses(
                arena_dir, output_format, model_count
            )
            if not models_data:
                self.log_message(
                    f"[judge] No model responses found in {arena_dir.name}/ directory.", "warning"
                )
                generate_compare_template(compare_file, model_count)
                self.log_message(f"[ok] Blank template written to {compare_file.name}.", "success")
                return

            self.log_message(f"[judge] Found {len(models_data)} models. Requesting Gemini evaluation...", "action")
            from core.judge import GeminiJudge
            judge = GeminiJudge()
            verdict = await judge.evaluate(prompt, models_data, api_key)

            compact = self.query_one("#cb-compact", Checkbox).value

            build_compare_markdown(prompt, models_data, compare_file, verdict=verdict, compact=compact)

            # --- Req 5: archiving workflow (local to this arena) ---
            archive = settings.get("archive", False)
            if archive:
                self.log_message("[judge] Archiving model responses …", "action")
                archive_dir = str(settings.get("archive_dir", "ARCHIVE"))
                archived = archive_model_responses(arena_dir, archive_dir)
                if archived:
                    ensure_model_templates(arena_dir, model_count)
                    self.log_message(f"[ok] Archived responses to {archive_dir}.", "success")

            self.log_message(f"[ok] AI Judge evaluation written to {compare_file.name}.", "success")
        except Exception as exc:
            self.log_message(f"[error] AI Judge failed: {exc}", "error")

    def action_clear(self) -> None:
        """Clear the queue and uncheck all checkboxes."""
        _FILES_TXT.write_text("", encoding="utf-8")

        self._suppress_checkbox_events = True
        try:
            for entry in self.query(TreeEntry):
                entry.value = False
        finally:
            self._suppress_checkbox_events = False

        self.log_message("[queue] Cleared.", "warning")
        self._load_queue()

    def _update_files_txt(self, path: Path, *, add: bool) -> None:
        """Update files.txt with path addition or removal, preserving comments."""
        raw_lines: list[str] = []
        if _FILES_TXT.is_file():
            try:
                raw_lines = _FILES_TXT.read_text(encoding="utf-8").splitlines()
            except Exception:
                pass

        path_resolved = path.resolve()

        # Build a list of resolved paths for non-comment lines
        existing_resolved: list[tuple[int, Path]] = []
        for idx, line in enumerate(raw_lines):
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                try:
                    # Strip any optional line range suffix
                    from core.parser import parse_file_entry
                    p_parsed, _, _ = parse_file_entry(stripped)
                    existing_resolved.append((idx, p_parsed.resolve()))
                except Exception:
                    pass

        if add:
            # Add only if not already present
            if not any(r[1] == path_resolved for r in existing_resolved):
                raw_lines.append(str(path))
        else:
            # Remove all occurrences of this path
            indices_to_remove = {r[0] for r in existing_resolved if r[1] == path_resolved}
            raw_lines = [line for idx, line in enumerate(raw_lines) if idx not in indices_to_remove]

        # Write lines back, preserving comments and blank lines
        _FILES_TXT.write_text(
            "\n".join(raw_lines) + ("\n" if raw_lines else ""),
            encoding="utf-8",
        )


def main() -> None:
    AggregatorTUI().run()


if __name__ == "__main__":
    main()
