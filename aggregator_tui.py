"""Terminal User Interface for the File Aggregator.

Launch via:  aggt
Requires:    pip install textual
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import ClassVar

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.reactive import reactive
from textual.widgets import (
    Button,
    Checkbox,
    Footer,
    Header,
    Input,
    Label,
    Log,
    Static,
)

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
}
"""


class TreeEntry(Checkbox):
    """Selectable file entry in the project tree."""

    def __init__(self, label: str, file_path: Path, value: bool = False) -> None:
        super().__init__(label, value=value)
        self.file_path = file_path


class AggregatorTUI(App[None]):
    """Interactive TUI for browsing, selecting, and aggregating project files."""

    TITLE = "File Aggregator"
    CSS = _CSS

    BINDINGS: ClassVar[list[Binding]] = [
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
                    yield Log(id="activity-log", auto_scroll=True)

        with Horizontal(id="controls"):
            yield Button("⟳  Refresh", id="btn-refresh", variant="default")
            yield Button("▶  Aggregate", id="btn-aggregate", variant="primary")
            yield Button("✕  Clear", id="btn-clear", variant="warning")
            yield Button("⏻  Quit", id="btn-quit", variant="error")

        yield Footer()

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

    @on(Input.Submitted, "#path-input")
    def handle_path_submitted(self, event: Input.Submitted) -> None:
        raw = event.value.strip()
        log = self.query_one("#activity-log", Log)

        if not raw:
            self._manual_root = None
            self.action_refresh()
            log.write_line("[tree] Manual path cleared.")
            return

        candidate = Path(raw).expanduser()
        try:
            candidate = candidate.resolve()
        except Exception:
            pass

        if not candidate.exists() or not candidate.is_dir():
            log.write_line(f"[error] Invalid directory: {raw}")
            return

        self._manual_root = candidate
        self.action_refresh()
        log.write_line(f"[tree] Manual root set: {candidate}")

    def _load_tree(self) -> None:
        """Scan project directory and rebuild the tree panel."""
        log = self.query_one("#activity-log", Log)
        scroll = self.query_one("#tree-scroll", ScrollableContainer)
        scroll.remove_children()

        root = self._detect_root()
        path_input = self.query_one("#path-input", Input)
        if self._manual_root is not None:
            path_input.value = str(self._manual_root)
        elif not path_input.value:
            path_input.value = str(root)
        patterns = load_ignore_patterns(root)

        self._populate_tree(scroll, root, root, patterns)
        log.write_line(f"[tree] Loaded from: {root}")

    def _populate_tree(
        self,
        container: ScrollableContainer,
        dir_path: Path,
        root: Path,
        patterns: frozenset[str],
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
            if should_ignore(item, root, patterns):
                continue

            indent = "  " * depth
            if item.is_dir() and not item.is_symlink():
                container.mount(Label(f"{indent}📁 {item.name}/"))
                self._populate_tree(container, item, root, patterns, depth + 1)
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
        log = self.query_one("#activity-log", Log)

        scroll.remove_children()

        if not _FILES_TXT.is_file():
            self._queue_count = 0
            title.update("📋  Queue  (0 files)")
            return

        try:
            paths = read_file_paths(_FILES_TXT)
        except Exception as exc:
            log.write_line(f"[error] Could not read files.txt: {exc}")
            return

        for path in paths:
            scroll.mount(Label(str(path)))

        self._queue_count = len(paths)
        title.update(f"📋  Queue  ({self._queue_count} files)")
        log.write_line(f"[queue] {self._queue_count} file(s) loaded.")

    @on(Checkbox.Changed)
    def handle_checkbox(self, event: Checkbox.Changed) -> None:
        """Add or remove a file from files.txt when checked/unchecked."""
        if self._suppress_checkbox_events:
            return
        if not isinstance(event.checkbox, TreeEntry):
            return

        entry = event.checkbox
        log = self.query_one("#activity-log", Log)

        self._update_files_txt(entry.file_path, add=event.value)
        action = "Added" if event.value else "Removed"
        log.write_line(f"[queue] {action}: {entry.file_path.name}")
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
    def handle_quit(self) -> None:
        self.action_quit()

    def action_refresh(self) -> None:
        """Manual refresh of tree and queue."""
        self._load_tree()
        self._load_queue()

    @work(thread=True)
    def action_aggregate(self) -> None:
        """Run aggregation in a background thread."""
        log = self.query_one("#activity-log", Log)
        self.call_from_thread(log.write_line, "[run] Starting aggregation…")

        try:
            paths = read_file_paths(_FILES_TXT)
            if not paths:
                self.call_from_thread(
                    log.write_line, "[warn] files.txt is empty — nothing to aggregate."
                )
                return

            root = find_project_root(paths[0])
            patterns = load_ignore_patterns(root or self._detect_root())

            if root:
                tree_lines = [f"Project Root: {root.name}/"] + generate_tree(
                    root, root, patterns
                )
                _STRUCTURE_TXT.write_text("\n".join(tree_lines), encoding="utf-8")
                self.call_from_thread(log.write_line, "[ok] structure.txt written")

            aggregate_files(paths, _ARENA_TXT, root)
            self.call_from_thread(
                log.write_line, f"[ok] arena.txt written ({len(paths)} file(s))."
            )

        except FileNotFoundError:
            self.call_from_thread(
                log.write_line, "[error] files.txt not found — add files first."
            )
        except Exception as exc:
            self.call_from_thread(log.write_line, f"[error] {exc}")

    def action_clear(self) -> None:
        """Clear the queue and uncheck all checkboxes."""
        _FILES_TXT.write_text("", encoding="utf-8")

        self._suppress_checkbox_events = True
        try:
            for entry in self.query(TreeEntry):
                entry.value = False
        finally:
            self._suppress_checkbox_events = False

        log = self.query_one("#activity-log", Log)
        log.write_line("[queue] Cleared.")
        self._load_queue()

    def _update_files_txt(self, path: Path, *, add: bool) -> None:
        """Update files.txt with path addition or removal."""
        existing = []
        if _FILES_TXT.is_file():
            try:
                existing = read_file_paths(_FILES_TXT)
            except Exception:
                pass

        path_resolved = path.resolve()
        existing_resolved = [p.resolve() for p in existing]

        if add:
            if path_resolved not in existing_resolved:
                existing.append(path)
        else:
            existing = [p for p in existing if p.resolve() != path_resolved]

        _FILES_TXT.write_text(
            "\n".join(str(p) for p in existing) + ("\n" if existing else ""),
            encoding="utf-8",
        )


def main() -> None:
    AggregatorTUI().run()


if __name__ == "__main__":
    main()
