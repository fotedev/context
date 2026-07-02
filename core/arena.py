"""Arena directive parsing, conflict-resolved arena planning, and arena
directory resolution.

A ``# Target Arena: NNN-<name>`` directive on the first non-empty line of an
input file pins that file's arena number. The filename remains the source of
truth for the arena name. build_arena_plan turns a set of inputs + directives
into final ArenaAssignment records, resolving number conflicts.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


# ---------------------------------------------------------------------------
# Arena directive parsing (`# Target Arena: 006-AdminDashboard`)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ArenaDirective:
    """Parsed `# Target Arena:` directive from the first non-empty line of an
    input file.

    * ``number`` is the explicit arena number from the directive, or ``None``
      if the file has no directive.
    * ``name`` is the explicit arena name from the directive.  This is
      informational only — the **filename** remains the source-of-truth for
      the resolved arena name.  ``name`` is preserved for validation
      reporting so stale directives can be flagged.
    """

    number: int | None = None
    name: str | None = None

    @property
    def has_directive(self) -> bool:
        return self.number is not None


_DIRECTIVE_NUMBER_RE = re.compile(r"^(\d{1,})\s*-?\s*(.*)$")


def parse_target_arena_directive(
    text: str, prefix: str = "# Target Arena:"
) -> ArenaDirective:
    """Parse the optional ``# Target Arena: NNN-<name>`` directive from *text*.

    Rules:
    * Only the **first non-empty line** is inspected.
    * Match is case-insensitive on the *prefix* (e.g. ``# target arena:``
      works) but the dash + digits are strict.
    * A successful parse returns ``ArenaDirective(number=N, name="…")``.
    * A missing or malformed directive returns ``ArenaDirective()`` (no
      number, no name).
    """
    first_line = next((ln for ln in text.splitlines() if ln.strip()), "")
    if not first_line:
        return ArenaDirective()

    stripped = first_line.lstrip()
    if not stripped.lower().startswith(prefix.lower()):
        return ArenaDirective()

    payload = stripped[len(prefix):].strip()
    match = _DIRECTIVE_NUMBER_RE.match(payload)
    if not match:
        return ArenaDirective()

    raw_num, raw_name = match.group(1).strip(), match.group(2).strip()
    if not raw_num.isdigit():
        return ArenaDirective()
    return ArenaDirective(number=int(raw_num), name=raw_name or None)


def _read_first_line_safely(path: Path) -> str:
    """Read just the first non-empty line of *path* with encoding fallback.

    Returns ``""`` when the file cannot be decoded at all.
    """
    for encoding in ("utf-8-sig", "utf-8", "utf-16", "latin-1"):
        try:
            with path.open("r", encoding=encoding) as fh:
                for raw in fh:
                    line = raw.strip()
                    if line:
                        return line
            return ""
        except (UnicodeDecodeError, OSError):
            continue
    return ""


def _safe_read_directive(path: Path) -> ArenaDirective:
    """Read *path* and parse its arena directive, returning an empty one on
    any decode failure (we never want a bad encoding to crash discovery).
    """
    text = _read_first_line_safely(path)
    if not text:
        return ArenaDirective()
    return parse_target_arena_directive(text)


@dataclass(frozen=True)
class ArenaAssignment:
    """Final, conflict-resolved arena assignment for a single input file."""

    filepath: Path
    arena_name: str        # derived from filename (source of truth)
    arena_number: int      # final resolved number
    directive: ArenaDirective  # original directive (may be empty)


def build_arena_plan(
    inputs: list[tuple[Path, str]],
    directive_lookup: dict[Path, ArenaDirective],
    *,
    on_conflict: str = "warn_and_shift",
    max_iterations: int = 10_000,
) -> tuple[list[ArenaAssignment], list[str]]:
    """Compute final arena numbers for a set of inputs.

    The algorithm:
    1. Split inputs into ``explicit`` (have a directive with a number) and
       ``implicit`` (no directive).
    2. Sort each group alphabetically by filename (deterministic).
    3. Assign explicit inputs their directive numbers.  When two directives
       collide on the same number, the **first** (alphabetical) wins; the
       conflicting one is shifted to the next free number (per
       ``on_conflict="warn_and_shift"``).
    4. Assign implicit inputs the smallest free numbers, starting after the
       highest explicit number.

    Args:
        inputs: List of (filepath, filename-derived arena name).
        directive_lookup: Map filepath → parsed directive.
        on_conflict: ``"warn_and_shift"`` (default), ``"fail"``, or
            ``"silent"``.  Anything else falls back to ``warn_and_shift``.
        max_iterations: Safety bound to prevent infinite loops when scanning
            for the next free number.

    Returns:
        Tuple of (assignments, warnings).  The ``assignments`` list mirrors
        the input order from step 1+3+4 (explicit first, then implicit), so
        downstream consumers see directive-driven arenas before auto-numbered
        ones.

    Raises:
        RuntimeError: When ``on_conflict="fail"`` and a collision occurs, or
            when ``max_iterations`` is exhausted while searching for a free
            number.
    """
    assignments: list[ArenaAssignment] = []
    warnings: list[str] = []
    used: set[int] = set()

    explicit: list[tuple[Path, str, ArenaDirective]] = [
        (p, n, directive_lookup[p])
        for p, n in inputs
        if p in directive_lookup and directive_lookup[p].has_directive
    ]
    explicit.sort(key=lambda t: t[0].name.lower())

    implicit: list[tuple[Path, str]] = [
        (p, n)
        for p, n in inputs
        if not (p in directive_lookup and directive_lookup[p].has_directive)
    ]
    implicit.sort(key=lambda t: t[0].name.lower())

    def _next_free(start: int) -> int:
        candidate = max(start, 1)
        for _ in range(max_iterations):
            if candidate not in used:
                return candidate
            candidate += 1
        raise RuntimeError(
            f"build_arena_plan: exhausted {max_iterations} iterations looking "
            f"for a free arena number (used so far: {sorted(used)})"
        )

    for filepath, arena_name, directive in explicit:
        requested = directive.number  # type: ignore[assignment]  # has_directive guarantees non-None
        if requested in used:
            shifted = _next_free(requested + 1)
            if on_conflict == "fail":
                raise RuntimeError(
                    f"Arena number conflict: {filepath.name} requested "
                    f"#{requested:03d} but it is already taken."
                )
            if on_conflict != "silent":
                warnings.append(
                    f"Conflict: {filepath.name} requested "
                    f"#{requested:03d}-{directive.name or arena_name!r} but "
                    f"that number is taken. Shifting to #{shifted:03d}-"
                    f"{arena_name}."
                )
            requested = shifted
        assignments.append(
            ArenaAssignment(
                filepath=filepath,
                arena_name=arena_name,
                arena_number=requested,
                directive=directive,
            )
        )
        used.add(requested)

    next_num = (max(used) + 1) if used else 1
    for filepath, arena_name in implicit:
        n = _next_free(next_num)
        assignments.append(
            ArenaAssignment(
                filepath=filepath,
                arena_name=arena_name,
                arena_number=n,
                directive=directive_lookup.get(filepath, ArenaDirective()),
            )
        )
        used.add(n)
        next_num = n + 1

    return assignments, warnings


# ---------------------------------------------------------------------------
# Output directory resolution (Req 1) — arena-specific subdirectory helper
# ---------------------------------------------------------------------------


def resolve_arena_dir(
    output_dir: Path,
    arena_name: str,
    preferred_number: int | None = None,
) -> Path:
    """Resolve the NNN-<arena-name> directory inside ``context_output/arenas/``.

    Backward-compatible: when ``preferred_number`` is ``None`` (legacy path),
    reuses the highest existing sequence number for *arena_name* or creates
    ``<max+1>-<arena_name>``.

    When ``preferred_number`` is provided, that exact number is used (existing
    folder is reused, missing folder is created).  This is the path used by
    the ``# Target Arena:`` directive feature.

    Args:
        output_dir: Resolved output directory (e.g. ``context_output/``).
        arena_name: The arena name (filename-derived; source of truth).
        preferred_number: Optional explicit number from the directive.

    Returns:
        Path to the arena directory (created if necessary).
    """
    arenas_base = output_dir / "arenas"
    arenas_base.mkdir(parents=True, exist_ok=True)

    if preferred_number is not None:
        target = arenas_base / f"{preferred_number:03d}-{arena_name}"
        target.mkdir(parents=True, exist_ok=True)
        return target

    max_all = 0
    existing_match = None
    max_match = 0

    for d in arenas_base.iterdir():
        if d.is_dir() and "-" in d.name:
            parts = d.name.split("-", 1)
            if parts[0].isdigit():
                num = int(parts[0])
                if num > max_all:
                    max_all = num
                if parts[1] == arena_name:
                    if num > max_match:
                        max_match = num
                        existing_match = d

    if existing_match is not None:
        return existing_match

    next_num = max_all + 1
    next_dir = arenas_base / f"{next_num:03d}-{arena_name}"
    next_dir.mkdir(parents=True, exist_ok=True)
    return next_dir