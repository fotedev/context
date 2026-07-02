# Refactor `core/parser.py` + Add `--status` — Implementation Plan

> **Goal (الهدف):** Split the bloated `core/parser.py` (≈1673 lines, 3+ mixed
> concerns) into focused modules **without breaking any existing import**, and
> add an `agg --status` flag that gives AI agents a tiny, token-cheap snapshot
> of the project's arena state.
>
> This file is the **only spec you need**. Follow it top-to-bottom. Do **not**
> improvise the module layout — the exact symbol-to-module mapping below is
> mandatory.

---

## 0. Read this first — the one rule you must not break 🔴

**`core/parser.py` must keep exporting every public name it exports today.**

Four files import from `core.parser`:

| File | What it imports |
|---|---|
| `aggregator.py` | `aggregate_files, find_project_root, generate_tree, load_ignore_patterns, initialize_environment, read_file_entries, resolve_output_dir, resolve_models_dir, discover_files_txt_with_directives, resolve_arena_dir, load_settings, save_settings, display_settings, migrate_old_outputs, sync_paste_attachments, build_arena_plan, ArenaAssignment, ArenaDirective` |
| `aggregator_gui.py` | all of the above **plus** `read_file_paths, should_ignore` |
| `aggregator_tui.py` | `aggregate_files, find_project_root, generate_tree, load_ignore_patterns, read_file_entries, read_file_paths, should_ignore, stream_file_content, parse_file_entry, load_settings, resolve_output_dir, resolve_arena_dir` |
| `renumber_arenas.py` | `ArenaDirective, build_arena_plan, discover_files_txt_with_directives` |

**You will NOT edit a single import line in those four files.** Instead you will
turn `core/parser.py` into a **backward-compatibility shim** that re-exports the
moved symbols (see Phase D). This is what makes the refactor safe for a single
pass — zero blast radius on callers.

When in doubt: the move is correct only if `python -c "from core.parser import *"`
still works AND `python -m py_compile` passes on all five files.

---

## 1. Current state (as-is)

`core/parser.py` mixes **6 concerns** in one 1673-line file:

1. **Settings** — `DEFAULT_SETTINGS`, `load_settings`, `save_settings`,
   `display_settings`, `_migrate_settings_file`, `ensure_context_dir`,
   `_DEFAULT_IGNORE_TEMPLATE`
2. **Paste-attachments archival** — `_read_text_safely`,
   `extract_first_sentences`, `slugify_two_sentences`,
   `sync_paste_attachments`, 3 regexes
3. **Discovery + ignore** — `discover_files_txt`,
   `discover_files_txt_with_directives`, `load_ignore_patterns`,
   `should_ignore`, `_check_glob_match`, `_read_pattern_file`,
   `_DEFAULT_IGNORE`, `_ROOT_MARKERS`
4. **Arena logic** — `ArenaDirective`, `ArenaAssignment`,
   `parse_target_arena_directive`, `_read_first_line_safely`,
   `_safe_read_directive`, `build_arena_plan`, `resolve_arena_dir`
5. **Path parsing / aggregation** — `resolve_cross_platform_path`,
   `parse_file_entry`, `read_file_entries`, `stream_file_content`,
   `read_file_paths`, `aggregate_files`
6. **Tree / migration / output dirs** — `generate_tree`, `find_project_root`,
   `get_display_path`, `initialize_environment`, `_ensure_model_files`,
   `resolve_output_dir`, `resolve_models_dir`, `migrate_old_outputs`

`core/__init__.py` currently is:
```python
from . import parser
from . import counter
from . import judge
```

There is **no `lib/` directory** yet.

---

## 2. Target state (to-be)

```
core/
├── __init__.py        ← updated: import new submodules too (Phase D)
├── settings.py        ← NEW: concerns 1 + 2  (settings + paste-attachments)
├── discovery.py       ← NEW: concern 3 + get_latest_state() (NEW, for --status)
├── arena.py           ← NEW: concern 4
├── parser.py          ← SLIMMED: concerns 5 + 6 + re-export shim
├── counter.py         ← untouched
└── judge.py           ← untouched
```

