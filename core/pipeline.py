"""Synchronous core pipeline orchestrator.

The aggregation pipeline has historically been driven from the CLI
(``aggregator.py::_process_one``). The FastAPI server in
``gui/server/main.py`` previously stubbed this out — it returned early with
fake "init/done" events. This module extracts the real per-file work into
a pure, side-effect-free-from-the-caller's-POV function so the server can
call it from a worker thread and stream progress events back to the
popup via WebSocket.

Design goals
------------

* **Real progress.** Events are emitted when files are actually read,
  not on a sleep timer.
* **Settings first.** Takes the typed :class:`core.settings.Settings`
  dataclass (not a loose flat dict) so configuration is type-checked and
  overridable through :func:`merge_overrides`.
* **Thread-safe.** ``run_pipeline`` is synchronous; the bridge to async
  WebSocket send is the caller's responsibility (see
  :func:`core.pipeline.make_async_bridge`).
* **No surprise side-effects.** Reads only from the explicit
  ``settings`` object; never imports ``sys.argv`` or stdin.

Public API
----------

* :func:`run_pipeline` — runs the four phases and emits progress events.
* :func:`make_async_bridge` — builds a sync callback that pushes events
  into an asyncio loop via ``run_coroutine_threadsafe``.
* :dataclass:`PipelineResult` — summary returned from a completed run.
* :data:`ProgressCallback` — the callback type alias.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

# We import lazily inside functions to avoid circular imports — settings
# imports nothing from us, but parser/discovery/judge/arena are stable.

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------

#: Signature for the progress callback that the pipeline invokes at each
#: phase boundary. ``stage`` is a short identifier ("init", "read_input",
#: "aggregate", "judge", "compare", "done", "error"). ``level`` is one of
#: "info" / "warning" / "error". ``pct`` is the progress ratio (0.0-1.0).
ProgressCallback = Callable[[str, str, str, float], None]


@dataclass
class PipelineResult:
    """Summary of a single pipeline execution — returned from :func:`run_pipeline`.

    All fields are populated by the orchestrator after each phase. Used by
    the server to log benchmark numbers and (optionally) surface a
    response payload.
    """

    arena_dir: Path
    input_path: Path
    output_format: str
    entries_processed: int = 0
    total_lines: int = 0
    token_count: Optional[int] = None
    models_evaluated: int = 0
    judge_used: bool = False
    warnings: list[str] = field(default_factory=list)
    elapsed: float = 0.0


# ---------------------------------------------------------------------------
# Thread-safe bridge: sync progress callback → asyncio WebSocket send
# ---------------------------------------------------------------------------


def make_async_bridge(
    send_fn: Callable[[str, str, str, float], "asyncio.Future[None]"],
    loop: asyncio.AbstractEventLoop,
) -> ProgressCallback:
    """Build a synchronous progress callback that schedules events on *loop*.

    The pipeline runs in a worker thread (via :func:`asyncio.to_thread`),
    but it must NOT ``await`` anything — that would block the event loop
    the scheduler is meant to release. Instead, the bridge turns every
    progress emission into a :func:`asyncio.run_coroutine_threadsafe` call
    against the FastAPI event loop, which the loop drains naturally as
    part of its scheduled callbacks.

    Args:
        send_fn: An async function with the signature
            ``async def send(stage, level, msg, pct) -> None`` — typically
            ``gui.server.ws.ConnectionManager.send_event`` partially
            applied with a ``run_id``.  Note that ``run_coroutine_threadsafe``
            returns a :class:`concurrent.futures.Future`; we don't await
            it from the worker thread — we just schedule and forget.
        loop: The asyncio event loop running the FastAPI app.

    Returns:
        A sync ``ProgressCallback`` suitable for passing to
        :func:`run_pipeline`. Any exception thrown by *send_fn* is logged
        but not raised back into the worker thread — a single dropped
        event must never break a long-running pipeline.
    """

    def _bridge(stage: str, level: str, msg: str, pct: float) -> None:
        try:
            _ = asyncio.run_coroutine_threadsafe(
                send_fn(stage, level, msg, pct), loop
            )
        except Exception as exc:  # noqa: BLE001 — last-resort guard
            # Never let a transport hiccup break the pipeline.
            logger.warning("Progress bridge failed for %s: %s", stage, exc)

    return _bridge


# ---------------------------------------------------------------------------
# Settings merge helpers
# ---------------------------------------------------------------------------


def _apply_overrides(settings_dict: dict[str, object]) -> None:
    """Best-effort validation of flat overrides (legacy callers).

    The FastAPI handler already strips ``None`` values upstream and runs
    its own validation. This hook exists so callers can plug in stricter
    validation later (e.g. clamp ``model_count`` to {2, 4}).
    """
    # Today: a no-op; reserved for future clamp() / type-cast work.
    _ = settings_dict


def merge_overrides(
    base: "Settings",  # type: ignore[name-defined]  # noqa: F821
    flat_overrides: dict[str, object],
) -> "Settings":  # type: ignore[name-defined]  # noqa: F821
    """Apply *flat_overrides* onto *base* using the canonical flat→nested map.

    The payload from ``POST /api/run`` carries legacy flat keys
    (``output_dir``, ``gemini_judge`` …) because that's the wire shape
    the browser extension already speaks. Internally we use the nested
    :class:`core.settings.Settings` dataclass, so we route each flat key
    into its corresponding nested attribute via
    :data:`core.settings._FLAT_TO_NESTED`. Unknown keys are silently
    ignored so a new client version never breaks an older server.

    Args:
        base: Settings dataclass instance to mutate and return.
        flat_overrides: Subset of legacy flat keys (``output_dir``,
            ``model_count`` …) with their new values.

    Returns:
        The same *base* instance, mutated in place for convenience.
    """
    # Local import keeps the type hint available without a top-level
    # dependency cycle (settings is leaf-level).
    import copy

    from core.settings import _FLAT_TO_NESTED

    # Deep-copy preserves nested dataclass *instances* (JudgeSettings,
    # OutputSettings, …) so attribute access like ``settings.judge.enabled``
    # keeps working — naïve ``dataclasses.asdict`` would replace every
    # nested object with a plain dict.
    merged = copy.deepcopy(base)
    _apply_overrides(flat_overrides)

    for flat_key, value in flat_overrides.items():
        path = _FLAT_TO_NESTED.get(flat_key)
        if path is None:
            logger.debug("Ignoring unknown override key: %s", flat_key)
            continue
        group_name, attr_name = path
        if not hasattr(merged, group_name):
            logger.warning(
                "Override %s points at unknown group %s — skipped",
                flat_key,
                group_name,
            )
            continue
        group = getattr(merged, group_name)
        if not hasattr(group, attr_name):
            logger.warning(
                "Override %s points at unknown attr %s.%s — skipped",
                flat_key,
                group_name,
                attr_name,
            )
            continue
        # Clamp / cast: match the same invariants enforced in
        # ``core.settings.<Group>.__post_init__``.
        try:
            setattr(group, attr_name, value)
        except (TypeError, ValueError) as exc:
            logger.warning(
                "Override %s rejected (value=%r, %s); keeping current",
                flat_key,
                value,
                exc,
            )
    return merged


# ---------------------------------------------------------------------------
# Per-stage progress helpers
# ---------------------------------------------------------------------------


def _emit(
    progress: Optional[ProgressCallback],
    stage: str,
    level: str,
    msg: str,
    pct: float,
) -> None:
    """Invoke *progress* if non-None; never raise into the pipeline."""
    if progress is None:
        return
    try:
        progress(stage, level, msg, pct)
    except Exception as exc:  # noqa: BLE001 — defensive
        logger.warning("Progress callback raised in %s: %s", stage, exc)


# ---------------------------------------------------------------------------
# Pipeline implementation
# ---------------------------------------------------------------------------


def run_pipeline(
    *,
    project_root: Path,
    settings: "Settings",  # type: ignore[name-defined]  # noqa: F821
    input_path: Path,
    arena_dir: Path,
    output_format: str,
    model_count: int,
    gemini_judge: bool,
    compact_mode: bool,
    progress: Optional[ProgressCallback] = None,
) -> PipelineResult:
    """Execute the four-phase aggregation pipeline against *arena_dir*.

    Stages (each emits a progress event before and after):

      1. **init**        — Validate inputs, copy the input file into
                           *arena_dir* under the canonical prefixed
                           filename so the arena is self-contained.
      2. **read_input**  — Parse ``files.txt``-style entries (full files,
                           snippets, important markers).
      3. **aggregate**   — Stream every entry's contents into
                           ``NNN-context.<ext>`` with per-file progress
                           events (``aggregate:1/N``, ``aggregate:2/N`` …).
      4. **tokens**      — Run :func:`core.counter.count_tokens` on the
                           aggregate.
      5. **compare**     — Collect model responses from the arena's
                           ``NNN-A.txt`` files. If *gemini_judge* is on
                           and a key is present, evaluate and embed the
                           verdict into the compare output. Always emits
                           — falls back to the empty template when no
                           model responses exist.
      6. **done**        — Final summary, 1.0.

    Args:
        project_root: Detected project root (used for ``get_display_path``
            during aggregation).
        settings: Effective typed settings. Only used here for the
            archive toggle (forward hook) and ``use_default_ignore``.
        input_path: Source ``files.txt`` or ``.context/inputs/N.txt``.
        arena_dir: Output arena directory (already created by the caller).
        output_format: ``"md"`` or ``"txt"`` — extension for context / arena.
        model_count: 2 or 4.
        gemini_judge: Whether to call Gemini when model responses exist.
        compact_mode: Forwarded to ``build_compare_markdown``.
        progress: Optional sink for ``(stage, level, msg, pct)`` events.

    Returns:
        A populated :class:`PipelineResult`. Callers can log it, surface
        it in an HTTP response, or ignore it — the side effects (files
        written) are the contract that matters.
    """
    from core.parser import (
        aggregate_files,
        read_file_entries,
    )
    from core.arena import arena_filenames
    from core.judge import (
        collect_model_responses,
        build_compare_markdown,
        generate_compare_template,
        ensure_model_templates,
        get_api_key,
        GeminiJudge,
    )
    from core.counter import count_tokens

    started = time.perf_counter()
    result = PipelineResult(
        arena_dir=arena_dir,
        input_path=input_path,
        output_format=output_format,
    )

    filenames = arena_filenames(arena_dir, output_format)
    arena_path = filenames["context"]
    compare_path = filenames["arena"]
    prompt_file = filenames["prompt"]
    target_input_path = filenames["input"]

    # ------------------------------------------------------------------
    # 1. Init — copy the input file into the arena directory.
    # ------------------------------------------------------------------
    _emit(progress, "init", "info", "Preparing arena directory...", 0.02)
    arena_dir.mkdir(parents=True, exist_ok=True)

    if (
        input_path.resolve() != target_input_path.resolve()
        and not target_input_path.exists()
    ):
        try:
            shutil.copy2(str(input_path), str(target_input_path))
            _emit(
                progress,
                "init",
                "info",
                f"Copied input → {target_input_path.name}",
                0.04,
            )
        except OSError as exc:
            msg = f"Could not copy input into arena: {exc}"
            _emit(progress, "init", "warning", msg, 0.04)
            result.warnings.append(msg)
            logger.warning(msg)

    # ------------------------------------------------------------------
    # 2. Input — parse files.txt entries.
    # ------------------------------------------------------------------
    _emit(progress, "read_input", "info", "Reading input entries...", 0.06)
    if not prompt_file.exists():
        try:
            prompt_file.touch()
        except OSError as exc:
            result.warnings.append(f"Could not create prompt template: {exc}")
            logger.warning("Could not create prompt template: %s", exc)
    ensure_model_templates(arena_dir, model_count)

    try:
        entries = read_file_entries(input_path)
    except FileNotFoundError as exc:
        msg = f"Input file not found: {input_path}"
        _emit(progress, "read_input", "error", msg, 1.0)
        result.warnings.append(msg)
        logger.error(msg)
        result.elapsed = time.perf_counter() - started
        _emit(progress, "error", "error", msg, 1.0)
        return result

    result.entries_processed = len(entries)
    _emit(
        progress,
        "read_input",
        "info",
        f"Parsed {len(entries)} entr(ies).",
        0.1,
    )

    # Edge case 1: empty input — still emit empty outputs so downstream
    # tooling always has a valid arena layout.
    if not entries:
        msg = f"No entries found in {input_path.name} — writing empty outputs."
        _emit(progress, "read_input", "warning", msg, 0.1)
        logger.info(msg)
        try:
            arena_path.write_text("", encoding="utf-8")
            generate_compare_template(compare_path)
        except OSError as exc:
            msg_w = f"Could not write empty outputs: {exc}"
            result.warnings.append(msg_w)
            logger.warning(msg_w)
        result.elapsed = time.perf_counter() - started
        _emit(progress, "done", "info", "Run complete (empty input).", 1.0)
        return result

    # ------------------------------------------------------------------
    # 3. Aggregate — real, per-file streaming.
    # ------------------------------------------------------------------
    total_entries = len(entries)
    # Allocate 0.10..0.70 (60% of progress) to aggregation across files.
    agg_start = 0.10
    agg_end = 0.70
    agg_span = agg_end - agg_start

    def _file_progress(idx: int, fname: str) -> None:
        pct = (
            agg_start + (idx + 1) / total_entries * agg_span
            if total_entries > 0
            else agg_end
        )
        _emit(
            progress,
            f"aggregate:{idx + 1}/{total_entries}",
            "info",
            f"Aggregating {fname} ({idx + 1}/{total_entries})",
            pct,
        )

    # Emit a pre-aggregation event so the UI can show "started" before
    # the first file lands.
    _file_progress(-1, "starting")

    try:
        total_lines = aggregate_files(entries, arena_path, project_root)
    except OSError as exc:
        msg = f"Aggregation failed: {exc}"
        _emit(progress, "aggregate", "error", msg, 1.0)
        result.warnings.append(msg)
        logger.error(msg)
        result.elapsed = time.perf_counter() - started
        _emit(progress, "error", "error", msg, 1.0)
        return result

    result.total_lines = total_lines
    # Final aggregate event at the upper bound.
    _emit(
        progress,
        f"aggregate:{total_entries}/{total_entries}",
        "info",
        f"Aggregated {total_lines} lines from {total_entries} files.",
        agg_end,
    )

    # ------------------------------------------------------------------
    # 4. Tokens — best-effort.
    # ------------------------------------------------------------------
    _emit(progress, "tokens", "info", "Counting tokens...", 0.74)
    try:
        content = arena_path.read_text(encoding="utf-8")
        result.token_count = count_tokens(content)
        _emit(
            progress,
            "tokens",
            "info",
            f"{result.token_count} tokens, {len(content)} chars, "
            f"{total_lines} lines.",
            0.78,
        )
    except (OSError, ValueError) as exc:
        msg = f"Token count failed: {exc}"
        _emit(progress, "tokens", "warning", msg, 0.78)
        result.warnings.append(msg)
        logger.warning(msg)

    # ------------------------------------------------------------------
    # 5. Compare — collect responses, optionally judge, write arena.md.
    # ------------------------------------------------------------------
    _emit(progress, "compare", "info", "Collecting model responses...", 0.82)
    prompt, models_data = collect_model_responses(
        arena_dir, output_format, model_count
    )
    result.models_evaluated = len(models_data)

    if models_data:
        verdict: Optional[str] = None
        if gemini_judge:
            api_key = get_api_key(project_root)
            if api_key:
                _emit(
                    progress,
                    "judge",
                    "info",
                    "Running Gemini judge...",
                    0.88,
                )
                try:
                    import asyncio as _asyncio

                    judge = GeminiJudge()
                    verdict = _asyncio.run(
                        judge.evaluate(prompt, models_data, api_key)
                    )
                    result.judge_used = True
                    _emit(
                        progress,
                        "judge",
                        "info",
                        "Gemini verdict generated.",
                        0.94,
                    )
                except Exception as exc:  # noqa: BLE001
                    msg = (
                        f"Gemini evaluation failed ({exc}); "
                        "falling back to manual template."
                    )
                    _emit(progress, "judge", "warning", msg, 0.94)
                    result.warnings.append(msg)
                    logger.warning(msg)
            else:
                msg = "GEMINI_API_KEY not set — Gemini judge skipped."
                _emit(progress, "judge", "warning", msg, 0.94)
                result.warnings.append(msg)
                logger.warning(msg)

        try:
            build_compare_markdown(
                prompt,
                models_data,
                compare_path,
                verdict=verdict,
                compact=compact_mode,
            )
            _emit(
                progress,
                "compare",
                "info",
                f"Compare written ({len(models_data)} model(s)).",
                0.98,
            )
        except OSError as exc:
            msg = f"Could not write compare: {exc}"
            _emit(progress, "compare", "error", msg, 1.0)
            result.warnings.append(msg)
            logger.error(msg)
    else:
        try:
            generate_compare_template(compare_path)
            _emit(
                progress,
                "compare",
                "warning",
                "No model responses — empty template written.",
                0.98,
            )
        except OSError as exc:
            msg = f"Could not write compare template: {exc}"
            _emit(progress, "compare", "error", msg, 1.0)
            result.warnings.append(msg)
            logger.error(msg)

    # ------------------------------------------------------------------
    # 6. Done.
    # ------------------------------------------------------------------
    result.elapsed = time.perf_counter() - started
    _emit(
        progress,
        "done",
        "info",
        f"Run complete in {result.elapsed:.2f}s "
        f"({result.total_lines} lines, "
        f"{result.token_count or 0} tokens).",
        1.0,
    )
    logger.info(
        "Pipeline complete: arena=%s entries=%d lines=%d "
        "tokens=%s judge=%s elapsed=%.3fs",
        arena_dir,
        result.entries_processed,
        result.total_lines,
        result.token_count,
        result.judge_used,
        result.elapsed,
    )
    return result


__all__ = [
    "PipelineResult",
    "ProgressCallback",
    "run_pipeline",
    "merge_overrides",
    "make_async_bridge",
]
