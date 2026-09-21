# File Aggregator - Complete Usage Guide

An advanced tool for collecting the contents of source files and code snippets, building a map of the project structure, and automatically comparing the outputs of different AI models using an intelligent judge. The tool is designed to be your perfect companion when using platforms like **LMArena**.

---

## Core Features

### 1. Intelligent Judge System (Gemini AI Judge Mode)
The **Gemini Flash API** is integrated to act as an "independent judge and evaluator" of model outputs:
- **Automatic evaluation:** the model inspects and compares the answers pasted into the `arena.{md,txt}` file.
- **Winner selection:** it analyzes the code carefully (efficiency, security, structure) and clearly states the **winning model** along with the technical reasons.

### 2. Smart Token Counter
- The tool counts the total number of tokens for the aggregated context file before it is sent.
- It relies on the `tiktoken` library for maximum accuracy, with a smart estimation fallback if it is not installed.

### 3. Advanced Code Snippet Support (Code Snippets & Structures)
The tool is not limited to collecting whole files — it also supports selecting precise parts of code via files in `.context/inputs/`:
- **Code snippets:** collect specific lines (e.g. `/path/to/file.py:10-20`).
- **Multi-range snippets:** collect several ranges from the same file separated by `...` (e.g. `/path/to/file.py:10-20,50-60`).
- **Important structures:** highlight structural parts of the code such as Types and Interfaces by prefixing an exclamation mark (e.g. `!/path/to/types.ts:1-15`).

### 4. Organized Output Structure (Arena-Based Output)
- Organized `arenas/` folders are created under `context_output/` for each input file.
- Each folder uses the format `NNN-<file-name>/` (e.g. `001-fix-navbar-bug/`).
- Existing folders are never overwritten — numbering always increments automatically.
- **Recursive search:** input files are discovered automatically inside subfolders of `.context/inputs/`.
- **Smart naming:** the subfolder path is merged with the file name to build the Arena name:
  - Example: `.context/inputs/UI/AdminPage.txt` → `010-UI-AdminPage/`
- **Target Arena directive:** you can pin the Arena number by adding a comment on the first line of the input file:
  ```
  # Target Arena: 006-AdminDashboard
  ```

### 5. Model Archiving
- Model responses can be archived in an `ARCHIVE/` folder inside each Arena while preserving the original template.
- Controlled via the `archive` setting in `.context/settings.json`.

### 6. Paste Attachments Archiving
- `.txt` files from `tmp/paste-attachments/<date>/` can be copied automatically into the output folder with smart naming based on the first two sentences of the file content.
- Controlled via the `paste_attachments_enabled` setting in `.context/settings.json`.

---

## Project Architecture

The tool's source code is split into separate modules for easier development and maintenance:

```text
context/
├── aggregator.py              # Main CLI entry point
├── aggregator_tui.py          # Interactive terminal UI (TUI) - requires textual
├── aggregator_gui.py          # Graphical interface (GUI) - Tkinter
├── install.py                 # Script to install optional libraries (tiktoken, textual)
├── renumber_arenas.py         # Migration tool to renumber Arena folders
├── core/
│   ├── __init__.py            # Package initialization
│   ├── parser.py              # Path parsing, aggregation, tree, re-exports
│   ├── arena.py               # Target Arena directives, number planning, conflict resolution
│   ├── discovery.py           # File discovery, ignore patterns, state snapshot
│   ├── settings.py            # Settings management, paste attachment archiving
│   ├── counter.py             # Token counting (tiktoken with fallback)
│   └── judge.py               # Gemini Flash API integration for judging and evaluation
├── gui/
│   ├── browser-extension/     # (archived - currently unused)
│   └── vscode-extension/     # (archived - currently unused)
├── skills/
│   └── migrate-to-flat-layout/
│       └── migrate_inputs.py  # Migration script
├── arena-context/
│   ├── SKILL.md               # Arena context skill
│   └── organize-root.md       # Root organization skill
├── .context/
│   ├── settings.json          # Persistent settings
│   ├── ignore                 # Custom ignore patterns
│   ├── inputs/                # Input files (primary discovery location)
│   └── last_arena.json        # Arena state snapshot (breadcrumb for AI agents)
├── .env                       # Gemini API key (at the tool root)
├── .env.example               # Template for the .env file
├── requirements.txt           # Optional requirements (tiktoken, textual)
└── context_output/            # Output folder (created automatically)
    ├── arenas/                # Organized Arena folders
    │   └── NNN-<name>/        # One folder per input
    │       ├── NNN-<name>.txt         # Original input file (preserved copy)
    │       ├── NNN-context.{md,txt}   # Aggregated file contents
    │       ├── NNN-arena.{md,txt}     # Model comparison
    │       ├── NNN-prompt.txt         # The prompt sent to the models
    │       ├── NNN-A.txt              # Model A response
    │       ├── NNN-B.txt              # Model B response
    │       └── ARCHIVE/               # Archive (optional)
    ├── structure/
    │   └── structure.txt      # Project structure tree
    ├── models/                # Legacy (migrated) models folder
    └── tmp/                   # Temporary files
```

