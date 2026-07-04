# Organize Root — Mini-Skill for Arena Context

This instruction set is a mini-skill for the AI agent to organize root-level files in the **Context** project. When triggered, the agent is responsible for executing this layout migration manually rather than having the tool perform automatic file operations.

## Target Files for Organization

| Legacy Location (Root) | Target Location | Description |
|---|---|---|
| `./arena.txt` · `./structure.txt` · `./compare.md` | `context_output/` | Legacy tool outputs |
| `./files.txt` · `./files_*.txt` | `.context/inputs/` | Legacy inputs to be discovered |
| `./models/` (entire directory) | `context_output/models/` | Model responses and legacy archives |
| `./models/ARCHIVE/` | `context_output/models/ARCHIVE/` | Timestamped archive history |

### Category Organization (NEW)
You can organize input files into subdirectories within `.context/inputs/` for better organization:
```
.context/inputs/
├── UI/
│   ├── AdminPage.txt        # ← Found as "UI-AdminPage"
│   └── HomePage.txt         # ← Found as "UI-HomePage"
├── API/
│   └── UserAuth.txt         # ← Found as "API-UserAuth"
└── Common/
    └── Types.txt            # ← Found as "Common-Types"
```
The tool automatically discovers all `.txt` files in subdirectories and uses the directory structure as part of the arena naming.

## Agent Instructions

When you detect legacy files in the project root, perform the following steps:

1. **Verify Target Folders**:
   - Ensure `context_output/` exists.
   - Ensure `.context/inputs/` exists.
   - Ensure `context_output/models/` does not already contain active responses to avoid overwriting newer data.

2. **Move Tool Outputs**:
   - Move any legacy `arena.txt`, `structure.txt`, and `compare.md` (including multi-file versions like `arena_1.txt`, etc.) from the root directory into `context_output/`.

3. **Move Input Manifests**:
   - Move any `files.txt` and `files_*.txt` from the root directory into `.context/inputs/`.

4. **Move Model Responses**:
   - Move the entire `./models/` folder (with `A/`, `B/`, `prompt/` subdirectories, and any `ARCHIVE/` subdirectory history) into `context_output/models/`.
   - Once all files are safely moved, delete the empty `./models/` directory in the project root.

5. **Verify Configuration**:
   - Ensure `.context/settings.json` contains the required paths. The actual config uses additional fields but must include at minimum:
     ```json
     {
       "output_dir": "context_output"
     }
     ```
   - The `inputs_dir` path is derived from the `settings.json` location: `.context/inputs/` is always relative to `.context/settings.json`.
   - Ensure `.context/ignore` contains ignore entries for `context_output` and `.context` to prevent infinite recursion during file aggregation. Verify these patterns are present:
     ```
     context_output
     .context
     ```

6. **Verify Migration**:
   - Run `python aggregator.py` to confirm the tool discovers inputs from `.context/inputs/` and writes outputs to `context_output/arenas/`.
   - If the tool reports "No files*.txt found", the migration was incomplete — check for leftover files in the root.

## Current Project State

The following migrations have already been completed:
- `./arena.txt`, `./structure.txt`, `./compare.md` → `context_output/`
- `./models/` → `context_output/models/` (with `A/`, `B/`, `prompt/`, `ARCHIVE/` subdirectories)

Still pending:
- `./files.txt` exists in root — should be moved to `.context/inputs/`
