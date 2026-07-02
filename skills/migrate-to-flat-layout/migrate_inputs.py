#!/usr/bin/env python3
"""Migrate legacy .context/inputs/*.txt into matching v3 flat arena dirs.

Input-authoritative matching: for each input file, look at all arena dirs whose
``NNN-<name>`` suffix matches the input's stem. If at least one of those arenas
already has a copy of the input, the input is "already migrated" — skip it
(do not create a duplicate in a dead lower-numbered duplicate arena). If no
matching arena exists, the input is an orphan — skip and let the tool create
the arena on its next run. If matching arenas exist but none has a copy, move
the input into the lowest-numbered matching arena.

Only touches .gitignore when .context/inputs/ would be empty after the move —
otherwise the dir still has live files that must not be silently ignored.

Usage:
    python migrate_inputs.py                # run from project root
    python migrate_inputs.py --dry-run      # show what would move
    python migrate_inputs.py /path/to/proj  # explicit project root
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

GITIGNORE_ENTRY = ".context/inputs/"
GITIGNORE_COMMENT = "# Migrated legacy inputs dir (see migrate-to-flat-layout skill)"


def _group_arenas(arenas_dir: Path) -> dict[str, list[Path]]:
    """Group arena dirs by their name suffix (after the NNN- prefix).

    Skips dirs that don't follow the ``NNN-<name>`` pattern (e.g. ``ARCHIVE``,
    ``backup``). When the same name has duplicate arenas (``030-X`` and
    ``031-X``), they are all collected under the same key so the planner can
    pick the right one.

    Within each group, arenas are sorted by **integer** prefix (not string) so
    that ``9-X`` correctly precedes ``10-X`` even if the tool ever drops its
    current 3-digit zero-padding convention (``f"{n:03d}"``).
    """
    grouped: dict[str, list[Path]] = {}
    for arena in arenas_dir.iterdir():
        if not arena.is_dir() or "-" not in arena.name:
            continue
        prefix, _, _ = arena.name.partition("-")
        if not prefix.isdigit():
            continue
        name = arena.name.split("-", 1)[1]
        grouped.setdefault(name, []).append(arena)
    for name in grouped:
        grouped[name].sort(key=lambda p: int(p.name.split("-", 1)[0]))
    return grouped


def _plan_migration(
    inputs_dir: Path, arenas_dir: Path
) -> tuple[list[tuple[Path, Path, Path]], list[tuple[Path, list[Path]]], list[Path]]:
    """Categorize inputs into (moves, already_migrated, orphans).

    - moves: ``(arena, src, dst)`` tuples — input needs to be moved into the arena.
    - already_migrated: ``(src, arenas_with_copy)`` — at least one arena already
      has a copy; the input is redundant in ``.context/inputs/`` and should NOT
      be moved (avoids creating a duplicate in a dead lower-numbered arena).
    - orphans: input paths with no matching arena — the tool will create one
      on its next run.
    """
    arenas_by_name = _group_arenas(arenas_dir)

    moves: list[tuple[Path, Path, Path]] = []
    already: list[tuple[Path, list[Path]]] = []
    orphans: list[Path] = []

    for input_path in sorted(inputs_dir.glob("*.txt")):
        if not input_path.is_file():
            continue
        candidates = arenas_by_name.get(input_path.stem, [])
        if not candidates:
            orphans.append(input_path)
            continue
        with_copy = [a for a in candidates if (a / input_path.name).exists()]
        if with_copy:
            already.append((input_path, with_copy))
            continue
        # Matching arenas exist but none has the input — move to the
        # lowest-numbered candidate (the one the tool would have created first).
        target_arena = candidates[0]
        moves.append((target_arena, input_path, target_arena / input_path.name))

    return moves, already, orphans


def _count_remaining(inputs_dir: Path) -> int:
    """Count .txt files still in .context/inputs/ (used to gate gitignore)."""
    if not inputs_dir.is_dir():
        return 0
    return sum(1 for p in inputs_dir.glob("*.txt") if p.is_file())


def migrate_inputs(root: Path, dry_run: bool = False) -> dict:
    """Plan and (if not dry_run) execute the migration. Returns a summary dict."""
    inputs_dir = root / ".context" / "inputs"
    arenas_dir = root / "context_output" / "arenas"

    if not inputs_dir.is_dir():
        print(f"No inputs dir at {inputs_dir} — nothing to migrate.")
        return {
            "moves": [],
            "already": [],
            "orphans": [],
            "moved_count": 0,
            "remaining_in_inputs": 0,
        }
    if not arenas_dir.is_dir():
        print(f"Error: arenas dir not found at {arenas_dir}.", file=sys.stderr)
        return {
            "moves": [],
            "already": [],
            "orphans": [],
            "moved_count": 0,
            "remaining_in_inputs": _count_remaining(inputs_dir),
        }

    moves, already, orphans = _plan_migration(inputs_dir, arenas_dir)

    if not moves and not already and not orphans:
        print("No input files to migrate.")
        return {
            "moves": [],
            "already": [],
            "orphans": [],
            "moved_count": 0,
            "remaining_in_inputs": _count_remaining(inputs_dir),
        }

    # Section 1: would-be moves
    if moves:
        verb = "Would move" if dry_run else "Moved"
        print(f"\n{verb} ({len(moves)}):")
        for arena, src, dst in moves:
            print(f"  {src.relative_to(root)} → {arena.relative_to(root)}/")

    # Section 2: already migrated (the most common case once the tool has run)
    if already:
        print(
            f"\nAlready migrated ({len(already)}) — input is already in the "
            f"project; skipped to avoid creating a duplicate:"
        )
        for src, arenas_with_copy in already:
            arena_names = ", ".join(a.name for a in arenas_with_copy)
            print(f"  {src.relative_to(root)}  (in: {arena_names})")

    # Section 3: orphans (no matching arena yet)
    if orphans:
        print(
            f"\nOrphans ({len(orphans)}) — no matching arena; tool will create "
            f"on next run:"
        )
        for o in orphans:
            print(f"  {o.relative_to(root)}")

    moved_count = 0
    if not dry_run and moves:
        for arena, src, dst in moves:
            try:
                dst.parent.mkdir(parents=True, exist_ok=True)
                src.rename(dst)
                moved_count += 1
            except OSError as exc:
                print(f"Warning: could not move {src} → {dst}: {exc}", file=sys.stderr)

    remaining = _count_remaining(inputs_dir)
    return {
        "moves": moves,
        "already": already,
        "orphans": orphans,
        "moved_count": moved_count,
        "remaining_in_inputs": remaining,
    }


def ensure_gitignore(root: Path, dry_run: bool = False) -> None:
    """Append ``.context/inputs/`` to the project's .gitignore if not already there.

    Matching is normalized: strips whitespace + leading ``/`` + trailing ``/``
    so that existing entries like ``/.context/inputs`` or ``.context/inputs``
    are correctly recognized as the same path.
    """
    gitignore = root / ".gitignore"
    try:
        content = gitignore.read_text(encoding="utf-8") if gitignore.is_file() else ""
    except OSError as exc:
        print(f"Warning: could not read .gitignore: {exc}", file=sys.stderr)
        return

    def _normalize(entry: str) -> str:
        return entry.strip().lstrip("/").rstrip("/")

    target = _normalize(GITIGNORE_ENTRY)
    for line in content.splitlines():
        if _normalize(line) == target:
            print(f"\n.gitignore already contains {GITIGNORE_ENTRY} — skipping.")
            return

    sep = "\n" if content and not content.endswith("\n") else ""
    addition = f"{sep}\n{GITIGNORE_COMMENT}\n{GITIGNORE_ENTRY}\n"

    if dry_run:
        print(f"\n[gitignore] Would append:\n{addition}")
        return

    try:
        with gitignore.open("a", encoding="utf-8") as fh:
            fh.write(addition)
        print(f"\nAdded {GITIGNORE_ENTRY} to .gitignore.")
    except OSError as exc:
        print(f"Warning: could not update .gitignore: {exc}", file=sys.stderr)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Migrate .context/inputs/*.txt into matching v3 flat arena dirs."
    )
    parser.add_argument(
        "root",
        nargs="?",
        default=".",
        help="Project root (default: current directory).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show the 3-section migration plan and the would-be .gitignore change.",
    )
    args = parser.parse_args(argv[1:])

    root = Path(args.root).resolve()
    if not root.is_dir():
        print(f"Error: {root} is not a directory.", file=sys.stderr)
        return 1

    summary = migrate_inputs(root, dry_run=args.dry_run)
    remaining = summary["remaining_in_inputs"]
    has_activity = bool(summary["moves"] or summary["already"] or summary["orphans"])

    if remaining == 0:
        # The legacy dir is fully drained (or was always empty/missing) —
        # safe to gitignore regardless of whether there was any activity.
        ensure_gitignore(root, dry_run=args.dry_run)
    elif has_activity:
        print(
            f"\n.gitignore NOT updated: {remaining} file(s) still in "
            f".context/inputs/. Re-run this skill after the tool processes "
            f"orphans, or after manually cleaning up the inputs dir."
        )

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
