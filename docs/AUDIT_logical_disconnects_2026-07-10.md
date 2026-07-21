# Logical Disconnects Audit — Context Tool

| Field | Value |
| --- | --- |
| Audit date | 2026-07-10 |
| Audited commit | `cd0053a` (master @ origin/master) |
| Codebase | `C:\programming\Python\Projects\context` |
| Scope | `gui/browser-extension/**`, `gui/server/**`, `core/pipeline.py`, `core/judge.py`, `core/parser.py`, `core/settings.py`, `core/arena.py`, `core/discovery.py`, `aggregator.py`, `aggregator_gui.py` |
| Correction (2026-07-10) | The decomposed `gui/` package (10 modules, ~2,400 lines — `app.py`, `aggregation_runner.py`, `scanner.py`, `queue_manager.py`, `builders.py`, `log_panel.py`, `api_key_dialog.py`, `theme.py`, `paths.py`, `util.py`) is **dead code**: zero inbound imports from any runtime entry point. The live Tk GUI is the monolithic `aggregator_gui.py`. See **D1** below and `docs/AUDIT_corrigendum_2026-07-10.md` §0.2. |
| Method | End-to-end trace of every data flow from input surface (CLI flag, browser-extension popup button, Tk widget toggle, HTTP `POST /api/*`, WS connect) → intermediate transform → persistence layer (filesystem, in-memory store, dataclass hierarchy). |
| Severity model | **Critical** — breaks a documented user-facing feature or silently corrupts persistent state. **Structural** — non-crashing invariant violation that creates drift or a hidden footgun. **UX Flaw** — observable quality issue with no data loss. |

---

## Executive Summary

The Context Tool has three independent contract layers — the Python CLI (`aggregator.py`), the Tk GUI (`aggregator_gui.py`), and the FastAPI browser-extension server (`gui/server/main.py`) — that all *appear* to share the same `core/` engine but in fact implement **parallel settings loaders, parallel output-path resolvers, and parallel env-key lookups**. None of the three consumers agrees with the others about the canonical `Settings` shape, the canonical location for the `.env` file, or the canonical flat ↔ nested upgrade direction. *(The decomposed `gui/` package — `gui/app.py` and friends — is dead code; see **D1**. The live Tk GUI is the monolithic `aggregator_gui.py`.)*

On top of this, the browser-extension popup that was wired in v2.6.0 (commit `d9fcd3a`) **never calls** the run-path endpoints it defines: `/api/run` is dead, `/ws/run/{run_id}` has neither bearer-token auth nor loopback enforcement, and the WS connection never happens because no client opens it. The four Critical findings below fall out of this single architectural decision (extend the run path through HTTP+WS **without** integrating it into the popup UI) interacting with the dataclass refactor that landed in `core/settings.py`.

The Tk GUI is the worst-affected surface in user-visible terms: every settings toggle in the GUI calls `self._settings["gemini_judge"] = …` against a `Settings` **dataclass instance**, which raises `TypeError`, which is swallowed by a `try/except` that surrounds `save_settings(...)` (but the type error fires on the assignment *before* `save_settings` is reached). Net effect: **GUI settings toggles never persist**.

A separate finding tracked here for completeness: the decomposed `gui/` package itself (10 modules, ~2,400 lines, intended to replace the monolithic `aggregator_gui.py` per `d9fcd3a`) is **unreachable dead code**. The refactoring was started but the entry point was never switched over. `gui/__init__.py:21-25` falsely claims `aggregator_gui.py` is a thin glue module forwarding to `gui.app.run_gui`; in reality `aggregator_gui.py` is 1,513 lines defining its own `AggregatorGUI(tk.Tk)` and is the live GUI. See **D1** below and `docs/AUDIT_corrigendum_2026-07-10.md` §0.2 for the full reasoning.

Recommended fix order:

