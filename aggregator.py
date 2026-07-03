# & C:\Users\FOTE\AppData\Local\Programs\Python\Python314\python.exe c:/programming/Python/Projects/context/aggregator.py
"""File Aggregator — consolidates source files and generates project trees.

Outputs (written into the configurable output folder, e.g. ``context_output/``):
    context.{md,txt} — all file contents with relative-path headers (the LLM context)
    structure.txt    — visual directory tree of the detected project root
    arena.{md,txt}   — LMArena-style model comparison (Gemini judge or template)

The aggregate filename (``aggregate_filename``) and compare filename
(``compare_filename``) are settings; the extension follows ``output_format``.

Configuration precedence (Req 4):
    Command Line Flags > Interactive Prompts (--interactive) >
    Settings File (.context/settings.json) > Hardcoded Defaults.

Runs completely silently (non-interactive) by default.
"""

import sys
import asyncio
from pathlib import Path
from typing import cast

# Reconfigure stdout/stderr to UTF-8 to prevent encoding errors on Windows terminals
# pylint: disable=line-too-long
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]
# pylint: enable=line-too-long


# Import from core module package (for CLI execution and backwards compatibility with TUI/GUI)
from core.parser import (
    aggregate_files,
    find_project_root,
    generate_tree,
    load_ignore_patterns,
    initialize_environment,
    read_file_entries,
    resolve_output_dir,
    resolve_models_dir,
    discover_files_txt_with_directives,
    resolve_arena_dir,
    load_settings,
    save_settings,
    display_settings,
    migrate_old_outputs,
    migrate_to_per_file_folders,
    migrate_to_flat_layout,
    sync_paste_attachments,
    build_arena_plan,
    ArenaAssignment,
    ArenaDirective,
    get_latest_state,
    write_state_breadcrumb,
)
from core.counter import count_tokens
from core.judge import (
    collect_model_responses,
    build_compare_markdown,
    generate_compare_template,
    get_api_key,
    archive_model_responses,
    ensure_model_templates,
    GeminiJudge,
)
from core.arena import arena_filenames, arena_model_filename

# ---------------------------------------------------------------------------
# Interactive prompt helper (Req 4)
# ---------------------------------------------------------------------------


def _prompt_toggle(prompt: str, default_setting: bool) -> bool:
    """Interactive toggle prompt using Space+Enter / Enter semantics.

    * Pressing ``Enter`` selects the default/settings value.
    * Pressing ``Space`` then ``Enter`` enables/overrides the option
      (i.e. flips the value to ``True``).

    Args:
        prompt: The question text to display.
        default_setting: Current effective value (from settings/flags).

    Returns:
        The resolved boolean choice.
    """
    while True:
        try:
            raw = input(prompt)
        except EOFError:
            # Non-interactive terminal — fall back to default.
            return default_setting

        # Space + Enter → override (enable). Enter → default value.
        if " " in raw:
            return True
        if raw == "" or raw.strip() == "":
            return default_setting
        # Be lenient: accept y/n too.
        stripped = raw.strip().lower()
        if stripped in ("y", "yes", "true", "1"):
            return True
        if stripped in ("n", "no", "false", "0"):
            return False
        print("Press Enter for default, or Space then Enter to override.")


def _prompt_choice_count(prompt: str, default_count: int) -> int:
    """Interactive count prompt: Enter=default, Space+Enter=4.

    Args:
        prompt: The question text to display.
        default_count: Current effective model_count.

    Returns:
        The resolved model count (2 or 4).
    """
    while True:
        try:
            raw = input(prompt)
        except EOFError:
            return default_count

        if " " in raw:
            return 4
        if raw == "" or raw.strip() == "":
            return default_count
        stripped = raw.strip().lower()
        if stripped in ("2", "4"):
            return int(stripped)
        try:
            n = int(stripped)
            if n in (2, 4):
                return n
        except ValueError:
            pass
        print("Press Enter for default, or Space then Enter for 4.")


def _prompt_choice_format(prompt: str, default_format: str) -> str:
    """Interactive format prompt: Enter=default, Space+Enter=.txt.

    Args:
        prompt: The question text to display.
        default_format: Current effective output_format ("md" or "txt").

    Returns:
        The resolved format string ("md" or "txt").
    """
    while True:
        try:
            raw = input(prompt)
        except EOFError:
            return default_format

        if " " in raw:
            return "txt"
        if raw == "" or raw.strip() == "":
            return default_format
        stripped = raw.strip().lower().lstrip(".")
        if stripped in ("md", "txt"):
            return stripped
        print("Press Enter for default, or Space then Enter for .txt.")