---

## Available Interfaces

You can run the tool in different ways from the terminal:

| Command | Interface type | Ideal usage |
| :--- | :--- | :--- |
| **`agg`** | **CLI** (Direct) | Direct execution with automatic project root discovery. |
| **`aggf`** | **CLI** (Current) | Run the script treating the **current folder** as the root. |
| **`aggt`** | **TUI** (Terminal UI) | Interactive browsing and file selection inside the terminal (requires `pip install textual`). |
| **`aggg`** | **GUI** (Window) | Classic window interface (Tkinter) with dark mode. |

---

## Quick CLI Commands

```bash
# Basic execution
agg                     # Run with automatic root discovery
aggf                    # Run with the current folder as root
aggt                    # Interactive terminal interface (TUI)
aggg                    # Graphical interface (GUI)

# Define the commands in a PowerShell Profile
function agg { python C:\path\to\context\aggregator.py $args }
function aggf { python C:\path\to\context\aggregator.py . $args }
function aggt { python C:\path\to\context\aggregator_tui.py $args }
function aggg { python C:\path\to\context\aggregator_gui.py $args }

# On Linux/WSL (add to ~/.bashrc or ~/.zshrc)
alias agg='python3 /path/to/context/aggregator.py'
alias aggf='python3 /path/to/context/aggregator.py .'
alias aggt='python3 /path/to/context/aggregator_tui.py'
alias aggg='python3 /path/to/context/aggregator_gui.py'
```

### CLI Flags

| Flag | Effect |
| :--- | :--- |
| `--interactive` | Show all interactive prompts (overrides settings.json) |
| `--output DIR` | Set the output folder manually (overrides `output_dir` in settings) |
| `--status` | Print a project state snapshot for AI agents and exit |
| `--json` | With `--status`: output JSON to stdout (for scripting) |
| `-q`, `--quiet` | With `--status`: print only the next Arena number on a single line |
| `--settings` | Print the settings file path, its contents, and the schema, then exit |
| (no flags) | Read settings.json, auto-discover input files, run silently |

### Installing Optional Libraries

```bash
python install.py
```

This script installs `tiktoken` (for accurate token counting) and `textual` (for the TUI). The tool works without them, but counting will be less accurate.

---

## Model Comparison & Evaluation (LMArena & Judge Mode)

When running `agg` or `aggf` with `--interactive`, the script asks you about:
- **Gemini Judge:** automatic or manual
- **Compact Mode:** reduce tokens by stripping redundant whitespace
- **Model count:** 2 or 4
- **Output format:** `.md` or `.txt`

### Arena File Structure (v3+ Flat Layout)

```
003-Hero/
├── 003-Hero.txt       ← Original input file (preserved copy)
├── 003-context.md     ← Aggregated file contents (the context sent to the models)
├── 003-arena.md       ← Model comparison file
├── 003-prompt.txt     ← The prompt that was sent
├── 003-A.txt          ← Model A response
├── 003-B.txt          ← Model B response
└── ARCHIVE/           ← Archive of model responses (optional)
```

**Note:** every file carries the `NNN-` prefix matching its folder name to avoid collisions when several Arenas are open. Legacy files without the prefix (from the v2 layout) are hidden automatically from `structure.txt` and the project tree via a structural rule in `should_ignore()`.

### Legacy File Cleanup (Phase 3 Migration)

Legacy files without a prefix are cleaned up automatically on every run:
- **Rename:** unprefixed files are renamed with the correct prefix (e.g. `arena.txt` → `003-arena.md`)
- **Deduplication:** if a prefixed and an unprefixed copy are identical, the unprefixed one is deleted
- **Warning on differences:** if the contents differ, both copies are kept and manual review is requested

---

## Target Arena Directive

You can pin the Arena number by adding a comment on the first non-empty line of the input file:

```txt
# Target Arena: 006-AdminDashboard
/path/to/component.tsx
/path/to/styles.css:10-30
```

- If two Arenas claim the same number, you are warned and one of them is moved to the next available number.
- The file name remains the decisive source for the Arena name (not the comment).
- This feature can be disabled with `respect_target_arena_directive: false` in the settings.

---

## Outputs

Once a run finishes, you will find:

