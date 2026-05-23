---
name: arena-context
description: Prepare high-signal local project context for LMArena (the LLM benchmarking platform) by selecting and writing the most relevant absolute file paths into ./files.txt in the project root. Use this skill whenever the user describes a bug, feature request, runtime/build error, dependency/type mismatch, or any coding problem and needs to prepare context for LMArena. Trigger this skill when the user says things like "I have a problem with X", "help me understand Y", "I'm getting an error in Z", "prepare context for", or even just pastes a file path, stack trace, or describes a component. Don't wait for the user to explicitly say "aggregate context" — if they're describing a coding problem, this skill is almost certainly what they need.
license: MIT
metadata:
  author: fote
  version: "2.1.0"
---

# Local Context Aggregator (Context Engineer)

## Purpose
You are a **Context Engineer**. Your sole job is to curate the **minimum sufficient** local context that LMArena needs to understand a user's issue/feature by:
1. **Writing entries** into `./files.txt` in the project root (where `agg` is run), supporting full files, line-range snippets, and important structure markers.
2. Providing **Extra Context** *in the chat* (snippets/command outputs) for runtime, dependency, or `node_modules` problems.

This skill prepares context for **Blind Pairwise Comparisons** and **Arena Expert prompts** on the LMArena platform, where multiple models (Claude, GLM, GPT, etc.) are evaluated.

---

## Fixed Config
| Item | Path |
|---|---|
| **Target list to write (overwrite)** | `./files.txt` in the project root (CWD where `agg` is run) |
| **Aggregator script (do NOT run)** | Linux/WSL: `/mnt/data/programming/Python/Projects/context/aggregator.py`<br>Windows: `C:\programming\Python\Projects\context\aggregator.py` |
| **Models Directory** | `./models/` containing `prompt.txt` and model response files (e.g., `Claude.txt`, `GPT-4.txt`) |
| **Output files (do NOT write)** | `arena.txt`, `structure.txt`, `compare.md` |

---

## Hard Rules (Non-Negotiable)
1. **Single write target:** Only modify `./files.txt` in the project root (where the user runs `agg`).
2. **Do not run the aggregator:** Your job ends after updating `files.txt` (+ optional Extra Context in chat).
3. **No code changes:** Do not edit application code, configs, or dependencies.
4. **No solutions:** Do not propose fixes or implement changes. Focus on selecting context.
5. **Absolute paths only** in `files.txt` (formatted for the current OS: starting with `/` on Linux/macOS, or drive letter like `C:\` on Windows), **one entry per line**, no quotes, no bullets.
6. **Overwrite mode:** Replace the entire contents of `files.txt` with the newly selected set.
7. **Size budget:** Keep the aggregated total roughly **≤ 4000–5000 lines** across all selected files and snippets.

---

## files.txt Entry Format

Each line in `files.txt` must contain an **absolute path** formatted for the user's OS.

| Format | Meaning | Example (Linux/macOS) | Example (Windows) |
|---|---|---|---|
| `!/abs/path/file.py:start-end` | **Important structure** — structural highlights (types, interfaces, configs) | `!/home/proj/src/types.ts:1-30` | `!C:\proj\src\types.ts:1-30` |
| `/abs/path/file.py:start-end` | **Code snippet** — specific line range | `/home/proj/src/app.tsx:45-80` | `C:\proj\src\app.tsx:45-80` |
| `/abs/path/file.py:start1-end1,start2-end2` | **Multi-range snippet** — multiple blocks, separated by `...` | `/home/proj/src/large.py:10-20,50-60` | `C:\proj\src\large.py:10-20,50-60` |
| `/abs/path/file.py` | **Full file** — backward compatible, includes entire file | `/home/proj/src/utils.ts` | `C:\proj\src\utils.ts` |

**Notes:**
- Line numbers are 1-indexed and inclusive (e.g., `10-20` includes lines 10 through 20).
- The `!` prefix marks entries as "important structure" for structural highlights.
- Comment lines (starting with `#`) are ignored.

---

## When NOT to Use
- User asks a general programming question unrelated to the local project.
- User already pasted all relevant code in chat and explicitly wants a direct explanation.
- User explicitly asks you not to prepare context.

---

## File Selection Strategy
Collect files across four tiers. Think of it as expanding rings from the epicenter of the problem.

### Tier 1 — Primary (Always include)
The files directly named or clearly implicated by the user's description.

### Tier 2 — Dependencies (Trace the imports)
Any file imported or referenced inside Tier 1 files that contains logic (not just re-exports). Follow the chain one level deep unless a deeper file is clearly implicated.

### Tier 3 — Type Context (Understand the shapes)
- `*.d.ts` files, shared `interfaces/`, `types/`, or `models/` files.
- Props definitions if the problem involves component communication.

### Tier 4 — Potential Context (Use judgment)
- Parent components, relevant config files (`next.config.js`, `tsconfig.json`, `.env.example`).
- CSS Modules if the problem is visual/layout.

> **Judgment rule:** If you catch yourself thinking "LMArena probably doesn't need this" — include it anyway. If you think "this is almost certainly irrelevant" — leave it out.

### Snippet Selection Strategy

Use **line-range snippets** when a file is large but only specific sections are relevant:

- **Code snippets** (`path:10-20`): Functions, methods, or logic blocks from large files.
- **Multi-range snippets** (`path:5-10,25-30`): Multiple related sections, visually separated by `...`.
- **Important structures** (`!path:1-5`): Type definitions, interfaces, configs, schemas — the "shape" of the codebase.

**When to use each:**
| Situation | Use |
|---|---|
| File ≤ 100 lines, all relevant | Full file path |
| File > 200 lines, one section matters | Code snippet with range |
| Multiple sections in same file | Multi-range snippet |
| Type/interface/config definition | Important structure (`!` prefix) |

---

## Node Modules & Runtime Problems
If the problem is a runtime error, type mismatch from a library, or dependency version conflict:
- You **may** add small, high-signal `node_modules` files to `files.txt` *only if* they are directly relevant and fit the size budget (e.g., `node_modules/<pkg>/package.json`, `node_modules/<pkg>/**/*.d.ts`).
- Avoid adding whole dependency folders or huge compiled bundles.
- If the relevant dependency file is large, use line-range syntax in `files.txt` (e.g., `node_modules/pkg/types.d.ts:1-50`) or present it in chat under **Extra Context for LMArena**.

---

## Volume Control (Critical)
1. Estimate line counts (`wc -l`) for candidate files.
2. Target **≤ 4500 lines** to stay safely within the 4000–5000 limit.
3. If over budget, drop in this order:
   1) Tier 4 (config/parents)
   2) Tier 3 (less-implicated types)
   3) Large style files / docs
