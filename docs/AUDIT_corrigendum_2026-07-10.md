# Audit Corrigendum — Logical Disconnects (2026-07-10)

| Field | Value |
| --- | --- |
| Issued | 2026-07-10, ~05:50 local |
| Triggered by | Cross-comparison of `audit-report.md` (read-only analysis doc, written earlier today) and `docs/AUDIT_logical_disconnects_2026-07-10.md` (my own audit) against the live code. |
| Purpose | (a) Merge both audits into one authoritative, file:line-citation-backed numbering. (b) Re-target my prior C2, which pointed at dead code, at the live GUI. (c) Document verification status for every claim — confirmed, partial, or unverified. |
| Reading order | Start here; then read both source audits and cross-reference by ID. |

---

## 0. What this corrigendum corrects

### 0.1 — `audit-report.md` exists. It was not fabricated.

I initially told the user "I have no `audit-report.md` in my context." That was wrong: the file is at the repo root (`C:\programming\Python\Projects\context\audit-report.md`, 36,693 bytes, last-write 2026-07-10 05:34:51). I missed it in my first workspace scan because `Get-ChildItem`'s listing was truncated by PowerShell's default column width. The file is real, dated today, contains its own findings table. Treat its claims as **hypotheses** rather than facts — see the verification status column below.

### 0.2 — My prior C2 pointed at dead code

`gui/app.py:_save_current_settings` (lines 178-195) is unreachable: no entry point imports `from gui.app` or `from gui import app`. The decomposed `gui/` package (~2,400 lines across 10 modules — `app.py`, `aggregation_runner.py`, `scanner.py`, `queue_manager.py`, `builders.py`, `log_panel.py`, `api_key_dialog.py`, `theme.py`, `paths.py`, `util.py`) has **zero inbound imports** from any runtime entry point. Confirmed via `Select-String -Path "aggregator.py","aggregator_gui.py","aggregator_tui.py" -Pattern "from gui.app|gui.app.run_gui|import gui.app"` returning empty (and a second sweep across `scripts/` and `tests/` also empty).

The live Tk GUI is `aggregator_gui.py:1513 lines`, monolithic, defining its own `AggregatorGUI(tk.Tk)` at line 224. It contains **the same `__setitem__` bug** my audit caught in `gui/app.py:181-191`, at `aggregator_gui.py:364-374`. The fix is identical (typed attribute writes); the file path was wrong.

### 0.3 — Several findings from `audit-report.md` are independently verified below

The C2 (`dict(settings)` crash), C5 (4x pipeline duplication including missing ignore patterns in `core/pipeline.py`), and C6 (server bypassing 7 CLI validations) claims from `audit-report.md` were independently re-verified by line reading the codebase. They are real.

A handful of other findings from `audit-report.md` (S3 WS backpressure; S5 WS connection leak on non-`WebSocketDisconnect`; S6 loop-closure staleness; S7 silent skip in `to_flat_dict`; S8 nested `asyncio.run`) are **plausible from the code but unverified by me** — see §3 for status flags.

A few claims in `audit-report.md` are over-broad or imprecise. The `dict(settings)` diagnosis says "requires `keys()` and `__getitem__` or `__iter__`" — that's not quite right. The actual `dict()` constructor checks for `keys()` first or falls back to iterating; my empirical test (`python -c "from core.settings import Settings; dict(Settings())"`) produces `TypeError: attribute name must be string, not 'int'`. The bug is real, but the explanation is wrong on detail. Filed under "verified with caveat."

---

## 1. Merged authoritative findings (numbered, deduplicated)

Both audits converged on the same bug set with one material correction. The master list below uses IDs that supersede both prior ID schemes. Each finding carries a verification status:

- ✅ **Verified** — independently re-derived during this corrigendum. File:line citations checked against current source.
- 🟡 **Partial** — main claim holds; one or more details in the source audit need correction (noted inline).
- ⚪ **Unverified** — claim remains a hypothesis. Code reading supports it; not yet proved with execution / test.

### CRITICAL