Dependency direction (no cycles allowed):
```
settings.py  ←  (nothing internal)
arena.py     ←  (nothing internal)
discovery.py ←  imports from arena.py  (ArenaDirective, _safe_read_directive)
parser.py    ←  imports from settings.py, discovery.py, arena.py, counter.py
```

**Why paste-attachments lives in `settings.py`:** it is 100% settings-driven
(reads `paste_attachments_*` keys) and is conceptually "config-driven archival".
Keeping it with settings avoids creating a tiny extra module.

---

## 3. Phase A — Create `core/settings.py`

Move these symbols **verbatim** (copy the code, do not rewrite logic) from
`core/parser.py` into `core/settings.py`:

| Symbol | Current lines | Notes |
|---|---|---|
| `DEFAULT_SETTINGS` | 80–102 | module-level dict |
| `_DEFAULT_IGNORE_TEMPLATE` | 105–165 | string constant |
| `ensure_context_dir` | 172–218 | calls `save_settings` (same module now ✔) |
| `load_settings` | 226–280 | calls `ensure_context_dir`, `_migrate_settings_file` |
| `save_settings` | 283–297 | |
| `display_settings` | 300–327 | |
| `_FORBIDDEN_FILENAME_CHARS` | 336 | regex |
| `_PURE_NUMERIC_OR_PUNCT` | 338 | regex |
| `_SENTENCE_SPLIT_RE` | 340 | regex |
| `_read_text_safely` | 343–356 | |
| `extract_first_sentences` | 359–371 | |
| `slugify_two_sentences` | 374–402 | |
| `_migrate_settings_file` | 405–450 | calls `save_settings` |
| `sync_paste_attachments` | 453–560 | `import shutil` stays local inside fn |

**Imports needed at top of `core/settings.py`:**
```python
from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import cast
```

**Module docstring** (put at top):
```python
"""Settings & configuration management + paste-attachments archival.

Holds the DEFAULT_SETTINGS schema, the .context/settings.json load/save/migrate
lifecycle, and the settings-driven paste-attachments archival feature.
"""
```

✅ **Checkpoint A:** `python -c "import core.settings as s; print(s.DEFAULT_SETTINGS['output_dir'])"`
must print `context_output`. (It will also fail elsewhere because parser.py
still references these names — that's fine, fixed in Phase D. Just confirm
`settings.py` parses: `python -m py_compile core/settings.py`.)

---

## 4. Phase B — Create `core/arena.py`

Move these symbols **verbatim** from `core/parser.py` into `core/arena.py`:

| Symbol | Current lines |
|---|---|
| `ArenaDirective` (frozen dataclass) | 1235–1253 |
| `_DIRECTIVE_NUMBER_RE` | 1256 |
| `parse_target_arena_directive` | 1259–1288 |
| `_read_first_line_safely` | 1291–1306 |
| `_safe_read_directive` | 1309–1316 |
| `ArenaAssignment` (frozen dataclass) | 1319–1326 |
| `build_arena_plan` | 1329–1438 |
| `resolve_arena_dir` | 1446–1499 |

**Imports needed at top of `core/arena.py`:**
```python
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
```
(`build_arena_plan` does not need `typing`; it uses only builtins. Double-check
no other imports were used — if `cast`/`Iterator` appear, drop them; they are
not needed here.)

**Module docstring:**
```python
"""Arena directive parsing, conflict-resolved arena planning, and arena
directory resolution.

A ``# Target Arena: NNN-<name>`` directive on the first non-empty line of an
input file pins that file's arena number. The filename remains the source of
truth for the arena name. build_arena_plan turns a set of inputs + directives
into final ArenaAssignment records, resolving number conflicts.
"""
```

