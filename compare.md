# Model Comparison (LMArena Style - 1 Models)
## The Prompt
> <role>
You are a senior Python developer improving a CLI tool called "context" (arena-context skill). The tool aggregates source files for LMArena blind pairwise comparisons. You write clean, minimal Python code following existing patterns in the codebase.
</role>
<context>
The tool has three entry points: aggregator.py (CLI), aggregator_tui.py, aggregator_gui.py. The core logic lives in core/ (parser.py, counter.py, judge.py). Currently it reads a single files.txt, generates arena.txt (aggregated code), structure.txt (project tree), and compare.md (model comparison via Gemini judge).
Project root detection: find_project_root() in parser.py searches parent directories for markers (.git, package.json, pyproject.toml, requirements.txt, src). The first file path in files.txt is used as the starting point.
Compact mode in core/judge.py does: (1) removes "### Notes" sections, (2) collapses blank lines, (3) trims trailing whitespace. It's a token saver for LMArena.
</context>
<current_code>
<!-- NOTE: The actual source code of these files will be provided/appended to the context. Use these descriptions for context. -->
<file path="aggregator.py">
Main entry point. Reads files.txt → generates arena.txt, structure.txt, compare.md. Has hardcoded input() prompts for Gemini judge and compact mode.
</file>
<file path="core/parser.py">
File parsing, path resolution, tree generation, ignore patterns. _DEFAULT_IGNORE is a hardcoded frozenset. read_file_entries() skips blank lines and # comments.
</file>
<file path="core/counter.py">
Token counting using tiktoken.
</file>
<file path="core/judge.py">
Gemini AI judge integration. build_compare_markdown() accepts compact flag. collect_model_responses() reads from models/ dir.
</file>
</current_code>
<requirements>
<requirement id="1" priority="high">
OUTPUT ORGANIZATION: Create a dedicated output folder (context_output/) instead of dumping files in the current working directory (CWD). All generated files (e.g. arena.txt, structure.txt, compare.md, and their multi-file equivalents) must be written inside this folder. The output folder path must be configurable via the --output flag.
</requirement>
<requirement id="2" priority="high">
MULTI-FILE SUPPORT: Automatically discover and process ALL files*.txt files in the CWD matching the pattern files.txt and files_*.txt (e.g. files.txt, files_1.txt, files_02.txt). Each discovered input file must produce its own set of arena/structure/compare outputs with a matching suffix inside the output folder (e.g. files_1.txt produces context_output/arena_1.txt, context_output/structure_1.txt, and context_output/compare_1.md).
</requirement>
<requirement id="3" priority="medium">
FLEXIBLE files.txt FORMAT WITH WARNINGS: Support free text and comment lines before and after file path entries.
- Ignore lines starting with '#' (comments) and blank lines (separators).
- Any line that doesn't resolve to a valid existing file path must print a warning to stderr (e.g., "Warning: Invalid path skipped: [line content]"), but the tool must proceed to process the remaining valid paths instead of failing or silently ignoring typos.
</requirement>
<requirement id="4" priority="high">
NON-INTERACTIVE BY DEFAULT & RESOLUTION RULES:
- Remove all hardcoded input() prompts. The tool runs completely silently (non-interactively) by default.
- Configuration precedence rule:
  Command Line Flags > Interactive Prompts (if --interactive) > Settings File (.context/settings.json) > Hardcoded Defaults.
- Add an --interactive CLI flag. When interactive mode is enabled, prompt the user for options in this exact order (where pressing Enter selects the default/setting value, and Space + Enter enables/overrides the option):
  a. "Run Gemini auto-comparison? [Enter=skip, Space=run]: "
  b. "Reduce tokens? Compact mode [Enter=skip, Space=enable]: "
  c. "Archive model responses? [Enter=no, Space=archive]: "
  d. "How many models? [Enter=2, Space=4]: "
  e. "Output format? [Enter=.md, Space=.txt]: "
</requirement>
<requirement id="5" priority="high">
DETAILED ARCHIVING WORKFLOW: When archiving is enabled:
  1. For each model response file (e.g., A.txt, B.txt, etc.) currently in models/, move it to the archive directory (models/ARCHIVE/ by default) renamed with a timestamp in the pattern `<model_name>_<timestamp>.<ext>` (e.g., A_20260622_143022.txt).
  2. If the destination filename already exists, handle the collision by appending `_1`, `_2`, etc. before the extension (e.g. A_20260622_143022_1.txt).
  3. Clear the models/ directory of the active model responses (do not clear other unrelated files).
  4. Prompt for the new model count (Enter=2, Space=4) and auto-create fresh empty templates (e.g. A.txt, B.txt) in models/.