def _prompt_merge() -> bool:
    """EC5: prompt whether to merge old files in the output folder.

    Enter = merge, Space+Enter = skip. Returns ``True`` to merge.
    """
    return _prompt_toggle(
        "Warn: Merge? [Enter=merge, Space=skip]: ", default_setting=True
    )


def _prompt_update_structure(prompt: str) -> bool:
    """Prompt the user whether to update structure.txt.

    * Enter key or inputs like 'y', 'yes' -> True (Update)
    * Space then Enter or inputs like 'n', 'no' -> False (Keep existing)
    """
    while True:
        try:
            raw = input(prompt)
        except EOFError:
            return True

        if " " in raw:
            return False
        if raw == "" or raw.strip() == "":
            return True
        stripped = raw.strip().lower()
        if stripped in ("y", "yes"):
            return True
        if stripped in ("n", "no"):
            return False
        print("Press Enter to update, or Space then Enter to skip/keep.")


# ---------------------------------------------------------------------------
# Output filename helpers (Req 2 — suffixed outputs)
# ---------------------------------------------------------------------------

_LEGACY_OUTPUT_NAMES = {
    "arena.txt",
    "arena.md",
    "context.txt",
    "context.md",
    "structure.txt",
    "compare.md",
    "compare.txt",
}


def _output_names(suffix: str, output_format: str) -> tuple[str, str, str]:
    """Build the (aggregate, structure, compare) filenames for a given suffix.

    Args:
        suffix: Output suffix (``""`` for files.txt, ``"_1"`` for files_1.txt).
        output_format: ``"md"`` or ``"txt"`` — sets compare extension.

    Returns:
        Tuple of (aggregate_filename, structure_filename, compare_filename).
    """
    # v3+ rename: ``arena.txt`` is now the LMArena compare file (when
    # ``output_format="txt"``); the aggregate lives in ``context.{ext}``.
    aggregate = f"context{suffix}.{output_format}"
    structure = f"structure{suffix}.txt"
    compare = f"arena{suffix}.{output_format}"
    return aggregate, structure, compare


# ---------------------------------------------------------------------------
# Per-file processing (Req 2 — one input → one output set)
# ---------------------------------------------------------------------------


