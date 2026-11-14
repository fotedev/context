# Reorganization Plan — Context Project Root

**Date:** 2026-07-06
**Project:** C:\programming\Python\Projects\context

## Goal
Reduce root-level clutter by moving documentation and utility scripts into subdirectories, deleting stale log files and temp artifacts.

## Proposed Target Structure

```
context/
├── docs/                              # All documentation
│   ├── README.md
│   ├── Calculate Lines of Code per File.md
│   ├── CODEBASE_ANALYSIS_REPORT.md
│   ├── features.md
│   ├── IMPLEMENTATION_SUMMARY.md
│   ├── REFACTOR_AND_STATUS_PLAN.md
│   └── VISUALIZATION_PROMPT.md
├── scripts/                           # Utility scripts
│   ├── cleanup_first_heart.py
│   ├── install.py
│   └── renumber_arenas.py
├── core/                              # Core modules (unchanged)
├── gui/                               # GUI assets (unchanged)
├── arena-context/                     # Skills (unchanged)
├── skills/                            # Skills (unchanged)
│
│   # --- Files that stay at root ---
├── aggregator.py                      # Main CLI entry point
├── aggregator_gui.py                  # GUI entry point
├── aggregator_tui.py                  # TUI entry point
├── files.txt                          # Input manifest
├── prompt.txt                         # Tool input
├── requirements.txt                   # Python dependencies
├── .env                               # Environment variables
├── .env.example                       # Env template
├── .gitignore                         # Git config
├── .context/                          # Tool config directory
├── context_output/                    # Tool output directory
```

## Changes

### Moves (10 files)

| File | From | To | Reason |
|------|------|----|--------|
| README.md | root | docs/ | Documentation |
| Calculate Lines of Code per File.md | root | docs/ | Documentation |
| CODEBASE_ANALYSIS_REPORT.md | root | docs/ | Documentation |
| features.md | root | docs/ | Documentation |
| IMPLEMENTATION_SUMMARY.md | root | docs/ | Documentation |
| REFACTOR_AND_STATUS_PLAN.md | root | docs/ | Documentation |
| VISUALIZATION_PROMPT.md | root | docs/ | Documentation |
| cleanup_first_heart.py | root | scripts/ | Utility script |
| install.py | root | scripts/ | Utility script |
| renumber_arenas.py | root | scripts/ | Utility script |

### Deletions (9 files)

| File | Reason |
|------|--------|
| __init__.py.log | Stale log file |
| aggregator_gui.py.log | Stale log file |
| aggregator_tui.py.log | Stale log file |
| aggregator.py.log | Stale log file |
| judge.py.log | Stale log file |
| parser.py.log | Stale log file |
| context.txt | Tool output at root |
| full-chat.txt | Tool output at root |
| temp/ | Empty temp directory |

### .gitignore Updates

Add patterns for:
```
*.log
.venv/
venv/
.vscode/
.windsurf/
__pycache__/
temp/
tmp/
```

## Files to Update (Relative Links)

- `docs/README.md` — verify internal links still resolve
- `docs/features.md` — verify internal links still resolve
- `docs/IMPLEMENTATION_SUMMARY.md` — verify internal links still resolve

## Result

| Metric | Before | After |
|--------|--------|-------|
| Root files | 40 | ~15 |
| Documentation at root | 7 | 0 |
| Utility scripts at root | 3 | 0 |
| Log files at root | 6 | 0 |