</requirement>
<requirement id="6" priority="medium">
AUTO NOTES: Look for optional model notes files in models/ (e.g. A_NOTES.md or A_NOTES.txt matching the chosen output format extension). If a notes file exists for a model, insert its content under a "### Notes" section below that model's response in the compare output. If no notes file exists, do not write a "### Notes" section.
</requirement>
<requirement id="7" priority="medium">
MODEL COUNT CHOICE & TEMPLATES: Detect existing model files (A.txt, B.txt, C.txt, D.txt). When model_count is configured to 4 but only A.txt and B.txt exist, auto-create empty C.txt and D.txt files and print: "Created empty C.txt and D.txt. Please paste their responses."
</requirement>
<requirement id="8" priority="medium">
MERGED CONFIGURATION DIRECTORY:
- Store all configurations in a single `.context/` directory in the project root.
- Read ignore patterns from `.context/ignore`. If missing, auto-create it with default patterns merged with built-in default ignore patterns (e.g. .git, node_modules, pycache, etc.). Add context_output/ and .context/ to the ignore patterns. Keep backwards compatibility: if `.contextignore` exists in the project root, read and merge its patterns as well.
- Store persistent settings at `.context/settings.json`. If missing, auto-create it with defaults.
</requirement>
<requirement id="9" priority="high">
PERSISTENT SETTINGS SCHEMA: The settings file (.context/settings.json) must conform to this schema:
{
  "output_dir": "context_output",
  "output_format": "md",
  "model_count": 2,
  "gemini_judge": false,
  "compact_mode": false,
  "archive": false,
  "archive_dir": "models/ARCHIVE"
}
</requirement>
<requirement id="10" priority="high">
SETTINGS CLI flag: Add a --settings CLI flag. When passed, the script must print the path to the active `.context/settings.json`, display its current JSON content, and print instructions/template explaining how to edit/create it. Then exit cleanly.
</requirement>
</requirements>
<edge_cases>
<case id="1" input="empty files.txt" action="Create empty templates (arena.txt, structure.txt, compare.md) in the output folder. Ensure they exist but are empty." />
<case id="2" input="invalid settings.json" action="Fall back to defaults. Print warning to stderr every run. If settings.json is completely empty, print: 'Use context skill with AI model to initialize preferences.'" />
<case id="3" input="model_count=4 but only 2 files" action="Auto-create empty C.txt, D.txt. Prompt user to paste content." />
<case id="4" input="archive timestamp collision" action="Append _1, _2, etc. (e.g. A_20260622_143022_1.txt) to prevent overwriting existing archives." />
<case id="5" input="context_output/ has old files" action="If in interactive mode: prompt 'Warn: Merge? [Enter=merge, Space=skip]'. If in non-interactive mode: default silently to auto-merging/overwriting." />
<case id="6" input="GEMINI_API_KEY not set" action="Print a warning to stderr and skip the Gemini judge step. Do not throw an error or crash. Note: the .env containing GEMINI_API_KEY lives in the tool's root directory, not the project root." />
<case id="7" input="notes extension mismatch" action="Only match notes files whose extensions match the chosen output extension (e.g. if output format is 'md', match A_NOTES.md, ignore A_NOTES.txt)." />
<case id="8" input="old files in CWD" action="If in interactive mode: prompt 'Warn: Clean? [Enter=clean, Space=skip]'. If in non-interactive mode: default silently to skipping cleaning (do nothing to protect user files)." />
</edge_cases>
<constraints>
- Maintain backwards compatibility: running the tool with no arguments must still work seamlessly.
- Accept an optional --output flag to override the output folder location.
- Automatically add the output folder (e.g. context_output/) and the configuration folder (.context/) to parser ignore patterns.
- Do not break the existing core/ module APIs or external integration assumptions.
</constraints>
<examples>
<example>
<files.txt>
# Bug in navbar layout
# CSS grid breaking on mobile < 768px
C:/proj/src/components/Navbar.tsx
C:/proj/src/components/Navbar.module.css
C:/proj/src/layouts/MainLayout.tsx:45-80
# TODO: check responsive breakpoints
</files.txt>
→ Parser extracts 3 valid paths, skips comment and blank lines, and prints warnings for any lines that are invalid paths (if any).
</example>
<example>
<settings.json>
{
  "output_dir": "context_output",
  "output_format": "txt",
  "model_count": 4,
  "gemini_judge": true,
  "compact_mode": true,
  "archive": true,
  "archive_dir": "models/ARCHIVE"
}
</settings.json>
→ Run uses these settings silently. If --interactive is passed, these settings act as the default choices.
</example>
<example>
<archive>
models/ARCHIVE/A_20260622_143022.txt exists → new file becomes A_20260622_143022_1.txt
</archive>
</example>
</examples>
<deliverable>
Update aggregator.py with: multi-file discovery, organized output folder, CLI flags (--interactive, --output, --settings), auto-notes, archive system, output format choice, model count choice, .context/settings.json support, and all edge case handling.
Update core/parser.py: .context/ignore support with default template, fallback check for root .contextignore, warning logic for invalid file entries in read_file_entries().
Update core/judge.py: auto-notes merging from notes files matching the target format.
Follow these quality guidelines:
1. Write clean, idiomatic Python code.
2. Maintain documentation integrity. Keep comments and docstrings.
3. Validate user preferences defensively.
4. Perform self-checks against the edge cases checklist before concluding.
</deliverable>

