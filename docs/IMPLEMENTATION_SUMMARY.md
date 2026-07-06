# Implementation Summary

## Overview

This document summarizes the implementation of the context tool — a CLI tool that aggregates source files for LMArena blind pairwise comparisons. The tool supports automated workflow management with arena-based output organization, AI judge integration, and flexible input discovery.

## Current Architecture

### Core Module Structure

The core logic lives in `core/` with focused modules:

```
core/
├── __init__.py        # Package initialization, imports all submodules
├── settings.py        # Settings management + paste-attachments archival
├── discovery.py       # File discovery, ignore patterns, arena state snapshots
├── arena.py           # Arena directive parsing, conflict resolution, directory resolution
├── parser.py          # Path parsing, aggregation, tree generation, output migration (backward-compat shim)
├── counter.py         # Token counting using tiktoken
└── judge.py           # Gemini AI judge integration, model response collection
```

**Dependency Direction (no cycles):**
- `settings.py` ← no internal imports
- `arena.py` ← no internal imports
- `discovery.py` ← imports from `arena.py` and `settings.py`
- `parser.py` ← imports from `settings.py`, `discovery.py`, `arena.py`, `counter.py`

### Entry Points

| Command | File | Interface |
|---------|------|-----------|
| `agg` | `aggregator.py` | CLI (Direct) — reads from CWD, auto-detects project root |
| `aggf` | `aggregator.py .` | CLI (Current Dir) — treats CWD as root |
| `aggt` | `aggregator_tui.py` | TUI (Terminal UI) — interactive file browsing |
| `aggg` | `aggregator_gui.py` | GUI (Tkinter Window) — dark mode support |

---

## Key Implementations

### 1. Settings Management (`core/settings.py`)

**Default Settings Schema:**
```python
DEFAULT_SETTINGS = {
    "output_dir": "context_output",
    "output_format": "md",           # "md" or "txt"
    "model_count": 2,
    "gemini_judge": False,
    "compact_mode": False,
    "archive": False,
    "archive_dir": "ARCHIVE",
    "paste_attachments_enabled": False,
    "paste_attachments_source_dir": "tmp/paste-attachments",
    "paste_attachments_target_subdir": "tmp/paste-attachments",
    "paste_attachments_date_format": "%Y-%m-%d",
    "paste_attachments_copy_mode": "copy",
    "respect_target_arena_directive": True,
    "target_arena_directive_prefix": "# Target Arena:",
    "on_arena_number_conflict": "warn_and_shift",
    "use_default_ignore": True,
}
```

**Features:**
- Auto-creates `.context/settings.json` with defaults on first run
- Merges user settings with defaults for forward compatibility
- Migrates deprecated keys (`inputs_dir`, `aggregate_filename`, `compare_filename`)
- `--settings` CLI flag displays current settings and schema

### 2. File Discovery (`core/discovery.py`)

**Three-tier discovery (all merged, no short-circuit):**

1. **Tier 1: v3 arena-dir scan (primary, prefix-aware)** — Scans `<root>/<output_dir>/arenas/` for `NNN-<name>/` directories. Input file matched exactly as `<prefix>-<arena_name>.txt`.

2. **Tier 2: legacy `.context/inputs/*.txt` (v1 style, recursive)** — Each file becomes one arena. Arena name derived from relative path (e.g., `UI/AdminPage.txt` → `UI-AdminPage`).

3. **Tier 3: legacy CWD `files.txt` / `files_*.txt` (oldest style)** — Skipped when file is missing or empty.

**Ignore Pattern Management:**
- Reads patterns from `.context/ignore`
- `use_default_ignore` setting controls auto-creation of default patterns
- Default patterns include: `.git`, `node_modules`, `venv`, `__pycache__`, `context_output`, `.context`, etc.
- Default patterns also include legacy unprefixed arena files (A-F.txt, arena.md, context.md, etc.)
- LRU-cached glob matching for performance

**Structural Arena-File Rule (`_is_unprefixed_arena_file`):**
- Filters unprefixed v2 legacy files from tree/structure.txt regardless of user ignore settings
- Applies even when `use_default_ignore` is False (structural invariant)
- Only affects files inside `<output_dir>/arenas/<NNN-name>/` directories
- Files must carry the arena's `NNN-` prefix to pass the filter
- Subdirectories (like ARCHIVE/) are exempt; their contents are filtered individually

