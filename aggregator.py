# & C:\Users\FOTE\AppData\Local\Programs\Python\Python314\python.exe c:/programming/Python/Projects/context/aggregator.py
"""File Aggregator — consolidates source files and generates project trees.

Outputs (written into the configurable output folder, e.g. ``context_output/``):
    arena.txt     — all file contents with relative-path headers
    structure.txt — visual directory tree of the detected project root
    compare.md    — LMArena-style model comparison (Gemini judge or template)

Configuration precedence (Req 4):
    Command Line Flags > Interactive Prompts (--interactive) >
    Settings File (.context/settings.json) > Hardcoded Defaults.

Runs completely silently (non-interactive) by default.
"""

import sys
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
    discover_files_txt,
    load_settings,
    save_settings,
    display_settings,
    migrate_old_outputs,
)
from core.counter import count_tokens
from core.judge import (
    collect_model_responses,
    build_compare_markdown,
    generate_compare_template,
    get_api_key,
    get_gemini_verdict,
    archive_model_responses,
    ensure_model_templates,
)

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


# ---------------------------------------------------------------------------
# Output filename helpers (Req 2 — suffixed outputs)
# ---------------------------------------------------------------------------

_LEGACY_OUTPUT_NAMES = {
    "arena.txt",
    "structure.txt",
    "compare.md",
    "compare.txt",
}


def _output_names(suffix: str, output_format: str) -> tuple[str, str, str]:
    """Build the (arena, structure, compare) filenames for a given suffix.

    Args:
        suffix: Output suffix (``""`` for files.txt, ``"_1"`` for files_1.txt).
        output_format: ``"md"`` or ``"txt"`` — sets compare extension.

    Returns:
        Tuple of (arena_filename, structure_filename, compare_filename).
    """
    arena = f"arena{suffix}.txt"
    structure = f"structure{suffix}.txt"
    compare = f"compare{suffix}.{output_format}"
    return arena, structure, compare


# ---------------------------------------------------------------------------
# Per-file processing (Req 2 — one input → one output set)
# ---------------------------------------------------------------------------