---
## Model prompt-feedback
### Response
Model 1 : "## Positive Feedback ✅
1. **Structure is excellent** — `<role>`, `<context>`, `<requirements>`, `<edge_cases>`, `<constraints>`, `<examples>`, `<deliverable>` is a clean hierarchy. Models will parse this reliably.
2. **Prioritized requirements** — High/medium/low helps models know where to focus effort and what to implement first.
3. **Edge cases are thorough** — You thought about timestamp collisions, invalid settings, missing API keys, old CWD files. Most prompts skip this entirely.
4. **Enter/Space pattern** — Creative and well-explained. The "doing nothing = skip" philosophy is consistent and intuitive.
5. **Settings.json** — Smart. Persistent config + `--interactive` override means the tool works both as a set-and-forget CLI and an interactive tool.
6. **Examples section** — The `files.txt` example with mixed comments and paths clarifies requirement 3 perfectly. The archive collision example is precise.
7. **Constraints are realistic** — "Don't break core/ APIs" and "backwards compatible" keep models from overhauling everything.
8. **Context section** — Explaining compact mode and project root detection upfront prevents models from reinventing or breaking existing behavior.

---
## Passive Feedback ⚠️
1. **Scope creep — archive system is overkill.** Requirements 4c/4d/4e (archive with timestamps, re-ask model count, collision handling) is a full feature on its own. It distracts from the core ask. Frontier models might spend 30% of tokens on archive logic instead of multi-file + output folder. **Consider moving to a separate prompt.**
2. **Requirements 4 and 8 overlap.** Settings.json stores `model_count`, `gemini_judge`, `compact_mode`, `archive` — but requirement 4 also defines interactive prompts for ALL of these. The model has to reconcile: "when does settings.json win vs interactive prompt?" This ambiguity will produce inconsistent implementations. **Add a resolution rule**, e.g.: `CLI flags > --interactive prompts > settings.json > defaults`.
3. **Requirement 3 is already done.** Current `read_file_entries()` already skips `#` comments and blank lines. The only new thing is "skip any line that doesn't look like a valid file path" — but that's dangerous (silently dropping typos). **Clarify: should invalid paths warn or silently skip?**
4. **Output format choice (.md vs .txt) is low-value complexity.** Requirement 4e adds a prompt, a settings key, a flag, and note-extension-matching logic — all for a file extension swap. **Consider dropping it or hardcoding `.md`.**
5. **Two dot-config systems is confusing.** `.contextignore` + `.context/settings.json` = two different config locations. Users will forget which goes where. **Consider merging into `.context/` only** — put `ignore` and `settings.json` both inside `.context/`.
6. **Mini-skill (requirement 9) is too vague.** "When user mentions 'context settings', help them" — this is a chat behavior, not a code requirement. Frontier models won't know what to build. **Either define a concrete CLI subcommand (`aggregator.py --setup`) or drop it.**
7. **Edge cases 5 and 8 reference interactive prompts in non-interactive context.** "Merge? [Enter=merge, Space=skip]" and "Clean? [Enter=clean, Space=skip]" only make sense in `--interactive` mode, but the default is non-interactive. **Specify: these prompts only appear with `--interactive`, otherwise default to merge/clean silently.**
8. **Deliverable asks for too many changes at once.** 4 files modified, 8+ features, edge case handling. This is 2-3 prompts worth of work. Frontier models may cut corners on the high-priority items trying to fit everything in their response. **Consider splitting into Phase 1 (reqs 1, 2, 4 partial, 7, 8) and Phase 2 (reqs 3, 5, 6, 9, archive).**
9. **No mention of `files.txt` naming convention for multi-file.** You say `files_1.txt`, `files_2.txt` in requirement 2 but `files_006.txt`, `files_007.txt` in your original message. **Pick one pattern and specify it explicitly** — e.g., `files.txt`, `files_NNN.txt` where NNN is zero-padded.
10. **`<current_code>` section is summaries, not code.** Models perform better with actual code snippets. You already have the full files listed in `files.txt` — the prompt says "read the attached files" but the `<current_code>` block just describes them. **Either paste key sections inline or trust that the aggregator output will be attached separately** (and say so explicitly)."
Model 2 : "This is an exceptionally well-crafted prompt. Using XML-style tags (`<role>`, `<requirements>`, `<edge_cases>`) is exactly how you get the best performance out of frontier models like Claude 3.5 Sonnet or GPT-4o.
Here is both the **positive feedback** (what you absolutely nailed) and the **constructive/passive feedback** (tiny logic gaps or areas where the AI might get confused).
### ✅ Positive Feedback (What makes this prompt top-tier)
1. **XML Tag Structure:** Frontier models are explicitly trained to parse `<context>`, `<requirements>`, and `<edge_cases>`. This guarantees the AI won't "forget" instructions halfway through.
2. **Explicit Edge Cases:** You didn't just ask for an archive system; you explicitly solved the "timestamp collision" and "missing API key" problems before the AI even had to guess. This will save you 2-3 debugging turns.
3. **The "Enter vs Space" Paradigm:** Standardizing the UI behavior and giving exact examples of the text strings (`[Enter=skip, Space=run]`) means the AI won't invent its own random CLI behavior.
4. **Settings Schema:** Providing the exact JSON schema (`{"output_dir": "...", ...}`) removes ambiguity about variable names and types.
5. **Clear Scope:** The `<deliverable>` section clearly bounds the AI. It tells it exactly which files to touch (`aggregator.py`, `core/parser.py`, `core/judge.py`) and warns it not to break existing APIs.
### 💡 Constructive/Passive Feedback (Areas to tweak before sending)
1. **Interactive vs. Non-Interactive Conflict in Edge Cases:**
   * *The Issue:* Requirement 4 says the script is NON-INTERACTIVE by default. However, Edge Case 5 asks `"Warn: Merge? [Enter=merge, Space=skip]"` and Edge Case 8 asks `"Warn: Clean? [Enter=clean, Space=skip]"`.
   * *The Fix:* You should specify what the tool does silently when `--interactive` is **not** passed. *(e.g., "If not interactive, default to auto-merging old output and auto-cleaning CWD without asking.")*
