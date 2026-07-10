# ruff: noqa: E402 — local imports after sys.path manipulation
"""FastAPI app factory for the context tool server.

All routes are JSON, loopback-bound, and bearer-token authenticated
(except ``/health`` and ``/auth/pair``). The server imports ``core/``
modules directly — no subprocess, no duplicated logic — so behaviour
matches the CLI exactly.

Response shapes (finalised here, mirrored in ``shared/types.ts``):
  * ``GET /api/settings`` → ``{settings, message}``  (NOT flat dict)
  * ``GET /api/inputs``   → ``{items, message}``      (NOT bare list)
  * ``POST /api/run``     → ``{run_id, arena_number, arena_path, warnings}``
"""

import asyncio
import json
import logging
import os
import shutil
import sys
import time
import uuid
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

TOOL_ROOT = Path(__file__).resolve().parents[2]
if str(TOOL_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOL_ROOT))

import core.pipeline as pipeline_mod  # noqa: E402
from gui.server.launcher import (  # noqa: E402
    bootstrap_env,
    get_gemini_key,
    get_project_root,
    set_gemini_key,
)
from gui.server.logging_setup import configure_logging  # noqa: E402
from gui.server.security import (  # noqa: E402
    enforce_loopback,
    get_current_token,
    verify_pairing_code,
)
from gui.server.ws import manager
from gui.server.ws import router as ws_router  # noqa: E402

# ---------------------------------------------------------------------------
# Logging (Task 3 — unified structured logging)
# ---------------------------------------------------------------------------
configure_logging()
logger = logging.getLogger("gui.server")

# ---------------------------------------------------------------------------
# Pydantic request models
# ---------------------------------------------------------------------------


class InputCreate(BaseModel):
    name: str
    content: str


class SettingsUpdate(BaseModel):
    """Partial settings update — all fields optional. Mirrors Req-10 schema.

    ``output_dir`` is included so ``POST /api/run`` overrides can honour the
    CLI ``--output`` flag (gap 4).
    """

    output_dir: Optional[str] = None
    output_format: Optional[str] = None
    model_count: Optional[int] = None
    gemini_judge: Optional[bool] = None
    compact_mode: Optional[bool] = None
    archive: Optional[bool] = None
    archive_dir: Optional[str] = None
    paste_attachments_enabled: Optional[bool] = None
    respect_target_arena_directive: Optional[bool] = None
    on_arena_number_conflict: Optional[str] = None
    use_default_ignore: Optional[bool] = None


class EnvUpdate(BaseModel):
    gemini_api_key: str


class ModelUpdate(BaseModel):
    content: str


class RunRequest(BaseModel):
    input: str
    overrides: Optional[SettingsUpdate] = None


class RunCheckRequest(BaseModel):
    input: str


class IgnoreUpdate(BaseModel):
    patterns: list[str]


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_SETTINGS: dict[str, object] = {
    "output_dir": "context_output",
    "output_format": "md",
    "model_count": 2,
    "gemini_judge": False,
    "compact_mode": False,
    "archive": False,
    "archive_dir": "ARCHIVE",
    "paste_attachments_enabled": False,
    "respect_target_arena_directive": True,
    "on_arena_number_conflict": "warn_and_shift",
    "use_default_ignore": True,
}

# Exact string from edge case 2 — asserted verbatim in the response body.
_EMPTY_SETTINGS_MSG = "Use context skill with AI model to initialize preferences."


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