1. Unify the three settings loaders around `core.settings.load_settings` / `save_settings` (closes Critical #2 and #3, Structural #2 and #5 in one refactor).
2. Wire a Run button + WS-pre-connect handshake into the popup (closes Critical #1 and UX #2) **or** delete the dead `/api/run` and `/ws/run/{id}` plumbing until you're ready.
3. Add bearer-token auth to `/ws/run/{id}` (closes Critical #4 and UX #5).
4. Unify the two `.env` lookup paths (closes Structural #1).
5. Polish — concurrent-update lock (UX #1), content-script fallback (UX #3), settings accessor caching (UX #4).

---

## CRITICAL Findings

### C1 — Browser extension never triggers a run; `/api/run` and the entire WS pipeline are dead endpoints

**Severity:** Critical (1 of 4)

**Files:**

- `gui/browser-extension/src/popup/App.tsx:1-19`
- `gui/browser-extension/src/popup/components/ServerStatus.tsx:1-53`
- `gui/browser-extension/src/popup/components/SettingsPanel.tsx:1-133`
- `gui/browser-extension/src/popup/components/InputManager.tsx:1-113`
- `gui/browser-extension/src/popup/components/EnvSetup.tsx:1-44`
- `gui/browser-extension/src/shared/api.ts:121-131`
- `gui/browser-extension/src/shared/types.ts:62-88`
- `gui/server/main.py:501-597`
- `gui/server/ws.py:72-87`

**Symptom**

The popup mounts exactly four components — `ServerStatus`, `SettingsPanel`, `InputManager`, `EnvSetup` — and **none of them ever invokes `api.run()` or `api.checkRun()`**. The methods exist on the `api` shim:

```ts
// gui/browser-extension/src/shared/api.ts:121-131
checkRun: (input: string) =>
  fetchAPI<RunCheckResponse>('/api/run/check', {
    method: 'POST',
    body: JSON.stringify({ input }),
  }),

run: (req: RunRequest) =>
  fetchAPI<RunResponse>('/api/run', {
    method: 'POST',
    body: JSON.stringify(req),
  }),
```

… and the type system declares `RunRequest`, `RunResponse`, `RunCheckResponse`, `RunOverrides` (`types.ts:62-88`). But searching the entire `gui/browser-extension/src/` tree for `WebSocket`, `new WebSocket`, `ws://`, or `onmessage` returns **zero matches**. There is no "Run", "Aggregate", "Process", or "Send to Pipeline" button anywhere in the popup. No input picker. No run-id display. No progress bar.

**Why it is illogical**

The comment chain in `main.py:1-13` declares `/api/run` and `/ws/run/{run_id}` as core surfaces:

```python
# gui/server/main.py:1-13
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
```

`types.ts:1` echoes: `Shared types — MUST mirror the server pydantic models`. The HTTP route is plumbed, the WS endpoint is plumbed, the typed API client is plumbed. **The connection from the client UI to the client API client is missing.**

The popup's error banner `ServerStatus.tsx:27` even tells the user what to do:

```ts
setError('Server offline. Run `python aggregator.py --serve`');
```

…but only when the server is offline. Once paired, the popup provides no UI to actually use the run-path it has authenticated to.

**Concrete fallout**

`_execute_typed_run` in `main.py:608-682` schedules `manager.send_event(...)` over WS for every progress event. `send_event` (`ws.py:45-66`) silently drops events when no connection is registered:

```python
# gui/server/ws.py:45-56
async def send_event(self, run_id, stage, level, msg, pct):
    ws = self.active_connections.get(run_id)
    if ws is None:
        logger.debug("ws.event.dropped run_id=%s stage=%s reason=no_connection", ...)
        return
    ...
```

With no client that ever opens the socket, **every progress event from every run is silently dropped to `logger.debug`**. The entire bridge (`pipeline.py:88-126`, `make_async_bridge`) is wasted work for every invocation. `test_browser_extension_dist.py` exists and verifies wire-format compatibility at the `api.ts` shim level, which masks the absence of a real consumer — the test asserts `'"/api/run"' in text`, but the popup never calls that function.

**Fix**

Either:

- **(a) Add the Run UI.** Insert a `RunPanel` into `App.tsx` between `InputManager` and `EnvSetup` (or as a separate top-level tab). It should:
  1. Bind to `api.getInputs()` for an input picker.
  2. Bind to `api.getSettings()` for the `model_count` / `output_format` / `gemini_judge` toggles.
  3. Call `api.checkRun(input)` first; on `conflict: true`, render a "Merge or Skip?" dialog before `api.run({input, overrides})`.
  4. On `{run_id, ...}`, connect to `ws://127.0.0.1:8765/ws/run/{run_id}` (request the `websocket` permission in `manifest.json` if not already present) and render `manager.send_event` payloads into a progress bar keyed on `pct`.

- **(b) Delete the dead plumbing.** If the popup cannot trigger a run in this milestone, remove:
  - `core/pipeline.py` (583 LOC) and tests for it that don't have another consumer.
  - `_execute_typed_run` from `main.py`.
  - `/api/run` and `/api/run/check` routes.
  - `gui/server/ws.py` entirely.
  - `tests/test_ws.py`, `tests/test_gui_server.py` run-paths, `tests/test_browser_extension_dist.py`.

Doing (a) is the intended outcome per `d9fcd3a`. Doing (b) is honest if the UI is not landing this milestone.

---

### C2 — Tk GUI settings toggles never persist; `self._settings["key"] = value` raises `TypeError` on the `Settings` dataclass

**Severity:** Critical (2 of 4)

**Correction (2026-07-10):** This finding was originally filed against `gui/app.py` in the decomposed (and now-confirmed dead — see **D1**) `gui/` package. The identical bug is present in the **live** Tk GUI at `aggregator_gui.py:364-374`. The bug, root cause, evidence, and fix are unchanged; the file:line references below have been retargeted to the live code. See `docs/AUDIT_corrigendum_2026-07-10.md` §0.2 and §2.1.

**Files:**

- `aggregator_gui.py:328-356` (`_load_and_apply_settings` — load path)
- `aggregator_gui.py:364-374` (`_save_current_settings` — save path, the bug)
- `aggregator_gui.py:376-379` (the `try/except` around `save_settings` only)
- `core/parser.py:36-43` (re-export)
- `core/settings.py:147-209` (`Settings` dataclass, no `__setitem__`)
- `core/settings.py:204-209` (`Settings.get`, the only reason reads work)
- `core/settings.py:703-713` (`save_settings` calls `settings.to_dict()`)

**Symptom**

The Tk GUI's `_save_current_settings` does this on every widget trace:

```python
# aggregator_gui.py:359-379
def _save_current_settings(self, *args) -> None:
    if self._suppress_settings_save:
        return
    self._settings["gemini_judge"] = self._judge_var.get()       # line 364 — TypeError
    self._settings["compact_mode"] = self._compact_var.get()     # line 365
    self._settings["archive"] = self._archive_var.get()           # line 366
    self._settings["output_dir"] = (...)                          # line 367
    try:
        self._settings["model_count"] = int(...)                  # line 370
    except ValueError:
        self._settings["model_count"] = 2                         # line 372
    self._settings["output_format"] = ...                         # line 374
    try:
        save_settings(self._project_root, self._settings)         # line 377
    except Exception as exc:
        self._log_panel.write(f"Could not save settings: {exc}", tag="warn")
```

`self._settings` is **not** a `dict`. It is a `Settings` dataclass instance — `aggregator_gui.py:330`:

```python
def _load_and_apply_settings(self) -> None:
    self._settings = load_settings(self._project_root)
```

`load_settings` (`core/settings.py:608-682`) declares its return type as `Settings` and constructs one via `settings_from_dict(nested_input)` (line 680). The instance attribute is therefore a `Settings` dataclass, not the `dict[str, object]` the GUI's surrounding code assumes.

The `Settings` class (`core/settings.py:147-209`) defines:

- `__getitem__` (line 183) — so `self._settings["gemini_judge"]` (read) works as a "best-effort" proxy through `to_flat_dict()`.
- `get` (line 204) — so `self._settings.get("gemini_judge", False)` (read with default) works.
- **No `__setitem__`** — so `self._settings["gemini_judge"] = value` (write) raises `TypeError: 'Settings' object does not support item assignment`.

The `try/except` at `aggregator_gui.py:376-379` is positioned **around `save_settings` only**, not around the assignments on lines 364-374. So the type error fires before the try block, the write to the dataclass attribute is never even attempted, and the only thing that ever makes it into the log panel is the `TypeError` message if Python's traceback reaches it at all (in Tk's trace callbacks it generally does surface to `stderr` but does **not** appear in the GUI log panel).

**Why it is illogical**

The `commit 57608f1` refactor that flattened the dataclass hierarchy was supposed to be transparent to consumers. The CLI's `aggregator.py:616-622`:

```python
output_dir = resolve_output_dir(init_root, settings, cli_output)
output_format = str(settings.get("output_format", "md"))  # .get works
```

…uses `.get`, which is provided. It silently succeeds. So when the same refactor reached the GUI, the assumption was "if `.get(key)` works in the CLI, the GUI's assignment-and-`.get` pattern will also work." The flaw is that the GUI's save path uses `[]=` for writes, which `Settings` does not implement. The "best-effort compatibility" shim covers half the contract (reads) and not the other half (writes).

The same shape of bug exists in the dead `gui/app.py:181-191` (with a lying type annotation at `gui/app.py:98`); that file is being deleted as part of **D1**'s remediation. The fix below targets the live `aggregator_gui.py` instance of the bug.

**Verification I performed** (re-verified 2026-07-10 — see `docs/AUDIT_corrigendum_2026-07-10.md` §2.1 for the live tool-call evidence)

- Read the entire `Settings` class definition (`core/settings.py:147-209`); no `__setitem__` defined.
- Empirical test: `python -c "from core.settings import Settings; s = Settings(); s['gemini_judge'] = True"` → `TypeError: 'Settings' object does not support item assignment`.
- Confirmed `save_settings` (`core/settings.py:703-713`) expects a `Settings` instance:
  ```python
  def save_settings(root: Path, settings: Settings) -> None:
      ...
      _save_nested_dict(root, settings.to_dict())
  ```
- The fact that the GUI never crashes hard when toggling checkboxes is itself the giveaway — the exception is being swallowed by Tk's variable-trace mechanism; if the trace callback raises, the underlying Variable is in an inconsistent state but Tk keeps painting the widget value back from the in-memory Tkvar on the next event. So the user's checkbox shows "checked" but the dataclass state is unchanged, the disk file is unchanged, and on the next GUI launch the load path reads the old setting from disk.

**Concrete fallout**

Every Tk GUI settings toggle fails to persist. `aggregator_gui.py:364-374` is dead code from the user's point of view. The visible symptom in the GUI log panel — `Could not save settings: 'Settings' object does not support item assignment` — is easy to mis-attribute to a transient file-write race.

**Fix**

Replace the dict-style mutation with attribute-style (or with an explicit flat dict adapter):

```python
# aggregator_gui.py:359-379 — proposed fix
def _save_current_settings(self, *args) -> None:
    if self._suppress_settings_save:
        return
    settings = self._settings
    # settings is a Settings dataclass instance; write through its typed API.
    settings.judge.enabled = bool(self._judge_var.get())
    settings.compact.enabled = bool(self._compact_var.get())
    settings.archive.enabled = bool(self._archive_var.get())
    settings.output.dir = (self._output_dir_var.get().strip() or "context_output")
    settings.models.count = int(self._model_count_var.get())
    settings.output.format = self._output_format_var.get()
    try:
        save_settings(self._project_root, settings)
    except Exception as exc:
        self._log_panel.write(f"Could not save settings: {exc}", tag="warn")
```

…plus, in the M1 settings-unification PR, retype the surrounding `self._settings` annotations to `Settings` (currently `dict[str, object]`, a lie). A second-pass fix is to add a `Settings.__setitem__` proxy that maps a single-segment key to the corresponding nested attribute, making the legacy dict-style writes safe again — but that recreates the C3 dual-format hazard at the type layer.

---

### C3 — Server's `read_settings` / `update_settings` corrupt the nested-form `settings.json` the CLI writes

**Severity:** Critical (3 of 4)

**Files:**

- `gui/server/main.py:112-124` (`DEFAULT_SETTINGS` flat dict)
- `gui/server/main.py:172-204` (`read_settings` flat merge)
- `gui/server/main.py:206-210` (`write_settings` straight JSON dump)
- `gui/server/main.py:254-261` (`update_settings`)
- `core/settings.py:296-348` (`_FLAT_TO_NESTED`, `_LEGACY_FLAT_DETECTION_KEYS`)
- `core/settings.py:360-387` (`_looks_like_flat_shape`, the detector)
- `core/settings.py:390-401` (`_flat_dict_to_nested` silently ignores unknown keys)
- `core/settings.py:666-676` (legacy-flat upgrade rewrites file in nested form)
- `core/settings.py:703-713` (`save_settings` writes nested form)
- `aggregator.py:596-610` (CLI persists settings after `--interactive`)

**Symptom**

Three places persist `settings.json`. They disagree about the schema.

| Surface | Schema written | Loader reads as | Loader's interpretation |
| --- | --- | --- | --- |
| `aggregator.py` (CLI) → `core.settings.save_settings` (line 605) | nested dict (via `settings.to_dict()` at `core/settings.py:713`) | `core.settings.load_settings` (`core/settings.py:608-682`) — auto-detects nested vs flat via `_looks_like_flat_shape`; if flat, **upgrades in place** to nested (line 666-667) | nested, after on-disk upgrade |
| Tk GUI → `core.parser.save_settings` (`aggregator_gui.py:377`) | tries to write `Settings.to_dict()` (typed) **but the call is reached only after the assignments on lines 364-374 raise — see C2** so nothing is ever actually written by the GUI | n/a | n/a (never writes) |
| Browser extension → server `PUT /api/settings` → `gui.server.main.update_settings` → `gui.server.main.write_settings` | flat dict (via `json.dumps` of the merged flat result, `gui/server/main.py:208-209`) | next CLI run → `core.settings.load_settings` detects **flat** (the unambiguous flat keys `output_dir`, `gemini_judge`, … are still present from the flat defaults merge), upgrades in place via `_flat_dict_to_nested` (line 663-667), and `_flat_dict_to_nested` **silently ignores keys it doesn't know** — i.e. **the user's nested `output`, `judge`, `compact`, `paste_attachments`, `target_arena`, `ignore`, `inputs` group dicts are dropped on the next CLI save** | flat |

The execution path that demonstrates this:

1. User runs `python aggregator.py --interactive`, customizes settings. CLI persists nested-form `settings.json` (`aggregator.py:604-610` → `save_settings` → nested).
2. User installs the browser extension, pairs with the server, opens the popup.
3. User toggles the "Gemini Judge" checkbox. `SettingsPanel.tsx:74` calls `api.updateSettings({gemini_judge: e.target.checked})`.
4. Server `PUT /api/settings` handler (`gui/server/main.py:254-261`):
   ```python
   current, _ = read_settings()                       # reads nested file
   current.update(payload.model_dump(exclude_none=True))   # merges into the merged-FLAT default shape!
   write_settings(current)                           # writes back as flat-with-leftover-nested-group-keys
   ```
5. The file now contains BOTH the flat keys AND the user's nested groups:
   ```json
   {
     "output_dir": "context_output",
     "output_format": "md",
     "model_count": 2,
     "gemini_judge": true,
     "compact_mode": false,
     ...,
     "output": {"dir": "custom-dir", "format": "md"},
     "judge": {"enabled": true}
   }
   ```
6. Next CLI run: `load_settings` calls `_looks_like_flat_shape` (`core/settings.py:360-387`):

   ```python
   def _looks_like_flat_shape(raw):
       if any(key in raw for key in _LEGACY_FLAT_DETECTION_KEYS):
           return True   # ← output_dir IS in raw → returns True
       ...
   ```

   …which returns `True`. The file is treated as legacy flat. `_flat_dict_to_nested` (line 390-401) consumes it:

   ```python
   def _flat_dict_to_nested(flat):
       nested = {}
       for key, value in flat.items():
           if key in _DROPPED_FLAT_KEYS:
               continue
           if key in _FLAT_TO_NESTED:
               group_name, attr_name = _FLAT_TO_NESTED[key]
               nested.setdefault(group_name, {})[attr_name] = value
           # Unknown keys are silently ignored
       return nested
   ```

   The `output`, `judge`, `compact`, `paste_attachments`, `target_arena`, `ignore`, `inputs` group keys are not in `_FLAT_TO_NESTED` — they are the nested group names themselves, so the function ignores them. **All user-customized values under nested groups are silently dropped** from the result `nested` dict. The CLI then writes the (now degraded) nested result back at line 667.

**Why it is illogical**

The file-format split was a deliberate design choice that the server-side loader never got. The server is operating on a different schema than the CLI's `save_settings` produces, with no upgrade or downgrade path. The TypeScript `Settings` interface in `types.ts:5-17` is also flat, so even the contract documented as "Response shapes … mirrored in `shared/types.ts`" (`main.py:9-13`) is a third incompatible shape.

Three orthogonal definitions of "what is in `settings.json`" cannot coexist. The migration was supposed to be transparent; the consumer code in `gui/server/main.py` was not updated.

**Concrete fallout**

Every `PUT /api/settings` from the browser extension progressively flattens nested settings. Every subsequent CLI run amplifies the loss. The user's `(paste_attachments.target_subdir, target_arena.directive_prefix, …)` values disappear without an error.

**Fix**

Choose one schema on the wire (the nested one is canonical — it's what the CLI writes), and rewrite the server's settings handlers to use it:

```python
# gui/server/main.py — proposed replacement

from core.settings import (
    DEFAULT_SETTINGS,
    load_settings,        # typed, handles nested/flat detection transparently
    save_settings,
)

@app.get("/api/settings")
async def get_settings(token = Depends(get_current_token)):
    settings = load_settings(get_project_root())
    return {"settings": settings.to_dict(), "message": None}

@app.put("/api/settings")
async def update_settings(
    payload: SettingsUpdate,
    token = Depends(get_current_token),
):
    settings = load_settings(get_project_root())
    flat = payload.model_dump(exclude_none=True)
    # Delegate to the same merge pipeline the CLI uses for overrides.
    settings = pipeline_mod.merge_overrides(settings, flat)
    save_settings(get_project_root(), settings)
    return {"settings": settings.to_dict(), "message": None}
```

… and replace `DEFAULT_SETTINGS` (line 112-124, ~13 lines, manually maintained) with a thin adapter call:

```python
DEFAULT_SETTINGS: dict[str, object] = _to_flat_dict(Settings())
```

…but really the better fix is for the server to stop exposing flat-shaped JSON entirely. The TS `Settings` interface would have to become nested-shaped, which is a contract change. Better still: have the server do the conversion server-side and have TS ask for it; the contract becomes {nested} → TS renders nested; override keys are flat and stay flat (matching `RunOverrides`). One direction on the wire per concern.

---

### C4 — WebSocket endpoint has neither loopback enforcement nor bearer-token auth

**Severity:** Critical (4 of 4)

**Files:**

- `gui/server/main.py:145-158` (CORS + HTTP loopback middleware)
- `gui/server/security.py:49-68` (`enforce_loopback`)
- `gui/server/security.py:71-86` (`get_current_token` dependency)
- `gui/server/main.py:153` (router registration — only `ws_router` is included here)
- `gui/server/ws.py:72-87` (the unguarded endpoint)

**Symptom**

Every HTTP route except `/health` and `/auth/pair` declares `token: str = Depends(get_current_token)` (`gui/server/main.py:234, 250, 256, 266, 295, 308, 342, 358, 373, 381, 401, 424, 437, 470, 503`). HTTP loopback is enforced by `loopback_middleware` (`gui/server/main.py:155-158`, calling `enforce_loopback` at `gui/server/security.py:49-68`):

```python
# gui/server/main.py:155-158
@app.middleware("http")
async def loopback_middleware(request: Request, call_next):
    enforce_loopback(request)
    return await call_next(request)
```

The WebSocket endpoint:

```python
# gui/server/ws.py:72-87
@router.websocket("/ws/run/{run_id}")
async def websocket_endpoint(websocket: WebSocket, run_id: str) -> None:
    """Accept a WS for a run and keep it alive until disconnect."""
    await manager.connect(websocket, run_id)
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect(run_id)
        logger.info("ws.client.disconnected run_id=%s", run_id)
```

…has **no `Depends(get_current_token)`, no loopback check, no origin check**. Worse: `loopback_middleware` is registered with `@app.middleware("http")`. FastAPI dispatches HTTP routes and WebSocket routes through **separate Starlette routing layers** — `@app.middleware("http")` does **not** run for WebSocket upgrades. Documentation reference: Starlette's `Router` only invokes HTTP middleware on HTTP routes; `WebSocket` routes use the `WebSocketRoute` code path which does not run `BaseHTTPMiddleware` (only `ExceptionMiddleware` and CORS — both of which CORS already opens with `allow_origins=["*"]`).

**Attack surface**

Current state with **no client** calling this endpoint (C1):

- Exploitability is nil because nobody listens.

State the moment a Run button lands (after C1's fix):

- Any process on the host that can speak HTTP/1.1 Upgrade can connect to `ws://127.0.0.1:8765/ws/run/<anything>`, register as a phantom listener, and receive every subsequent `manager.send_event` payload for that `run_id`.
- For `compact=False` runs the payloads contain the prompt + every model's full LMArena response (the `compare_path` body). That is user-confidential work product.
- A second misconfigured browser extension (or any userland script with fetch to localhost) can passively sniff every pipeline run.

**Why it is illogical**

The HTTP layer's defense-in-depth is good. The WS layer skipped both halves of it. There is no reason in the code comments (or in the test layout — `tests/test_ws.py:88-108` calls `websocket_endpoint(ws, "run-test")` directly, bypassing all auth) for the omission. It looks like the WS endpoint was added at the end of the v2.6.0 sprint and never audited against the security model applied to the rest of the server.

**Fix**

Either add the dependency (cleanest, requires the client to send the token as a query parameter or `Sec-WebSocket-Protocol`):

```python
# gui/server/ws.py — proposed fix
from fastapi import Query
from gui.server.security import get_current_token

@router.websocket("/ws/run/{run_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    run_id: str,
    token: str | None = Query(default=None),
):
    # Reject if the supplied token isn't in the valid-token set.
    if not token or token not in _valid_tokens:
        await websocket.close(code=4401, reason="Invalid or expired token")
        return
    # Caller's host must still be loopback.
    client = websocket.client
    if client is None or client.host not in ("127.0.0.1", "::1", "localhost"):
        await websocket.close(code=4403, reason="Non-loopback address")
        return
    await manager.connect(websocket, run_id)
    ...
```

…or, less aggressively, add an HTTP middleware-style wrapper for WS that does the same two checks. Whatever the path, the dual gap of "no auth" + "no loopback" must be closed in one PR so it doesn't get half-fixed.

---

### C5 — Four separate pipeline implementations; 4× orchestration duplication

**Severity:** Critical (added 2026-07-10; see `docs/AUDIT_corrigendum_2026-07-10.md` §1 M7)

**Files:**

- `aggregator.py:241-414` (`_process_one` — CLI)
- `aggregator_gui.py:1127-1404` (`_aggregate_worker` — live Tk GUI)
- `core/pipeline.py:242-574` (`run_pipeline` — the path the server exercises)
- `gui/aggregation_runner.py:146-456` (`run_aggregation` — dead twin of the live GUI; will be removed with **D1**)

**Symptom**

Four independent orchestrators implement the same six-phase sequence (init → read_input → aggregate → tokens → compare → done, with optional judge). Each has its own progress mechanism:

| # | File | Entry function | Lines | Progress mechanism |
|---|------|---------------|-------|-------------------|
| 1 | `aggregator.py` | `_process_one` | 241-414 | `print()` to stdout |
| 2 | `aggregator_gui.py` | `_aggregate_worker` | 1127-1404 | direct `_log_write()` to Tk widget |
| 3 | `core/pipeline.py` | `run_pipeline` | 242-574 | `ProgressCallback` → WebSocket bridge |
| 4 | `gui/aggregation_runner.py` | `run_aggregation` | 146-456 | `LogFn`/`StepFn`/`StatusFn`/`CancelFn` |

Adding any feature (e.g. a JSON output format, a token-usage report) requires coordinated edits in four files with different error-handling conventions.

**Why it is illogical**

The `core/pipeline.py` version is architecturally the best (callback-driven, decoupled from I/O, WebSocket-ready), but neither the CLI nor the live GUI can use it because they pre-date it. The duplication isn't plain text — the four diverge in *behaviour* (see **C6**), so the surface "they all do the same thing" is false.

**Verification I performed** (re-verified 2026-07-10; see `docs/AUDIT_corrigendum_2026-07-10.md` §2.7)

- Read all four functions end-to-end.
- Empirically confirmed `core/pipeline.py` does **not** call `load_ignore_patterns` or `build_arena_plan` — `Select-String` against `core/pipeline.py` for `load_ignore_patterns|build_arena_plan` returns zero matches; the same pattern against `aggregator.py`, `aggregator_gui.py`, and `gui/aggregation_runner.py` returns multiple matches.

**Fix (consolidation, addressed in Milestone 4 of the roadmap below)**

Promote `core.pipeline.run_pipeline` to be the single canonical orchestrator. Have the CLI call it through a thin wrapper that translates progress callbacks to stdout. Have the live GUI call it through a thin wrapper that translates callbacks to `_log_write()`. Delete the dead twin as part of **D1**.

---

### C6 — Server's `core/pipeline.py` skips seven CLI validations; CLI and server produce different arena numbers for the same input

**Severity:** Critical (added 2026-07-10; see `docs/AUDIT_corrigendum_2026-07-10.md` §1 M8)

**Files:**

- `aggregator.py:472-843` (CLI orchestrator with the seven validations)
- `core/pipeline.py:242-574` (the server's orchestrator, missing them)
- `gui/server/main.py:608-682` (`_execute_typed_run` — calls `core/pipeline.py` directly)

**Symptom**

The CLI's `aggregator.py` runs seven validations before and after the pipeline; the server's `_execute_typed_run` runs **none** of them. The `core/pipeline.py` orchestrator (the only one the server exercises) never imports `load_ignore_patterns`, `build_arena_plan`, the structure-drift detector, the post-run directive reporter, `write_state_breadcrumb`, `sync_paste_attachments`, or the legacy migrations.

| # | CLI validation | CLI line | Server `_execute_typed_run`? |
|---|----------------|----------|------------------------------|
| 1 | `load_ignore_patterns` | `aggregator.py:674` | **Missing** — pipeline ignores it |
| 2 | `build_arena_plan` (directive resolution) | `aggregator.py:725-751` | **Missing** — server uses `next_arena_number` (`main.py:560`) |
| 3 | Structure drift detection (tree compare + prompt) | `aggregator.py:686-714` | **Missing** |
| 4 | Post-run directive report | `aggregator.py:790-827` | **Missing** |
| 5 | `write_state_breadcrumb` | `aggregator.py:834-841` | **Missing** |
| 6 | `sync_paste_attachments` | `aggregator.py:831` | **Missing** |
| 7 | Legacy migrations (`migrate_old_outputs`, `migrate_to_per_file_folders`, `migrate_to_flat_layout`) | `aggregator.py:626-634` | **Missing** — server has a separate `/api/run/check` endpoint that covers only old-file detection |

**Concrete fallout — same input, different output directory:**

A `files.txt` containing `# Target Arena: 005 my-benchmark` and a list of source files:

- **CLI:** Parses the directive, reads `settings.on_arena_number_conflict` (default `"warn_and_shift"`), writes to `<output_dir>/arenas/005-my-benchmark/`. If `005` already exists, shifts to `006` and warns.
- **Server:** Ignores the directive entirely. `next_arena_number()` (`gui/server/main.py:212`, called at line 560) computes `max(existing) + 1`. Writes to `<output_dir>/arenas/042-my-benchmark/`. The directive's requested number is silently dropped.

The extension user and the CLI user get different arena numbers for the same input.

**Why it is illogical**

The seven validations are not optional. They are the contract that makes a "Context Tool run" mean the same thing to the CLI user, the GUI user, and the extension user. Skipping them in the server means the server's output is not a "Context Tool run" in the same sense.

**Verification I performed** (re-verified 2026-07-10; see `docs/AUDIT_corrigendum_2026-07-10.md` §2.8)

- Read `_execute_typed_run` (`gui/server/main.py:608-682`) end-to-end. The function body is `asyncio.to_thread(pipeline_mod.run_pipeline, ...)` plus error logging. It calls none of the seven validations.
- `Select-String` against `gui/server/main.py` for `load_ignore_patterns|build_arena_plan|write_state_breadcrumb|sync_paste_attachments|migrate_to_flat_layout|migrate_to_per_file_folders|migrate_old_outputs` returns **zero** matches. The only arena-numbering call site is `next_arena_number` at line 212, called at line 560 — the simple `max(existing) + 1` strategy, not `build_arena_plan`.

**Fix (consolidation, addressed in Milestone 4 of the roadmap below)**

Make `core/pipeline.py` the only orchestrator and move all seven validations *into* it (or into a `preflight`/`postflight` step it calls). Once C5 is fixed by promoting `core/pipeline.py` to be canonical, the seven missing validations are restored in the same PR.

---

## STRUCTURAL Findings

### S1 — Server's `/health` and `/api/run` use two different Gemini-key scanners

**Severity:** Structural (1 of 5)

**Files:**

- `gui/server/launcher.py:80-89` (`get_gemini_key`, tool-root only)
- `gui/server/launcher.py:91-104` (`set_gemini_key`, writes to tool root)
- `gui/server/main.py:229` (`/health` reports `has_gemini_key` via `get_gemini_key`)
- `gui/server/main.py:534-539` (`/api/run` warns via `get_gemini_key`)
- `core/judge.py:59-89` (`get_api_key`, project-root → cwd → tool-root cascade)
- `core/pipeline.py:477` (the actual judge call uses `get_api_key`)
- `core/judge.py:77-80` (the cascade)

**Symptom**

`launcher.get_gemini_key()` reads only the **tool-root** `.env`:

```python
# gui/server/launcher.py:80-89
def get_gemini_key() -> bool:
    env_path = TOOL_ROOT / ".env"
    env_vars = dotenv_values(env_path)
    key = env_vars.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")
    return bool(key and key.strip())
```

`core.judge.get_api_key()` cascades through **project root → cwd → tool root**:

```python
# core/judge.py:59-89
def get_api_key(root_dir: Path | None = None) -> str | None:
    if root_dir:
        load_dotenv(root_dir)
    load_dotenv(Path.cwd())
    load_dotenv(Path(__file__).parent.parent)  # tool root directory
    api_key = os.environ.get("GEMINI_API_KEY")
    if api_key:
        return api_key
    print("Warning: GEMINI_API_KEY not found in environment or .env files. ...", file=sys.stderr)
    return None
```

`gui/server/main.py:534-539` runs the warning off `launcher.get_gemini_key()`:

```python
if typed_settings.judge.enabled and not get_gemini_key():
    warnings.append("GEMINI_API_KEY not set — Gemini judge step skipped")
    typed_settings.judge.enabled = False
```

But `core/pipeline.py:477` calls `core.judge.get_api_key(project_root)` for the actual Gemini request. So:

- User keeps their `.env` in the project root (the documented pattern from `aggregator.py`'s CLI path: `judge.py:77-80` is documented as "first the project root, then CWD, then tool root").
- They start the server.
- `/health` says `has_gemini_key: false`.
- `/api/run` returns `warnings: ["GEMINI_API_KEY not set — Gemini judge step skipped"]` even though the actual Gemini call would have succeeded if it had been attempted.
- Worse: after they call `/api/env` to "fix" the issue, `set_gemini_key` writes to the tool-root `.env`. From the user's perspective, the popup told them to set the key to make the warning go away; they did; the warning went away; but what actually happened is the lookup scope shifted to a different file (tool root), not the key moved to where the system was reading from (project root).

**Why it is illogical**

Two systems, two definitions of "where the key lives." A user cannot reason about which file matters. The "warning" misleads them about the cause of the warning.

**Fix**

Either collapse to one resolver or surface both:

```python
# gui/server/launcher.py — proposed fix
from core.judge import get_api_key as _get_api_key

def get_gemini_key() -> bool:
    # Use the same cascading resolver the CLI uses, scope to the detected
    # project root. Return bool for backward compat with the existing
    # /health endpoint.
    return bool(_get_api_key(get_project_root()) or _get_api_key())
```

… and let the actual judge call do the same cascade. The `set_gemini_key` write target is a separate question — pick one (project root) or accept the user explicitly tells the server which file to use as the `.env`.

---

### S2 — GUI server reads through a Python dict and re-types, then un-types for path resolution

**Severity:** Structural (2 of 5)

**Files:**

- `gui/server/main.py:172-204` (`read_settings` → flat dict)
- `gui/server/main.py:382, 403, 425, 453` (`get_output_dir(flat_view)` callers)
- `gui/server/main.py:510-557` (`/api/run` re-types to `Settings`, merges, then `flat_view = typed_settings.to_flat_dict()`)
- `core/pipeline.py:145-213` (`merge_overrides` — typed mutation)
- `core/settings.py:174-179` (`to_flat_dict`)

**Symptom**

Inside the same `/api/run` handler the server runs the same `Settings` representation through three shapes:

```python
# gui/server/main.py:510-557 (abridged)
flat_settings, _ = read_settings()                                # line 510 — flat dict
from core.settings import Settings, _flat_dict_to_nested,
                          settings_from_dict
nested_input = _flat_dict_to_nested(flat_settings)                # line 520 — nested dict
typed_settings: Settings = settings_from_dict(nested_input)       # line 521 — typed Settings

# Apply per-request overrides.
if payload.overrides:
    override_dict = payload.overrides.model_dump(exclude_none=True)
    typed_settings = pipeline_mod.merge_overrides(                  # line 530 — typed merge
        typed_settings, override_dict,
    )

# Resolve paths from the typed settings.                              line 541
root = get_project_root()
input_path = root / ".context" / "inputs" / f"{payload.input}.txt"

# Re-derive the flat view only for code paths (like the legacy
# ``get_output_dir`` helper) that still expect flat dicts.            line 555-557
flat_view = typed_settings.to_flat_dict()
arenas_dir = get_output_dir(flat_view) / "arenas"                  # line 558 — flat dict reused
```

This is "two parallel worlds" anti-pattern: typed internals, untyped edge code, boundary conversions on every call. `get_output_dir` (lines 167-170, used at 382, 403, 425, 453) is hand-rolled:

```python
def get_output_dir(settings: dict[str, object]) -> Path:
    out_dir = get_project_root() / str(settings["output_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir
```

…and reads `settings["output_dir"]` flat-key-style. Any future change that intends to honor `typed_settings.archive.dir` directly will silently produce a different file path because the typed `archive.dir` default and the flat `archive_dir` default can disagree (S5).

**Why it is illogical**

The refactor in `core/settings.py` introduced the typed `Settings` hierarchy to unify the surface. Then half the server code was retro-fitted to use it via a flat-dict adapter (`to_flat_dict`), and the other half kept the flat-dict assumption. The whole pipeline ended up doing three shapes per request.

**Fix**

Either:
- **(a)** Replace `get_output_dir(settings: dict)` with `get_output_dir(settings: Settings)` and pass `typed_settings` consistently. Use `settings.output.dir` directly.
- **(b)** Mark the flat-dict adapters as deprecated and add a runtime assertion that `isinstance(settings, Settings)` in `_save_nested_dict` and `read_settings`/`write_settings`.

Either way, eliminating the dual-shape coexistence is the win.

---

### S3 — `/api/run` payload's `RunOverrides` type has fewer fields than the Pydantic `SettingsUpdate` it models

**Severity:** Structural (3 of 5)

**Files:**

- `gui/browser-extension/src/shared/types.ts:62-69` (`RunOverrides`, 6 keys)
- `gui/browser-extension/src/shared/types.ts:5-17` (`Settings`, 11 keys)
- `gui/browser-extension/src/shared/api.ts:79-83` (`updateSettings: (settings: Partial<Settings>)`)
- `gui/server/main.py:67-84` (`SettingsUpdate`, 11 keys)
- `gui/server/main.py:95-97` (`RunRequest`, uses `SettingsUpdate`)

**Symptom**

The TS `RunOverrides` (the body sent in `POST /api/run`):

```ts
// gui/browser-extension/src/shared/types.ts:62-69
export interface RunOverrides {
  output_dir?: string;
  output_format?: 'md' | 'txt';
  model_count?: number;
  gemini_judge?: boolean;
  compact_mode?: boolean;
  archive?: boolean;
}
```

…has six fields. The server's `SettingsUpdate` (the actual Pydantic model that receives the payload):

```python
# gui/server/main.py:67-84
class SettingsUpdate(BaseModel):
    output_dir: Optional[str] = None
    output_format: Optional[str] = None
    model_count: Optional[int] = None
    gemini_judge: Optional[bool] = None
    compact_mode: Optional[bool] = None
    archive: Optional[bool] = None
    archive_dir: Optional[str] = None                          # ← extra
    paste_attachments_enabled: Optional[bool] = None         # ← extra
    respect_target_arena_directive: Optional[bool] = None     # ← extra
    on_arena_number_conflict: Optional[str] = None            # ← extra
    use_default_ignore: Optional[bool] = None                 # ← extra
```

…has eleven. The TS `Settings` interface also has all eleven; the relationship between `RunOverrides` (subset), `SettingsUpdate` (full), and `Settings` (full response) is **not codified anywhere in the TS layer**. There is no `Partial<Settings>` excluding the run-scoped keys, no `Pick<Settings, K>` over the override subset, no codegen step from Pydantic.

Three orthogonal definitions of "what is in `settings.json`" — same hazard as C3 but at the type layer — cannot coexist safely.

**Fix**

Either:
- **(a) Codegen.** Use `datamodel-code-generator` or `pydantic-to-typescript` to produce `types.ts` from the FastAPI OpenAPI schema. One source, three projections. This catches drifts on every server start.
- **(b) Hand-maintained invariant tests.** Add a `tests/test_types_sync.py` that opens the FastAPI app via `app.openapi()` and asserts every key in `RunOverrides` exists in `SettingsUpdate`'s schema and vice versa for the obvious pairs.

---

### S4 — The CLI's interactive prompts and the GUI runner work on flat-key reads that rebuild the full flat dict per call

**Severity:** Structural (4 of 5)

**Files:**

- `core/settings.py:183-202` (`__getitem__` calls `to_flat_dict()`)
- `core/settings.py:204-209` (`get` → `to_flat_dict()`)
- `core/settings.py:404-412` (`_to_flat_dict`, iterates `_FLAT_TO_NESTED`)
- `aggregator.py:616-622` (CLI resolution of effective settings — 5 `.get` calls)
- `aggregator_gui.py:_aggregate_worker` (more `.get` calls in inner loop; the dead `gui/aggregation_runner.py:189-219, 298, 414` referenced in the original audit is being deleted as part of **D1**)

**Symptom**

The "best-effort compatibility" shim at `core/settings.py:183-209` reads:

```python
def __getitem__(self, key: str) -> object:
    flat = self.to_flat_dict()
    if key in flat:
        return flat[key]
    if hasattr(self, key):
        return getattr(self, key)
    raise KeyError(key)

def get(self, key: str, default: object | None = None) -> object | None:
    try:
        return self[key]
    except KeyError:
        return default
```

`to_flat_dict` is implemented as a table-driven rebuild:

```python
# core/settings.py:404-412
def _to_flat_dict(settings: Settings) -> dict[str, object]:
    flat: dict[str, object] = {}
    for flat_key, (group_name, attr_name) in _FLAT_TO_NESTED.items():
        group = getattr(settings, group_name, None)
        if group is None:
            continue
        flat[flat_key] = getattr(group, attr_name)
    return flat
```

…iterating the entire `_FLAT_TO_NESTED` table (17 entries today, see `core/settings.py:296-315`) on **every read**. So every `settings.get("gemini_judge")` call is O(17); `settings.get("output_format")` is O(17); five such calls per input file in the CLI's `main()` and the GUI runner's `run_aggregation` is 85 table lookups per input. Not slow today; a footgun the moment someone writes a polling loop.

**Why it is illogical**

The shim was added to keep `dict`-style callers working during a transition. The transition is over; the shim is permanent. The cost is real but unmeasured by any benchmark. There's no comment saying "this is the last release using flat keys."

**Fix**

Memoize on the instance:

```python
# core/settings.py — proposed addition
class Settings:
    ...
    def __post_init__(self) -> None:
        # Cache the flat-dict view so the compatibility shims are O(1).
        object.__setattr__(self, "_flat_cache", None)

    def to_flat_dict(self) -> dict[str, object]:
        cache = getattr(self, "_flat_cache", None)
        if cache is None:
            cache = _to_flat_dict(self)
            object.__setattr__(self, "_flat_cache", cache)
        return cache
```

…and invalidate the cache in `merge_overrides` after mutation (`merge_overrides` clones via `copy.deepcopy`, so a new instance gets a fresh `None` cache — that already works for free; need to verify `__post_init__` runs on the deepcopy).

---

### S5 — Server defaults in `DEFAULT_SETTINGS` drift from real dataclass defaults

**Severity:** Structural (5 of 5)

**Files:**

- `gui/server/main.py:112-124` (hand-rolled flat default dict)
- `core/settings.py:418` (`DEFAULT_SETTINGS = _to_flat_dict(Settings())` — the canonical copy)

**Symptom**

The server defines its own flat default dict at `gui/server/main.py:112-124`:

```python
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
```

The canonical copy at `core/settings.py:418`:

```python
DEFAULT_SETTINGS: dict[str, object] = _to_flat_dict(Settings())
```

…is automatically derived from the dataclass. The two will agree only as long as no one changes a default in `Settings` (`core/settings.py:59-147`) without manually updating the server's copy. The first time someone changes — say — `paste_attachments.target_subdir` from `"tmp/paste-attachments"` to `"uploads"`, the CLI defaults will disagree with the server's defaults, no error will surface, and the user will see stale defaults in the extension UI for the variable that nobody updated in two places.

**Why it is illogical**

The Python module-level import at `gui/server/main.py:35-49` (top of file) doesn't import `core.settings.DEFAULT_SETTINGS` because the file is already mid-handcrafting its own defaults. Anyone editing settings doesn't realize there are two copies to update.

**Fix**

Single source of truth: import and forward-declare:

```python
# gui/server/main.py — proposed replacement
from core.settings import DEFAULT_SETTINGS as _DEFAULTS

# Make sure it's a fresh dict (not the module global from core.settings
# which other tests may mutate).
DEFAULT_SETTINGS: dict[str, object] = dict(_DEFAULTS)
```

…or better, as part of the same fix as C3, kill `gui/server/main.py`'s `DEFAULT_SETTINGS` and `read_settings`/`write_settings` entirely and call `core.settings.load_settings` / `save_settings` directly.

---

## UX FLAW Findings

### U1 — Settings save race: `PUT /api/settings` reads-merge-writes; concurrent requests clobber

**Severity:** UX Flaw (1 of 5)

**Files:**

- `gui/server/main.py:254-261` (`update_settings` handler)
- `gui/server/main.py:172-204` (`read_settings`)
- `gui/server/main.py:206-210` (`write_settings`)
- `gui/server/main.py:293-303` (`update_ignore` handler — same pattern)

**Symptom**

```python
# gui/server/main.py:254-261
@app.put("/api/settings")
async def update_settings(
    payload: SettingsUpdate, token: str = Depends(get_current_token)
):
    current, _ = read_settings()                                # full read from disk
    current.update(payload.model_dump(exclude_none=True))       # merge in-memory
    write_settings(current)                                     # full overwrite
```

The popup's `SettingsPanel.handleUpdate` (`SettingsPanel.tsx:40-49`) saves after every checkbox change. Two rapid toggles from the user produce two concurrent `PUT`s. Classic lost-update race:

1. Request A reads file with `gemini_judge=false, compact_mode=false`.
2. Request B reads file with `gemini_judge=false, compact_mode=false`.
3. Request A's payload is `{gemini_judge: true}`. A.merges, A.writes: `gemini_judge=true, compact_mode=false`.
4. Request B's payload is `{compact_mode: true}`. B.merges, B.writes: `gemini_judge=false, compact_mode=true`.

The user's "first toggle won, second lost" outcome is silent. Same hazard exists for `update_ignore` (`gui/server/main.py:293-303`).

**Why it is illogical**

No per-key compare-and-set, no file lock, no versioning. Asynchronous Python on a single-threaded event loop doesn't *guarantee* serial `await` hand-offs between awaits — between `await read_settings()` and `await write_settings(...)`, another `async def` can run on the loop.

**Fix**

Pick one:

- **Lock.** Hold an `asyncio.Lock` around the read-merge-write; trivially correct, trivial overhead.
- **Atomic PATCH.** Send per-key updates with a version stamp; reject writes that don't match the current version.
- **In-memory source of truth.** Cache the `Settings` instance per request and only re-persist from the cache. Simpler if there's a single writer — the popup is essentially single-writer in practice (one user), but the TS panel issues every change as a fire-and-forget `PUT`.

---

### U2 — Pipeline emits progress events before the WS client has had a chance to connect

**Severity:** UX Flaw (2 of 5)

**Files:**

- `gui/server/main.py:582-597` (run is `asyncio.create_task`; HTTP response returns immediately)
- `gui/server/ws.py:45-66` (`send_event` silently drops when no connection)
- `core/pipeline.py:325-393` (events emitted back-to-back starting at `pct=0.02`)

**Symptom**

`/api/run` returns immediately at `gui/server/main.py:592-597` while the work is scheduled as `asyncio.create_task(...)` at line 582. The first progress emission lands at `core/pipeline.py:325` (`"init", 0.02`). For a popup to receive progress, it must:

1. Receive `{run_id, ...}` from the HTTP response.
2. Match `run_id` to a yet-to-be-triggered UI flow (state machine in the popup, currently not implemented).
3. Open `new WebSocket("/ws/run/{run_id}")` from the service-worker context (Chromium MV3 requires `host_permissions` for WS too, see `manifest.json:15-18`).
4. Complete the WebSocket upgrade handshake.

In practice this takes 50–500 ms after the HTTP response is in hand. The pipeline's `aggregate` stage emits `aggregate:1/N`, `aggregate:2/N`, … events back-to-back at `core/pipeline.py:411-416` (typically 5–20 ms apart for small files, up to several seconds apart for huge ones). All those events hit `manager.send_event` with no registered connection → `gui/server/ws.py:50-55` returns silently.

The popup eventually subscribes and sees only what the pipeline hasn't yet emitted — typically a `done`/`error` event after the work has already finished, **if** it's still listening.

**Why it is illogical**

The contract documented in code (`/api/run` returns `run_id` so the client *can* connect) reads as "the server emits, the client listens, the stream is end-to-end." The runtime sequence is HTTP-then-WS, which by definition races with the work.

**Fix**

Two practical options:

- **(a) Pre-connect.** Have the popup generate a `run_id` client-side (UUID v4) and POST `/api/run` with `{input, overrides, client_run_id}`. Open the WS to `/ws/run/{client_run_id}` *before* the POST. The server uses the client-supplied id. This makes the connection deterministically ready before the first event.
- **(b) Buffered server replay.** Have the server keep a per-`run_id` event buffer (say, 200 events or the first 5 seconds). When the WS connects, replay the buffer before switching to live. Requires the WS endpoint to look up `run_id`s that haven't necessarily started yet. Simple implementation: keep `dict[str, list[tuple]]` of recent events; flush on connect; cap with `collections.deque(maxlen=200)`.

Either is straightforward. The current contract needs an explicit fix because it relies on a timing coincidence.

---

### U3 — DOM selectors ride on Tailwind utilities; content script has no fallback for LMArena redesigns

**Severity:** UX Flaw (3 of 5)

**Files:**

- `gui/browser-extension/src/content/lmarena.ts:10-18` (selector table)
- `gui/browser-extension/src/content/lmarena.ts:167-184` (`MutationObserver` watcher)
- `gui/browser-extension/src/content/lmarena.ts:104-118` (`sendCapture` and the toast UI)

**Symptom**

The selectors at `gui/browser-extension/src/content/lmarena.ts:10-18`:

```ts
const SELECTORS = {
    carousel: '[role="region"][aria-roledescription="carousel"]',
    slide: '[role="group"][aria-roledescription="slide"]',
    slideHeaderName: ':scope > div:first-child span.truncate',
    slideResponseBody: 'div.prose',
    slideToolbar:
        'div.flex.items-center.justify-between.gap-2 > div.flex.items-center.gap-1',
    userBubbleProse: '.self-end .prose',
} as const;
```

The doc-comment claims selectors prefer ARIA anchors because "Tailwind utility classes are the part most likely to change on redesign." In practice four of the six selectors ride on Tailwind utilities:

- `div.flex.items-center.justify-between.gap-2 > div.flex.items-center.gap-1`
- `div.prose` (Tailwind `@tailwindcss/typography`)
- `span.truncate` (Tailwind utility)
- `.self-end .prose` (Tailwind utilities + typography plugin class)

The watcher runs on a 400 ms debounced `MutationObserver` (`gui/browser-extension/src/content/lmarena.ts:178-182`):

```ts
new MutationObserver(() => {
    window.clearTimeout(debounceTimer);
    debounceTimer = window.setTimeout(attachButtons, 400);
}).observe(document.body, { childList: true, subtree: true });
```

…and `attachButtons` (`lmarena.ts:167-172`) silently no-ops when the slide is missing the markers. There is no "I couldn't find the carousel" toast; the user sees their injected "Send to Context" buttons fail to appear after a redesign and has no actionable signal.

**Why it is illogical**

The fallback story is implicit "I'll come back and fix this when LMArena redesigns." That fallback runs in production at the worst time — when the user is mid-comparison, the extension stops working, and they have no diagnostic surface.

**Fix**

- Add `try/catch` around `attachButtons` and a one-shot toast on first failure: `flashToast("Context extension: LMArena markup may have changed — see console", true)`.
- Log the failing selector and the candidate DOM subtree to `console.error` so developers reading DevTools can file a useful bug.
- Consider a `MutationObserver` summary that fires once per minute if zero slides have been matched, instead of forever polling.
- Periodically verify selectors against a known list of LMArena deployments (CI snapshot test against a recorded DOM).

---

### U4 — `Settings.__getitem__` rebuilds the full flat dict on every key access

**Severity:** UX Flaw (4 of 5)

**Files:** `core/settings.py:183-209`

Same root cause as S4 (rebuilt every `.get`/`.[]`). The user-facing manifestation: any third-party consumer (or future feature) that does attribute polling will degrade silently. The interface encourages the bad pattern by making it look cheap.

**Fix**

See S4 — memoize `to_flat_dict()` on the instance, or commit to typed-only access by removing `__getitem__` and `get` and migrating every consumer (which would include C2 + the CLI).

---

### U5 — CORS `allow_origins=["*"]` + missing WS auth = attack surface expansion

**Severity:** UX Flaw (5 of 5)

**Files:**

- `gui/server/main.py:145-151` (CORS middleware: `allow_origins=["*"]`)
- `gui/server/ws.py:72-87` (no auth)
- `gui/browser-extension/manifest.json:15-18` (`host_permissions: ["http://127.0.0.1:8765/*"]`, **no WS permissions**)

**Symptom**

The HTTP server applies `allow_origins=["*"]` (line 147) with the comment "safe-ish here because loopback middleware rejects non-local clients, but production should pin the extension ID." The WS server has no such defense. The manifest doesn't request the WebSocket permission either — meaning **a future WebSocket client added without updating the manifest will silently fail cross-origin too**, masking the real auth gap with a different error.

Combined with C4, this is the soft underbelly.

**Fix**

Same as C4 (auth on WS) plus:

- Add `ws://127.0.0.1:8765/*` to `host_permissions` in `manifest.json` (if a WS client is in scope).
- Document that `allow_origins=["*"]` is a deferred debt; the loopback middleware is the only barrier today.

---

## Verification: what is NOT broken

For completeness, I verified the following surfaces and found no disconnect:

### CLI ↔ core pipeline parity

The CLI's `aggregator.py:main` and the Tk GUI runner `aggregator_gui.py:_aggregate_worker` (lines 1127-1404) both drive the same underlying `aggregate_files`, `count_tokens`, `collect_model_responses`, `build_compare_markdown`, `generate_compare_template`, `archive_model_responses`. They both resolve settings via `load_settings`, run migrations before initialization, build the same target-arena plan, share the cancel-requested pattern. **No path-shape mismatch at the file-write layer; both produce v3-prefixed flat layouts under the same `output_dir`.** *(Updated 2026-07-10: the original "duplication is plain text, not semantic drift" framing is now **superseded by C5** above — the four-orchestrator split has behavioural differences in the server's path; the CLI and the live GUI runner still agree on file-write parity, but the server's `core/pipeline.py` does not.)*

### `get_output_dir` output-path question (Q2)

The server's `main.py:558` resolves `out_dir = get_output_dir(flat_view)` and writes arenas to `out_dir/arenas/NNN-NAME`. The CLI writes to `resolve_output_dir(...)` (`core/parser.py:188`, re-export of `core.arena.resolve_output_dir`). Both feed the same on-disk location keyed off `settings.output_dir`. **No conflict in defaults** — when `settings.output_dir` is `"context_output"` (default) both write to `context_output/arenas/`. Conflict would surface only if Settings persistence is broken (which it is — C3), at which point the two sides disagree on which key to honor because the file itself is degraded.

### Async event ordering inside a single run

`pipeline_mod.make_async_bridge` uses `asyncio.run_coroutine_threadsafe` to schedule WS sends back on the FastAPI loop (`core/pipeline.py:117-126`). The bridge is correct: each progress callback launches a coroutine on the loop; the loop drains them in FIFO order at its next iteration. No race within a single thread. The race users might worry about (concurrent runs) holds because the loop is single-threaded and `WebSocket.send_json` is awaited; multiple `run_id`s can have active connections in parallel without interference. The only real race is U2 (events emitted before the client connects).

### Loopback middleware for HTTP

`main.py:155-158` + `security.py:49-68` correctly rejects non-loopback HTTP. The whitelist includes `testclient` because the TestClient attaches that host — reasonable for in-process tests, and because the loopback middleware runs **before** route dispatch, requests from any non-listed host 403 with no leak of route internals.

### `archived_model_responses` triggers in both CLI and GUI

The CLI runs `archive_model_responses(arena_dir, archive_dir)` after `_process_one` (`aggregator.py:775-783`). The GUI runner does the same after `build_compare_markdown` (`aggregator_gui.py:_aggregate_worker` near `build_compare_markdown`; the dead `gui/aggregation_runner.py:411-422` referenced in the original audit is being deleted as part of **D1**). Both pass `archive_dir = str(settings.get("archive_dir", "ARCHIVE"))` (the GUI; `aggregator.py:623`). Same default, same fallback chain.

---

## Summary Table

| ID | Severity | Component | One-line |
| --- | --- | --- | --- |
| **C1** | Critical | Extension ↔ Server | Popup has no Run button; `/api/run` and `/ws/run/{id}` are dead. |
| **C2** | Critical | Tk GUI settings | `self._settings["k"] = v` raises `TypeError`; toggles never persist. *(live location: `aggregator_gui.py:364-374`)* |
| **C3** | Critical | Server settings I/O | Server reads/writes flat while CLI writes nested → silent corruption. |
| **C4** | Critical | WS auth | `/ws/run/{id}` has neither loopback enforcement nor bearer-token check. *(deferred — see §4.4 of the corrigendum)* |
| **C5** | Critical | Pipeline duplication | 4× independent orchestrators; new features require coordinated edits in 4 places. *(see `docs/AUDIT_corrigendum_2026-07-10.md` §1 M7)* |
| **C6** | Critical | Server bypasses CLI validations | 7 validations present in the CLI are skipped by `core/pipeline.py`; same input produces different output between CLI and server. *(see `docs/AUDIT_corrigendum_2026-07-10.md` §1 M8)* |
| **S1** | Structural | `.env` precedence | `get_gemini_key` (tool root) ≠ `judge.get_api_key` (3-tier cascade). |
| **S2** | Structural | Settings shape duality | Same handler reads flat, merges typed, then writes flat. |
| **S3** | Structural | API/TS schema drift | `RunOverrides` has 6 keys, `SettingsUpdate` has 11 — TS isn't generated. |
| **S4** | Structural | Settings shim cost | `.get(k)` rebuilds flat dict on every call; called from the inner loop. |
| **S5** | Structural | Default-table drift | `DEFAULT_SETTINGS` copy in server diverges from dataclass-derived defaults. |
| **U1** | UX | Concurrent update | Read-modify-write race on `/api/settings` + `/api/ignore`. |
| **U2** | UX | WS race | First progress events fire before popup can connect → all silently dropped. |
| **U3** | UX | Extraction fragility | 4/6 selectors on Tailwind utilities; no "I couldn't find carousel" toast. |
| **U4** | UX | Shim hot-path | `__getitem__` rebuilds `_FLAT_TO_NESTED` on every read; no memoization. |
| **U5** | UX | CORS/WS overlap | `allow_origins=["*"]` + WS no-auth is the soft underbelly for C4. |
| **D1** | Tech debt | Decomposed `gui/` package | ~2,400 lines across 10 modules; zero inbound imports from any runtime entry point. Recommendation: `git rm` (in progress as of 2026-07-10). *(see `docs/AUDIT_corrigendum_2026-07-10.md` §1 D1)* |

---

## Recommended Remediation Roadmap

The fixes cluster into five natural milestones (M1–M4 below plus the new M5 for C5/C6 consolidation). **D1 is being addressed immediately** as part of the 2026-07-10 cleanup PR — see the dead-code purge steps accompanying this audit.

### Milestone 1 — Unify settings I/O (closes C2, C3, S2, S4, S5)

Scope: `core/settings.py`, `gui/server/main.py`, `aggregator_gui.py` *(was `gui/app.py`; the file:line references in this milestone were retargeted in the 2026-07-10 corrigendum — the bug is identical, the path is live)*. Effort: ~1–2 days.

1. Promote `core.settings.DEFAULT_SETTINGS` to the single source of truth. Replace `gui/server/main.py:112-124` with `DEFAULT_SETTINGS: dict[str, object] = dict(_to_flat_dict(Settings()))` (or just stop using flat defaults on the server entirely).
2. Replace `gui/server/main.py:172-210` (`read_settings`, `write_settings`) with thin wrappers over `core.settings.load_settings` / `save_settings`. Surface the typed shape to callers; mark the dict-style helpers `@deprecated`.
3. In `aggregator_gui.py:359-379`, change `_save_current_settings` to assign through the typed attributes (`settings.judge.enabled = …`, etc.). Retype the surrounding `self._settings` annotation to `Settings`.
4. Memoize `Settings.to_flat_dict()` (or remove the shim).

Outcome: the server's settings path becomes correct by construction; the Tk GUI starts persisting; the migration debt is paid down in one PR.

### Milestone 2 — Wire or wire-and-delete the run path (closes C1, U2)

Scope: `gui/browser-extension/src/popup/**`, `gui/server/main.py`, `gui/server/ws.py`. Effort: 1–2 days for the wire-up; half a day to delete.

Decision point: are we shipping Run from the popup in this milestone?

- **Yes:** Add a `RunPanel` to `App.tsx`. Pre-connect to WS with a client-generated `run_id` (or implement U2's buffered server replay — preferred since it's a smaller API change). Update `manifest.json` to add the WS host permission.
- **No:** Delete `/api/run`, `/api/run/check`, `_execute_typed_run`, `core/pipeline.py`, `gui/server/ws.py`, and the now-orphaned tests. Keep the run button offline, mention in `README` that runs are still CLI-only (`python aggregator.py`).

### Milestone 3 — WS auth + CORS pinning (closes C4, U5)  *(deferred per corrigendum §4.4)*

**Defer.** Per `docs/AUDIT_corrigendum_2026-07-10.md` §4.4: WS is unreachable today (see C1); fix it before any client reaches for it, not before. Land **after** M1, M2, and M5 are in. The audit's original ordering placed M3 between M2 and M4; the corrigendum reorders it to the back of the queue. Scope and fix details below for when it does land.

Scope: `gui/server/security.py`, `gui/server/ws.py`, `gui/server/main.py`, `manifest.json`. Effort: half a day.

1. Add bearer-token verification to `websocket_endpoint` (token via `?token=` query param or `Sec-WebSocket-Protocol`). Add loopback host check.
2. Replace `allow_origins=["*"]` with the production-acceptable surface (the extension's stable origin id once known; fall back to `null` + bearer-only if the extension origin is not enumerable server-side).
3. Add `ws://127.0.0.1:8765/*` to `host_permissions` if the WS client is in scope.

### Milestone 4 — Polish (closes U1, U3, leaves U4 closed by M1)

Scope: `gui/server/main.py:206-261, 293-303`, `gui/browser-extension/src/content/lmarena.ts:104-184`. Effort: half a day.

1. Wrap `read_settings`/`write_settings` in an `asyncio.Lock` to close U1.
2. Add a "couldn't find the carousel" diagnostic toast to `flashToast` and `attachButtons`. Add periodic selector-health logging.
3. (If U4 isn't closed by Milestone 1's memoization, do it here.)

### Milestone 5 — Consolidate pipeline orchestrators (closes C5, C6)  *(new in 2026-07-10)*

Scope: `aggregator.py:_process_one`, `aggregator_gui.py:_aggregate_worker`, `core/pipeline.py:run_pipeline`. Effort: 1–2 days.

1. Promote `core/pipeline.py:run_pipeline` to be the single canonical orchestrator. Move all seven CLI validations (ignore patterns, arena-directive resolution, structure-drift detection, post-run directive report, `write_state_breadcrumb`, `sync_paste_attachments`, legacy migrations) into it — or into `preflight`/`postflight` steps it calls.
2. Have the CLI call `run_pipeline` through a thin wrapper that translates progress callbacks to stdout.
3. Have the live GUI call `run_pipeline` through a thin wrapper that translates callbacks to `_log_write()`.
4. Delete the dead twin `gui/aggregation_runner.py:run_aggregation` as part of the **D1** purge.

Outcome: 4× → 1× orchestrator, the seven missing validations are restored in the server path, and any future feature lands in one place.

---

## Appendix A — Evidence Index

The following reads informed the report above:

| File | Lines read |
| --- | --- |
| `gui/server/main.py` | full (1-682) |
| `gui/server/security.py` | full (1-86) |
| `gui/server/ws.py` | full (1-87) |
| `gui/server/launcher.py` | full (1-105) |
| `core/pipeline.py` | full (1-583) |
| `core/settings.py` | full (1-1039) |
| `core/judge.py` | 1-150 |
| `core/parser.py` | 1-120 |
| `aggregator.py` | full (1-847) |
| `aggregator_gui.py` | full (1-1,513) — *live Tk GUI; the C2 `__setitem__` bug lives here, not in the dead `gui/app.py`* |
| `gui/browser-extension/src/popup/App.tsx` | full |
| `gui/browser-extension/src/popup/components/{ServerStatus,SettingsPanel,InputManager,EnvSetup,PairDialog}.tsx` | full |
| `gui/browser-extension/src/popup/main.tsx` | full |
| `gui/browser-extension/src/popup/index.html` | full |
| `gui/browser-extension/src/shared/{api,types}.ts` | full |
| `gui/browser-extension/src/background/service-worker.ts` | full |
| `gui/browser-extension/src/content/lmarena.ts` | full |
| `gui/browser-extension/manifest.json` | full |
| `tests/test_ws.py` | full |
| `tests/test_browser_extension_dist.py` | searched (`/api/run` references) |

The original C2 finding read `gui/app.py` (570 lines), `gui/aggregation_runner.py` (466 lines), and `gui/api_key_dialog.py` (183 lines) — the decomposed (now-confirmed-dead) `gui/` package. After the 2026-07-10 retarget, those reads are subsumed by the `aggregator_gui.py` read; the decomposed `gui/` modules are being deleted as part of the **D1** purge (`git rm gui/app.py gui/scanner.py gui/queue_manager.py gui/builders.py gui/aggregation_runner.py gui/log_panel.py gui/api_key_dialog.py gui/theme.py gui/paths.py gui/util.py`).

## Appendix B — Glossary

- **Dataclass refactor** — `commit 57608f1` ("fix: resolve ruff lint errors blocking CI") followed by `d9fcd3a` ("feat: release v2.6.0 — async pipeline, ws streaming, gui decomposition, tests"). These two commits together introduced the nested `Settings` hierarchy in `core/settings.py`, extracted `core/pipeline.py` from a server stub, and rewired the browser-extension server around typed settings.
- **v3 flat arena layout** — every file inside an arena directory is prefixed with the arena's `NNN-` (e.g. `003-context.md`, `003-A.txt`). Older prefixes are absent; `migrate_to_flat_layout` brings legacy outputs forward.
- **`run_id`** — UUID v4 generated server-side per `/api/run`. Returned in the response body; consumed by `/ws/run/{run_id}`.
- **Loopback middleware** — FastAPI HTTP middleware (`@app.middleware("http")`) registered on the app and dispatching every HTTP request through `enforce_loopback` before routing. **Does not apply to WebSocket routes** in Starlette — this is a real FastAPI gotcha that the audit traces through.