2. **Requirement 9 ("Mini-Skill"):**
   * *The Issue:* You wrote: *"When user mentions 'context settings', help them create/edit .context/settings.json."* The AI writing your Python code will be confused by this, because a Python script can't "listen" to what a user mentions in a chat.
   * *The Fix:* If you want the Python script to do this, change it to: *"Add a `--settings` CLI flag that prints the path to settings.json and explains how to edit it."* (If this is actually meant for the `SKILL.md` file rather than the Python code, remove it from this prompt).
3. **Archive Logic Clarity (Req 4):**
   * *The Issue:* "Re-ask model count from archived set." This phrasing is a bit ambiguous.
   * *The Fix:* Make the workflow literal for the AI: *"When archiving, move current A.txt, B.txt to ARCHIVE/ with timestamps, then clear the models/ directory and create fresh A.txt, B.txt based on the chosen model count."*
4. **Don't forget the actual code!**
   * Just a reminder: Your `<current_code>` section currently only contains descriptions of the files. Make sure when you actually send this to the model, you paste the *real* code of `aggregator.py`, `parser.py`, etc., below the prompt (or attach them as files as we prepared earlier).
**Final Verdict:** 9.5/10 prompt. If you clarify what happens to Edge Case 5 & 8 when `--interactive` is OFF, the model will write exactly what you want on the very first try."

---
## Verdict
- **Winner:**
- **Reasoning:**
  1.

---
*Generated by File Aggregator Tool*