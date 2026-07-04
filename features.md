# Context Tool — Feature Structure

CLI tool that aggregates source files for LMArena blind pairwise comparisons.

## Directory Structure (v3+ Flat Layout)

```
project/
├── .context/
│   ├── settings.json          # persistent preferences
│   ├── ignore                 # user-defined ignore patterns (NOT .contextignore)
│   ├── inputs/                # input manifests (legacy v1 discovery tier)
│   │   ├── UI/
│   │   │   ├── AdminPage.txt  # found as "UI-AdminPage"
│   │   │   └── HomePage.txt   # found as "UI-HomePage"
│   │   ├── API/
│   │   │   └── UserAuth.txt   # found as "API-UserAuth"
│   │   ├── Common/
│   │   │   └── Types.txt      # found as "Common-Types"
│   │   └── fix-navbar-bug.txt # compatible flat structure
│   └── last_arena.json        # state breadcrumb (auto-written each run)
├── context_output/            # all generated outputs
│   ├── arenas/                # per-input arena folders (auto-numbered)
│   │   ├── 001-UI-AdminPage/  # v3+ flat: every file carries the NNN- prefix
│   │   │   ├── 001-UI-AdminPage.txt  # input (self-contained copy)
│   │   │   ├── 001-context.md        # aggregated source code
│   │   │   ├── 001-arena.md          # model comparison
│   │   │   ├── 001-prompt.txt        # prompt sent to models
│   │   │   ├── 001-A.txt             # Model A response
│   │   │   ├── 001-B.txt             # Model B response
│   │   │   ├── 001-A_NOTES.md        # optional notes for Model A
│   │   │   └── ARCHIVE/              # archived responses
│   │   ├── 002-UI-HomePage/
│   │   ├── 003-API-UserAuth/
│   │   └── 004-Common-Types/
│   ├── structure/
│   │   └── structure.txt       # project tree (centralized)
│   └── tmp/
│       └── paste-attachments/  # paste-attachments archival output
├── files.txt                   # fallback input (CWD, for quick one-off runs)
├── .env                        # GEMINI_API_KEY (tool root, not project)
└── aggregator.py               # main script
```

---

## Scenarios

### Scenario 1: First Run (no settings, no .context/)

```
$ python aggregator.py

→ Creates .context/settings.json with defaults
  "Created .context/settings.json — edit your preferences or delete to reset."
→ Creates .context/ignore with default template (when use_default_ignore=true)
→ Creates files.txt if missing
→ Reads settings.json → uses defaults
→ Processes files.txt
→ Outputs to context_output/
```

### Scenario 2: Normal Run (settings exist)

```
$ python aggregator.py

→ Reads .context/settings.json
→ Skips all prompts (gemini_judge=false, compact_mode=false, etc.)
→ Three-tier input discovery (see below)
→ For each input file:
   - Generates NNN-context.{md,txt} (aggregated source code)
   - Generates NNN-arena.{md,txt} (model comparison)
→ Generates structure.txt
→ Merges A_NOTES.md, B_NOTES.md if they exist
→ Writes .context/last_arena.json state breadcrumb
→ Done. No prompts.
```

### Scenario 2b: Three-Tier Input Discovery

```
Tier 1 (Primary): v3 arena-dir scan
  → Scans <output_dir>/arenas/ for NNN-<name>/ directories
  → Matches input file exactly as NNN-<name>.txt
  → Deduplicates by resolved path

Tier 2 (Legacy v1): .context/inputs/*.txt (recursive)
  → Each file generates one arena
  → Arena name from relative path: UI/AdminPage.txt → UI-AdminPage

Tier 3 (Oldest): CWD files.txt / files_*.txt
  → Skipped when missing or empty (prevents blocking Tier 1)
```

### Scenario 2c: Flexible files.txt Format

```
files.txt contains:
# Bug in navbar layout
# The CSS grid is breaking on mobile

C:/proj/src/components/Navbar.tsx
C:/proj/src/components/Navbar.module.css
C:/proj/src/layouts/MainLayout.tsx:45-80

# TODO: also check the responsive breakpoints
# The issue only happens on screens < 768px

→ Parser skips # comment lines
→ Parser skips blank lines
→ Parser extracts only valid file paths:
   - C:/proj/src/components/Navbar.tsx (full file)
   - C:/proj/src/components/Navbar.module.css (full file)
   - C:/proj/src/layouts/MainLayout.tsx:45-80 (snippet)
→ Comments/notes are ignored, tool works normally
→ Users can write free text without breaking anything
```

### Scenario 3: Interactive Run (--interactive flag)

```
$ python aggregator.py --interactive

→ Reads settings.json as defaults
→ Shows all prompts (Enter=skip, Space=enable):
   1. "Run Gemini auto-comparison? [Enter=skip, Space=run]: "
   2. "Reduce tokens? Compact mode [Enter=skip, Space=enable]: "
   3. "Archive model responses? [Enter=no, Space=archive]: "
   4. "How many models? [Enter=2, Space=4]: "
   5. "Output format? [Enter=.md, Space=.txt]: "
→ User choices are SAVED back to settings.json
→ Processes as normal
```