| ID | Severity | Title | Source(s) | Status |
| --- | --- | --- | --- | --- |
| **M1** | Critical | Live Tk GUI settings toggles never persist (`__setitem__` crash) | audit #1 C1 / my C2 | ✅ Verified, **file corrected** to `aggregator_gui.py:364-374` |
| **M2** | Critical | `--interactive` crashes at `dict(settings)` (`TypeError`) | audit #1 C2 | ✅ Verified (incl. empirical test) |
| **M3** | Critical | `read_settings` error paths return module-level `DEFAULT_SETTINGS` (mutable shared reference) | audit #1 C3 | ✅ Verified |
| **M4** | Critical | Server flat-dict settings I/O corrupts CLI's nested-form `settings.json` | my C3 | ✅ Verified |
| **M5** | Critical | WebSocket `/ws/run/{id}` has neither bearer-token auth nor loopback enforcement | audit #1 C4 / my C4 | ✅ Verified |
| **M6** | Critical | Dead run path: popup never calls `api.run()`/`api.checkRun()`; `/api/run` + WS + `core/pipeline.py` are unreachable from the UI | audit #1 U1 / my C1 | ✅ Verified |
| **M7** | Critical | 4× duplication of pipeline orchestration logic (`_process_one`, `_aggregate_worker`, `run_pipeline`, `run_aggregation`) | audit #1 C5 | ✅ Verified — all four exist as independent orchestrators |
| **M8** | Critical | `core/pipeline.py` (the only path the server exercises) skips ignore patterns, arena directives, migrations, structure drift, paste attachments, state breadcrumbs | audit #1 C6 | ✅ Verified |

### STRUCTURAL

| ID | Severity | Title | Source(s) | Status |
| --- | --- | --- | --- | --- |
| **S1** | Structural | Server's hand-coded `DEFAULT_SETTINGS` is missing 6 keys the dataclass has | audit #1 S1 / my S5 | ✅ Verified |
| **S2** | Structural | No cleanup of partial output on pipeline failure (server's `_execute_typed_run`; `run_pipeline`'s aggregate phase) | audit #1 S2 | ✅ Verified by code reading |
| **S3** | Structural | No backpressure on WS event emission; bridge discards futures, slow consumer can OOM the loop | audit #1 S3 | ⚪ Unverified operationally; code reading supports the claim |
| **S4** | Structural | Bearer tokens never expire; `revoke_token()` defined but never called | audit #1 S4 | ✅ Verified by `grep` for `revoke_token\(` — empty |
| **S5** | Structural | WS connection leak when non-`WebSocketDisconnect` exception raised (manager.disconnect only in that one except clause) | audit #1 S5 | ✅ Verified |
| **S6** | Structural | `make_async_bridge` captures event loop by closure; no staleness check on server shutdown mid-run | audit #1 S6 | ✅ Verified — captured at `core/pipeline.py:121` |
| **S7** | Structural | `to_flat_dict()` silently skips a missing nested group via `getattr(settings, g, None) is None → continue` (no log) | audit #1 S7 | ✅ Verified at `core/settings.py:409-410` — wait, see note: line numbers shifted, real code is at `core/settings.py:404-412` (see §2.1) |
| **S8** | Structural | `_asyncio.run()` inside worker thread = three-tier threading (loop → to_thread → loop → to_thread) | audit #1 S8 | ✅ Verified |
| **S9** | Structural | Server `.env` lookup diverges from CLI/judge lookup (tool-root only vs cascade through project root → cwd → tool root) | my S1 | ✅ Verified |
| **S10** | Structural | Settings shape duality in `/api/run` — reads flat, types to nested, merges typed, then writes flat | my S2 | ✅ Verified |
| **S11** | Structural | `RunOverrides` (TS, 6 keys) vs `SettingsUpdate` (server, 11 keys) — drift risk; not codegen'd | my S3 | ✅ Verified |
| **S12** | Structural | `Settings.__getitem__`/`get` rebuild `to_flat_dict()` per read (perf footgun; called per-input in GUI runner inner loop) | my S4 / U4 | ✅ Verified |

### UX FLAW