### 3. Arena Directive Parsing (`core/arena.py`)

**`# Target Arena:` directive:**
- First non-empty line of input file can specify: `# Target Arena: 006-AdminDashboard`
- Pins the arena number; filename remains source-of-truth for arena name
- Case-insensitive prefix matching
- Conflict resolution: `warn_and_shift` (default), `fail`, or `silent`

**`build_arena_plan()` algorithm:**
1. Split inputs into explicit (have directive) and implicit (no directive)
2. Sort each group alphabetically by filename
3. Assign explicit inputs their directive numbers (resolve conflicts)
4. Assign implicit inputs smallest free numbers after highest explicit

### 4. Arena-Based Output Organization

**v3+ flat layout (current):**
```
context_output/
├── arenas/
│   ├── 001-fix-navbar-bug/
│   │   ├── 001-fix-navbar-bug.txt    # input (prefixed)
│   │   ├── 001-context.md            # aggregated code (prefixed)
│   │   ├── 001-arena.md              # LMArena comparison (prefixed)
│   │   ├── 001-prompt.txt            # prompt (prefixed)
│   │   ├── 001-A.txt                 # model A response (prefixed)
│   │   ├── 001-B.txt                 # model B response (prefixed)
│   │   └── 001-A_NOTES.md            # model A notes (prefixed)
│   └── 002-refactor-api/
│       └── ...
└── models/                            # legacy models directory (migrated from root)
```

**Prefixed filename helpers:**
- `arena_filenames(arena_dir, output_format)` → dict with `input`, `context`, `arena`, `prompt`
- `arena_model_filename(arena_dir, letter)` → `NNN-Letter.txt`

### 5. Output Migration System

**Legacy CWD migration (`migrate_old_outputs`):**
- Moves legacy output files (`arena.txt`, `structure.txt`, `compare.md`) from CWD to `output_dir/`
- Moves `root/models/` to `output_dir/models/`
- Safety guard: skips if output dir already populated

**Per-file folder migration (`migrate_to_per_file_folders`):**
- Reorganizes flat outputs into v2 per-file folders (e.g., `arena/arena.txt`)
- Idempotent: re-running on already-migrated tree is a no-op

**Flat layout migration (`migrate_to_flat_layout`):**
- Phase 1: v2 → v3 flat (flatten subfolders into arena root)
- Phase 2: v3 → v3+ rename (`arena.txt` → `context.{ext}`, `compare.{ext}` → `arena.{ext}`)
- Phase 3: Cleanup unprefixed v3 leftovers (rename or deduplicate legacy files)
- Supports dry-run mode for preview

**Legacy file cleanup (`_cleanup_unprefixed_legacy_files`):**
- Reconciles unprefixed v2 leftovers against canonical v3+ prefixed names
- Renames orphaned unprefixed files to v3+ names (idempotent)
- Removes duplicates when content is byte-identical
- Warns when content differs (requires manual review)
- Never deletes prefixed files or divergent content

### 6. Paste-Attachments Archival

**Purpose:** Archive manually-pasted long text files into the output directory.

**Workflow:**
1. User pastes text into `tmp/paste-attachments/<date>/` folder
2. Tool copies/moves files to `output_dir/<target>/<date>/` with slugified filenames
3. Slug derived from first two sentences of content (casefolded, sanitized)

**Configuration:**
- `paste_attachments_enabled`: Master toggle
- `paste_attachments_source_dir`: Where to find pastes (default: `tmp/paste-attachments`)
- `paste_attachments_target_subdir`: Where to archive (default: `tmp/paste-attachments`)
- `paste_attachments_copy_mode`: `"copy"` or `"move"`

### 7. Gemini AI Judge Integration (`core/judge.py`)

**Features:**
- `.env` file loading with `GEMINI_API_KEY` detection
- Model response collection from `models/` directory or arena-specific directories
- Compact mode: removes `### Notes` sections, collapses blank lines, trims whitespace
- Notes auto-merge: inserts `A_NOTES.md`/`A_NOTES.txt` content under model responses
- Archive flow: saves timestamped copies before clearing for new round