def _process_one(
    files_txt: Path,
    suffix: str,
    root: Path | None,
    output_dir: Path,
    patterns: frozenset[str],
    output_format: str,
    gemini_judge: bool,
    compact_mode: bool,
    models_dir: Path,
) -> None:
    """Process a single files*.txt input → arena/structure/compare outputs.

    Args:
        files_txt: Path to the input files listing.
        suffix: Output suffix derived from the input filename.
        root: Detected project root (or None).
        output_dir: Resolved output directory.
        patterns: Compiled ignore patterns.
        output_format: "md" or "txt".
        gemini_judge: Whether to run the Gemini judge.
        compact_mode: Whether to use compact compare output.
        models_dir: Canonical models directory.
    """
    arena_name, structure_name, compare_name = _output_names(suffix, output_format)
    arena_path = output_dir / arena_name
    structure_path = output_dir / structure_name
    compare_path = output_dir / compare_name

    # Read entries. Missing file → empty list (EC1: still emit empty outputs).
    try:
        entries = read_file_entries(files_txt)
    except FileNotFoundError:
        print(f"Input file not found: {files_txt}", file=sys.stderr)
        entries = []

    # EC1: empty files.txt → create empty templates in the output folder.
    if not entries:
        print(
            f"No entries found in {files_txt.name} — writing empty outputs to {output_dir}/"
        )
        for p in (arena_path, structure_path):
            p.parent.mkdir(parents=True, exist_ok=True)
            _ = p.write_text("", encoding="utf-8")
        generate_compare_template(compare_path)
        return

    # 1. Project tree
    if root:
        print(f"[{files_txt.name}] Project root detected: {root}")
        tree_lines = [f"Project Root: {root.name}/"] + generate_tree(
            root, root, patterns
        )
        _ = structure_path.write_text(
            "\n".join(tree_lines), encoding="utf-8"
        )
        print(f"[{files_txt.name}] Structure written → {structure_path}")
    else:
        print(
            f"[{files_txt.name}] No project root detected — skipping structure.",
            file=sys.stderr,
        )
        _ = structure_path.write_text("", encoding="utf-8")

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
    aggregate_files(entries, arena_path, root)
    print(f"[{files_txt.name}] Aggregation complete.")

    # 3. Token counts
    try:
        arena_content = arena_path.read_text(encoding="utf-8")
        token_count = count_tokens(arena_content)
        print(
            f"[{files_txt.name}] Total size: {len(arena_content)} characters"
            + f" | Estimated tokens: {token_count}"
        )
    except (OSError, ValueError) as exc:
        print(f"[{files_txt.name}] Warning: Could not count tokens: {exc}")

    # 4. Compare output from models/ dir (or llm.txt fallback) or template
    prompt, models_data = collect_model_responses(root, output_format, models_dir)
    if models_data:
        verdict: str | None = None
        if gemini_judge:
            api_key = get_api_key(root)
            if api_key:
                try:
                    verdict = get_gemini_verdict(prompt, models_data, api_key)
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
    args = parser.parse_args()

    # Resolve project root from positional arg or CWD.
    root_str = cast(str | None, args.root)
    cmd_root = Path(root_str) if root_str else None
    init_root = cmd_root.resolve() if cmd_root else Path.cwd()

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
    models_dir = resolve_models_dir(output_dir)
    output_format = str(settings.get("output_format", "md"))
    gemini_judge = bool(settings.get("gemini_judge", False))
    compact_mode = bool(settings.get("compact_mode", False))
    archive = bool(settings.get("archive", False))
    raw_model_count = settings.get("model_count", 2)
    model_count = int(raw_model_count) if isinstance(raw_model_count, (int, str)) else 2
    archive_dir = str(settings.get("archive_dir", "models/old"))
    archive_scheme = str(settings.get("archive_scheme", "numbered"))

    # --- Migrate legacy CWD outputs + root models/ into output_dir/ ------
    _ = migrate_old_outputs(init_root, output_dir)

    # --- Initialize environment (files.txt, models/, prompt.txt) ---------
    initialize_environment(init_root, model_count, output_dir)

    # --- EC3 / Req 7: ensure model templates for chosen count ------------
    _ = ensure_model_templates(init_root, model_count, models_dir)

    # --- EC5: old files in output folder ---------------------------------
    any_old = (
        any((output_dir / name).is_file() for name in _LEGACY_OUTPUT_NAMES)
        or any(output_dir.glob("arena_*.txt"))
        or any(output_dir.glob("structure_*.txt"))
    )
    if any_old and is_interactive:
        merge = _prompt_merge()
        if not merge:
            print("Skipping merge — existing output files will be overwritten.")
    # Non-interactive: default silently to overwriting (auto-merge).

    # --- Req 5: archiving workflow ---------------------------------------
    if archive:
        archived = archive_model_responses(
            init_root, archive_dir, models_dir, archive_scheme,
        )
        if archived:
            # Re-create fresh templates for the configured model count.
            _ = ensure_model_templates(init_root, model_count, models_dir)
            print(f"Archived {len(archived)} file(s) to {archive_dir}.")

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

    # --- Req 2: discover and process ALL files*.txt ----------------------
    discovered = discover_files_txt(cwd)
    if not discovered:
        print("No files*.txt found in CWD — nothing to do.")
        return

    for files_input, suffix in discovered:
        try:
            _process_one(
                files_txt=files_input,
                suffix=suffix,
                root=root,
                output_dir=output_dir,
                patterns=patterns,
                output_format=output_format,
                gemini_judge=gemini_judge,
                compact_mode=compact_mode,
                models_dir=models_dir,
            )
        except Exception as exc:  # pylint: disable=broad-exception-caught  # noqa: BLE001 — last-resort guard per file
            print(
                f"ERROR processing {files_input.name}: {exc}",
                file=sys.stderr,
            )

    print(f"\nDone. Outputs written to: {output_dir}")


if __name__ == "__main__":
    main()