def _process_one(
    files_txt: Path,
    arena_name: str,
    root: Path | None,
    output_dir: Path,
    patterns: frozenset[str],
    output_format: str,
    gemini_judge: bool,
    compact_mode: bool,
    model_count: int,
    preferred_number: int | None = None,
    settings: dict[str, object] | None = None,
) -> None:
    """Process a single input → v3-prefixed flat outputs in the arena directory.

    v3+ prefixed flat layout: every file inside the arena directory
    carries the same ``NNN-`` prefix as the folder name. For example::

        003-Hero/
        ├── 003-Hero.txt       ← input (self-contained copy)
        ├── 003-context.md     ← aggregate source code
        ├── 003-arena.md       ← LMArena comparison
        ├── 003-A.txt          ← Model A response
        ├── 003-B.txt          ← Model B response
        ├── 003-prompt.txt     ← Prompt sent to models
        └── 003-A_NOTES.md     ← (optional) Notes for Model A

    The prefix on every file (not just the folder) solves a tab-disambiguation
    problem when the user has multiple arenas open simultaneously.

    Args:
        files_txt: Path to the input files listing.
        arena_name: Output arena name derived from the input filename.
        root: Detected project root (or None).
        output_dir: Resolved output directory.
        patterns: Compiled ignore patterns.
        output_format: "md" or "txt".
        gemini_judge: Whether to run the Gemini judge.
        compact_mode: Whether to use compact compare output.
        model_count: Number of model response files to create.
        preferred_number: Optional explicit arena number from the
            ``# Target Arena:`` directive. Forwarded to
            :func:`resolve_arena_dir`.
        settings: Effective settings dict (kept for symmetry with the
            legacy signature; arena filenames are now computed via
            :func:`arena_filenames`).
    """
    import shutil as _shutil

    arena_dir = resolve_arena_dir(output_dir, arena_name, preferred_number=preferred_number)
    arena_dir.mkdir(parents=True, exist_ok=True)

    # v3+ prefixed output paths — every file lives directly in arena_dir
    # and carries the arena's NNN- prefix. Filenames honour ``output_format``
    # for context/arena extensions.
    filenames = arena_filenames(arena_dir, output_format)
    arena_path = filenames["context"]
    compare_path = filenames["arena"]
    prompt_file = filenames["prompt"]
    target_input_path = filenames["input"]

    # Copy input file into arena_dir (renamed to the prefixed name if
    # needed) so the arena is self-contained.
    if files_txt.resolve() != target_input_path.resolve() and not target_input_path.exists():
        try:
            _shutil.copy2(str(files_txt), str(target_input_path))
            print(f"[{files_txt.name}] Copied input → {target_input_path}")
        except OSError as exc:
            print(
                f"[{files_txt.name}] Warning: Could not copy input into arena: {exc}",
                file=sys.stderr,
            )

    # Ensure flat prompt.txt + A.txt/B.txt/... templates exist in arena_dir.
    if not prompt_file.exists():
        _ = prompt_file.touch()
        print(f"[{files_txt.name}] Created {prompt_file}")
    ensure_model_templates(arena_dir, model_count)

    # Read entries. Missing file → empty list (EC1: still emit empty outputs).
    try:
        entries = read_file_entries(files_txt)
    except FileNotFoundError:
        print(f"Input file not found: {files_txt}", file=sys.stderr)
        entries = []

    # EC1: empty files.txt → create empty templates in the output folder.
    if not entries:
        print(
            f"No entries found in {files_txt.name} — writing empty outputs to {arena_dir}/"
        )
        _ = arena_path.write_text("", encoding="utf-8")
        generate_compare_template(compare_path)
        return

    # 2. File aggregation
    full_files = sum(1 for _, ranges, _ in entries if ranges is None)
    snippets = sum(
        1 for _, ranges, important in entries
        if ranges is not None and not important
    )
    important = sum(
        1 for _, ranges, imp in entries
        if ranges is not None and imp
    )

    parts: list[str] = []
    if full_files:
        parts.append(f"{full_files} file(s)")
    if snippets:
        parts.append(f"{snippets} snippet(s)")
    if important:
        parts.append(f"{important} structure(s)")
    print(
        f"[{files_txt.name}] Aggregating {' + '.join(parts)} → {arena_path} …"
    )
    total_lines = aggregate_files(entries, arena_path, root)
    print(f"[{files_txt.name}] Aggregation complete. Total lines: {total_lines}")

    # 3. Token counts
    try:
        arena_content = arena_path.read_text(encoding="utf-8")
        token_count = count_tokens(arena_content)
        print(
            f"[{files_txt.name}] Total size: {len(arena_content)} characters"
            + f" | Total lines: {total_lines}"
            + f" | Estimated tokens: {token_count}"
        )
    except (OSError, ValueError) as exc:
        print(f"[{files_txt.name}] Warning: Could not count tokens: {exc}")

    # 4. Compare output from arena_dir flat model files (or llm.txt fallback).
    prompt, models_data = collect_model_responses(
        arena_dir, output_format, model_count
    )
    if models_data:
        verdict: str | None = None
        if gemini_judge:
            api_key = get_api_key(root)
            if api_key:
                try:
                    judge = GeminiJudge()
                    verdict = asyncio.run(judge.evaluate(prompt, models_data, api_key))
                    print(
                        f"[{files_txt.name}] Gemini comparison evaluation generated successfully."
                    )
                except RuntimeError as e:
                    print(
                        f"[{files_txt.name}] Warning: Gemini evaluation "
                        + f"failed ({e}). Falling back to manual template.",
                        file=sys.stderr,
                    )
            else:
                print(
                    f"[{files_txt.name}] API key skipped. Falling back "
                    + "to manual template.",
                    file=sys.stderr,
                )

        build_compare_markdown(
            prompt, models_data, compare_path,
            verdict=verdict, compact=compact_mode,
        )
        mode_str = " (COMPACT)" if compact_mode else ""
        judge_str = " with Gemini AI Judge" if verdict else ""
        print(
            f"[{files_txt.name}] Compare generated → {compare_path} "
            + f"({len(models_data)} models){mode_str}{judge_str}"
        )
    else:
        generate_compare_template(compare_path)
        print(
            f"[{files_txt.name}] No model responses found — default template → {compare_path}"
        )


# ---------------------------------------------------------------------------
# Interactive option resolution (Req 4 — prompt order a–e)
# ---------------------------------------------------------------------------


