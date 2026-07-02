# Skill: Migrate to Flat Layout (v3)

## When to use
Use this skill when updating an old project to the new File Aggregator flat layout (v3).
The old layout used subfolders (`arena/`, `answers/`) inside each arena directory and
stored input files in `.context/inputs/`. The new layout puts everything flat inside
the arena directory and moves the input files into their respective arena folders.

## Scope
- This skill is for **one-shot cleanup of legacy projects**. It is destructive
  (moves files out of `.context/inputs/`), so it must run only when the user asks
  for it.
- The tool itself (`aggregator.py`) is safe to run on legacy projects — it auto-
  flattens internal arena subfolders on every run via `migrate_to_flat_layout`,
  and copies input files into each arena dir on the fly. The skill is only
  needed to **finish the cleanup** (move the originals + gitignore the old path).

## Procedure

1. **Identify Project Root**: Ensure you are in the project root containing
   `.context/` and `context_output/`.

2. **Flatten Arena Subfolders (Dry-Run)**: Run the built-in migration helper in
   dry-run mode to see what internal arena files will be moved to the root:
   ```bash
   python -c "
   from pathlib import Path
   from core.parser import migrate_to_flat_layout
   paths = migrate_to_flat_layout(Path.cwd() / 'context_output', dry_run=True)
   if paths:
       print('Would move:')
       for p in paths:
           print(f'  - {p}')
   else:
       print('Nothing to flatten.')
   "
   ```

3. **Review Output**: Check the terminal output. It should list files moving
   from subfolders to the arena root.

4. **Apply Internal Flatten**: Once approved, apply the migration:
   ```bash
   python -c "from pathlib import Path; from core.parser import migrate_to_flat_layout; migrate_to_flat_layout(Path.cwd() / 'context_output')"
   ```

5. **Migrate Input Files (Dry-Run first)**: Preview which inputs the helper
   would move, and which it would leave as orphans (no matching arena):
   ```bash
   python skills/migrate-to-flat-layout/migrate_inputs.py --dry-run
   ```

6. **Apply Input Move**: Once approved, run without `--dry-run`:
   ```bash
   python skills/migrate-to-flat-layout/migrate_inputs.py
   ```
   Orphan inputs (no matching arena) are left in place — the tool will create
   the arena + copy them on its next run.

7. **Verify Flatness**: List the contents of an arena folder to ensure files
   are flat and inputs are present:
   ```bash
   ls context_output/arenas/001-*/
   ```

8. **Final pass with the tool**: Run `python aggregator.py` once to apply any
   remaining auto-migration (e.g., for orphan inputs that need a new arena
   folder).

## Important Notes
- The migration is idempotent. Running it multiple times is safe.
- Do not delete `.context/` entirely; it still holds `settings.json` and
  `ignore`.
- The skill does **not** create arena folders — that is `resolve_arena_dir`'s
  job in the tool. If an input has no matching arena, the skill leaves it
  alone.
- After migration, running `python aggregator.py` on this project will
  maintain the flat layout automatically.
- `.context/inputs/` is added to `.gitignore` after the move, so the legacy
  path does not get re-tracked.