def create_app() -> FastAPI:
    """Build the FastAPI app with all routes registered."""
    # Ensure .env exists on first run (edge case 6).
    bootstrap_env()

    app = FastAPI(title="Context Tool Server", version="1.0.0")

    # CORS: allow the extension origin + explicit Codespaces forwarded origins.
    # ``allow_origins=["*"]`` is safe-ish here because loopback middleware
    # rejects non-local clients, but production should pin the extension ID.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(ws_router)

    @app.middleware("http")
    async def loopback_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
        enforce_loopback(request)
        return await call_next(request)

    # --- path helpers -----------------------------------------------------

    def get_context_dir() -> Path:
        ctx_dir = get_project_root() / ".context"
        ctx_dir.mkdir(parents=True, exist_ok=True)
        return ctx_dir

    def get_output_dir(settings: dict[str, object]) -> Path:
        out_dir = get_project_root() / str(settings["output_dir"])
        out_dir.mkdir(parents=True, exist_ok=True)
        return out_dir

    def read_settings() -> tuple[dict[str, object], str | None]:
        """Read ``.context/settings.json`` → ``(merged_settings, message)``.

        Returns the exact empty-settings message (edge 2) in the body, not
        only on stderr, so the browser client can surface it.
        """
        settings_path = get_context_dir() / "settings.json"
        if not settings_path.exists():
            settings_path.write_text(
                json.dumps(DEFAULT_SETTINGS, indent=2), encoding="utf-8"
            )
            # CRITICAL: return a *copy* of DEFAULT_SETTINGS, never the
            # module-level reference — otherwise update_settings() mutates
            # the global and settings leak across test invocations.
            return DEFAULT_SETTINGS.copy(), None
        try:
            content = settings_path.read_text(encoding="utf-8")
        except OSError as exc:
            msg = "Warning: Invalid settings.json. Falling back to defaults."
            logger.warning("%s (reason=%s)", msg, exc)
            return DEFAULT_SETTINGS, msg
        if not content.strip():
            logger.warning("%s", _EMPTY_SETTINGS_MSG)
            return DEFAULT_SETTINGS, _EMPTY_SETTINGS_MSG
        try:
            data = json.loads(content)
        except json.JSONDecodeError as exc:
            msg = "Warning: Invalid settings.json. Falling back to defaults."
            logger.warning("%s (reason=%s)", msg, exc)
            return DEFAULT_SETTINGS, msg
        merged = DEFAULT_SETTINGS.copy()
        merged.update(data)
        return merged, None

    def write_settings(settings: dict[str, object]) -> None:
        settings_path = get_context_dir() / "settings.json"
        settings_path.write_text(
            json.dumps(settings, indent=2), encoding="utf-8"
        )

    def next_arena_number(arenas_dir: Path) -> int:
        """``max(existing NNN) + 1`` — never overwrites (edge 4)."""
        if not arenas_dir.exists():
            return 1
        max_num = 0
        for d in arenas_dir.iterdir():
            if d.is_dir() and d.name[:3].isdigit():
                max_num = max(max_num, int(d.name[:3]))
        return max_num + 1

    # --- public / pre-auth routes ----------------------------------------

    @app.get("/health")
    async def health():
        return {
            "version": "1.0.0",
            "project_root": str(get_project_root()),
            "has_gemini_key": get_gemini_key(),
            "pid": os.getpid(),
        }

    @app.get("/project-root")
    async def project_root(token: str = Depends(get_current_token)):
        return {"root": str(get_project_root())}

    @app.post("/auth/pair")
    async def pair(payload: dict):
        code = payload.get("code")
        if not code:
            raise HTTPException(
                status_code=400, detail="Pairing code required"
            )
        token = verify_pairing_code(code)
        return {"token": token}

    # --- settings (wrapper shape — gap 5) --------------------------------

    @app.get("/api/settings")
    async def get_settings(token: str = Depends(get_current_token)):
        settings, message = read_settings()
        return {"settings": settings, "message": message}

    @app.put("/api/settings")
    async def update_settings(
        payload: SettingsUpdate, token: str = Depends(get_current_token)
    ):
        current, _ = read_settings()
        current.update(payload.model_dump(exclude_none=True))
        write_settings(current)
        return {"settings": current, "message": None}

    # --- ignore patterns (gap 1 — Req 9) ---------------------------------

    @app.get("/api/ignore")
    async def get_ignore(token: str = Depends(get_current_token)):
        root = get_project_root()
        ctx_ignore = get_context_dir() / "ignore"
        cwd_ignore = root / ".contextignore"

        ctx_patterns: list[str] = []
        if ctx_ignore.exists():
            ctx_patterns = [
                ln.strip()
                for ln in ctx_ignore.read_text(encoding="utf-8").splitlines()
                if ln.strip()
            ]
        cwd_patterns: list[str] = []
        if cwd_ignore.exists():
            cwd_patterns = [
                ln.strip()
                for ln in cwd_ignore.read_text(encoding="utf-8").splitlines()
                if ln.strip()
            ]
        return {
            "patterns": list(dict.fromkeys(ctx_patterns + cwd_patterns)),
            "sources": {
                ".context/ignore": ctx_patterns,
                ".contextignore": cwd_patterns,
            },
        }

    @app.put("/api/ignore")
    async def update_ignore(
        payload: IgnoreUpdate, token: str = Depends(get_current_token)
    ):
        # Write only .context/ignore — never touch .contextignore (read-only
        # backward-compat file from the UI).
        ctx_ignore = get_context_dir() / "ignore"
        ctx_ignore.write_text(
            "\n".join(payload.patterns) + "\n", encoding="utf-8"
        )
        return {"ok": True}

    # --- inputs (wrapper shape — gap 6 / edge 9) -------------------------

    @app.get("/api/inputs")
    async def list_inputs(token: str = Depends(get_current_token)):
        root = get_project_root()
        inputs_dir = root / ".context" / "inputs"
        results: list[dict[str, object]] = []
        if inputs_dir.exists():
            for f in inputs_dir.glob("*.txt"):
                results.append(
                    {
                        "name": f.stem,
                        "path": str(f),
                        "mtime": f.stat().st_mtime,
                        "size": f.stat().st_size,
                        "source": "inputs-dir",
                    }
                )
        cwd_files = root / "files.txt"
        if cwd_files.exists() and not any(
            r["name"] == "files" for r in results
        ):
            results.append(
                {
                    "name": "files",
                    "path": str(cwd_files),
                    "mtime": cwd_files.stat().st_mtime,
                    "size": cwd_files.stat().st_size,
                    "source": "cwd-fallback",
                }
            )
        if not results:
            return {"items": [], "message": "No input files found"}
        return {"items": results, "message": None}

    @app.post("/api/inputs")
    async def create_input(
        payload: InputCreate, token: str = Depends(get_current_token)
    ):
        inputs_dir = get_project_root() / ".context" / "inputs"
        inputs_dir.mkdir(parents=True, exist_ok=True)
        safe_name = "".join(
            c for c in payload.name if c.isalnum() or c in ("-", "_")
        )
        if not safe_name:
            raise HTTPException(
                status_code=400, detail="Invalid input name"
            )
        file_path = inputs_dir / f"{safe_name}.txt"
        file_path.write_text(payload.content, encoding="utf-8")
        return {"path": str(file_path), "name": safe_name}

    @app.delete("/api/inputs/{name}")
    async def delete_input(name: str, token: str = Depends(get_current_token)):
        inputs_dir = get_project_root() / ".context" / "inputs"
        safe_name = "".join(
            c for c in name if c.isalnum() or c in ("-", "_")
        )
        file_path = inputs_dir / f"{safe_name}.txt"
        if file_path.exists():
            file_path.unlink()
            return {"ok": True}
        raise HTTPException(status_code=404, detail="Input not found")

    # --- env / Gemini key (edge 6) ---------------------------------------

    @app.post("/api/env")
    async def update_env(
        payload: EnvUpdate, token: str = Depends(get_current_token)
    ):
        set_gemini_key(payload.gemini_api_key)
        return {"ok": True, "has_gemini_key": True}

    # --- arenas ----------------------------------------------------------

    @app.get("/api/arenas")
    async def list_arenas(token: str = Depends(get_current_token)):
        out_dir = get_output_dir(read_settings()[0])
        arenas_dir = out_dir / "arenas"
        results: list[dict[str, object]] = []
        if arenas_dir.exists():
            for d in sorted(arenas_dir.iterdir()):
                if d.is_dir() and d.name[:3].isdigit():
                    results.append(
                        {
                            "number": int(d.name[:3]),
                            "name": d.name[4:],
                            "files": [
                                f.name for f in d.iterdir() if f.is_file()
                            ],
                        }
                    )
        return results

    @app.get("/api/arenas/{n}/{file}")
    async def get_arena_file(
        n: int, file: str, token: str = Depends(get_current_token)
    ):
        arenas_dir = get_output_dir(read_settings()[0]) / "arenas"
        if not arenas_dir.exists():
            raise HTTPException(status_code=404, detail="Arena not found")
        arena_dir = next(
            (
                d
                for d in arenas_dir.iterdir()
                if d.is_dir() and d.name.startswith(f"{n:03d}-")
            ),
            None,
        )
        if not arena_dir:
            raise HTTPException(status_code=404, detail="Arena not found")
        file_path = arena_dir / file
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="File not found")
        return PlainTextResponse(file_path.read_text(encoding="utf-8"))

    # --- models (Req 7 / edge 3) -----------------------------------------

    @app.get("/api/models")
    async def list_models(token: str = Depends(get_current_token)):
        models_dir = get_output_dir(read_settings()[0]) / "models"
        files: dict[str, str] = {}
        notes: dict[str, str] = {}
        if models_dir.exists():
            for f in models_dir.iterdir():
                if f.is_file():
                    if f.stem.endswith("_NOTES"):
                        notes[f.stem.replace("_NOTES", "")] = f.name
                    elif len(f.stem) == 1 and f.stem in "ABCD":
                        files[f.stem] = f.name
        return {"count": len(files), "files": files, "notes": notes}

    @app.put("/api/models/{target}")
    async def update_model(
        target: str,
        payload: ModelUpdate,
        token: str = Depends(get_current_token),
    ):
        # Accept A-D for model responses + "prompt" for the shared prompt
        # file (Req 5 — flat models/ layout includes prompt.txt).
        valid_targets = {"A", "B", "C", "D", "prompt"}
        if target not in valid_targets:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid model target '{target}'. "
                f"Expected one of {sorted(valid_targets)}.",
            )
        settings = read_settings()[0]
        models_dir = get_output_dir(settings) / "models"
        models_dir.mkdir(parents=True, exist_ok=True)
        # Auto-create empty C/D when model_count=4 (Req 7, edge 3).
        # Only for model-letter targets, not "prompt".
        if target in "ABCD" and settings.get("model_count") == 4:
            for ltr in "ABCD":
                p = models_dir / f"{ltr}.txt"
                if not p.exists():
                    p.write_text("", encoding="utf-8")
        file_path = models_dir / f"{target}.txt"
        file_path.write_text(payload.content, encoding="utf-8")
        return {"ok": True, "target": target, "path": str(file_path)}

    # --- run pre-flight (gap 2 — edge 5) ---------------------------------

    @app.post("/api/run/check")
    async def check_run_conflicts(
        payload: RunCheckRequest, token: str = Depends(get_current_token)
    ):
        """Pre-flight: detect old output files for the target arena name.

        The popup calls this before ``/api/run``; if ``conflict`` is true it
        shows a "Merge or Skip?" dialog (interactive parity with the CLI's
        edge-case-5 prompt).

        The check looks for ANY existing arena folder whose name suffix
        matches ``-{payload.input}`` — not just the next-numbered one.
        Otherwise an arena pre-created at e.g. ``001-files`` would be
        invisible to a check that resolves to ``002-files``.
        """
        settings = read_settings()[0]
        out_dir = get_output_dir(settings)
        arenas_dir = out_dir / "arenas"
        existing: list[str] = []
        if arenas_dir.exists():
            for d in arenas_dir.iterdir():
                if (
                    d.is_dir()
                    and d.name[:3].isdigit()
                    and d.name.endswith(f"-{payload.input}")
                ):
                    existing.extend(
                        f.name for f in d.iterdir() if f.is_file()
                    )
        return {"conflict": len(existing) > 0, "existing_files": existing}

    # --- run (gap 3 — no-crash Gemini key contract) ----------------------

    @app.post("/api/run")
    async def run_pipeline(
        payload: RunRequest, token: str = Depends(get_current_token)
    ):
        run_id = str(uuid.uuid4())
        run_started = time.perf_counter()

        # 1. Read flat settings from disk and upgrade to the typed nested
        #    ``Settings`` dataclass — the canonical configuration object.
        flat_settings, _ = read_settings()
        from core.settings import (  # noqa: E402 — local import for clarity
            Settings,
            _flat_dict_to_nested,
            settings_from_dict,
        )

        # Build the typed Settings from whatever shape the on-disk file
        # happens to be in (nested dict → already canonical;
        # legacy flat dict → upgraded transparently).
        nested_input = _flat_dict_to_nested(flat_settings)
        typed_settings: Settings = settings_from_dict(nested_input)

        # 2. Apply per-request overrides. ``payload.overrides`` carries the
        #    flat-key shape (browser extension wire format) — the
        #    ``core.pipeline.merge_overrides`` helper routes each flat key
        #    into its nested attribute.
        warnings: list[str] = []
        if payload.overrides:
            override_dict = payload.overrides.model_dump(exclude_none=True)
            typed_settings = pipeline_mod.merge_overrides(
                typed_settings, override_dict
            )

        # No-crash contract (edge 6): missing key disables judge, never 4xx.
        if typed_settings.judge.enabled and not get_gemini_key():
            warnings.append(
                "GEMINI_API_KEY not set — Gemini judge step skipped"
            )
            typed_settings.judge.enabled = False

        # 3. Resolve paths from the typed settings.
        root = get_project_root()
        input_path = root / ".context" / "inputs" / f"{payload.input}.txt"
        if (
            not input_path.exists()
            and payload.input == "files"
            and (root / "files.txt").exists()
        ):
            input_path = root / "files.txt"
        if not input_path.exists():
            raise HTTPException(
                status_code=404, detail="Input file not found"
            )

        # Re-derive the flat view only for code paths (like the legacy
        # ``get_output_dir`` helper) that still expect flat dicts.
        flat_view = typed_settings.to_flat_dict()
        arenas_dir = get_output_dir(flat_view) / "arenas"
        arenas_dir.mkdir(parents=True, exist_ok=True)
        arena_num = next_arena_number(arenas_dir)
        arena_prefix = f"{arena_num:03d}"
        arena_dir = arenas_dir / f"{arena_prefix}-{payload.input}"
        arena_dir.mkdir(parents=True, exist_ok=True)
        # Synchronous copy so /api/arenas/{n}/{file} can read
        # ``NNN-<input>.txt`` immediately after the HTTP response (matches
        # the contract TestArenasEndpoint.test_get_arena_file_returns_text
        # relies on).
        shutil.copy(input_path, arena_dir / f"{arena_prefix}-{payload.input}.txt")

        logger.info(
            "Pipeline run started: run_id=%s arena=%s input=%s overrides=%d",
            run_id,
            arena_dir.name,
            payload.input,
            len(payload.overrides.model_dump(exclude_none=True))
            if payload.overrides
            else 0,
        )

        # 4. Spawn the async worker that drives the real pipeline and
        #    forwards progress events to the popup via WebSocket.
        asyncio.create_task(
            _execute_typed_run(
                run_id=run_id,
                arena_dir=arena_dir,
                input_path=input_path,
                settings=typed_settings,
                project_root=root,
                started_monotonic=run_started,
            )
        )
        return {
            "run_id": run_id,
            "arena_number": arena_num,
            "arena_path": str(arena_dir),
            "warnings": warnings,
        }

    return app


