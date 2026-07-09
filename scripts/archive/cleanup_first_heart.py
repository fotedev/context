"""first_heart input-file cleanup script.

Migrates arena input files under ``<project>/<output_dir>/arenas/`` to the
v3 flat layout the new :func:`core.discovery.discover_files_txt` Tier 1
expects (one ``NNN-<name>.txt`` per arena dir).

The script is **dry-run by default**. Pass ``--apply`` to actually mutate
the filesystem. It performs four steps per arena:

* **Step A (Rename):** Rename legacy / wrongly-prefixed ``.txt`` files to
  the canonical ``NNN-<name>.txt`` that Tier 1 looks up exactly.
* **Step B (Wipe bad paths):** Drop lines that point to v2-style output
  artefacts (``answers/...``, ``compare.md``, ``arena.md``, ``context.md``)
  or to files that no longer exist on disk.
* **Step C (Heuristic search):** For each arena, look under the project's
  ``src/`` tree and project root for source files whose name contains the
  arena's name suffix (case-insensitive substring match, restricted to
  common web/TS extensions).
* **Step D (Directive check):** Ensure line 1 is the canonical
  ``# Target Arena: NNN-<name>`` directive.

Usage::

    python cleanup_first_heart.py
    python cleanup_first_heart.py --apply
    python cleanup_first_heart.py --project C:/path/to/project --output-dir context_output
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Reserved filenames in an arena dir — must NEVER be picked as the input.
# These are output artefacts that may legitimately exist alongside an input.
# ---------------------------------------------------------------------------
RESERVED_ARENA_STEMS: frozenset[str] = frozenset(
    {
        "arena",
        "compare",
        "context",
        "prompt",
        "A",
        "B",
        "C",
        "D",
    }
)

# File extensions to consider when heuristically searching for source code.
SOURCE_EXTENSIONS: tuple[str, ...] = (
    ".tsx",
    ".ts",
    ".jsx",
    ".js",
    ".css",
    ".scss",
    ".sass",
    ".vue",
    ".svelte",
    ".html",
    ".md",
    ".json",
    ".sql",
)

# Substrings in a path that mark it as a v2 output artefact — auto-wiped.
V2_OUTPUT_TOKENS: tuple[str, ...] = (
    "/answers/",
    "\\answers\\",
    "/compare.md",
    "\\compare.md",
    "/arena.md",
    "\\arena.md",
    "/context.md",
    "\\context.md",
)

# Max heuristic matches per arena (avoid dumping 80 files for "Hero").
MAX_HEURISTIC_MATCHES: int = 10

# Arena names too generic for substring matching — skip heuristic, leave the
# input file empty (with the directive). All of these appeared in real
# first_heart data as v1 legacy "I just dumped files here" arenas.
GENERIC_ARENA_NAMES: frozenset[str] = frozenset(
    {
        "files",
        "data",
        "utils",
        "lib",
        "components",
        "hooks",
        "types",
        "locales",
        "config",
    }
)

# Top-level dirs to NEVER search when looking for source files. Many of
# these are tool caches or generated coverage reports that would create
# false positives for any arena name containing common substrings.
NOISE_TOP_LEVEL_DIRS: frozenset[str] = frozenset(
    {
        "node_modules",
        "coverage",
        "dist",
        "build",
        ".git",
        ".next",
        ".venv",
        ".opencode",
        ".cursor",
        ".agent",
        ".agents",
        ".impeccable",
        ".netlify",
        ".vscode",
        ".specify",
        ".trae",
        "get-shit-done",
        "gifts",
        "i18n-audit",
        "sandbox",
        "uploads",
        "public",
        "specs",
        "supabase",
    }
)


# ---------------------------------------------------------------------------
# Data classes — one per arena, accumulated across steps for the dry-run
# report. No field is mutated after the corresponding step runs.
# ---------------------------------------------------------------------------


@dataclass
class ArenaPlan:
    """Planned changes for a single arena directory."""

    arena_dir: Path
    arena_id: str  # e.g. "006-AdminDashboard"
    arena_name: str  # e.g. "AdminDashboard"

    # Step A
    rename_from: Path | None = None
    rename_to: Path | None = None
    already_correct: bool = False

    # Step B
    bad_paths_to_wipe: list[str] = field(default_factory=list)
    surviving_paths: list[str] = field(default_factory=list)

    # Step C
    heuristic_matches: list[Path] = field(default_factory=list)

    # Step D
    directive_status: str = ""  # "ok" | "missing" | "mismatch"
    directive_line: str = ""

    @property
    def input_path(self) -> Path:
        return self.arena_dir / f"{self.arena_id}.txt"

    def has_any_action(self) -> bool:
        return bool(
            self.rename_from
            or self.bad_paths_to_wipe
            or self.heuristic_matches
            or self.directive_status != "ok"
        )


# ---------------------------------------------------------------------------
# Step A — find legacy / wrongly-prefixed .txt and plan a rename.
# ---------------------------------------------------------------------------


def _list_candidate_inputs(arena_dir: Path) -> list[Path]:
    """All non-reserved .txt files in the arena dir, sorted by name.

    "Reserved" here means anything that looks like an output artefact for
    the current arena — either the bare ``prompt.txt`` / ``arena.md`` /
    ``A.txt`` style or the v3-prefixed equivalent (``003-prompt.txt`` etc.).
    Those are NEVER valid input files and must not be confused for the
    canonical ``NNN-<name>.txt`` input.
    """
    out: list[Path] = []
    for p in sorted(arena_dir.iterdir()):
        if not p.is_file():
            continue
        if p.suffix != ".txt":
            continue
        if _is_reserved(p.name, arena_dir.name):
            continue
        out.append(p)
    return out


def _is_reserved(filename: str, arena_dirname: str) -> bool:
    """Decide whether *filename* is a v2 or v3 reserved output artefact.

    Reserved stems (without extension): ``prompt``, ``arena``, ``context``,
    ``compare``, plus ``A``/``B``/``C``/``D`` for the model-answer slots.

    A file is reserved if its stem (after stripping ``.txt``) is one of:
      * a bare reserved stem (``prompt.txt``, ``A.txt`` ...);
      * a v3-prefixed reserved stem — the arena's numeric prefix + dash +
        reserved stem (``003-prompt.txt``, ``003-A.txt`` ...).

    The numeric prefix is extracted from ``arena_dirname`` (e.g. ``"003"``
    from ``"003-Hero"``). We never split the filename on ``-`` and accept
    arbitrary leftovers — that would false-positive on legitimate arena
    names like ``synthesis-prompt`` or ``change-visual-identity``.
    """
    stem = filename[:-len(".txt")]  # drop .txt
    if stem in RESERVED_ARENA_STEMS:
        return True
    # v3-prefixed: derive the numeric prefix from arena_dirname.
    prefix = ""
    if arena_dirname and "-" in arena_dirname:
        prefix = arena_dirname.split("-", 1)[0]
    if prefix and prefix.isdigit():
        for reserved in RESERVED_ARENA_STEMS:
            if stem == f"{prefix}-{reserved}":
                return True
    return False


def plan_rename(plan: ArenaPlan) -> None:
    """Step A: figure out which file should be renamed to ``<NNN>-<name>.txt``.

    Logic:
    * If the canonical name already exists and is non-empty: mark as correct.
    * Else if exactly ONE non-reserved ``.txt`` exists: rename it.
    * Else if multiple candidates: bail out — refuse to guess. Operator must
      pick manually. (Should be rare.)
    """
    expected = plan.input_path

    if expected.is_file() and expected.stat().st_size >= 0:
        # File exists (size may be 0). Either way, no rename needed.
        plan.already_correct = True
        return

    candidates = _list_candidate_inputs(plan.arena_dir)
    if len(candidates) == 1:
        plan.rename_from = candidates[0]
        plan.rename_to = expected
    elif len(candidates) == 0:
        # No source .txt at all — nothing to rename. Step D will add a directive.
        return
    else:
        # Multiple candidates — ambiguous. Don't touch.
        plan.rename_from = None  # signal: ambiguous
        plan.directive_status = "ambiguous-multiple-inputs"


# ---------------------------------------------------------------------------
# Step B — classify lines into "keep" vs "wipe".
# ---------------------------------------------------------------------------


def _is_v2_output_path(line: str) -> bool:
    return any(tok in line for tok in V2_OUTPUT_TOKENS)


def classify_lines(plan: ArenaPlan, source_file: Path | None) -> None:
    """Step B: parse the existing (post-rename) input file and split lines.

    * Directive line (``# Target Arena: ...``) is preserved verbatim.
    * Lines pointing to v2 output artefacts (``answers/``, ``compare.md``,
      ``arena.md``, ``context.md``) are flagged for wipe.
    * Other lines that resolve to real files are kept.
    * Other lines that resolve to NON-existent files are also flagged
      (these are the stale paths that broke the original arena).

    If ``source_file`` is None (no input existed), this is a no-op.
    """
    if source_file is None or not source_file.is_file():
        return

    try:
        text = source_file.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        text = source_file.read_text(encoding="latin-1")

    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            # Comment / directive — keep as-is.
            plan.surviving_paths.append(raw)
            continue
        if _is_v2_output_path(stripped):
            plan.bad_paths_to_wipe.append(stripped)
            continue
        # Reject "trivial" paths that resolve to non-files. ``.`` / ``..``
        # / ``/`` all pass Path.exists() but carry no information; in
        # particular the ``.`` left over from markdown front-matter /
        # separator lines keeps sneaking back in as a "surviving path".
        if stripped in {".", "..", "./", "../", "/", "\\"}:
            plan.bad_paths_to_wipe.append(stripped)
            continue
        # Reject lines whose only path characters are separators or
        # punctuation (e.g. ``---``, ``***``, ``|---|---|`` from markdown
        # tables that ``_is_v2_output_path`` didn't catch). The original
        # file is text and these aren't file paths in any sense.
        if all(c in "-*|_= " for c in stripped):
            plan.bad_paths_to_wipe.append(stripped)
            continue
        # Check existence — compare against project root, not cwd.
        p = Path(stripped)
        if not p.is_absolute():
            # Assume relative to project root.
            p = plan.arena_dir.parent.parent.parent / stripped
        # Try as-is and try lowercase-letter path normalization for Windows.
        if p.is_file():
            plan.surviving_paths.append(raw)
        else:
            plan.bad_paths_to_wipe.append(stripped)


# ---------------------------------------------------------------------------
# Step C — heuristic search.
# ---------------------------------------------------------------------------


def _strip_name_to_keywords(arena_name: str) -> list[str]:
    """Split an arena name like "AdminDashboard" into matchable tokens.

    Strategy: case-insensitive substring on the full name (good enough for
    first_heart's PascalCase filenames), plus a dash/camel split fallback
    so e.g. "BirthdayCountdown" still matches "BirthdayCountdown.tsx"
    without false positives on random files.
    """
    # The full arena name (case-insensitive) is the primary matcher.
    return [arena_name.lower()]


def find_heuristic_matches(
    plan: ArenaPlan, project_root: Path
) -> None:
    """Step C: scan the project for source files matching the arena name.

    Skips:
    * Generic arena names ("files", "data", "utils", ...) — substring would
      match dozens of unrelated files.
    * All paths under noise directories (coverage, node_modules, .cursor,
      get-shit-done, ...).

    Note: a minimum-name-length guard was tried here but rejected — even a
    short legitimate name like ``Why`` (3 chars) maps to real source files
    (``Why.tsx``); the GENERIC_ARENA_NAMES stoplist plus the noise-dir
    filter is enough protection against false positives.
    """
    name_lower = plan.arena_name.lower()
    if name_lower in GENERIC_ARENA_NAMES:
        return

    keywords = _strip_name_to_keywords(plan.arena_name)
    if not keywords:
        return

    seen: set[Path] = set()
    candidates: list[Path] = []

    # Search roots: src/ (preferred — that's where real code lives) and the
    # project root for top-level config/docs (README.md, FEATURES.md, etc.).
    search_roots: list[Path] = []
    src_dir = project_root / "src"
    if src_dir.is_dir():
        search_roots.append(src_dir)
    search_roots.append(project_root)

    for root in search_roots:
        if not root.is_dir():
            continue
        for p in root.rglob("*"):
            try:
                # Reject anything whose path contains a noise directory.
                if any(part in NOISE_TOP_LEVEL_DIRS for part in p.parts):
                    continue
                if not p.is_file():
                    continue
            except OSError:
                continue
            if p.suffix.lower() not in SOURCE_EXTENSIONS:
                continue
            if p.stem.lower() in {"index", "readme", "license", "package"}:
                # Generic stems — too many false positives.
                continue
            stem_lower = p.stem.lower()
            if not any(kw in stem_lower for kw in keywords):
                continue
            try:
                resolved = p.resolve()
            except OSError:
                continue
            if resolved in seen:
                continue
            seen.add(resolved)
            candidates.append(p)
            if len(candidates) >= MAX_HEURISTIC_MATCHES:
                break
        if len(candidates) >= MAX_HEURISTIC_MATCHES:
            break

    plan.heuristic_matches = candidates


# ---------------------------------------------------------------------------
# Step D — directive check.
# ---------------------------------------------------------------------------


def check_directive(plan: ArenaPlan, source_file: Path | None) -> None:
    """Step D: confirm line 1 is ``# Target Arena: <arena_id>``."""
    expected_line = f"# Target Arena: {plan.arena_id}"

    if source_file is None or not source_file.is_file():
        plan.directive_status = "missing"
        plan.directive_line = expected_line
        return

    try:
        text = source_file.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        text = source_file.read_text(encoding="latin-1")

    first_line = text.splitlines()[0].strip() if text.splitlines() else ""
    if first_line == expected_line:
        plan.directive_status = "ok"
        plan.directive_line = first_line
    elif first_line.startswith("# Target Arena:"):
        plan.directive_status = "mismatch"
        plan.directive_line = expected_line
    else:
        plan.directive_status = "missing"
        plan.directive_line = expected_line


# ---------------------------------------------------------------------------
# Orchestration.
# ---------------------------------------------------------------------------


_ARENA_NUM_RE = re.compile(r"^(\d{3})-(.+)$")


def discover_arenas(project_root: Path, output_dir: str) -> list[ArenaPlan]:
    """Enumerate numbered arena dirs under ``<project>/<output_dir>/arenas/``."""
    arenas_root = project_root / output_dir / "arenas"
    if not arenas_root.is_dir():
        return []
    plans: list[ArenaPlan] = []
    for arena_dir in sorted(arenas_root.iterdir()):
        if not arena_dir.is_dir():
            continue
        m = _ARENA_NUM_RE.match(arena_dir.name)
        if not m:
            continue
        arena_id = arena_dir.name  # e.g. "006-AdminDashboard"
        arena_name = m.group(2)
        plans.append(ArenaPlan(arena_dir=arena_dir, arena_id=arena_id, arena_name=arena_name))
    return plans


def run_pipeline(
    plans: list[ArenaPlan], project_root: Path
) -> None:
    """Run Steps A-D on every arena plan (mutates the plans in place).

    In dry-run mode the rename hasn't happened yet, so Steps B and D must
    read from the *source* file (the legacy name) when one is queued for
    rename. Once we move to --apply the rename happens first and the rest
    of the pipeline re-reads from the canonical path.
    """
    for plan in plans:
        # A
        plan_rename(plan)

        # Decide which existing file to read for B and D:
        # * If Step A is renaming, the legacy file holds the old content.
        # * Otherwise the canonical (already-correct) file is the source.
        if plan.rename_from:
            source_for_bd = plan.rename_from
        else:
            source_for_bd = plan.input_path

        # B
        classify_lines(plan, source_for_bd if source_for_bd.exists() else None)

        # C
        find_heuristic_matches(plan, project_root)

        # D
        check_directive(plan, source_for_bd if source_for_bd.exists() else None)


# ---------------------------------------------------------------------------
# Reporting — only the dry-run path is exercised here.
# ---------------------------------------------------------------------------


def print_dry_run(plans: list[ArenaPlan], project_root: Path) -> None:
    print("=" * 78)
    print(f"DRY RUN — first_heart cleanup ({len(plans)} arenas)")
    print(f"Project root : {project_root}")
    print(f"Output dir   : {project_root.name}/context_output/arenas/")
    print("=" * 78)

    no_action = 0
    for plan in plans:
        if not plan.has_any_action():
            no_action += 1
            continue

        print(f"\n[ {plan.arena_id} ]  ({plan.arena_dir})")
        # Step A
        if plan.already_correct:
            print("  A. rename       : (already correct) skip")
        elif plan.rename_from and plan.rename_to:
            print(f"  A. rename       : {plan.rename_from.name}  ->  {plan.rename_to.name}")
        elif plan.directive_status == "ambiguous-multiple-inputs":
            print("  A. rename       : AMBIGUOUS (multiple candidate .txt) — manual review")
        else:
            print("  A. rename       : no candidate .txt — will create from scratch")
        # Step B
        if plan.bad_paths_to_wipe:
            print(f"  B. wipe ({len(plan.bad_paths_to_wipe)} lines):")
            for line in plan.bad_paths_to_wipe:
                print(f"      - {line}")
        else:
            print("  B. wipe         : (none)")
        # Surviving paths (informational)
        if plan.surviving_paths:
            real_paths = [p for p in plan.surviving_paths if not p.strip().startswith("#")]
            if real_paths:
                print(f"  B. keep  ({len(real_paths)} paths):")
                for p in real_paths:
                    print(f"      + {p}")
        # Step C
        if plan.heuristic_matches:
            print(f"  C. heuristic ({len(plan.heuristic_matches)} matches):")
            for p in plan.heuristic_matches:
                try:
                    rel = p.relative_to(project_root)
                except ValueError:
                    rel = p
                print(f"      > {rel.as_posix()}")
        else:
            print("  C. heuristic    : (no matches)")
        # Step D
        if plan.directive_status == "ok":
            print(f"  D. directive    : ok  ({plan.directive_line!r})")
        elif plan.directive_status == "mismatch":
            print(f"  D. directive    : MISMATCH (would rewrite to {plan.directive_line!r})")
        elif plan.directive_status == "missing":
            print(f"  D. directive    : MISSING (would prepend {plan.directive_line!r})")
        elif plan.directive_status == "ambiguous-multiple-inputs":
            print("  D. directive    : skipped (ambiguous in Step A)")
        else:
            print(f"  D. directive    : {plan.directive_status}")

    print("\n" + "=" * 78)
    print(f"Summary: {no_action} arenas need no change, "
          f"{len(plans) - no_action} arenas need cleanup.")


# ---------------------------------------------------------------------------
# Apply — actually mutate files. Run only after a successful dry-run review.
# ---------------------------------------------------------------------------


def apply_changes(plans: list[ArenaPlan], project_root: Path) -> None:
    """Execute the planned changes on disk.

    Order matters:
    1. All renames first (so subsequent reads see the canonical filename).
    2. Then for each arena, read the (now-renamed) input, build the new
       content, and write it back atomically via a sibling temp file.

    The new file content is composed as:
      1. The directive line (prepended if missing, rewritten if mismatched).
      2. Any surviving valid paths from the original file.
      3. Any heuristic matches that aren't already in the surviving set,
         expressed as project-root-relative POSIX paths.
      4. A trailing newline.
    """
    print("=" * 78)
    print(f"APPLYING changes to {len(plans)} arenas in {project_root}")
    print("=" * 78)

    # --- Step 1: rename all queued files ---------------------------------
    rename_count = 0
    for plan in plans:
        if plan.rename_from and plan.rename_to:
            if plan.rename_from.resolve() != plan.rename_to.resolve():
                plan.rename_to.parent.mkdir(parents=True, exist_ok=True)
                plan.rename_from.rename(plan.rename_to)
                print(
                    f"  renamed: {plan.rename_from.name}  ->  "
                    f"{plan.rename_to.name}  ({plan.arena_id})"
                )
                rename_count += 1
    print(f"\nRenamed {rename_count} files.")

    # --- Step 2: rebuild each input file --------------------------------
    write_count = 0
    for plan in plans:
        target = plan.input_path  # canonical NNN-name.txt
        try:
            new_content = _build_new_content(plan, project_root)
            target.write_text(new_content, encoding="utf-8")
            write_count += 1
        except OSError as exc:
            print(f"  ERROR writing {target}: {exc}", file=sys.stderr)

    print(f"Rewrote {write_count} input files.")


def _build_new_content(plan: ArenaPlan, project_root: Path) -> str:
    """Compose the final input file content for *plan*.

    Structure:
      * Directive line first (always).
      * Then surviving valid paths from the original (deduped, project-
        relative POSIX).
      * Then heuristic matches that aren't already covered.
      * One blank line between directive and path block (cosmetic).
    """
    parts: list[str] = []

    # Directive
    parts.append(plan.directive_line or f"# Target Arena: {plan.arena_id}")

    # Existing valid paths (non-comment lines from the original file)
    seen: set[str] = set()
    real_survivors: list[str] = []
    for raw in plan.surviving_paths:
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        canonical = _canonicalise(s, project_root)
        if canonical in seen:
            continue
        seen.add(canonical)
        real_survivors.append(canonical)

    # Heuristic matches
    for match in plan.heuristic_matches:
        try:
            canonical = match.resolve().relative_to(project_root.resolve()).as_posix()
        except (ValueError, OSError):
            canonical = str(match)
        if canonical in seen:
            continue
        seen.add(canonical)
        real_survivors.append(canonical)

    if real_survivors:
        parts.append("")  # blank line between directive and paths
        parts.extend(real_survivors)

    return "\n".join(parts) + "\n"


def _canonicalise(path_str: str, project_root: Path) -> str:
    """Return a project-root-relative POSIX string for *path_str* (best-effort).

    Used for dedupe across surviving + heuristic paths. Falls back to the
    raw stripped string when the path can't be resolved.
    """
    p = Path(path_str.strip())
    if not p.is_absolute():
        p = project_root / path_str.strip()
    try:
        return p.resolve().relative_to(project_root.resolve()).as_posix()
    except (ValueError, OSError):
        return path_str.strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--project",
        default=r"C:\programming\Python\Projects\first_heart",
        help="Project root to clean.",
    )
    parser.add_argument(
        "--output-dir",
        default="context_output",
        help="Output dir name containing 'arenas/' (default: context_output).",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually mutate files. Default is dry-run.",
    )
    args = parser.parse_args(argv)

    project_root = Path(args.project)
    if not project_root.is_dir():
        print(f"ERROR: project root not found: {project_root}", file=sys.stderr)
        return 1

    plans = discover_arenas(project_root, args.output_dir)
    if not plans:
        print(f"ERROR: no arenas found under {project_root / args.output_dir / 'arenas'}",
              file=sys.stderr)
        return 1

    run_pipeline(plans, project_root)

    if args.apply:
        apply_changes(plans, project_root)
    else:
        print_dry_run(plans, project_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
