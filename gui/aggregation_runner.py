"""Background aggregation pipeline runner (Tk-free).

The legacy :class:`gui.app.AggregatorGUI` used a 250-line
``_aggregate_worker`` thread function that interleaved three
responsibilities: pipeline orchestration, logging-coloured messages,
and Tk UI status updates. Splitting those concerns lets us unit-test
the orchestration independently of Tk.

This module exposes :func:`run_aggregation`, which runs the full
``loaded settings → migrate → discover → per-input aggregate →
collect model responses → judge → compare`` sequence exactly as the
CLI does, but routes every user-visible message to the supplied
*log* callable and every status-bar update to *set_status*. A
*cancel_requested* callable lets the GUI thread cleanly abort
between iterations.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from pathlib import Path
from typing import Callable, Optional

from core.arena import (
    ArenaAssignment,
    ArenaDirective,
    arena_filenames,
    resolve_arena_dir,
)
from core.judge import (
    GeminiJudge,
    archive_model_responses,
    build_compare_markdown,
    collect_model_responses,
    ensure_model_templates,
    generate_compare_template,
    load_dotenv,
)
from core.parser import (
    aggregate_files,
    build_arena_plan,
    discover_files_txt_with_directives,
    generate_tree,
    initialize_environment,
    load_ignore_patterns,
    load_settings,
    migrate_old_outputs,
    migrate_to_per_file_folders,
    read_file_entries,
    resolve_output_dir,
)

from gui.util import assert_writable


logger = logging.getLogger("gui.aggregation")


# Public callback signatures. They mirror the legacy GUI class methods
# (``_log_write`` / ``_step`` / ``_set_status``) so wiring is direct.
LogFn = Callable[[str, str], None]   # (message, tag)
StepFn = Callable[[str], None]        # (message) → log + status update
StatusFn = Callable[[str], None]      # status-bar text
CancelFn = Callable[[], bool]         # returns True if user cancelled


# ---------------------------------------------------------------------------
# API-key resolution (thread-safe helper used by run_aggregation)
# ---------------------------------------------------------------------------


def resolve_api_key(
    *,
    project_root: Path,
    tool_root: Path,
    cwd: Path,
    prompt_fn: Optional[Callable[[], Optional[str]]] = None,
    save_fn: Optional[Callable[[str], None]] = None,
    wait_timeout: float = 120.0,
) -> Optional[str]:
    """Look up the Gemini API key, falling back to *prompt_fn* if needed.

    Mirrors the legacy ``_resolve_api_key_for_thread`` helper: it first
    checks in-memory / env / dotenv sources, and if nothing is found
    delegates to *prompt_fn* (which the GUI layer implements as
    ``Lambda: open _ApiKeyDialog on the main thread and wait on an
    Event``).

    Args:
        project_root: Project the aggregation runs against.
        tool_root: Aggregator install directory.
        cwd: Process working directory.
        prompt_fn: Optional callable that returns the user-provided key
            (or ``None`` if they cancel). If ``None`` we never block.
        save_fn: Optional callable invoked with the new key when the
            user ticks "save to .env".
        wait_timeout: Max seconds to block waiting for the dialog.
            0 means do not block at all.

    Returns:
        The key string, or ``None`` if unavailable.
    """
    load_dotenv(project_root)
    load_dotenv(tool_root)
    load_dotenv(cwd)
    key = __import__("os").environ.get("GEMINI_API_KEY", "").strip()
    if key:
        return key

    if prompt_fn is None:
        return None

    holder: list[Optional[str]] = [None]
    ready = threading.Event()

    def _show() -> None:
        try:
            result = prompt_fn()
        except Exception as exc:  # noqa: BLE001
            logger.warning("API key prompt failed: %s", exc)
            result = None
        holder[0] = result
        if result and save_fn is not None:
            try:
                save_fn(result)
            except Exception as exc:  # noqa: BLE001
                logger.warning("save_api_key failed: %s", exc)
        ready.set()

    # The legacy code uses ``self.after(0, _show)`` to schedule on the
    # Tk main loop. Here we accept an already-threaded *prompt_fn* that
    # internally arranges the main-thread hop. We just need to wait
    # synchronously until it sets the result.
    th = threading.Thread(target=_show, daemon=True)
    th.start()
    ready.wait(timeout=wait_timeout)
    return holder[0]


# ---------------------------------------------------------------------------
# Aggregation runner
# ---------------------------------------------------------------------------


def run_aggregation(
    *,
    project_root: Path,
    tool_root: Path,
    cwd: Path,
    log: LogFn,
    step: StepFn,
    set_status: StatusFn,
    cancel_requested: CancelFn,
    api_key_provider: Optional[Callable[[], Optional[str]]] = None,
    api_key_save: Optional[Callable[[str], None]] = None,
) -> dict[str, object]:
    """Run the full aggregation pipeline in the calling thread.

    Intended to be invoked from a ``threading.Thread(target=...)`` so the
    GUI remains responsive. The pipeline matches the legacy behaviour
    1:1: every ``_log_write`` becomes ``log(msg, tag)``; ``_step``
    becomes ``step(msg)``; ``_set_status`` becomes
    ``set_status(msg)``.

    Args:
        project_root: Where the project lives (root of the aggregation).
        tool_root: Aggregator install dir (``gui.paths.PROJECT_DIR``).
        cwd: Process CWD.
        log: Callable for coloured log lines.
        step: Callable for high-level pipeline-step notifications.
        set_status: Callable for the status bar.
        cancel_requested: Callable returning ``True`` between iterations
            when the user clicks **Cancel**.
        api_key_provider: Optional GUI-thread callable returning a user
            key on demand. See :func:`resolve_api_key`.
        api_key_save: Optional callback for "save key to .env".

    Returns:
        Summary dict — ``{"processed": int, "total_tokens": int,
        "elapsed": float}``. Callers typically just log it.
    """
    started = time.perf_counter()
    try:
        step("Loading settings …")
        settings = load_settings(project_root)

        output_dir = resolve_output_dir(project_root, settings)
        output_format = str(settings.get("output_format", "md"))
        gemini_judge = bool(settings.get("gemini_judge", False))
        compact_mode = bool(settings.get("compact_mode", False))
        archive = bool(settings.get("archive", False))
        model_count = int(str(settings.get("model_count", 2)))

        # --- Migration ----------------------------------------------------
        step("Migrating legacy outputs if needed …")
        migrate_old_outputs(project_root, output_dir)
        migrate_to_per_file_folders(output_dir)

        # --- Environment Initialization ----------------------------------
        step("Initializing environment …")
        initialize_environment(project_root, model_count, output_dir)

        # --- Discover files*.txt -----------------------------------------
        step("Discovering inputs in .context/inputs/ or root …")
        discovered, directive_lookup = discover_files_txt_with_directives(
            project_root, project_root, settings
        )
        if not discovered:
            log("No input files found — nothing to do.", "warn")
            set_status("No inputs found.")
            return {"processed": 0, "total_tokens": 0, "elapsed": 0.0}

        # --- Target-arena directive plan ---------------------------------
        respect_directive = bool(
            settings.get("respect_target_arena_directive", True)
        )
        on_conflict = str(
            settings.get("on_arena_number_conflict", "warn_and_shift")
        )
        if respect_directive:
            assignments, plan_warnings = build_arena_plan(
                discovered, directive_lookup, on_conflict=on_conflict,
            )
            for warning in plan_warnings:
                log(f"[plan] {warning}", "warn")
            assignment_by_path = {a.filepath: a for a in assignments}
        else:
            assignment_by_path = {
                p: ArenaAssignment(
                    filepath=p,
                    arena_name=name,
                    arena_number=0,
                    directive=directive_lookup.get(p, ArenaDirective()),
                )
                for p, name in discovered
            }

        patterns = load_ignore_patterns(project_root, settings)
        processed_count = 0
        total_tokens = 0

        for files_input, arena_name in discovered:
            if cancel_requested():
                log("Aggregation cancelled by user.", "warn")
                set_status("Cancelled.")
                break

            step(f"Processing {files_input.name} …")

            assignment = assignment_by_path.get(files_input)
            preferred = (
                assignment.arena_number
                if assignment and assignment.arena_number > 0
                else None
            )
            arena_dir = resolve_arena_dir(
                output_dir, arena_name, preferred_number=preferred
            )
            filenames = arena_filenames(arena_dir, output_format)
            arena_path = filenames["context"]
            structure_path = output_dir / "structure" / "structure.txt"
            compare_path = filenames["arena"]

            for out_path in (arena_path, structure_path, compare_path):
                assert_writable(out_path)

            # ── Step 1: Read entries ──────────────────────────────────────
            entries = read_file_entries(files_input)
            if not entries:
                log(
                    f"[{files_input.name}] Queue is empty — "
                    "writing empty templates.",
                    "warn",
                )
                arena_path.write_text("", encoding="utf-8")
                structure_path.write_text("", encoding="utf-8")
                generate_compare_template(compare_path, model_count)
                continue

            n_full      = sum(1 for _, r, _i in entries if r is None)
            n_snippets  = sum(1 for _, r, i in entries if r is not None and not i)
            n_important = sum(1 for _, r, i in entries if r is not None and i)

            summary_parts: list[str] = []
            if n_full:      summary_parts.append(f"{n_full} file(s)")
            if n_snippets:  summary_parts.append(f"{n_snippets} snippet(s)")
            if n_important: summary_parts.append(f"{n_important} structure(s)")
            log(
                f"[{files_input.name}] Queue: {' + '.join(summary_parts)}",
                "info",
            )

            # ── Step 2: Project tree ────────────────────────────────────────
            output_dir_name = str(settings.get("output_dir", "context_output"))
            tree_lines = [f"Project Root: {project_root.name}/"] + generate_tree(
                project_root, project_root, patterns, output_dir=output_dir_name
            )
            structure_path.write_text("\n".join(tree_lines), encoding="utf-8")
            log(
                f"[{files_input.name}] structure written → {structure_path.name}",
                "ok",
            )

            # ── Step 3: Aggregate ──────────────────────────────────────────
            aggregate_files(entries, arena_path, project_root)
            log(f"[{files_input.name}] arena written → {arena_path.name}", "ok")

            # ── Step 4: Token count ────────────────────────────────────────
            try:
                arena_content = arena_path.read_text(encoding="utf-8")
                from core.counter import count_tokens

                token_count = count_tokens(arena_content)
                total_tokens += token_count
                char_count = len(arena_content)

                if token_count >= 128_000:
                    tok_tag, tok_icon = "error", "🔴"
                elif token_count >= 80_000:
                    tok_tag, tok_icon = "warn", "🟡"
                else:
                    tok_tag, tok_icon = "ok", "🟢"
                log(
                    f"[{files_input.name}] {tok_icon}  "
                    f"{char_count:,} chars | ~{token_count:,} tokens",
                    tok_tag,
                )
            except Exception as exc:  # noqa: BLE001
                log(f"[{files_input.name}] Token count warning: {exc}", "warn")

            # ── Step 5: Collect model responses ────────────────────────────
            prompt_file = filenames["prompt"]
            if not prompt_file.exists():
                _ = prompt_file.touch()
                log(f"[{files_input.name}] Created {prompt_file.name}", "ok")
            ensure_model_templates(arena_dir, model_count)

            prompt, models_data = collect_model_responses(
                arena_dir, output_format, model_count
            )

            if not models_data:
                generate_compare_template(compare_path, model_count)
                log(
                    f"[{files_input.name}] No model responses found — "
                    "blank template written.",
                    "warn",
                )
                processed_count += 1
                continue

            log(
                f"[{files_input.name}] Found {len(models_data)} "
                f"model response(s) in {arena_dir.name}/",
                "ok",
            )

            # ── Step 6: Gemini AI Judge (optional) ─────────────────────────
            verdict: Optional[str] = None
            if gemini_judge:
                if cancel_requested():
                    break
                step(
                    f"[{files_input.name}] Running Gemini AI Judge "
                    "(may take up to 45s) …"
                )
                api_key: Optional[str] = None
                if api_key_provider is not None:
                    api_key = api_key_provider()

                if api_key:
                    try:
                        judge = GeminiJudge()
                        verdict = asyncio.run(
                            judge.evaluate(prompt, models_data, api_key)
                        )
                        log(
                            f"[{files_input.name}] Gemini verdict received ✓",
                            "judge",
                        )
                    except Exception as exc:  # noqa: BLE001
                        log(
                            f"[{files_input.name}] Gemini API error: "
                            f"{exc} (falling back to manual template)",
                            "error",
                        )
                else:
                    log(
                        f"[{files_input.name}] No API key — "
                        "skipping Gemini Judge.",
                        "warn",
                    )

            # ── Step 7: Write comparison ───────────────────────────────────
            build_compare_markdown(
                prompt, models_data, compare_path,
                verdict=verdict, compact=compact_mode,
            )
            mode_str = " [COMPACT]" if compact_mode else ""
            judge_str = " + Gemini Judge" if verdict else ""
            log(
                f"[{files_input.name}] compare written → {compare_path.name}  "
                f"({len(models_data)} models){mode_str}{judge_str}",
                "ok",
            )

            # --- Archiving workflow (local to this arena) -------------------
            if archive:
                step(f"[{files_input.name}] Archiving model responses …")
                archive_dir = str(settings.get("archive_dir", "ARCHIVE"))
                archived = archive_model_responses(arena_dir, archive_dir)
                if archived:
                    ensure_model_templates(arena_dir, model_count)
                    log(
                        f"[{files_input.name}] Archived {len(archived)} "
                        f"response(s) to {archive_dir}.",
                        "ok",
                    )

            processed_count += 1

        # ── Final status ─────────────────────────────────────────────────
        final = f"Done — processed {processed_count} input(s)"
        if total_tokens > 0:
            final += f", ~{total_tokens:,} total tokens"
        set_status(final)
        log("─" * 48, "info")
        log("Aggregation complete ✓", "ok")

        elapsed = time.perf_counter() - started
        logger.info(
            "aggregation.complete processed=%d tokens=%d elapsed=%.3fs",
            processed_count,
            total_tokens,
            elapsed,
        )
        return {
            "processed": processed_count,
            "total_tokens": total_tokens,
            "elapsed": elapsed,
        }

    except FileNotFoundError as exc:
        log(f"File not found: {exc}", "error")
        set_status("Error — see log.")
    except OSError as exc:
        log(f"OS error: {exc}", "error")
        set_status("Error — see log.")
    except Exception as exc:  # noqa: BLE001 — last-resort guard
        log(f"Unexpected error: {exc}", "error")
        set_status("Error — see log.")
    return {"processed": 0, "total_tokens": 0, "elapsed": 0.0}


__all__ = [
    "LogFn",
    "StepFn",
    "StatusFn",
    "CancelFn",
    "resolve_api_key",
    "run_aggregation",
]