def _run_interactive_prompts(settings: dict[str, object]) -> dict[str, object]:
    """Prompt the user for all five options in the required order.

    Each prompt uses the current settings value as the default
    (Enter = keep setting, Space+Enter = override).

    Args:
        settings: Effective settings (already merged with defaults).

    Returns:
        A new settings dict with interactively-chosen values applied.
    """
    print()  # blank line before prompts
    gemini = _prompt_toggle(
        "Run Gemini auto-comparison? [Enter=skip, Space=run]: ",
        default_setting=bool(settings.get("gemini_judge", False)),
    )
    compact = _prompt_toggle(
        "Reduce tokens? Compact mode [Enter=skip, Space=enable]: ",
        default_setting=bool(settings.get("compact_mode", False)),
    )
    archive = _prompt_toggle(
        "Archive model responses? [Enter=no, Space=archive]: ",
        default_setting=bool(settings.get("archive", False)),
    )
    raw_val = settings.get("model_count", 2)
    default_count = int(raw_val) if isinstance(raw_val, (int, str)) else 2
    model_count = _prompt_choice_count(
        "How many models? [Enter=2, Space=4]: ",
        default_count=default_count,
    )
    output_format = _prompt_choice_format(
        "Output format? [Enter=.md, Space=.txt]: ",
        default_format=str(settings.get("output_format", "md")),
    )

    resolved = dict(settings)
    resolved["gemini_judge"] = gemini
    resolved["compact_mode"] = compact
    resolved["archive"] = archive
    resolved["model_count"] = model_count
    resolved["output_format"] = output_format
    return resolved


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------


