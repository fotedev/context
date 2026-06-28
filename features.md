# Context Tool — Feature Structure

CLI tool that aggregates source files for LMArena blind pairwise comparisons.

## Directory Structure (after first run)
        
```
project/
├── .context/
│   ├── settings.json          # persistent preferences
│   ├── ignore                 # user-defined ignore patterns
│   └── inputs/                # input manifests (primary discovery location)
│       ├── UI/                # ← Category subdirectory (new feature)
│       │   ├── AdminPage.txt  # ← Found as "UI-AdminPage"
│       │   └── HomePage.txt   # ← Found as "UI-HomePage"
│       ├── API/               # ← Another category subdirectory
│       │   └── UserAuth.txt   # ← Found as "API-UserAuth"
│       ├── Common/            # ← Common category
│       │   └── Types.txt      # ← Found as "Common-Types"
│       └── fix-navbar-bug.txt # Compatible flat structure
├── context_output/            # all generated outputs
│   ├── arenas/                # per-input arena folders (auto-numbered)
│   │   ├── 001-UI-AdminPage/  # ← Arena with category name
│   │   │   ├── arena.txt      # aggregated code
│   │   │   ├── structure.txt  # project tree
│   │   │   ├── compare.md     # model comparison (or .txt)
│   │   │   └── answers/       # model responses + prompt
│   │   │       ├── prompt.txt
│   │   │       ├── A.txt
│   │   │       └── B.txt
│   │   │       └── ARCHIVE/   # archived responses
│   │   ├── 002-UI-HomePage/
│   │   ├── 003-API-UserAuth/
│   │   └── 004-Common-Types/
│   └── models/                # legacy models directory (migrated from root)
│       ├── A.txt
│       ├── B.txt
│       └── prompt.txt
├── files.txt                  # fallback input (CWD, for quick one-off runs)
├── .env                       # GEMINI_API_KEY (tool root, not project)
└── aggregator.py              # main script
```

---

## Scenarios

### Scenario 1: First Run (no settings, no .context/)

```
$ python aggregator.py

→ Creates .context/settings.json with defaults
  "Created .context/settings.json — edit your preferences or delete to reset."
→ Creates .contextignore with default template
→ Creates files.txt if missing
→ Reads settings.json → uses defaults
→ Processes files.txt
→ Outputs to context_output/
```

### Scenario 1b: Recursive Input Discovery (NEW)

```
.context/inputs/
├── UI/
│   ├── AdminPage.txt        # ← Found as "UI-AdminPage"
│   └── HomePage.txt         # ← Found as "UI-HomePage"
├── API/
│   └── UserAuth.txt         # ← Found as "API-UserAuth"
└── Common/
    └── Types.txt            # ← Found as "Common-Types"

→ Automatically discovers all .txt files in subdirectories
→ Each file generates a unique Arena with category prefix:
  001-UI-AdminPage/
  002-UI-HomePage/
  003-API-UserAuth/
  004-Common-Types/
```

### Scenario 2: Normal Run (settings exist)

```
$ python aggregator.py

→ Reads .context/settings.json
→ Skips all prompts (gemini_judge=false, compact_mode=false, etc.)
→ Discovers files*.txt (files.txt, files_1.txt, files_2.txt)
→ For each input file:
   - Generates arena_XXX.txt
   - Generates structure_XXX.txt
→ Generates compare.md (or .txt per settings)
→ Merges A_NOTES.txt, B_NOTES.txt if they exist
→ Done. No prompts.
```

### Scenario 2b: Flexible files.txt Format

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
→ Shows all prompts:
   1. "Run Gemini auto-comparison? [Enter=skip, Space=run]: "
   2. "Reduce tokens? Compact mode [Enter=skip, Space=enable]: "
   3. "Archive model responses? [Enter=no, Space=archive]: "
   4. "How many models? [Enter=2, Space=4]: "
   5. "Output format? [Enter=.md, Space=.txt]: "
