# Calculate Lines of Code per File

> **Workspace:** C:\programming\Python\Projects\context
> **Last Updated:** July 2026

---

## Overview

This document describes the implementation of line counting functionality in the context aggregation tool. The feature counts lines of code for every file and displays them in `structure.txt` and aggregated output files.

## Current File Line Counts (as of July 2026)

| File | Lines |
|------|-------|
| `core/counter.py` | 67 |
| `core/parser.py` | 1,170 |
| `core/settings.py` | 616 |
| `core/discovery.py` | 386 |
| `core/arena.py` | 333 |
| `core/judge.py` | 729 |
| `aggregator.py` | 810 |
| `aggregator_gui.py` | 1,463 |
| `aggregator_tui.py` | 730 |

---

## Implementation Details

### 1. `count_lines` Function (`core/counter.py:41-67`)

The core line counting function that:
- Counts total lines in a file
- Supports optional line ranges (1-indexed, inclusive)
- Handles exceptions gracefully (returns 0 for missing/corrupted files)

```python
def count_lines(path: Path, ranges: list[tuple[int, int]] | None = None) -> int:
    """Count lines in a file, optionally limited to specific line ranges."""
    try:
        with path.open("r", encoding="utf-8") as fh:
            lines = fh.readlines()
            total = len(lines)
            if ranges is None:
                return total
            # ... range counting logic
    except (OSError, UnicodeDecodeError):
        return 0
```

### 2. `aggregate_files` Function (`core/parser.py:486-546`)

Updates file headers to include line counts:
- Full files: `# --- FILE: path/to/file.py (123 lines) ---`
- Snippets: `# --- SNIPPET: path/to/file.py [10-20] (11 lines) ---`
- Important structures: `# --- IMPORTANT STRUCTURE: path/to/file.py [1-50] (50 lines) ---`

Returns total lines aggregated across all files.

### 3. `generate_tree` Function (`core/parser.py:165-219`)

Displays line counts in the directory tree output:
- Files show as: `filename.py (123 lines)`
- Directories show as: `dirname/`

### 4. `aggregator.py` Integration

- Displays total line count after aggregation
- Shows line count alongside character and token counts in summary

---

## Verification

All methods are currently functional and tested. The `structure.txt` output in `context_output/structure/structure.txt` shows accurate line counts for all project files.

---

## Current Output Example

The `structure.txt` file now displays line counts for every file:

```
Project Root: context/
├── core/
│   ├── __init__.py (8 lines)
│   ├── arena.py (333 lines)
│   ├── counter.py (67 lines)
│   ├── discovery.py (421 lines)
│   ├── judge.py (729 lines)
│   ├── parser.py (1170 lines)
│   └── settings.py (559 lines)
├── aggregator.py (810 lines)
├── aggregator_gui.py (1463 lines)
└── aggregator_tui.py (730 lines)
```

---

## Testing the Feature

To verify line counts are working:

```bash
# Test count_lines directly
python -c "from core.counter import count_lines; from pathlib import Path; print(count_lines(Path('core/counter.py')))"

# Regenerate structure.txt with line counts
python aggregator.py

# Check the output
cat context_output/structure/structure.txt
```

---