⚠️ `resolve_arena_dir` (lines 1446–1499) has **no internal dependency** on parser
helpers — it only uses `Path`. Confirm while moving; if you see a call to
another parser function, stop and re-check (there shouldn't be).

✅ **Checkpoint B:** `python -m py_compile core/arena.py` passes.

---

## 5. Phase C — Create `core/discovery.py` (incl. NEW `get_latest_state`)

Move these symbols **verbatim** from `core/parser.py` into `core/discovery.py`:

| Symbol | Current lines |
|---|---|
| `_DEFAULT_IGNORE` | 24–73 |
| `discover_files_txt` | 1160–1207 |
| `discover_files_txt_with_directives` | 1210–1227 |
| `load_ignore_patterns` | 675–699 |
| `_read_pattern_file` | 702–722 |
| `_check_glob_match` | 725–728 |
| `should_ignore` | 731–763 |

> Note: `load_ignore_patterns` currently calls `ensure_context_dir` (now in
> `settings.py`) and `_read_pattern_file` (same module). `discover_files_txt`
> uses `cast`. `discover_files_txt_with_directives` calls `discover_files_txt`
> + `_safe_read_directive` (now in `arena.py`).

**Imports needed at top of `core/discovery.py`:**
```python
from __future__ import annotations

import fnmatch
import functools
import re
import sys
from pathlib import Path
from typing import cast

from core.settings import ensure_context_dir
from core.arena import ArenaDirective, _safe_read_directive
```

This is the **only** cross-module import edge and it points one way
(discovery → settings, discovery → arena). No cycle.

### 5.1 NEW function — add `get_latest_state()` for `--status`

Append this **new** function to `core/discovery.py`. This is the core of the
`--status` feature. Design decision (from the design discussion): **the `NNN-`
prefix is the authoritative source for numbering** (deterministic, OS/git-proof);
**mtime is used only as secondary "activity" info**, never for ordering or
numbering.

```python
import datetime as _dt  # add to the imports at top of discovery.py


def get_latest_state(
    arenas_dir: Path,
    inputs_dir: Path | None = None,
) -> dict[str, object]:
    """Return a token-cheap snapshot of the arena state for AI agents.

    Numbering is derived SOLELY from the ``NNN-`` prefix of arena directories
    (deterministic across OS / git / copy). mtime is reported only as a
    secondary "when did this last change" hint.

    Args:
        arenas_dir: ``<output_dir>/arenas`` directory.
        inputs_dir: Optional ``.context/inputs`` directory; when provided, its
            ``.txt`` count and newest file are included.

    Returns:
        Dict with keys: last_arena, next_number, total_arenas,
        latest_activity_arena, latest_activity_time, total_inputs,
        latest_input, latest_input_time.
    """
    state: dict[str, object] = {
        "last_arena": None,
        "next_number": 0,
        "total_arenas": 0,
        "latest_activity_arena": None,
        "latest_activity_time": "",
        "total_inputs": 0,
        "latest_input": None,
        "latest_input_time": "",
    }

    arena_num_re = re.compile(r"^(\d+)-(.+)$")

    numbered: list[tuple[int, str, Path]] = []
    if arenas_dir.is_dir():
        for p in arenas_dir.iterdir():
            if not p.is_dir():
                continue
            m = arena_num_re.match(p.name)
            if m:
                numbered.append((int(m.group(1)), m.group(2), p))

    state["total_arenas"] = len(numbered)

    if numbered:
        numbered.sort(key=lambda t: t[0])
        top_num, top_name, _ = numbered[-1]
        state["last_arena"] = f"{top_num:03d}-{top_name}"
        state["next_number"] = top_num + 1

        # Secondary: most recently touched arena by mtime (info only).
        newest = max(numbered, key=lambda t: t[2].stat().st_mtime)
        state["latest_activity_arena"] = f"{newest[0]:03d}-{newest[1]}"
        try:
            state["latest_activity_time"] = _dt.datetime.fromtimestamp(
                newest[2].stat().st_mtime
            ).strftime("%Y-%m-%d %H:%M")
        except OSError:
            state["latest_activity_time"] = ""

    if inputs_dir is not None and inputs_dir.is_dir():
        txts = sorted(p for p in inputs_dir.glob("*.txt") if p.is_file())
        state["total_inputs"] = len(txts)
        if txts:
            newest_in = max(txts, key=lambda f: f.stat().st_mtime)
            state["latest_input"] = newest_in.name
            try:
                state["latest_input_time"] = _dt.datetime.fromtimestamp(
                    newest_in.stat().st_mtime
                ).strftime("%Y-%m-%d %H:%M")
            except OSError:
                state["latest_input_time"] = ""

    return state
```

✅ **Checkpoint C:** `python -m py_compile core/discovery.py` passes.

---

## 6. Phase D — Slim `core/parser.py` into a shim + re-exports

After Phases A–C, `core/parser.py` should **delete** every symbol that was
moved (settings, paste, discovery, ignore, arena). What **remains** in
`parser.py` (concerns 5 + 6 — keep them where they are):

- `_ROOT_MARKERS`, `_MAX_TREE_DEPTH`
- `initialize_environment`, `_ensure_model_files`
- `find_project_root`
- `get_display_path`
- `generate_tree` (uses `should_ignore` → now imported from discovery)
- `resolve_cross_platform_path`, `parse_file_entry`, `read_file_entries`,
  `stream_file_content`, `read_file_paths`, `aggregate_files`
- `resolve_output_dir`, `resolve_models_dir`
- legacy-output migration: `_LEGACY_OUTPUT_FILES`, `_LEGACY_OUTPUT_GLOBS`,
  `_output_dir_already_populated`, `_resolve_migration_dest`,
  `migrate_old_outputs`

### 6.1 New imports to add near the top of the slimmed `parser.py`

```python
from core.settings import (
    DEFAULT_SETTINGS,
    ensure_context_dir,
    load_settings,
    save_settings,
    display_settings,
    sync_paste_attachments,
)
from core.discovery import (
    discover_files_txt,
    discover_files_txt_with_directives,
    load_ignore_patterns,
    should_ignore,
    get_latest_state,
)
from core.arena import (
    ArenaDirective,
    ArenaAssignment,
    parse_target_arena_directive,
    build_arena_plan,
    resolve_arena_dir,
)
```

These satisfy the slimmed `parser.py`'s own internal needs **and** make the
names re-exportable so `from core.parser import X` keeps working for the four
caller files. (Because `generate_tree` now needs `should_ignore`, and
`load_ignore_patterns` is no longer defined here — both come from discovery.)

> If `pyflakes`/your linter complains that some re-imported names are "unused"
> inside `parser.py`, that is **expected and correct** — they exist precisely
> to be re-exported. Do not delete them.

### 6.2 Update `core/__init__.py`

```python
# Core module initialization
from . import settings
from . import arena
from . import discovery
from . import parser
from . import counter
from . import judge
```

(Keep `parser` so old `from . import parser`-style and `core.parser` paths keep
working. Order: settings → arena → discovery → parser, matching the dependency
direction.)

✅ **Checkpoint D (the big one):**
```bash
python -c "from core.parser import aggregate_files, find_project_root, generate_tree, load_ignore_patterns, initialize_environment, read_file_entries, resolve_output_dir, resolve_models_dir, discover_files_txt_with_directives, resolve_arena_dir, load_settings, save_settings, display_settings, migrate_old_outputs, sync_paste_attachments, build_arena_plan, ArenaAssignment, ArenaDirective, read_file_paths, should_ignore, stream_file_content, parse_file_entry; print('all imports OK')"
python -m py_compile aggregator.py aggregator_gui.py aggregator_tui.py renumber_arenas.py core/parser.py core/settings.py core/arena.py core/discovery.py
```
Both must succeed. If the first fails, a symbol is missing from the shim
re-exports — add it.

---

## 7. Phase E — Add `--status` to `aggregator.py`

This is the second prompt's feature. It must **print state and exit before any
aggregation/migration** (token-cheap, side-effect-free).

### 7.1 New CLI flags (in `main()`, in the existing `argparse` block)

```python
_ = parser.add_argument(
    "--status",
    action="store_true",
    help="Print a compact project-state snapshot for AI agents and exit.",
)
_ = parser.add_argument(
    "--json",
    action="store_true",
    help="With --status: emit JSON to stdout (for programmatic use).",
)
_ = parser.add_argument(
    "-q", "--quiet",
    action="store_true",
    help="With --status: print only the next arena number on one line.",
)
```

> Name clash warning: the `argparse.ArgumentParser` local variable is also named
> `parser`. The CLI already does this (see `aggregator.py` `main()`). Keep the
  `argparse` object named `parser` to match existing style; the `--status`
  flags above use that local `parser`.

### 7.2 Handle `--status` FIRST in `main()`, right after root resolution

Insert this **immediately after** `init_root = ...` and **before** the
`--settings` check (or right after it — either is fine, but it must run before
`migrate_old_outputs` / aggregation):

```python
# --- --status: cheap snapshot for AI agents, then exit ----------------
show_status = cast(bool, args.status)
if show_status:
    settings = load_settings(init_root)
    output_dir = resolve_output_dir(init_root, settings)
    arenas_dir = output_dir / "arenas"
    inputs_dir_str = str(settings.get("inputs_dir", ".context/inputs"))
    inputs_dir = init_root / inputs_dir_str
    state = get_latest_state(arenas_dir, inputs_dir)

    if cast(bool, args.quiet):
        print(f"{state['next_number']:03d}" if state["next_number"] else "001")
        return

    if cast(bool, args.json):
        import json
        print(json.dumps(state, indent=2, ensure_ascii=False))
        return

    # Human-readable block (kept intentionally short to save agent tokens)
    print("--- PROJECT STATE ---")
    print(f"last_arena   : {state['last_arena'] or '(none)'}")
    print(f"next_number  : {state['next_number']:03d}" if state["next_number"] else "next_number  : 001")
    print(f"total_arenas : {state['total_arenas']}")
    if state["latest_activity_arena"]:
        print(f"last_activity: {state['latest_activity_arena']} ({state['latest_activity_time']})")
    print(f"total_inputs : {state['total_inputs']}")
    if state["latest_input"]:
        print(f"latest_input : {state['latest_input']} ({state['latest_input_time']})")
    return
```

Add `get_latest_state` to the existing `from core.parser import (...)` block at
the top of `aggregator.py` (it's re-exported by the shim, so this works without
touching the new module path):

```python
from core.parser import (
    ...,
    get_latest_state,   # ← add this line
)
```

### 7.3 Expected output example

Running `python aggregator.py --status` on the current `context_output/arenas/`
(9 arenas, highest `009-logic`) should print roughly:
```
--- PROJECT STATE ---
last_arena   : 009-logic
next_number  : 010
total_arenas : 9
last_activity: 009-logic (2026-07-01 22:28)
total_inputs : 8
latest_input : <newest>.txt (...)
```

`-q` → `010`. `--json` → the dict from `get_latest_state`.

✅ **Checkpoint E:** `python aggregator.py --status`, `python aggregator.py --status -q`,
`python aggregator.py --status --json` all run and exit without doing any
aggregation (no new files created in `context_output/`).

---

## 8. Phase F (optional but recommended) — breadcrumb cache

To harden against git-checkout / folder-copy timestamp loss, write a tiny
breadcrumb after a **successful** aggregation run and prefer it for the "when"
fields. Numbering still always comes from the live `NNN-` scan.

### 8.1 Write helper in `core/discovery.py`

```python
def write_state_breadcrumb(
    context_dir: Path, arenas_dir: Path, inputs_dir: Path | None = None
) -> None:
    """Persist a one-line JSON snapshot of state into .context/last_arena.json.

    Safe to call every run; overwrites in place. Never raises — breadcrumb is
    best-effort only.
    """
    import json
    state = get_latest_state(arenas_dir, inputs_dir)
    state["updated_at"] = _dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    try:
        context_dir.mkdir(parents=True, exist_ok=True)
        (context_dir / "last_arena.json").write_text(
            json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    except OSError:
        pass
```

### 8.2 Call it at the END of `aggregator.py`'s `main()`

After the final `print(f"\nDone. Outputs written to: {output_dir}")`:
```python
from core.parser import write_state_breadcrumb  # add to top-level imports
write_state_breadcrumb(init_root / ".context", output_dir / "arenas", init_root / str(settings.get("inputs_dir", ".context/inputs")))
```
Re-export `write_state_breadcrumb` from the parser shim too (Phase D 6.1 list).
This phase is **optional** — if timeboxed, ship Phases A–E and skip F; the scan
path is fully functional on its own.

---

## 9. Verification matrix (run ALL before declaring done)

| # | Command | Expected |
|---|---|---|
| 1 | `python -m py_compile core/settings.py core/arena.py core/discovery.py core/parser.py aggregator.py aggregator_gui.py aggregator_tui.py renumber_arenas.py` | exit 0, no output |
| 2 | `python -c "import core.settings, core.arena, core.discovery, core.parser; print('ok')"` | prints `ok` |
| 3 | The Checkpoint D import-all line | prints `all imports OK` |
| 4 | `python -c "from core.parser import ArenaDirective; print(ArenaDirective(number=6, name='x'))"` | prints the dataclass repr |
| 5 | `python -c "from core.arena import build_arena_plan, ArenaDirective; print(build_arena_plan([], {}))"` | prints `([], [])` |
| 6 | `python -c "from core.discovery import get_latest_state; from pathlib import Path; print(get_latest_state(Path('context_output/arenas'), Path('.context/inputs')))"` | dict with `total_arenas: 9`, `next_number: 10` |
| 7 | `python aggregator.py --status` | state block, exits, no new arena dirs created |
| 8 | `python aggregator.py --status -q` | `010` |
| 9 | `python aggregator.py --status --json` | valid JSON |
| 10 | `python renumber_arenas.py .` (dry-run) | still works (idempotent: `Renames planned: ...`) |
| 11 | `python aggregator.py` (full run) | completes as before; outputs still land in `context_output/arenas/` |
| 12 | After #11, re-run #7 | numbers updated correctly |

---

## 10. Guardrails & common pitfalls 🚧

1. **Never rename a public symbol.** `discover_files_txt_with_directives`,
   `build_arena_plan`, `resolve_arena_dir`, etc. keep their exact names. Only
   their *location* changes.
2. **`from __future__ import annotations` must be the first non-docstring line**
   in every new module (it already is in parser.py).
3. **Encoding fix block** (`sys.stdout.reconfigure(...)`) is only in the GUI/CLI
   entrypoints, NOT in core modules. Do not copy it into `core/*.py`.
4. **`generate_tree`** still does `from core.counter import count_lines` locally
   inside the function — leave that lazy import exactly where it is (avoids an
   import cycle). Same for `aggregate_files`.
5. **`sync_paste_attachments`** has `import shutil` *inside* the function. Keep
   it local — do not hoist to module top.
6. **Do not move `_DEFAULT_IGNORE` into discovery and also leave it in parser.**
   Pick discovery (per this plan) and delete from parser.
7. **The `argparse` local variable named `parser` shadows the module concept.**
   This is pre-existing in `aggregator.py`. When adding `--status` flags, use
   the existing local `parser` variable; do not introduce a new name.
8. **`get_latest_state` must never raise** on a missing/empty arenas dir — it
   returns zeros/None. Guard every `.stat()` with try/except as shown.
9. **Re-export names are "unused" on purpose.** Do not let a linter talk you
   into removing the shim re-imports in `core/parser.py`.
10. **Windows paths:** all `Path` usage stays as-is. No string concatenation of
    paths.

---

## 11. Definition of Done ✅

- [ ] `core/settings.py`, `core/arena.py`, `core/discovery.py` exist and compile.
- [ ] `core/parser.py` is slimmed and re-exports every name from §0's table.
- [ ] `core/__init__.py` imports the new submodules.
- [ ] `aggregator.py` supports `--status`, `--status -q`, `--status --json`.
- [ ] All 12 checks in §9 pass.
- [ ] No existing behavior changed: `aggregator.py` full run still produces the
      same outputs in the same places.
- [ ] (Optional) breadcrumb written after runs.

---

## 12. Rollback

The refactor is intentionally low-risk because of the shim. If something is
broken and you must roll back:
```bash
git checkout -- core/parser.py core/__init__.py aggregator.py
rm -f core/settings.py core/arena.py core/discovery.py
```
The four caller files were never edited, so reverting these alone restores the
working state. (The `--status` feature is lost on rollback — it only touches
`aggregator.py`.)

---

## 13. Execution order summary (do exactly this)

1. **Phase A** → create `core/settings.py`, compile-check.
2. **Phase B** → create `core/arena.py`, compile-check.
3. **Phase C** → create `core/discovery.py` (+ `get_latest_state`), compile-check.
4. **Phase D** → slim `core/parser.py`, add shim re-exports, update `__init__.py`, run Checkpoint D.
5. **Phase E** → add `--status` to `aggregator.py`, run Checkpoints E.
6. **Phase F** (optional) → breadcrumb.
7. Run the **full §9 verification matrix**.
8. Report which checkpoints passed/failed with the actual command output.

Stop and ask before deviating from the module layout in §2.