→ User choices override settings.json (but don't save back)
→ Processes as normal
```

### Scenario 4: Multi-File Run

```
$ python aggregator.py

→ Discovers: files.txt, files_1.txt, files_2.txt
→ For each:
   files.txt    → context_output/arena.txt
                  context_output/structure.txt
   files_1.txt  → context_output/arena_1.txt
                  context_output/structure_1.txt
   files_2.txt  → context_output/arena_2.txt
                  context_output/structure_2.txt
→ Single compare.md for all (or per-file if preferred)
```

### Scenario 5: Archive Flow

```
$ python aggregator.py --interactive

→ Prompt 3: "Archive model responses? [Space=archive]"
→ User presses Space
→ Script saves:
   models/ARCHIVE/A_20260622_143022.txt
   models/ARCHIVE/B_20260622_143022.txt
→ Re-asks: "How many models? [Enter=2, Space=4]"
→ User can now pick different subset from archive
→ Generates compare.md from selected models
```

### Scenario 6: Custom Output Directory

```
$ python aggregator.py --output my_folder

→ All outputs go to my_folder/ instead of context_output/
→ settings.json "output_dir" is overridden by flag
```

### Scenario 6b: Web Server Interface

```bash
# Enhanced web interface with local server
$ web-svr

→ Launches a local web server on http://localhost:5000
→ Opens in browser automatically
→ Provides interactive folder selection for answer storage
→ Features direct code pasting buttons and text areas
→ Full tool control from browser interface
→ Supports cross-platform development workflows
```

**Web Server Features:**
- **Automatic .env setup**: Creates configuration with GEMINI_API_KEY
- **Interactive folder selection**: Browse and select answer storage location
- **Direct code pasting**: Multiple input methods (clipboard, drag-drop, text areas)
- **Real-time control**: Live tool execution and monitoring
- **Cross-platform support**: Works on Windows, macOS, Linux, and cloud IDEs
- **Responsive design**: Optimized for desktop and mobile browsers

### Scenario 7: Notes Auto-Merge

```
models/A_NOTES.txt contains:
"Model A used a recursive approach which is cleaner."

→ In compare.md, under Model A's response:
   ### Notes
   Model A used a recursive approach which is cleaner.

→ If A_NOTES.txt doesn't exist → no Notes section for A
```

### Scenario 8: Compact Mode

```
settings.json: "compact_mode": true

→ compare.md generated with:
   - No "### Notes" sections
   - Collapsed blank lines
   - Trimmed whitespace
→ Token count reduced ~15-20%
```

### Scenario 9: No Model Files Exist

```
$ python aggregator.py

→ models/ is empty (no A.txt, B.txt)
→ Auto-creates: A.txt, B.txt (empty)
→ Prompts: "How many model files to create?"
→ User enters 4 → creates A.txt, B.txt, C.txt, D.txt
```

---

## CLI Flags

| Flag | Effect |
|------|--------|
| `--interactive` | Show all prompts, ignore settings.json preferences |
| `--output DIR` | Custom output directory |
| (no args) | Read settings.json, auto-discover files*.txt, run silently |

## Settings.json Keys

| Key | Default | Options |
|-----|---------|---------|
| `output_dir` | `"context_output"` | any folder name |
| `output_format` | `"md"` | `"md"` or `"txt"` |
| `model_count` | `2` | `2` or `4` |
| `gemini_judge` | `false` | `true` / `false` |
| `compact_mode` | `false` | `true` / `false` |
| `archive` | `false` | `true` / `false` |
| `archive_dir` | `"models/ARCHIVE"` | any folder name |
| `inputs_dir` | `".context/inputs"` | any folder name |

## Ignore Patterns

| File | Purpose |
|------|---------|
| `.contextignore` | User-defined ignore patterns (one per line, # comments) |
| `_DEFAULT_IGNORE` | Built-in patterns in parser.py (merged with .contextignore) |

## Output Formats

| Format | Compare File | Notes Files | Use Case |
|--------|-------------|-------------|----------|
| `.md` (default) | `compare.md` | `A_NOTES.md` | Markdown with formatting |
| `.txt` | `compare.txt` | `A_NOTES.txt` | Plain text, fewer tokens |

## Edge Cases

| Case | Behavior |
|------|----------|
| Empty `files.txt` | Create empty templates (arena.txt, structure.txt, compare.md) in output folder |
| Invalid `settings.json` | Fall back to defaults, print warning every run |
| Empty `settings.json` | Print: "Use context skill with AI model to set up preferences" |
| Missing `settings.json` | Auto-create with defaults |
| `model_count=4` but only 2 files | Auto-create empty C.txt, D.txt, prompt user to paste |
| Archive timestamp collision | Append `_1`, `_2`, etc. |
| `context_output/` has old files | Warn: "Merge? [Enter=merge, Space=skip]" |
| Gemini API key not set | Warn and skip judge (don't error) |
| Notes extension mismatch | Only match chosen output extension |
| Old files in CWD | Warn: "Clean? [Enter=clean, Space=skip]" |
| Nested subdirectories in inputs | Auto-discover recursively, flatten to category-name format |

## Project Root Detection

The tool detects the project root using `find_project_root()` in parser.py:
- Starts from the first file path in files.txt
- Searches parent directories for markers: `.git`, `package.json`, `pyproject.toml`, `requirements.txt`, `src`
- Falls back to CWD if no markers found

## API Key Location

The `.env` file with `GEMINI_API_KEY` lives in the **tool root directory** (where aggregator.py is), NOT in the user's project directory. This keeps the tool's config separate from the user's codebase.
