---
name: arena-context
description: Curates and writes high-signal project context for LMArena. Trigger on bug reports, runtime/build errors, feature requests, or stack traces. The agent must automatically write input path-listing .txt files to .context/inputs/<name>.txt. Do not write to project root files.txt or arena-prompt.md.
license: MIT
metadata:
  author: fote
  version: "2.5.1"

---
# Arena Context

Curates the minimum sufficient local context that LMArena needs to understand a coding problem by writing file paths and comments into `.context/inputs/<descriptive-name>.txt` (primary) or `./files.txt` (fallback) in the project root. The agent **must automatically use** `.context/inputs/` to store these path-listing `.txt` files, as the aggregator tool automatically scans and processes all files in this directory to generate isolated, numbered arenas.

Also provides Extra Context in chat for runtime or dependency issues that cannot be captured as file paths.

Prepares context for Blind Pairwise Comparisons and Arena Expert prompts on LMArena, where multiple models are evaluated head-to-head.

## Reference to prompt.txt & organize-root.md
- For the detailed specification, features, requirements, and edge cases of the context aggregator tool, refer to the workspace file: [prompt.txt](file:///c:/programming/Python/Projects/context/prompt.txt)
- For the layout organization steps and legacy file cleanup, refer to the mini-skill: [organize-root.md](file:///c:/programming/Python/Projects/context/arena-context/organize-root.md)


## Inputs
| Item | Path / Location |
|---|---|
| Target list to write (overwrite) | **Mandatory:** `.context/inputs/<descriptive-name>.txt` (The agent MUST create this file/folder. Do not write to root `files.txt` or `arena-prompt.md`) |
| Config directory | `.context/` containing `settings.json` and `ignore` |
| Aggregator script (do NOT run) | Linux/WSL: `/mnt/data/programming/Python/Projects/context/aggregator.py` · Windows: `C:/programming/Python/Projects/context/aggregator.py` |
| Models directory | `context_output/models/` containing `prompt.txt`, model responses (`A.txt`, `B.txt`, etc.), and notes |
| Size budget | Keep aggregated total ≤ 5000 lines across all selected files and snippets |

## Workflow
1. **ANALYZE** — Classify the problem: logic, UI, runtime, config, or dependency.
2. **SCAN** — Explore the project tree around implicated files.
3. **TRACE** — Follow imports and type references outward, one level deep unless deeper files are clearly implicated.
4. **ESTIMATE** — Gauge total line count (count lines for full files; `end - start + 1` for snippets). Target ≤ 4500 lines.
5. **CLASSIFY** — For each file: full file, code snippet (range), or important structure (`!` prefix).
6. **WRITE** — **Mandatory target location:** Overwrite/create `.context/inputs/<descriptive-name>.txt` (where `<descriptive-name>` is derived from the user's prompt, e.g., `fix-navbar-bug.txt`).
   - *Directory Creation:* The agent MUST automatically create the `.context/inputs/` directory if it does not exist (using standard file writing tools which automatically handle parent folder creation).
   - *No Root Files:* Do NOT write to root `files.txt` and do NOT create prompt files (like `arena-prompt.md`) in the project root.
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
### Input File Entry Syntax
Each line is an absolute path formatted for the user's OS, one entry per line, no quotes, no bullets. Comments and context from the user's prompt should be included as `#` prefixed lines.
| Format | Meaning | Linux example | Windows example |
|---|---|---|---|
| `!/abs/path/file.py:start-end` | Important structure | `!/home/proj/src/types.ts:1-30` | `!C:/proj/src/types.ts:1-30` |
| `/abs/path/file.py:start-end` | Code snippet | `/home/proj/src/app.tsx:45-80` | `C:/proj/src/app.tsx:45-80` |
| `/abs/path/file.py:s-e,s2-e2` | Multi-range snippet | `/home/proj/src/large.py:10-20,50-60` | `C:/proj/src/large.py:10-20,50-60` |
| `/abs/path/file.py` | Full file | `/home/proj/src/utils.ts` | `C:/proj/src/utils.ts` |
| `# comment text` | Context from user prompt | `# Navbar layout broken on mobile` | `# Navbar layout broken on mobile` |

Line numbers are 1-indexed and inclusive. The `!` prefix marks structural highlights. Comment lines starting with `#` are ignored by the aggregator but provide context for anyone reading the input file.

**Optional Directive:** You can add a `# Target Arena: NNN-<name>` directive on the first non-empty line to pin the arena number. If omitted, the tool auto-numbers arenas.

### Input File Structure
Put comments from the user's prompt at the top of the input file as context:
```
# User problem: Navbar.tsx layout is broken
# The CSS grid is breaking on mobile screens < 768px
# Error: Cannot read property 'style' of undefined

C:/proj/src/components/Navbar.tsx
C:/proj/src/components/Navbar.module.css
C:/proj/src/layouts/MainLayout.tsx:45-80
!C:/proj/src/types/nav.ts:1-15
```
This way the input file is self-documenting — anyone reading it knows what problem it addresses.

### Category Organization (NEW)
You can organize input files into subdirectories within `.context/inputs/` for better organization:
```
.context/inputs/
├── UI/
│   ├── AdminPage.txt        # ← Found as "UI-AdminPage"
│   └── HomePage.txt         # ← Found as "UI-HomePage"
├── API/
│   └── UserAuth.txt         # ← Found as "API-UserAuth"
└── Common/
    └── Types.txt            # ← Found as "Common-Types"
```
The tool automatically discovers all `.txt` files in subdirectories and uses the directory structure as part of the arena naming (e.g., `UI/AdminPage.txt` → `001-UI-AdminPage/`).

### Report Format
After writing `.context/inputs/<descriptive-name>.txt`, always reply with:
✅ **.context/inputs/<descriptive-name>.txt updated** — [N] files, [S] snippets, [I] structures selected for [problem summary]

**Arena output:** `context_output/arenas/NNN-<descriptive-name>/` (where NNN is auto-incremented)
- For files in subdirectories: `context_output/arenas/NNN-<category>-<name>/` (e.g., `001-UI-AdminPage/`)
- `NNN-context.md` (or `.txt`) — aggregated source code
- `NNN-arena.md` (or `.txt`) — model comparison template
- `NNN-prompt.txt` — prompt sent to models (if generated)
- `NNN-A.txt`, `NNN-B.txt` — model response files
- `structure.txt` — project tree (located in `context_output/structure/structure.txt`)
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
Copy this block alongside `NNN-context.md` and `NNN-arena.md` (located in `context_output/arenas/NNN-<descriptive-name>/`) into LMArena.

## Examples
### ✅ UI/Layout bug — focused selection
User: "Navbar.tsx layout is broken"
**Input File (Linux):**
```
# User problem: Navbar.tsx layout is broken
# CSS grid breaking on mobile screens < 768px

/home/proj/src/components/Navbar.tsx
/home/proj/src/components/Navbar.module.css
/home/proj/src/layouts/MainLayout.tsx:45-80
!/home/proj/src/types/nav.ts:1-15
```
**Input File (Windows):**
```
# User problem: Navbar.tsx layout is broken
# CSS grid breaking on mobile screens < 768px

C:/proj/src/components/Navbar.tsx
C:/proj/src/components/Navbar.module.css
C:/proj/src/layouts/MainLayout.tsx:45-80
!C:/proj/src/types/nav.ts:1-15
```
### ❌ UI/Layout bug — over-inclusive selection
Adding the entire `src/` directory or editing code to fix the layout both go beyond context curation. The skill's job ends at selecting files.

### ✅ Runtime/library type mismatch
User: "Type error mentions next-auth Session"
**Input File (Linux):**
```
# User problem: Type error mentions next-auth Session
# TypeError: Cannot read property 'user' of undefined

/home/proj/src/lib/auth.ts
/home/proj/src/app/api/auth/[...nextauth]/route.ts
!/home/proj/node_modules/next-auth/index.d.ts:45-75
```
**Input File (Windows):**
```
# User problem: Type error mentions next-auth Session
# TypeError: Cannot read property 'user' of undefined

C:/proj/src/lib/auth.ts
C:/proj/src/app/api/auth/[...nextauth]/route.ts
!C:/proj/node_modules/next-auth/index.d.ts:45-75
```
### ❌ Runtime/library type mismatch — wholesale dependency inclusion
Adding `node_modules/next-auth/` recursively overwhelms the size budget. Use targeted line-range snippets or Extra Context in chat instead.

### ✅ Large file, specific function
User: "The `processOrder` function in `orders.ts` has a bug"
**Input File (Linux):**
```
# User problem: processOrder function in orders.ts has a bug
# Order total is calculated incorrectly when discount is applied

/home/proj/src/services/orders.ts:120-180
/home/proj/src/services/orders.ts:1-30,200-220
!/home/proj/src/types/order.ts:1-40
```
**Input File (Windows):**
```
# User problem: processOrder function in orders.ts has a bug
# Order total is calculated incorrectly when discount is applied

C:/proj/src/services/orders.ts:120-180
C:/proj/src/services/orders.ts:1-30,200-220
!C:/proj/src/types/order.ts:1-40
```
### ❌ Large file, specific function — entire file inclusion
Adding the entire 800-line `orders.ts` wastes budget on irrelevant code. Use line-range snippets to focus on the implicated function and its type context.

## Scope Boundaries
- **Strict Target Directory Selection:** Always write input `.txt` files containing paths to `.context/inputs/<descriptive-name>.txt`. Never create files like `files.txt` or `arena-prompt.md` in the project root.
- Write only to `.context/inputs/` — leave application code, configs, and dependencies untouched so the user's codebase remains stable.
- Focus on selecting context rather than proposing fixes or implementing changes — LMArena's models handle the solution.
- The user runs `aggregator.py` themselves; the skill's job ends after writing the input file and providing the report.

## When Not to Use This Skill
- The user asks a general programming question unrelated to their local project.
- The user has already pasted all relevant code in chat and wants a direct explanation without LMArena involvement.
- The user explicitly requests that context not be prepared.
