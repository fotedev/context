---
name: arena-context
description: ARENA-CONTEXT writes relevant file paths into ./files.txt for LMArena. Trigger on bug reports, runtime/build errors, feature requests, type mismatches, or stack traces. Do NOT use for general questions without a local project.
license: MIT
metadata:
  author: fote
  version: "2.2.0"

---
# Arena Context
Curates the minimum sufficient local context that LMArena needs to understand a coding problem by writing file paths into `./files.txt` (project root). Also provides Extra Context in chat for runtime or dependency issues that cannot be captured as file paths.
Prepares context for Blind Pairwise Comparisons and Arena Expert prompts on LMArena, where multiple models are evaluated head-to-head.
## Inputs
| Item | Path |
|---|---|
| Target list (overwrite) | `./files.txt` in project root (CWD) |
| Aggregator script (read-only) | Linux/WSL: `/mnt/data/programming/Python/Projects/context/aggregator.py` · Windows: `C:/programming/Python/Projects/context/aggregator.py` |
| Models directory | `./models/` containing `prompt.txt` and model response files |
Size budget: keep aggregated total ≤ 4000–5000 lines across all selected files and snippets.
## Workflow
1. **ANALYZE** — Classify the problem: logic, UI, runtime, config, or dependency.
2. **SCAN** — Explore the project tree around implicated files.
3. **TRACE** — Follow imports and type references outward, one level deep unless deeper files are clearly implicated.
4. **ESTIMATE** — Gauge total line count (count lines for full files; `end - start + 1` for snippets). Target ≤ 4500 lines.
5. **CLASSIFY** — For each file: full file, code snippet (range), or important structure (`!` prefix).
6. **WRITE** — Overwrite `./files.txt` with entries using the output format below.
7. **REPORT** — Reply with the report format below.
### File Selection (expanding rings from the problem epicenter)
| Tier | What | Include when |
|---|---|---|
| 1 — Primary | Files directly named or clearly implicated | Always |
| 2 — Dependencies | Files imported by Tier 1 containing logic (not re-exports) | Always, one level deep |
| 3 — Type context | `*.d.ts`, shared `interfaces/`, `types/`, `models/`, props definitions | When shapes matter |
| 4 — Potential | Parent components, config files (`next.config.js`, `tsconfig.json`, `.env.example`), CSS Modules | Include when in doubt; leave out when clearly irrelevant |
### Snippet Selection
| Situation | Use |
|---|---|
| File ≤ 100 lines, all relevant | Full file path |
| File > 200 lines, one section matters | Code snippet with range |
| Multiple sections in same file | Multi-range snippet |
| Type / interface / config definition | Important structure (`!` prefix) |
### Volume Control
If over budget, drop in this order: (1) Tier 4, (2) less-implicated Tier 3, (3) large style files / docs. Replace dropped-but-important context with Extra Context snippets in chat so LMArena still receives the signal.
### Node Modules & Runtime Problems
For runtime errors, type mismatches from a library, or dependency version conflicts: add small, high-signal `node_modules` files only when directly relevant and within budget (e.g., `node_modules/<pkg>/package.json`, `node_modules/<pkg>/**/*.d.ts`). Use line-range syntax for large files, or present them in chat under Extra Context.
## Output Format
### files.txt Entry Syntax
Each line is an absolute path formatted for the user's OS, one entry per line, no quotes, no bullets.
| Format | Meaning | Linux example | Windows example |
|---|---|---|---|
| `!/abs/path/file.py:start-end` | Important structure | `!/home/proj/src/types.ts:1-30` | `!C:/proj/src/types.ts:1-30` |
| `/abs/path/file.py:start-end` | Code snippet | `/home/proj/src/app.tsx:45-80` | `C:/proj/src/app.tsx:45-80` |
| `/abs/path/file.py:s-e,s2-e2` | Multi-range snippet | `/home/proj/src/large.py:10-20,50-60` | `C:/proj/src/large.py:10-20,50-60` |
| `/abs/path/file.py` | Full file | `/home/proj/src/utils.ts` | `C:/proj/src/utils.ts` |
Line numbers are 1-indexed and inclusive. The `!` prefix marks structural highlights. Comment lines starting with `#` are ignored.
### Report Format
After writing `./files.txt`, always reply with:
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
## Examples
### ✅ UI/Layout bug — focused selection
User: "Navbar.tsx layout is broken"
**files.txt (Linux):**
```
/home/proj/src/components/Navbar.tsx
/home/proj/src/components/Navbar.module.css
/home/proj/src/layouts/MainLayout.tsx:45-80
!/home/proj/src/types/nav.ts:1-15
```
**files.txt (Windows):**
```
C:/proj/src/components/Navbar.tsx
C:/proj/src/components/Navbar.module.css
C:/proj/src/layouts/MainLayout.tsx:45-80
!C:/proj/src/types/nav.ts:1-15
```
### ❌ UI/Layout bug — over-inclusive selection
Adding the entire `src/` directory or editing code to fix the layout both go beyond context curation. The skill's job ends at selecting files.
### ✅ Runtime/library type mismatch
User: "Type error mentions next-auth Session"
**files.txt (Linux):**
```
/home/proj/src/lib/auth.ts
/home/proj/src/app/api/auth/[...nextauth]/route.ts
!/home/proj/node_modules/next-auth/index.d.ts:45-75
```
**files.txt (Windows):**
```
C:/proj/src/lib/auth.ts
C:/proj/src/app/api/auth/[...nextauth]/route.ts
!C:/proj/node_modules/next-auth/index.d.ts:45-75
```
### ❌ Runtime/library type mismatch — wholesale dependency inclusion
Adding `node_modules/next-auth/` recursively overwhelms the size budget. Use targeted line-range snippets or Extra Context in chat instead.
### ✅ Large file, specific function
User: "The `processOrder` function in `orders.ts` has a bug"
**files.txt (Linux):**
```
/home/proj/src/services/orders.ts:120-180
/home/proj/src/services/orders.ts:1-30,200-220
!/home/proj/src/types/order.ts:1-40
```
**files.txt (Windows):**
```
C:/proj/src/services/orders.ts:120-180
C:/proj/src/services/orders.ts:1-30,200-220
!C:/proj/src/types/order.ts:1-40
```
### ❌ Large file, specific function — entire file inclusion
Adding the entire 800-line `orders.ts` wastes budget on irrelevant code. Use line-range snippets to focus on the implicated function and its type context.
## Scope Boundaries
- Write only to `./files.txt` in the project root — leave application code, configs, and dependencies untouched so the user's codebase remains stable.
- Focus on selecting context rather than proposing fixes or implementing changes — LMArena's models handle the solution.
- The user runs `aggregator.py` themselves; the skill's job ends after writing `files.txt` and providing the report.

## When Not to Use This Skill
- The user asks a general programming question unrelated to their local project.
- The user has already pasted all relevant code in chat and wants a direct explanation without LMArena involvement.
- The user explicitly requests that context not be prepared.