### Scenario 4: Multi-File Run

```
$ python aggregator.py

→ Three-tier discovery finds:
   Tier 1: <output_dir>/arenas/001-fix-navbar.txt, 002-fix-header.txt
   Tier 2: .context/inputs/UI/AdminPage.txt → 003-UI-AdminPage
   Tier 3: CWD files.txt, files_1.txt
→ For each input:
   001-fix-navbar/  → 001-context.md, 001-arena.md
   002-fix-header/  → 002-context.md, 002-arena.md
   003-UI-AdminPage/ → 003-context.md, 003-arena.md
   files/           → files-context.md, files-arena.md
   files_1/         → files_1-context.md, files_1-arena.md
```

### Scenario 5: Archive Flow

```
$ python aggregator.py --interactive

→ Prompt 3: "Archive model responses? [Space=archive]"
→ User presses Space
→ Script archives per-arena:
   001-ARCHIVE/001-A_20260704_143022.txt
   001-ARCHIVE/001-B_20260704_143022.txt
→ Re-creates fresh templates: 001-A.txt, 001-B.txt
→ Re-asks: "How many models? [Enter=2, Space=4]"
→ User can now pick different subset from archive
→ Generates arena.md from selected models
```

### Scenario 6: Custom Output Directory

```
$ python aggregator.py --output my_folder

→ All outputs go to my_folder/ instead of context_output/
→ settings.json "output_dir" is overridden by flag
```

### Scenario 7: Notes Auto-Merge

```
001-A_NOTES.md contains:
"Model A used a recursive approach which is cleaner."

→ In 001-arena.md, under Model A's response:
   ### Notes
   Model A used a recursive approach which is cleaner.

→ If A_NOTES.md doesn't exist → no Notes section for A
```

### Scenario 8: Compact Mode

```
settings.json: "compact_mode": true

→ arena.md generated with:
   - No "### Notes" sections
   - Collapsed blank lines
   - Trimmed whitespace
→ Token count reduced ~15-20%
```

### Scenario 9: Arena Directives (Target Arena Pinning)

```
001-fix-navbar.txt first line:
# Target Arena: 005-fix-navbar

→ Arena is created as 005-fix-navbar/ (not auto-numbered)
→ Filename remains source of truth for arena name
→ Conflict resolution: warn_and_shift (default)
   - If #005 is taken, shifts to next free number
   - Prints warning on stderr
```

### Scenario 10: Paste-Attachments Archival

```
settings.json: "paste_attachments_enabled": true

→ After processing, scans <root>/tmp/paste-attachments/<today>/*.txt
→ Slugifies each file's first two sentences into a safe filename
→ Copies (or moves) into <output_dir>/tmp/paste-attachments/<today>/
→ Enables long-text pastes to be searchable in output directory
```

### Scenario 11: Status Snapshot for AI Agents

```
$ python aggregator.py --status

→ Prints compact project-state snapshot:
   last_arena   : 004-fix-header
   next_number  : 005
   total_arenas : 4
   last_activity: 004-fix-header (2026-07-04 14:30)
   total_inputs : 2
   latest_input : AdminPage.txt (2026-07-04 12:00)

$ python aggregator.py --status --json
→ Same data as JSON to stdout

$ python aggregator.py --status -q
→ Prints only the next arena number (e.g. "005")
```

### Scenario 12: Settings Inspection

```
$ python aggregator.py --settings

→ Prints active settings file path
→ Prints current settings content
→ Prints settings schema
→ Exits without processing
```

### Scenario 13: --status State Breadcrumb

```
→ Every run writes .context/last_arena.json
→ Contains: last_arena, next_number, total_arenas,
   latest_activity_arena, latest_activity_time,
   total_inputs, latest_input, latest_input_time
→ Token-cheap cache for AI agents
```

---

## CLI Flags

| Flag | Effect |
|------|--------|
| `--interactive` | Show all prompts, save choices back to settings.json |
| `--output DIR` | Custom output directory (overrides settings) |
| `--settings` | Print active settings file path, content, and schema; then exit |
| `--status` | Print compact project-state snapshot for AI agents; then exit |
| `--json` | With --status: emit JSON to stdout |
| `-q` / `--quiet` | With --status: print only the next arena number |
| `[root]` | Optional positional arg: project root directory (defaults to CWD/auto-detect) |
| (no args) | Read settings.json, three-tier discovery, run silently |

## Settings.json Keys

| Key | Default | Options |
|-----|---------|---------|
| `output_dir` | `"context_output"` | any folder name |
| `output_format` | `"md"` | `"md"` or `"txt"` |
| `model_count` | `2` | `2` or `4` |
| `gemini_judge` | `false` | `true` / `false` |
| `compact_mode` | `false` | `true` / `false` |
| `archive` | `false` | `true` / `false` |
| `archive_dir` | `"ARCHIVE"` | any folder name |
| `paste_attachments_enabled` | `false` | `true` / `false` |
| `paste_attachments_source_dir` | `"tmp/paste-attachments"` | any folder name |
| `paste_attachments_target_subdir` | `"tmp/paste-attachments"` | any folder name |
| `paste_attachments_date_format` | `"%Y-%m-%d"` | any strftime format |
| `paste_attachments_copy_mode` | `"copy"` | `"copy"` or `"move"` |
| `respect_target_arena_directive` | `true` | `true` / `false` |
| `target_arena_directive_prefix` | `"# Target Arena:"` | any prefix string |
| `on_arena_number_conflict` | `"warn_and_shift"` | `"warn_and_shift"`, `"fail"`, `"silent"` |
| `use_default_ignore` | `true` | `true` / `false` |