def main() -> None:
    """Orchestrate CLI parsing, settings resolution, and aggregation."""
    import argparse

    parser = argparse.ArgumentParser(
        prog="aggregator",
        description=(
            "Aggregate source files and generate project trees for "
            + "LMArena comparisons."
        ),
    )
    _ = parser.add_argument(
        "root",
        nargs="?",
        default=None,
        help="Optional project root directory (defaults to CWD / auto-detect).",
    )
    _ = parser.add_argument(
        "--interactive",
        action="store_true",
        help="Prompt for options interactively (otherwise run silently).",
    )
    _ = parser.add_argument(
        "--settings",
        action="store_true",
        help="Print the active settings file path, content, and schema; then exit.",
    )
    _ = parser.add_argument(
        "--output",
        default=None,
        help="Override the output folder (default: settings.output_dir).",
    )
    _ = parser.add_argument(
        "--status",
        action="store_true",
        help="Print a compact project-state snapshot for AI agents and exit.",
    )
    _ = parser.add_argument(
        "--json",
        action="store_true",
        help="With --status: emit JSON to stdout (for programmatic use).",
    )
    _ = parser.add_argument(
        "-q", "--quiet",
        action="store_true",
        help="With --status: print only the next arena number on one line.",
    )
    args = parser.parse_args()

    # Resolve project root from positional arg or CWD.
    root_str = cast(str | None, args.root)
    cmd_root = Path(root_str) if root_str else None
    init_root = cmd_root.resolve() if cmd_root else Path.cwd()

    # --- --status: cheap snapshot for AI agents, then exit ----------------
    show_status = cast(bool, args.status)
    if show_status:
        settings = load_settings(init_root)
        output_dir = resolve_output_dir(init_root, settings)
        arenas_dir = output_dir / "arenas"
        inputs_dir_str = str(settings.get("inputs_dir", ".context/inputs"))
        inputs_dir = init_root / inputs_dir_str
        state = get_latest_state(arenas_dir, inputs_dir)

        if cast(bool, args.quiet):
            print(f"{state['next_number']:03d}" if state["next_number"] else "001")
            return

        if cast(bool, args.json):
            import json as _json
            print(_json.dumps(state, indent=2, ensure_ascii=False))
            return

        # Human-readable block (kept intentionally short to save agent tokens)
        print("--- PROJECT STATE ---")
        print(f"last_arena   : {state['last_arena'] or '(none)'}")
        if state["next_number"]:
            print(f"next_number  : {state['next_number']:03d}")
        else:
            print("next_number  : 001")
        print(f"total_arenas : {state['total_arenas']}")
        if state["latest_activity_arena"]:
            print(f"last_activity: {state['latest_activity_arena']} ({state['latest_activity_time']})")
        print(f"total_inputs : {state['total_inputs']}")
        if state["latest_input"]:
            print(f"latest_input : {state['latest_input']} ({state['latest_input_time']})")
        return

    # --- Req 10: --settings flag -----------------------------------------
    show_settings = cast(bool, args.settings)
    if show_settings:
        display_settings(init_root)
        return

    # --- Load settings (Req 4 settings layer) ----------------------------
    settings = load_settings(init_root)

    # --- Req 4: interactive prompts (override settings) ------------------
    is_interactive = cast(bool, args.interactive)
    if is_interactive:
        settings = _run_interactive_prompts(settings)
        # Persist the interactively-chosen values for next time.
        try:
            save_settings(init_root, settings)
        except OSError as exc:
            print(
                f"Warning: Could not save settings: {exc}",
                file=sys.stderr,
            )

    # --- Req 4: CLI flag overrides (output) ------------------------------
    cli_output = cast(str | None, args.output)

    # Resolve runtime values.
    output_dir = resolve_output_dir(init_root, settings, cli_output)
    output_format = str(settings.get("output_format", "md"))
    gemini_judge = bool(settings.get("gemini_judge", False))
    compact_mode = bool(settings.get("compact_mode", False))
    archive = bool(settings.get("archive", False))
    raw_model_count = settings.get("model_count", 2)
    model_count = int(raw_model_count) if isinstance(raw_model_count, (int, str)) else 2
    archive_dir = str(settings.get("archive_dir", "ARCHIVE"))

    # --- Migrate legacy CWD outputs + root models/ into output_dir/ ------
    _ = migrate_old_outputs(init_root, output_dir)
    # --- Wrap any flat outputs into per-file folders (v2 layout) --------
    _ = migrate_to_per_file_folders(output_dir)
    # --- Flatten per-file folders into the v3 truly-flat layout ---------
    # Safe to run every time: idempotent on already-flat trees. Pass
    # ``settings`` so phase-2 renames (arena.txt → context.{ext},
    # compare.{ext} → arena.{ext}) honour the user's output_format and
    # aggregate_filename / compare_filename settings.
    _ = migrate_to_flat_layout(output_dir, settings=settings)

    # --- Initialize environment (files.txt) ---------
    initialize_environment(init_root, model_count, output_dir)

    # --- EC5: old files in output folder ---------------------------------
    any_old = (
        any((output_dir / name).is_file() for name in _LEGACY_OUTPUT_NAMES)
        or any(output_dir.glob("arena_*.txt"))
        or any(output_dir.glob("arena_*.md"))
        or any(output_dir.glob("context_*.txt"))
        or any(output_dir.glob("context_*.md"))
        or any(output_dir.glob("structure_*.txt"))
    )
    if any_old and is_interactive:
        merge = _prompt_merge()
        if not merge:
            print("Skipping merge — existing output files will be overwritten.")
    # Non-interactive: default silently to overwriting (auto-merge).


    # --- Detect project root (used for tree + ignore patterns) -----------
    files_txt = Path("files.txt")
    cwd = Path.cwd()

    # Determine root: explicit arg > first-entry-based detection > CWD.
    if cmd_root:
        root: Path | None = cmd_root.resolve()
    elif files_txt.is_file():
        try:
            entries = read_file_entries(files_txt)
            root = find_project_root(entries[0][0]) if entries else None
        except FileNotFoundError:
            root = None
    else:
        root = None

    if root is None:
        root = cwd

    patterns = load_ignore_patterns(root)

    # --- Centralize structure.txt and Drift Detection --------------------
    # Build live directory tree representation
    scan_root = root if root else cwd
    tree_lines = [f"Project Root: {scan_root.name}/"] + generate_tree(
        scan_root, scan_root, patterns
    )
    live_structure = "\n".join(tree_lines)

    # structure.txt also lives in its own folder for consistency.
    structure_path = output_dir / "structure" / "structure.txt"
    should_write_structure = False

    if not structure_path.is_file():
        should_write_structure = True
    else:
        try:
            existing_structure = structure_path.read_text(encoding="utf-8")
        except OSError:
            existing_structure = ""

        if existing_structure.strip() != live_structure.strip():
            if is_interactive:
                prompt = "WARNING: Project structure has changed. Would you like to update structure.txt? [Y/n] "
                if _prompt_update_structure(prompt):
                    should_write_structure = True
                else:
                    print("Kept existing structure.txt.")
            else:
                # Silent/non-interactive mode defaults to updating
                should_write_structure = True

    if should_write_structure:
        structure_path.parent.mkdir(parents=True, exist_ok=True)
        _ = structure_path.write_text(live_structure, encoding="utf-8")
        print(f"Structure written → {structure_path}")

    # --- Req 2: discover and process ALL files*.txt ----------------------
    discovered, directive_lookup = discover_files_txt_with_directives(
        cwd, root, settings
    )
    if not discovered:
        print("No files*.txt found in CWD or .context/inputs/ — nothing to do.")
        return

    # --- Target-arena directive plan --------------------------------------
    respect_directive = bool(settings.get("respect_target_arena_directive", True))
    on_conflict = str(settings.get("on_arena_number_conflict", "warn_and_shift"))

    if respect_directive:
        assignments, plan_warnings = build_arena_plan(
            discovered,
            directive_lookup,
            on_conflict=on_conflict,
        )
        # Print conflict warnings now so they are visible alongside stdout.
        for warning in plan_warnings:
            print(f"WARNING: {warning}", file=sys.stderr)
        # Build a quick lookup for the inner loop.
        assignment_by_path: dict[Path, ArenaAssignment] = {
            a.filepath: a for a in assignments
        }
    else:
        # Legacy behaviour: every input gets auto-numbered, no directives used.
        assignment_by_path = {
            p: ArenaAssignment(
                filepath=p,
                arena_name=name,
                arena_number=0,  # signal "auto" to _process_one
                directive=directive_lookup.get(p, ArenaDirective()),
            )
            for p, name in discovered
        }

    for files_input, arena_name in discovered:
        assignment = assignment_by_path.get(files_input)
        preferred = (
            assignment.arena_number
            if assignment and assignment.arena_number > 0
            else None
        )
        try:
            _process_one(
                files_txt=files_input,
                arena_name=arena_name,
                root=root,
                output_dir=output_dir,
                patterns=patterns,
                output_format=output_format,
                gemini_judge=gemini_judge,
                compact_mode=compact_mode,
                model_count=model_count,
                preferred_number=preferred,
                settings=settings,
            )
            # --- Req 5: archiving workflow (local to each arena) -----------------
            if archive:
                arena_dir = resolve_arena_dir(output_dir, arena_name, preferred_number=preferred)
                archived = archive_model_responses(arena_dir, archive_dir)
                if archived:
                    # Re-create fresh templates for the configured model count.
                    _ = ensure_model_templates(arena_dir, model_count)
                    print(f"[{files_input.name}] Archived {len(archived)} file(s) to {archive_dir}.")
        except Exception as exc:  # pylint: disable=broad-exception-caught  # noqa: BLE001 — last-resort guard per file
            print(
                f"ERROR processing {files_input.name}: {exc}",
                file=sys.stderr,
            )

    # --- Validation report (target-arena directives) ----------------------
    if respect_directive:
        n_total = len(discovered)
        n_with_directive = sum(
            1 for d in directive_lookup.values() if d.has_directive
        )
        n_shifted = sum(
            1
            for p, _ in discovered
            if directive_lookup.get(p, ArenaDirective()).has_directive
            and (
                (a := assignment_by_path.get(p))
                and a.directive.number != a.arena_number
            )
        )
        n_stale_names = sum(
            1
            for p, _ in discovered
            if (d := directive_lookup.get(p, ArenaDirective())).has_directive
            and d.name is not None
            and (
                (a := assignment_by_path.get(p))
                and d.name.lower().replace("-", "") != a.arena_name.lower().replace("-", "")
            )
        )
        n_auto = n_total - n_with_directive
        print()
        print("Arena directive check:")
        print(f"  Total inputs:                {n_total}")
        print(f"  With '# Target Arena:':      {n_with_directive}")
        if n_shifted:
            print(f"  Shifted (conflict):          {n_shifted}  (see warnings above)")
        if n_stale_names:
            print(
                f"  Stale directive name:        {n_stale_names}  "
                "(filename used as source of truth; update the directive to match)"
            )
        print(f"  Auto-numbered (no directive):{n_auto}")

    # --- Paste-attachments archival: copy today's manual pastes into
    # context_output/ with smart-keyword filenames. Disabled by default.
    _ = sync_paste_attachments(init_root, output_dir, settings)

    # --- Write state breadcrumb (Phase F: optional cache) -----------------
    try:
        write_state_breadcrumb(
            init_root / ".context",
            output_dir / "arenas",
            init_root / str(settings.get("inputs_dir", ".context/inputs")),
        )
    except OSError as exc:
        print(f"Warning: Could not write state breadcrumb: {exc}", file=sys.stderr)

    print(f"\nDone. Outputs written to: {output_dir}")


if __name__ == "__main__":
    main()