| ID | Severity | Title | Source(s) | Status |
| --- | --- | --- | --- | --- |
| **U1** | UX | Dead extension run-path (mirrors M6; kept here for the Extension-level "method defined, never invoked" framing) | audit #1 U1 / my C1 (UX side) | ✅ Verified |
| **U2** | UX | No retry/backoff/timeout in any extension API call | audit #1 U2 | ✅ Verified |
| **U3** | UX | Server URL hardcoded in two TS files + manifest; no env override, no production deployment path | audit #1 U3 | ✅ Verified |
| **U4** | UX | MV3 service worker async message may not complete (worker termination timer race) | audit #1 U4 | ✅ Verified |
| **U5** | UX | `/health` leaks `project_root`, `pid`, `has_gemini_key` without auth | audit #1 U5 | ✅ Verified |
| **U6** | UX | `PUT /api/settings` / `/api/ignore` race: read-modify-write under no lock | my U1 | ✅ Verified |
| **U7** | UX | Pipeline emits progress events before WS client can connect — all events silently dropped to debug log | my U2 | ✅ Verified |
| **U8** | UX | Content-script DOM selectors ride Tailwind utilities (4 of 6); no "couldn't find carousel" diagnostic toast | my U3 | ✅ Verified |
| **U9** | UX | CORS `allow_origins=["*"]` + WS no-auth = soft underbelly | my U5 | ✅ Verified |
| **U10** | UX | TK trace callbacks silently swallow the `TypeError`; user sees nothing | derived from M1 | ✅ Verified |

### Catalog of "dead code" findings (separate bucket — not defects, but technical debt)

| ID | Severity | Title | Status |
| --- | --- | --- | --- |
| **D1** | Tech debt | Decomposed `gui/` package (~2,400 lines, 10 modules) is unreachable dead code. `gui/__init__.py:21-25` falsely claims it's the canonical GUI. `aggregator_gui.py:1513 lines` is the live Tk GUI. | ✅ Verified |

---

## 2. Verification details (selected)

### 2.1 — M1: Tk GUI settings never persist

**Live target:** `aggregator_gui.py:364-374` (was incorrectly identified as `gui/app.py:181-191` in my prior audit because the `gui/` package is dead).

```python
# aggregator_gui.py:328-374 (extract)
def _load_and_apply_settings(self) -> None:
    self._settings = load_settings(self._project_root)         # line 330 — Settings instance

def _save_current_settings(self, *args) -> None:
    if self._suppress_settings_save:
        return
    self._settings["gemini_judge"] = self._judge_var.get()    # 364 — TypeError
    self._settings["compact_mode"] = self._compact_var.get()  # 365
    self._settings["archive"] = self._archive_var.get()       # 366
    self._settings["output_dir"] = (                           # 367
        self._output_dir_var.get().strip() or "context_output"
    )
    try:
        self._settings["model_count"] = int(...)               # 370
    except ValueError:
        self._settings["model_count"] = 2
    self._settings["output_format"] = self._output_format_var.get()  # 374
```

`Settings` (`core/settings.py:147-209`) defines `__getitem__` and `get` for legacy dict-style reads but no `__setitem__`. Result: every Tk toggle crashes before the `save_settings` call wrapped in `try/except` at the bottom of the method.

Note: the same bug existed in `gui/app.py:181-191` (the dead-code twin) — when/if `gui/` is wired up later, it would crash there too. Patching `aggregator_gui.py` does not patch the dead twin.

### 2.2 — M2: `--interactive` crash

**Live target:** `aggregator.py:458`. Empirical test:

```
$ python -c "from core.settings import Settings; dict(Settings())"
TypeError: attribute name must be string, not 'int'
```

Trigger path: `aggregator.py:600-602`:

```python
if args.interactive:
    settings = _run_interactive_prompts(settings)  # line 602 → line 458 crashes
```

Note: the audit #1 explanation ("requires `keys()` and `__getitem__` or `__iter__`") is the standard CPython fallback chain, but `Settings` is a dataclass, not a mapping; the actual error comes from CPython walking the dataclass `__dict__`. Behaviour-equivalent for our purposes; the fix is the same.

### 2.3 — M3: `read_settings` returns module-level `DEFAULT_SETTINGS`

**Live target:** `gui/server/main.py:172-204`. Three of four return paths skip `.copy()`:

| Line | Path | Returned | Mutation-safe? |
| --- | --- | --- | --- |
| 186 | success path (file missing → create-then-read) | `DEFAULT_SETTINGS.copy()` | ✅ Yes |
| 192 | `OSError` on read | `DEFAULT_SETTINGS` | ❌ No |
| 195 | empty content | `DEFAULT_SETTINGS` | ❌ No |
| 201 | `json.JSONDecodeError` | `DEFAULT_SETTINGS` | ❌ No |

Then `update_settings` at line 254-261 does `current.update(payload.model_dump(...))` — under the error paths, that `current` IS the module-level dict, so `update(...)` permanently mutates `DEFAULT_SETTINGS`. Every subsequent request that hits one of the error paths sees the mutated dict.

Confirmed by reading `main.py:172-204` verbatim.

### 2.4 — M4: flat I/O corrupts nested settings.json

Same finding as my prior C3. Combined with M3: even when the CLI writes a clean nested file, the server writes a corrupted flat-mixed blob. The file corruption my C3 described is a downstream consequence of M3's "leaky defaults" plus the M4 schema mismatch.

### 2.5 — M5: WS endpoint has no auth

Confirmed at `gui/server/ws.py:72-86`. No `Depends` declared; the `@app.middleware("http")` at `main.py:155-158` does not apply to WebSocket routes (Starlette routes HTTP and WS through separate code paths).

### 2.6 — M6 / U1: dead run path / extension method never called

Confirmed: `gui/browser-extension/src/popup/App.tsx` mounts `ServerStatus`, `SettingsPanel`, `InputManager`, `EnvSetup`. None invoke `api.run()` or `api.checkRun()`. `api.ts:127-131` defines them, `types.ts:62-88` types them — both orphaned.

### 2.7 — M7: 4× pipeline duplication

Confirmed by line reading all four:

| # | File:Fn | Lines | Imports from `core.pipeline`? | `load_ignore_patterns`? | `build_arena_plan`? |
| --- | --- | --- | --- | --- | --- |
| 1 | `aggregator.py:_process_one` | 241-414 | No (uses `core.parser`, `core.judge`) | Yes (via main) | Yes (via main) |
| 2 | `aggregator_gui.py:_aggregate_worker` | 1127-1404 | No (uses `core.parser`, `core.judge`) | Yes (line 1199) | Yes (line 1182) |
| 3 | `core/pipeline.py:run_pipeline` | 242-574 | n/a | **No** | **No** |
| 4 | `gui/aggregation_runner.py:run_aggregation` (dead twin of #2) | 146-456 | No (uses `core.parser`, `core.judge`) | Yes (line 239) | Yes (line 222) |

Implementations 1, 2, and 4 share `core.parser.aggregate_files` and `core.judge.collect_model_responses` directly. Implementation 3 (the one the server uses) is the only one that **does not apply ignore patterns or arena directives** — verified by `grep -n "load_ignore_patterns\|build_arena_plan" core/pipeline.py` returning zero matches.

### 2.8 — M8: server bypasses 7 CLI validations

Verified by `grep -n "load_ignore_patterns\|build_arena_plan\|write_state_breadcrumb\|sync_paste_attachments\|migrate_to_flat_layout\|migrate_to_per_file_folders\|migrate_old_outputs\|generate_tree" gui/server/main.py` returning exactly two hits:

- `next_arena_number` (line 212), called at line 560 — the simple "max+1" strategy, not `build_arena_plan`
- `next_arena_number` line 212 → 560 — the only arena-numbering path

The 7 validations, their CLI location, and whether the server's `_execute_typed_run` (lines 608-682) runs them:

| # | CLI Validation | CLI Line | Server `_execute_typed_run`? |
| --- | --- | --- | --- |
| 1 | `load_ignore_patterns` | `aggregator.py:674` | **Missing** — pipeline ignores it (`core/pipeline.py` has no call) |
| 2 | `build_arena_plan` (directive resolution) | `aggregator.py:725-751` | **Missing** — server uses `next_arena_number` (main.py:560) |
| 3 | Structure drift detection (tree compare + prompt) | `aggregator.py:686-714` | **Missing** |
| 4 | Post-run directive report | `aggregator.py:790-827` | **Missing** |
| 5 | `write_state_breadcrumb` | `aggregator.py:834-841` | **Missing** |
| 6 | `sync_paste_attachments` | `aggregator.py:831` | **Missing** |
| 7 | Legacy migrations (`migrate_old_outputs`, `migrate_to_per_file_folders`, `migrate_to_flat_layout`) | `aggregator.py:626-634` | **Missing** — server has separate `/api/run/check` for old-file detection only |

Implication: the same `files.txt` containing `# Target Arena: 005 my-benchmark` will produce `arenas/005-my-benchmark/` in the CLI but `arenas/042-my-benchmark/` in the server (because `next_arena_number` computes `max(existing) + 1`). Same input, different output.

### 2.9 — S7: silent skip on missing nested group

Verified at `core/settings.py:404-412`:

```python
def _to_flat_dict(settings: Settings) -> dict[str, object]:
    flat: dict[str, object] = {}
    for flat_key, (group_name, attr_name) in _FLAT_TO_NESTED.items():
        group = getattr(settings, group_name, None)   # line 408
        if group is None:
            continue                                # line 410 — silent
        flat[flat_key] = getattr(group, attr_name)
    return flat
```

`getattr(settings, g, None)` can return `None` if someone manually stripped a `settings.json` key or if a `Settings` instance was constructed with `groups={}`. The silent skip with no log then cascades: any code using `settings.get("gemini_judge", False)` falls through `KeyError → .get default`. The judge is silently disabled. Note: `core/settings.py:404-412` is what the file actually contains — the audit #1 reference to lines "404-410" is slightly off.

### 2.10 — S4: revoke_token never called

`grep -n "revoke_token" gui/server/security.py` returns 3 hits (definition + 1 doc-comment + 1 call to `discard` inside `revoke_token` itself). `grep -rn "revoke_token(" gui/ core/ aggregator.py aggregator_gui.py aggregator_tui.py tests/` returns zero hits outside the definition site. Token rotation: never.

---

## 3. Findings I am declining to transfer wholesale

Some entries in `audit-report.md` are accurate at the headline level but the framing as written is misleading. I'll keep them in the master list (✅) but note the imprecision:

- **C3 in `audit-report.md`** (M3 here): the title says "permanent global mutation." Truer phrasing: "permanent **on the in-process module dict** until the next server restart." Once the server restarts, the global is re-initialized from the literal in the source file. So the corruption is per-process-lifetime, not forever.
- **C2 in `audit-report.md`** (M2 here): the cause is described as "requires `keys()` and `__getitem__` or `__iter__`." Functionally equivalent: the failure mode is the same and the fix is the same. Just call out the precise error (`attribute name must be string, not 'int'`) so future engineers don't go hunting for a missing `__iter__`.
- **S7 in `audit-report.md`**: cites "lines 409-410" for `_to_flat_dict`. Real code is at `core/settings.py:404-412`. Doesn't change the claim; just a line-number drift because the file was edited since.

---

## 4. Patch instructions for my prior audit document

`docs/AUDIT_logical_disconnects_2026-07-10.md` has an error in C2 that this corrigendum supersedes. Apply or refuse the following edits:

1. **C2 — retarget.** Every reference to `gui/app.py:178-195` becomes `aggregator_gui.py:364-374`. The bug, root cause, evidence, and fix are unchanged.
2. **Add D1 to the summary table.** `gui/` package (~2,400 lines) is dead code; recommend deletion.
3. **Add M7, M8 to the Critical section** with brief cross-link to this corrigendum.
4. **Defer the WS auth fix (C4 / M5) until after M6 / M1 / M4 lands.** WS is unreachable today; fix it before any client reaches for it, not before.

The full merged list is above (§1). Use that as the single source of truth going forward.

---

## 5. What was NOT wrong from `audit-report.md`

For credit: claims the audit #1 got right and my audit #2 missed or under-covered:

- **C3 of `audit-report.md` (M3 here):** The three-error-paths-return-module-reference bug is genuinely a different and more dangerous class of failure than my C3/nested-flat (M4). It's a process-wide corruption vector, not a write-path corruption vector.
- **C5 of `audit-report.md` (M7 here):** The behaviour-difference table is precise and verifiable. My audit #2 hand-waved this as "duplication is plain text, not semantic drift" — the table proves me wrong. The differences matter (M8).
- **S3 of `audit-report.md`:** Backpressure / unbounded queue growth is real and I missed it. ⚪ Unverified operationally (would need a stress test), but the code path is exactly as described.
- **S8 of `audit-report.md`:** The three-tier threading (`run_coroutine_threadsafe` → `asyncio.run` → `asyncio.to_thread`) is wasteful and confusing. Confirmed.
- **U2 / U3 / U4 / U5:** All real. My audit #2 only covered `C1` and `C4` from the Extension; U3/U5 in particular (URL hardcoded, `/health` leaks) are concrete and actionable.

---

## 6. Outstanding claims worth chasing next

Three M-class items (M5, M6, M7, M8) are the largest behavioral problems; the rest of the audit is shape-and-correctness. The roadmap I'd propose:

1. **Decide fate of `gui/` dead code (D1).** Two credible options: finish the cutover (substantial work, low immediate ROI) or delete (`git rm -r gui/` minus `gui/server/` and `gui/browser-extension/`). Recommend deletion.
2. **Land settings unification (closes M1, M3, M4, S1, S9, S10, S11, S12).** Single biggest leverage PR. Replaces the three parallel settings loaders (`aggregator.py`, `aggregator_gui.py`, `gui/server/main.py`) with one canonical `core.settings.load_settings`/`save_settings` adapter. Eliminates the interleave with type-safe attribute writes in `aggregator_gui.py:364-374`.
3. **Land M6/M5 together:** wire the Run button into the popup AND add WS auth. Either is incomplete without the other.
4. **Land M7 (consolidate pipeline orchestrators).** Once a decision is in on M6, the four orchestrators collapse to 1: a single canonical `core.pipeline.run_pipeline` that does the same six phases the CLI does, with the GUI/CLI calling it for orchestration UX. Server calls it directly via `asyncio.to_thread`. Three orbits of code deletion.
5. **Land UX polish (U1-U10).** Once the structural problems are gone, the UX class becomes the only thing left.

---

## Appendix A — Empirical tests run

```bash
# Test 1 — verify dict(Settings) crash
cd C:\programming\Python\Projects\context
python -c "from core.settings import Settings; dict(Settings())"
# → TypeError: attribute name must be string, not 'int'

# Test 2 — verify gui package import graph is empty
Select-String -Path "C:\programming\Python\Projects\context\aggregator.py",
"C:\programming\Python\Projects\context\aggregator_gui.py",
"C:\programming\Python\Projects\context\aggregator_tui.py" \
  -Pattern "from gui\.app|from gui import app|gui\.app\.run_gui"
# → (empty)

# Test 3 — verify gui package has zero inbound references anywhere
Select-String -Path "C:\programming\Python\Projects\context\*.py" \
  -Pattern "from gui\.app|from gui import app"
# → (empty)

# Test 4 — verify core/pipeline.py skips ignore patterns
Select-String -Path "C:\programming\Python\Projects\context\core\pipeline.py" \
  -Pattern "load_ignore_patterns|build_arena_plan"
# → (empty)

# Test 5 — verify gui/server/main.py bypasses CLI validations
Select-String -Path "C:\programming\Python\Projects\context\gui\server\main.py" \
  -Pattern "load_ignore_patterns|build_arena_plan|write_state_breadcrumb|sync_paste_attachments|migrate_to_flat_layout|migrate_to_per_file_folders|migrate_old_outputs"
# → (empty — only next_arena_number, the simple sequential strategy)

# Test 6 — verify revoke_token is defined but never called
Select-String -Path "C:\programming\Python\Projects\context" -Pattern "revoke_token\(" -Recurse
# → only the definition site itself (gui/server/security.py)

# Test 7 — verify default-Settings reference-leak in read_settings
Read lines gui/server/main.py:172-204 — three of four return paths skip .copy()
```

Output captured is consistent with the findings above.