1. **`context_output/arenas/NNN-<name>/NNN-context.{md,txt}`**: all aggregated files and snippets.
2. **`context_output/structure/structure.txt`**: the full project structure tree.
3. **`context_output/arenas/NNN-<name>/NNN-arena.{md,txt}`**: the model comparison file with the **analytical report and winner announcement by the Gemini Judge**.

### State Breadcrumb

`context_output/.context/last_arena.json` is written automatically at the end of every run. It contains:
- The last Arena number and the next one
- The total number of Arenas
- The last activity and its timestamp
- The number of input files

You can use `agg --status` to print this information directly.

---

## Customization (Ignore Patterns)

To ignore specific files or folders, create a `.context/ignore` file inside the `.context/` folder and add the patterns you want to ignore.

### Default Patterns

The tool ignores automatically:
- `.git`, `node_modules`, `venv`, `.venv`
- `.vscode`, `.idea`, `.cursor`, `.windsurf`
- `__pycache__`, `*.pyc`, `dist`, `build`, `.next`
- `context_output`, `.context`, `files.txt`, `models/`
- Legacy unprefixed files inside Arena folders (e.g. `A.txt`, `arena.md`, `context.md`, `prompt.txt`)

**Note:** legacy files are also hidden by an independent structural rule in `should_ignore()`, even when `use_default_ignore` is disabled.

### Disabling the Default Patterns

To disable the default patterns and take full control of the `ignore` file:

```json
// .context/settings.json
{
  "use_default_ignore": false
}
```

When disabled, the `.context/ignore` file will not be created or modified automatically.

---

## Configuration

### Settings File

`.context/settings.json` — created automatically on first run:

```json
{
  "output_dir": "context_output",
  "output_format": "md",
  "model_count": 2,
  "gemini_judge": false,
  "compact_mode": false,
  "archive": false,
  "archive_dir": "ARCHIVE",
  "paste_attachments_enabled": false,
  "paste_attachments_source_dir": "tmp/paste-attachments",
  "paste_attachments_target_subdir": "tmp/paste-attachments",
  "paste_attachments_date_format": "%Y-%m-%d",
  "paste_attachments_copy_mode": "copy",
  "respect_target_arena_directive": true,
  "target_arena_directive_prefix": "# Target Arena:",
  "on_arena_number_conflict": "warn_and_shift",
  "use_default_ignore": true
}
```

| Key | Default | Description |
| :--- | :--- | :--- |
| `output_dir` | `"context_output"` | Main output folder |
| `output_format` | `"md"` | File format: `"md"` or `"txt"` |
| `model_count` | `2` | Number of response files (2 or 4) |
| `gemini_judge` | `false` | Enable automatic judging |
| `compact_mode` | `false` | Reduce tokens in the comparison file |
| `archive` | `false` | Archive model responses after each run |
| `archive_dir` | `"ARCHIVE"` | Archive folder inside each Arena |
| `paste_attachments_enabled` | `false` | Enable paste attachment archiving |
| `use_default_ignore` | `true` | Use the default patterns in `ignore` |
| `respect_target_arena_directive` | `true` | Honor `# Target Arena:` directives |
| `on_arena_number_conflict` | `"warn_and_shift"` | Conflict behavior: `"warn_and_shift"`, `"fail"`, or `"silent"` |

### Environment Variables

To enable the automatic judge feature, you must add your Gemini API key:

**On Linux / WSL (`~/.bashrc` or `~/.zshrc`):**
```bash
export GEMINI_API_KEY="your_api_key_here"
```

**On Windows (PowerShell Profile):**
```powershell
$env:GEMINI_API_KEY="your_api_key_here"
```

**Or** create a `.env` file at the tool root (next to `aggregator.py`):
```
GEMINI_API_KEY=your_api_key_here
```

### Configuration Precedence

```
Command Line Flags > Interactive Prompts > settings.json > Defaults
```

---

## Utility Scripts

### Renumber Arenas

```bash
python renumber_arenas.py              # Preview the plan only (dry-run)
python renumber_arenas.py --apply      # Perform the renaming
python renumber_arenas.py --apply --force  # Rename even with content present
```

A tool for reordering Arena folder numbers based on `# Target Arena:` directives in the input files.

### Install Libraries

```bash
python install.py
```

Installs `tiktoken` and `textual` — the optional libraries for accurate counting and the TUI.

---

## Roadmap

We keep improving the tool. Here is what we plan to add:

* [ ] **Cost Estimator:** calculate estimated token consumption cost based on official API prices before sending requests.
* [ ] **Custom Judge Personas:** direct the judge to focus on specific aspects via `--judge security` or `--judge performance`.
* [ ] **Incremental Context:** aggregate only files modified in Git to save tokens.
* [ ] **Interactive HTML Report:** an interactive dark-mode HTML page with a code diff viewer.
* [ ] **Web Server Interface:** a local server with a browser-based control panel.