**Edge Cases:**
- Missing API key: warns and skips judge (no crash)
- Notes extension mismatch: only matches chosen output extension
- Model count mismatch: auto-creates empty template files

### 8. Path Parsing and Aggregation

**Cross-platform path resolution:**
- Handles Windows/Linux path differences
- Suffix overlap detection for path mapping
- Drive letter normalization

**File entry parsing:**
- Full files: `/path/to/file.py`
- Line ranges: `/path/to/file.py:10-20`
- Multi-range snippets: `/path/to/file.py:5-10,25-30`
- Important structures: `!/path/to/types.ts:1-15`

**Streaming aggregation:**
- Memory-efficient streaming for large files
- Sorted range processing for non-contiguous snippets
- UTF-8/UTF-16/BOM encoding detection

### 9. Directory Tree Generation

**Features:**
- Recursive traversal with max depth limit (20)
- Symlink cycle prevention
- Line count per file using `count_lines()`
- Ignore pattern filtering

### 10. State Snapshot for AI Agents (`--status`)

**`get_latest_state()` returns:**
```python
{
    "last_arena": "003-fix-navbar",
    "next_number": 4,
    "total_arenas": 3,
    "latest_activity_arena": "002-refactor-api",
    "latest_activity_time": "2026-07-04 10:30",
    "total_inputs": 5,
    "latest_input": "fix-navbar.txt",
    "latest_input_time": "2026-07-04 09:15"
}
```

**`write_state_breadcrumb()`:**
- Persists JSON snapshot to `.context/last_arena.json`
- Best-effort only, never raises

---

## Backward Compatibility

**Existing users remain unaffected:**
- All CLI commands unchanged (`agg`, `aggf`, `aggt`, `aggg`)
- `core/parser.py` re-exports all public names for import compatibility
- Legacy `.contextignore` patterns still supported
- CWD `files.txt` fallback still works

**Migration paths:**
- `migrate_old_outputs()`: CWD outputs → `output_dir/`
- `migrate_to_per_file_folders()`: flat → v2 per-file layout
- `migrate_to_flat_layout()`: v2 → v3+ flat layout

---

## Configuration Precedence

```
Command Line Flags > Interactive Prompts (--interactive) > Settings File (.context/settings.json) > Hardcoded Defaults
```

---

## Testing and Validation

**Verification checklist:**
- [x] Three-tier file discovery (arena dirs, .context/inputs, CWD)
- [x] Arena directive parsing and conflict resolution
- [x] Prefixed filename generation
- [x] v3+ flat layout migration
- [x] Paste-attachments archival
- [x] Settings auto-creation and migration
- [x] Ignore pattern management with `use_default_ignore` toggle
- [x] Cross-platform path resolution
- [x] Encoding detection (UTF-8, UTF-16, BOM)
- [x] Backward compatibility with legacy imports
- [ ] Integration testing with actual tool execution
- [ ] Performance benchmarking
- [ ] Security review

---

## Future Enhancements

**Planned features:**
1. **Cost Estimator:** Calculate token cost based on API pricing (OpenAI, Anthropic, Google)
2. **Custom Judge Personas:** `--judge security` or `--judge performance` flags
3. **Incremental Context:** Only aggregate Git-modified files (staged/modified)
4. **Interactive HTML Report:** Dark mode HTML with code diff viewer

---

## File Organization

**Automatic arena naming:** `001-fix-navbar-bug` instead of just `fix-navbar-bug`

**Recursive discovery:** Supports nested input file organization in `.context/inputs/`

**Error handling:** Robust fallback mechanisms with graceful degradation

---

## Performance Considerations

- **Memory efficient:** Streaming for large file processing
- **LRU caching:** Glob pattern matching cached to reduce overhead
- **Lazy loading:** Only load necessary components
- **Token counting:** tiktoken with fallback estimation

---

## Conclusion

The context tool provides a robust CLI-based workflow for aggregating source files and comparing LMArena model outputs. The implementation features a well-structured modular architecture with backward compatibility, flexible configuration, and multiple migration paths for evolving the output layout over time.

**Key benefits:**
- **Modularity:** Focused modules with clear responsibilities
- **Flexibility:** Multiple input discovery methods and output formats
- **Extensibility:** Settings-driven configuration with forward compatibility
- **Reliability:** Comprehensive error handling and edge case management