# ---------------------------------------------------------------------------
# Async worker (lives at module level so FastAPI can schedule it from
# inside the route handler).
# ---------------------------------------------------------------------------


async def _execute_typed_run(
    *,
    run_id: str,
    arena_dir: Path,
    input_path: Path,
    settings,  # core.settings.Settings — avoiding top-of-file alias import
    project_root: Path,
    started_monotonic: float,
) -> None:
    """Drive :func:`core.pipeline.run_pipeline` for a single ``/api/run``.

    The pipeline is synchronous (file IO + a one-shot async Gemini call
    inside the ``judge`` stage). Running it directly from an async
    handler would block the event loop on disk reads, so we delegate to
    :func:`asyncio.to_thread` and pipe progress events through
    :func:`core.pipeline.make_async_bridge`, which schedules
    ``manager.send_event`` coroutines onto the FastAPI event loop via
    :func:`asyncio.run_coroutine_threadsafe`.
    """
    logger = logging.getLogger("gui.server.pipeline")
    logger.info(
        "pipeline.run.start run_id=%s arena=%s",
        run_id,
        arena_dir.name,
    )
    try:
        loop = asyncio.get_running_loop()

        async def _send(stage: str, level: str, msg: str, pct: float) -> None:
            await manager.send_event(run_id, stage, level, msg, pct)

        progress = pipeline_mod.make_async_bridge(_send, loop)

        result = await asyncio.to_thread(
            pipeline_mod.run_pipeline,
            project_root=project_root,
            settings=settings,
            input_path=input_path,
            arena_dir=arena_dir,
            output_format=str(settings.output.format),
            model_count=int(settings.models.count),
            gemini_judge=bool(settings.judge.enabled),
            compact_mode=bool(settings.compact.enabled),
            progress=progress,
        )
        elapsed = time.perf_counter() - started_monotonic
        logger.info(
            "pipeline.run.end run_id=%s arena=%s entries=%d lines=%d "
            "tokens=%s judge=%s elapsed=%.3fs",
            run_id,
            arena_dir.name,
            result.entries_processed,
            result.total_lines,
            result.token_count,
            result.judge_used,
            elapsed,
        )
    except Exception as exc:  # noqa: BLE001 — last-resort guard around the whole task
        elapsed = time.perf_counter() - started_monotonic
        logger.exception(
            "pipeline.run.error run_id=%s arena=%s elapsed=%.3fs: %s",
            run_id,
            arena_dir.name,
            elapsed,
            exc,
        )
        try:
            await manager.send_event(
                run_id, "error", "error", str(exc), 1.0
            )
        except Exception:  # noqa: BLE001 — swallow downstream WS failures
            logger.warning(
                "Could not deliver error event for run_id=%s (popup likely disconnected)",
                run_id,
            )
