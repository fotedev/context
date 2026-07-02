"""One-time migration: rename existing arena directories so their numbers
match the ``# Target Arena:`` directives in ``.context/inputs/*.txt``.

Usage::

    python renumber_arenas.py [<root>]           # dry-run (default)
    python renumber_arenas.py <root> --apply    # actually rename

What it does:
    1. Reads directives from ``<root>/.context/inputs/*.txt`` (filenames with
       no directive count as "implicit" and are placed after the explicit
       range, alphabetically).
    2. Builds the desired arena list (``NNN-<name>``).
    3. Compares against the existing ``<root>/context_output/arenas/`` dirs.
    4. Computes a sequence of renames (using a temporary two-step rename to
       avoid collisions).
    5. By default, only prints the plan; with ``--apply`` it executes it.

Safety:
    * Arenas that contain content (``arena.txt`` non-empty, or any
      ``answers/*.txt`` non-empty, or any non-template ``compare.md``)
      require ``--force`` OR an interactive ``yes`` to be renamed.
    * Empty arenas (just the template skeleton) are renamed automatically.
    * If two distinct arenas want the same final slot, the script aborts
      with a clear report instead of guessing.

This script is idempotent — running it twice in a row produces zero work
the second time.
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

# Make the core package importable when run as `python renumber_arenas.py`.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from core.parser import (  # noqa: E402
    ArenaDirective,
    build_arena_plan,
    discover_files_txt_with_directives,
)


_ARENA_NUMBER_RE = re.compile(r"^(\d{3})-(.+)$")


def _parse_existing_arenas(arenas_dir: Path) -> dict[int, Path]:
    """Map existing arena number → directory path.  Returns only well-formed
    ``NNN-name`` directories (skips other files/folders).
    """
    existing: dict[int, Path] = {}
    if not arenas_dir.is_dir():
        return existing
    for p in sorted(arenas_dir.iterdir()):
        if not p.is_dir():
            continue
        match = _ARENA_NUMBER_RE.match(p.name)
        if match:
            existing[int(match.group(1))] = p
    return existing


def _arena_has_content(arena_dir: Path) -> bool:
    """Return True when the arena has any user-generated content beyond the
    empty template skeleton (empty answers/, zero-byte arena.txt, template
    compare.md).
    """
    arena_txt = arena_dir / "arena.txt"
    if arena_txt.is_file() and arena_txt.stat().st_size > 0:
        return True

    compare_md = arena_dir / "compare.md"
    if compare_md.is_file() and compare_md.stat().st_size > 614:
        # Default template is ~600 bytes.  Anything meaningfully larger
        # counts as content.
        return True

    answers = arena_dir / "answers"
    if answers.is_dir():
        for f in answers.glob("*.txt"):
            try:
                if f.stat().st_size > 0:
                    return True
            except OSError:
                continue

    # Subdirectories like ARCHIVE/ count as content.
    for child in arena_dir.iterdir():
        if child.is_dir() and child.name not in {"answers"}:
            return True

    return False


def compute_renames(
    desired_by_num: dict[int, tuple[str, Path]],
    existing_by_num: dict[int, Path],
    *,
    force: bool = False,
) -> tuple[list[tuple[Path, Path]], list[str], list[str]]:
    """Compute a safe sequence of renames.

    Args:
        desired_by_num: Map of desired arena number → (arena_name, source input).
        existing_by_num: Map of existing arena number → directory path.
        force: When True, ignore content checks.

    Returns:
        (renames, skipped_with_content, errors)
        - renames: list of (from_path, to_path) to execute (in safe order).
        - skipped_with_content: human-readable reasons for skipping.
        - errors: hard errors that prevent the migration.
    """
    renames: list[tuple[Path, Path]] = []
    skipped: list[str] = []
    errors: list[str] = []

    # 1. Detect hard collisions in the desired state.
    name_counts: dict[str, list[int]] = {}
    for num, (name, _src) in desired_by_num.items():
        name_counts.setdefault(name, []).append(num)
    for name, nums in name_counts.items():
        if len(nums) > 1:
            errors.append(
                f"Hard collision: {nums!r} all want arena name {name!r}. "
                "Resolve manually before running migration."
            )
    if errors:
        return renames, skipped, errors

    # 2. Build desired map keyed by (number, name) → existing dir (if any).
    # The "current name" of an existing arena is its current folder name.
    # We need to find, for each desired (num, name), which existing dir
    # currently holds that name (by number OR by name).
    existing_by_name: dict[str, list[int]] = {}
    for num, p in existing_by_num.items():
        match = _ARENA_NUMBER_RE.match(p.name)
        if match:
            existing_by_name.setdefault(match.group(2), []).append(num)

    # Track which existing dirs we've already claimed.
    claimed: set[Path] = set()

    # 3. For each desired (num, name), figure out the source path.
    moves: list[tuple[Path, int, str]] = []  # (from_path, desired_num, name)
    for num in sorted(desired_by_num):
        name, _src = desired_by_num[num]
        candidates = existing_by_name.get(name, [])
        if not candidates:
            # No existing dir with this name at all — nothing to move.
            continue
        # Prefer same number, else lowest available
        if num in candidates:
            src = existing_by_num[num]
        else:
            chosen_num = min(candidates)
            src = existing_by_num[chosen_num]
        if src in claimed:
            errors.append(
                f"Internal logic error: {src} claimed twice (for {num:03d}-{name})."
            )
            continue
        claimed.add(src)
        moves.append((src, num, name))

    # 4. Sort moves so we never overwrite an unprocessed directory.
    # Use the standard two-phase rename trick: move every source to a temp
    # name first, then to the final name.
    arenas_dir = next(iter(existing_by_num.values())).parent
    staged: list[tuple[Path, Path, int, str]] = []
    for src, num, name in moves:
        final = arenas_dir / f"{num:03d}-{name}"
        # Idempotency: skip when src is already at the desired slot.
        if src == final:
            continue
        if _arena_has_content(src) and not force:
            skipped.append(
                f"{src.name} → {num:03d}-{name}  (has content; rerun with --force)"
            )
            continue
        staged.append((src, arenas_dir / f"__tmp_{num:03d}_{name}", num, name))

    # Phase 1: src → tmp
    for src, tmp, _num, _name in staged:
        renames.append((src, tmp))
    # Phase 2: tmp → final (reverse so dests are processed before srcs)
    for src, tmp, num, name in reversed(staged):
        final = arenas_dir / f"{num:03d}-{name}"
        renames.append((tmp, final))

    return renames, skipped, errors


def _print_plan(plan: dict, renames: list[tuple[Path, Path]], skipped: list[str], errors: list[str], existing_count: int) -> None:
    print("=" * 72)
    print("RENUMBER ARENAS — plan")
    print("=" * 72)
    print(f"Desired arenas: {len(plan)}")
    print(f"Existing arenas: {existing_count}")
    print(f"Renames planned: {len(renames)}")
    print(f"Skipped (content, needs --force): {len(skipped)}")
    print(f"Errors (must fix manually): {len(errors)}")
    print()

    if renames:
        print("Renames:")
        for src, dst in renames:
            print(f"  {src.name}  →  {dst.name}")
    if skipped:
        print()
        print("Skipped (needs --force):")
        for line in skipped:
            print(f"  {line}")
    if errors:
        print()
        print("ERRORS (must resolve manually):")
        for line in errors:
            print(f"  {line}")
    print()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "root",
        nargs="?",
        default=".",
        help="Project root directory (default: current working directory).",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually rename directories (default: dry-run).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Rename even arenas with content (use with --apply).",
    )
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    if not (root / ".context" / "inputs").is_dir():
        print(f"ERROR: {root}/.context/inputs not found.", file=sys.stderr)
        return 1
    if not (root / "context_output" / "arenas").is_dir():
        print(
            f"ERROR: {root}/context_output/arenas not found.",
            file=sys.stderr,
        )
        return 1

    cwd = Path.cwd()
    inputs, directives = discover_files_txt_with_directives(
        cwd=cwd, root=root, settings={"inputs_dir": ".context/inputs"},
    )
    assignments, warnings = build_arena_plan(inputs, directives)
    if warnings:
        print("WARNING: directive plan has conflicts; resolve before migrating.")
        for w in warnings:
            print(f"  {w}")
        print()

    plan = {a.arena_number: (a.arena_name, a.filepath) for a in assignments}

    arenas_dir = root / "context_output" / "arenas"
    existing = _parse_existing_arenas(arenas_dir)
    renames, skipped, errors = compute_renames(plan, existing, force=args.force)

    if args.apply:
        if errors:
            print("Refusing to apply due to hard errors. Fix and retry.")
            return 2
        # Confirm if any renames affect content
        if skipped and not args.force:
            print("Refusing to apply because some arenas have content and --force not set.")
            return 3

    _print_plan(plan, renames, skipped, errors, existing_count=len(existing))

    if not args.apply:
        print("(dry-run — pass --apply to actually rename)")
        return 0

    # Execute the staged renames.
    for src, dst in renames:
        try:
            _ = shutil.move(str(src), str(dst))
        except OSError as exc:
            print(f"FAILED: {src.name} → {dst.name}: {exc}", file=sys.stderr)
            return 4

    print(f"Done. {len(renames)} rename(s) applied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())