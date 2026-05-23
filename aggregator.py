# & C:\Users\FOTE\AppData\Local\Programs\Python\Python314\python.exe c:/programming/Python/Projects/context/aggregator.py
"""File Aggregator — consolidates source files and generates project trees.

Outputs:
    arena.txt     — all file contents with relative-path headers
    structure.txt — visual directory tree of the detected project root
"""

import sys
from pathlib import Path

# Reconfigure stdout/stderr to UTF-8 to prevent encoding errors on Windows terminals
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')


# Import from core module package (for CLI execution and backwards compatibility with TUI/GUI)
from core.parser import (
    aggregate_files,
    find_project_root,
    generate_tree,
    load_ignore_patterns,
    read_file_paths,
    should_ignore,
    initialize_environment,
    read_file_entries,
)
from core.counter import count_tokens
from core.judge import (
    collect_model_responses,
    build_compare_markdown,
    generate_compare_template,
    get_api_key,
    get_gemini_verdict,
)

def _assert_writable(path: Path) -> None:
    """Raise OSError if path cannot be opened for writing."""
    try:
        path.open("a").close()
    except OSError as exc:
        raise OSError(f"Output file not writable: {path}") from exc

def main() -> None:
    """Orchestrate project-root detection, tree generation, and aggregation."""
    # Allow overriding the root directory via command line argument
    cmd_root = Path(sys.argv[1]) if len(sys.argv) > 1 else None

    # Initialize environment (files.txt, models/, prompt.txt)
    init_root = cmd_root.resolve() if cmd_root else Path.cwd()
    initialize_environment(init_root)

    files_txt = Path("files.txt")
    arena_txt = Path("arena.txt")
    structure_txt = Path("structure.txt")
    compare_txt = Path("compare.md")

    try:
        entries = read_file_entries(files_txt)
        if not entries:
            print("No entries found in files.txt — nothing to do.")
            return

        # Fail fast if outputs are not writable.
        _assert_writable(arena_txt)
        _assert_writable(structure_txt)
        _assert_writable(compare_txt)

        if cmd_root:
            root = cmd_root.resolve()
        else:
            root = find_project_root(entries[0][0])
        
        patterns = load_ignore_patterns(root)

        # Count types for reporting
        full_files = sum(1 for _, ranges, _ in entries if ranges is None)
        snippets = sum(1 for _, ranges, important in entries if ranges is not None and not important)
        important = sum(1 for _, ranges, imp in entries if ranges is not None and imp)

        # 1. Project tree
        if root:
            print(f"Project root detected: {root}")
            tree_lines = [f"Project Root: {root.name}/"] + generate_tree(
                root, root, patterns
            )
            structure_txt.write_text("\n".join(tree_lines), encoding="utf-8")
            print(f"Structure written → {structure_txt}")
        else:
            print("No project root detected — skipping structure.txt.", file=sys.stderr)

        # 2. File aggregation (full files + snippets + important structures)
        parts = []
        if full_files:
            parts.append(f"{full_files} file(s)")
        if snippets:
            parts.append(f"{snippets} snippet(s)")
        if important:
            parts.append(f"{important} structure(s)")
        print(f"Aggregating {' + '.join(parts)} → {arena_txt} …")
        aggregate_files(entries, arena_txt, root)
        print("Aggregation complete.")

        # 3. Calculate and display token counts
        try:
            arena_content = arena_txt.read_text(encoding="utf-8")
            token_count = count_tokens(arena_content)
            print(f"Total size: {len(arena_content)} characters | Estimated tokens: {token_count}")
        except Exception as exc:
            print(f"Warning: Could not count tokens: {exc}")

        # 4. Generate Compare from models/ dir or llm.txt (if exists) or template
        prompt, models_data = collect_model_responses(root)
        if models_data:
            # Ask for AI Judge
            judge_input = input("\nRun Gemini auto-comparison? [Y/n]: ").lower().strip()
            run_judge = judge_input != 'n'
            
            verdict = None
            if run_judge:
                api_key = get_api_key(root)
                if api_key:
                    try:
                        verdict = get_gemini_verdict(prompt, models_data, api_key)
                        print("Gemini comparison evaluation generated successfully.")
                    except Exception as e:
                        print(f"Warning: Gemini evaluation failed ({e}). Falling back to manual template.")
                else:
                    print("API key skipped. Falling back to manual template.")

            # Ask for compact mode
            compact_input = input("Reduce tokens? (Compact mode, remove Notes) [y/N]: ").lower().strip()
            compact = compact_input == 'y'
            
            build_compare_markdown(prompt, models_data, compare_txt, verdict=verdict, compact=compact)
            src = "models/" if (root / "models").is_dir() else "llm.txt"
            mode_str = " (COMPACT)" if compact else ""
            judge_str = " with Gemini AI Judge" if verdict else ""
            print(f"Compare generated from {src} → {compare_txt} ({len(models_data)} models){mode_str}{judge_str}")
        else:
            generate_compare_template(compare_txt)
            print(f"No model responses found — default template → {compare_txt}")

    except Exception as exc:          # noqa: BLE001 — last-resort guard in main
        print(f"CRITICAL ERROR: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