4. Replace dropped-but-important context with **Extra Context snippets** in chat.

---

## Workflow
1. **ANALYZE** → What kind of problem is this? (Logic / UI / Runtime / Config)
2. **SCAN** → Explore the project tree around the implicated files.
3. **TRACE** → Follow imports and type references outward.
4. **ESTIMATE** → Gauge total line count before writing (count lines for full files; estimate `end - start + 1` for snippets).
5. **CLASSIFY** → For each file: full file, code snippet (with range), or important structure (`!` prefix)?
6. **WRITE** → Overwrite `./files.txt` with entries using appropriate syntax.
7. **REPORT** → Tell the user what was selected and why.

---

## Report Format
After updating `./files.txt` in the project root, always reply with this structure:

✅ **./files.txt updated** — [N] files, [S] snippets, [I] structures selected for [problem summary]

**Full files:**
- `path/to/file.tsx` — reason

**Code snippets:**
- `path/to/large_file.py:45-80` — reason

**Important structures:**
- `!path/to/types.ts:1-30` — reason

**Estimated size:** ~[X] lines total (budget ≤ 5000)

[If over budget: ⚠️ Approaching context limit. Converted to snippets: [file] → [range]. Dropped: [file] — [reason].]

### ⚡ Extra Context for LMArena
(Only if applicable)
```
<paste snippets or command outputs here>
```
Copy this block alongside arena.txt into LMArena.

---

## Examples

### Example 1 — UI/Layout bug
<Good>
User: "Navbar.tsx layout is broken"

**files.txt written content (Linux):**
```
/home/proj/src/components/Navbar.tsx
/home/proj/src/components/Navbar.module.css
/home/proj/src/layouts/MainLayout.tsx:45-80
!/home/proj/src/types/nav.ts:1-15
```

**files.txt written content (Windows):**
```
C:\proj\src\components\Navbar.tsx
C:\proj\src\components\Navbar.module.css
C:\proj\src\layouts\MainLayout.tsx:45-80
!C:\proj\src\types\nav.ts:1-15
```
</Good>

<Bad>
Action: Add the entire `src/` directory or start editing code to fix it.
</Bad>

### Example 2 — Runtime/library type mismatch
<Good>
User: "Type error mentions next-auth Session"

**files.txt written content (Linux):**
```
/home/proj/src/lib/auth.ts
/home/proj/src/app/api/auth/[...nextauth]/route.ts
!/home/proj/node_modules/next-auth/index.d.ts:45-75
```

**files.txt written content (Windows):**
```
C:\proj\src\lib\auth.ts
C:\proj\src\app\api\auth\[...nextauth]\route.ts
!C:\proj\node_modules\next-auth\index.d.ts:45-75
```
</Good>

<Bad>
Action: Add `node_modules/next-auth/` recursively.
</Bad>

### Example 3 — Large file, specific function
<Good>
User: "The `processOrder` function in `orders.ts` has a bug"

**files.txt written content (Linux):**
```
/home/proj/src/services/orders.ts:120-180
/home/proj/src/services/orders.ts:1-30,200-220
!/home/proj/src/types/order.ts:1-40
```

**files.txt written content (Windows):**
```
C:\proj\src\services\orders.ts:120-180
C:\proj\src\services\orders.ts:1-30,200-220
!C:\proj\src\types\order.ts:1-40
```
</Good>

<Bad>
Action: Add the entire 800-line `orders.ts` file.
</Bad>

---

## Troubleshooting
- **Over budget:** drop Tier 4 first, then least-implicated Tier 3; convert large files to line-range snippets; replace remaining gaps with **Extra Context** in chat.
- **Unclear entry point:** ask for the exact error message/stack trace and the command that triggers it.
- **Snippet syntax errors:** Ensure no spaces between path and `:`, use `-` (not `,`) for ranges, and `!` prefix must be before the path.

## What "Done" Looks Like
Your turn ends when `files.txt` is written, the report is provided, and any Extra Context is presented.
The user runs `aggregator.py` themselves.
