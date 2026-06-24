# Organize Root — Mini-Skill for Arena Context

This instruction set is a mini-skill for the AI agent to organize root-level files in the **Context** project. When triggered, the agent is responsible for executing this layout migration manually rather than having the tool perform automatic file operations.

## Target Files for Organization

| Legacy Location (Root) | Target Location | Description |
|---|---|---|
| `./arena.txt` · `./structure.txt` · `./compare.md` | `context_output/` | Legacy tool outputs |
| `./files.txt` · `./files_*.txt` | `.context/inputs/` | Legacy inputs to be discovered |
| `./models/` (entire directory) | `context_output/models/` | Model responses and legacy archives |
| `./models/ARCHIVE/` | `context_output/models/ARCHIVE/` | Timestamped archive history |

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
   - Move the entire `./models/` folder (with `A.txt`, `B.txt`, `prompt.txt`, and any `old/` subdirectory history) into `context_output/models/`.
   - Once all files are safely moved, delete the empty `./models/` directory in the project root.

5. **Verify Configuration**:
   - Ensure `.context/settings.json` is updated to point to the correct paths:
     ```json
     {
       "output_dir": "context_output",
       "inputs_dir": ".context/inputs"
     }
     ```
   - Ensure `.context/ignore` contains ignore entries for `context_output/` and `.context/` to prevent infinite recursion during file aggregation.

6. **Verify Migration**:
   - Run `python aggregator.py` (or `agg`) to confirm the tool discovers inputs from `.context/inputs/` and writes outputs to `context_output/arenas/`.
   - If the tool reports "No files*.txt found", the migration was incomplete — check for leftover files in the root.