**Deprecated keys** (auto-removed from legacy settings files):
`inputs_dir`, `aggregate_filename`, `compare_filename`

## Ignore Patterns

| File | Purpose |
|------|---------|
| `.context/ignore` | User-defined ignore patterns (one per line, # comments) |
| `_DEFAULT_IGNORE_TEMPLATE` | Built-in patterns in core/settings.py (written when `use_default_ignore=true`) |

When `use_default_ignore=true` (default):
- Auto-creates `.context/ignore` with the default template if missing
- Rewrites if file still carries legacy description

When `use_default_ignore=false`:
- Never creates, writes, or overwrites `.context/ignore`
- Full project tree (including `.context/` and `context_output/`) shows in `structure.txt`

## Output Formats

| Format | Aggregate File | Compare File | Notes Files | Use Case |
|--------|---------------|-------------|-------------|----------|
| `.md` (default) | `NNN-context.md` | `NNN-arena.md` | `NNN-A_NOTES.md` | Markdown with formatting |
| `.txt` | `NNN-context.txt` | `NNN-arena.txt` | `NNN-A_NOTES.txt` | Plain text, fewer tokens |

## Edge Cases

| Case | Behavior |
|------|----------|
| Empty `files.txt` | Create empty templates (context.{ext}, arena.{ext}) in arena dir |
| Invalid `settings.json` | Fall back to defaults, print warning every run |
| Empty `settings.json` | Print: "Use context skill with AI model to set up preferences" |
| Missing `settings.json` | Auto-create with defaults |
| `model_count=4` but only 2 files | Auto-create empty C.txt, D.txt, print "Please paste their responses" |
| Archive timestamp collision | Append `_1`, `_2`, etc. |
| `context_output/` has old files | In interactive mode: prompt merge; non-interactive: default to overwriting |
| Gemini API key not set | Warn and skip judge (don't error) |
| Notes extension mismatch | Only match chosen output extension |
| Old files in CWD | Migrate to output_dir (v3+ flat layout) |
| Nested subdirectories in inputs | Auto-discover recursively (Tier 2), flatten to category-name format |
| v2 per-file folder layout | Auto-flatten to v3+ flat layout on every run (idempotent) |
| `# Target Arena:` number conflict | Warn and shift to next free number (configurable) |
| Cross-platform path resolution | Normalize Windows/POSIX separators, try suffix overlap with CWD |
| BOM-encoded files | Handle UTF-8-BOM and UTF-16 input files |

## Project Root Detection

The tool detects the project root using `find_project_root()` in core/parser.py:
- Starts from the first file path in files.txt
- Searches parent directories for markers: `.git`, `package.json`, `pyproject.toml`, `requirements.txt`, `src`
- Falls back to CWD if no markers found

## API Key Location

The `.env` file with `GEMINI_API_KEY` is searched in three locations (in order):
1. The project root (root_dir)
2. The current working directory
3. The tool's own root directory (where aggregator.py lives)

Non-interactive: returns `None` if key not found; caller skips judge.

## Interfaces

| Alias | Interface | Use Case |
|-------|-----------|----------|
| `agg` | CLI (Direct) | Run from files.txt with auto-detect project root |
| `aggf` | CLI (Current) | Run with CWD as root |
| `aggt` | TUI (Terminal UI) | Interactive file browsing in terminal (requires `textual`) |
| `aggg` | GUI (Window) | Tkinter GUI with dark mode, no dependencies |

## Auxiliary Scripts

| Script | Purpose |
|--------|---------|
| `install.py` | Install optional dependencies (tiktoken, textual) |
| `renumber_arenas.py` | One-time migration: rename arena directories to match `# Target Arena:` directives |
| `cleanup_first_heart.py` | Migrate legacy arena input files to v3 flat layout |

## Code Snippets & Important Structures

```
# In files.txt or .context/inputs/*.txt:

/path/to/file.py                    → full file (FILE header)
/path/to/file.py:10-20              → snippet (SNIPPET header)
/path/to/file.py:5-10,25-30         → multi-range snippet (..., separated)
!/path/to/types.ts:1-5              → important structure (IMPORTANT STRUCTURE header)
```

- Full files: `# --- FILE: src/utils.py (150 lines) ---`
- Snippets: `# --- SNIPPET: src/utils.py [10-20] (11 lines) ---`
- Important: `# --- IMPORTANT STRUCTURE: src/types.ts [1-5] (5 lines) ---`

## Token Counting

- Uses `tiktoken` (cl100k_base) if installed
- Fallback: `max(char_count / 4, word_count * 1.3)`
- Displayed after each arena aggregation
