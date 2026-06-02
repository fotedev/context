# ContextForge - Organized Features

A prioritized list of features for the ContextForge tool (a CLI/GUI tool that aggregates code context for LLMs with a Gemini AI Judge).

## Tier 1: Critical (Core Foundation)

These features are essential and form the backbone of the product.

1. **Local Python Server (FastAPI)**
   - Runs on `localhost:8080` (or similar port)
   - Serves `arena.txt` content to consumers
   - Health check endpoint
   - CORS configured to allow only the extension ID
   - **Why critical:** Foundation for the browser extension and any other interface that needs to consume context remotely.

2. **Browser Extension (Chrome Manifest V3)**
   - Content Script auto-injects context into LLM sites (LMArena, ChatGPT, Claude)
   - Detects the active LLM provider and pastes in the correct field
   - Uses `nativeInputValueSetter` + dispatched `input` event to bypass React/Vue controlled inputs
   - **Why critical:** This is the main UX differentiator. Transforms the tool from "developer utility" to "one-click product."

3. **Auto-Paste (Zero-Click Experience)**
   - On page load, fetch context from local server and paste into the active textarea
   - Optional: auto-click submit button
   - **Why critical:** Core value proposition; eliminates copy/paste friction.

4. **Core CLI (`agg`)**
   - File aggregation engine (reads `files.txt`)
   - Generates `structure.txt` (project tree)
   - Token counting with `tiktoken`
   - Produces `arena.txt`
   - **Why critical:** This is the original tool and the source of truth that all other interfaces consume.

5. **Gemini AI Judge (Model Comparison)**
   - Takes two model responses and evaluates them
   - Outputs verdict in `compare.md`
   - Uses user's own `GEMINI_API_KEY` (no server cost)
   - **Why critical:** Signature feature that justifies the product's existence.

## Tier 2: High Value (Major UX Improvements)

6. **Watch Mode (`agg --watch`)**
   - Server monitors file changes
   - On save (Ctrl+S), auto-rebuilds `arena.txt`
   - Extension auto-refreshes the pasted context
   - **Why high value:** Eliminates repeated manual rebuilds. Alone justifies a Pro tier.

7. **TUI (Terminal UI)**
   - Interactive terminal interface for users who prefer keyboard navigation
   - Uses the same core logic as CLI
   - **Why high value:** Captures "terminal junkie" developer segment.

8. **GUI (Graphical UI)**
   - File picker, visual structure tree, token visualization
   - Window-based interaction
   - **Why high value:** Lowers barrier for non-terminal users; great for marketing screenshots.

9. **Smart Clipboard (Auto-Copy)**
   - After `agg` runs, automatically copy `arena.txt` to OS clipboard
   - Print "Context copied! Ready to paste."
   - **Why high value:** 5-minute implementation with instant UX win for users who skip the extension.

10. **Two-Way Sync (Export Code)**
    - Extension reads AI response from the page
    - Sends generated code to local server
    - Server creates the actual files in the project folder
    - **Why high value:** "Killer feature" for Pro tier. Solves the reverse pain point (AI output back to disk).

## Tier 3: Power User Features

11. **Smart Auto-Context (Git-based)**
    - `agg-smart` command
    - Reads `git diff` / staged files automatically
    - Zero configuration required
    - **Why valuable:** Removes the need to maintain `files.txt`.

12. **Direct API Mode (Bypass Browser)**
    - User puts OpenAI/Anthropic keys in `.env`
    - `agg --arena` sends context to both models directly
    - Gemini judges, output printed to terminal + `compare.md`
    - **Why valuable:** Power users who don't want to use a browser at all.

13. **Auto-Judge**
    - Extension reads both model responses after they finish
    - Sends them to the local server
    - Server returns Gemini's verdict as a browser notification
    - **Why valuable:** Closes the loop fully automatically.

14. **VS Code Extension**
    - Right-click in VS Code → "Add to Context"
    - Replaces manual `files.txt` editing
    - Connects to the same local server
    - **Why valuable:** More natural integration point for developers than a browser.

15. **Multi-Provider Support**
    - Extension detects which LLM site is active (LMArena, ChatGPT, Claude, Gemini)
    - Knows the correct textarea selector for each
    - **Why valuable:** Removes per-site manual config.

## Tier 4: Nice-to-Have (Polish & Quality of Life)

16. **Prompt Snippets Library**
    - Predefined prompts: "Refactor", "Find bugs", "Write tests"
    - Dropdown in extension adds the prompt above the pasted context
    - **Why nice:** Saves typing; makes the tool feel like a personal assistant.

17. **HTML Report Export**
    - Beautiful, interactive HTML file with side-by-side comparison
    - Syntax highlighting, token counts, verdict
    - **Why nice:** Visual output; shareable artifacts.

18. **Cost Calculator**
    - Estimates API cost based on token count and selected model
    - **Why nice:** Helps users budget their AI usage.

19. **Incremental Aggregation via Git**
    - Only re-aggregates changed files
    - Faster rebuilds for large projects
    - **Why nice:** Performance optimization.

## Tier 5: Monetization Infrastructure

20. **License Key System**
    - `agg-activate xxxx-xxxx-xxxx-xxxx`
    - Verifies key via LemonSqueezy API
    - Stores in hidden `.context_license` file
    - Unlocks Pro features (GUI, TUI, AI Judge, Extension)
    - **Why needed:** Required to actually sell the Pro version.

## Suggested Work Order

1. Stabilize CLI + ensure `core` logic is framework-agnostic (Headless Architecture)
2. Add Smart Clipboard (quick win)
3. Build Local FastAPI Server
4. Build Chrome Extension with Auto-Paste
5. Add Watch Mode
6. Build TUI and GUI
7. Implement License Key system
8. Add Two-Way Sync, Smart Auto-Context, Direct API Mode (Pro tier)
9. Ship VS Code Extension, HTML Reports, Prompt Library
