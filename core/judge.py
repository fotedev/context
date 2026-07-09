"""Core judge module for the File Aggregator tool.
Handles Gemini AI judge integration, model response collection, notes
discovery, archiving, and comparison output generation.
"""
from __future__ import annotations

import abc
import asyncio
import json
import os
import re
import shutil
import sys
import urllib.error
import urllib.request
from datetime import datetime
from http.client import HTTPException, HTTPResponse
from pathlib import Path
from typing import cast

# ---------------------------------------------------------------------------
# .env loading
# ---------------------------------------------------------------------------


def load_dotenv(start_path: Path) -> None:
    """Simple parser to load .env file variables into os.environ."""
    current = start_path.resolve()
    while True:
        env_path = current / ".env"
        if env_path.is_file():
            try:
                with env_path.open("r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            key, val = line.split("=", 1)
                            _ = os.environ.setdefault(
                                key.strip(),
                                val.strip().strip('"').strip("'"),
                            )
            except OSError as e:
                print(
                    f"Warning: Failed to read .env at {env_path}: {e}",
                    file=sys.stderr,
                )
            break
        parent = current.parent
        if parent == current:
            break
        current = parent


# ---------------------------------------------------------------------------
# API key retrieval (Req 4 — non-interactive, Edge case 6)
# ---------------------------------------------------------------------------


def get_api_key(root_dir: Path | None = None) -> str | None:
    """Retrieve GEMINI_API_KEY from environment or .env files.

    Non-interactive: returns ``None`` if the key is not found.
    The caller should handle the missing-key case (e.g. print a warning
    and skip the judge step) — Edge case 6.

    The ``.env`` file is searched in three locations:
    1. The project root (*root_dir*).
    2. The current working directory.
    3. The tool's own root directory (where aggregator.py lives).

    Args:
        root_dir: Optional project root to search for a ``.env`` file.

    Returns:
        The API key string, or ``None`` if not found.
    """
    if root_dir:
        load_dotenv(root_dir)
    load_dotenv(Path.cwd())
    load_dotenv(Path(__file__).parent.parent)  # tool root directory
    api_key = os.environ.get("GEMINI_API_KEY")
    if api_key:
        return api_key
    print(
        "Warning: GEMINI_API_KEY not found in environment or .env files."
        " Skipping Gemini AI Judge.",
        file=sys.stderr,
    )
    return None


# ---------------------------------------------------------------------------
# Gemini AI Judge
# ---------------------------------------------------------------------------


class BaseJudge(abc.ABC):
    """Abstract base class defining the contract for AI Judges."""

    @abc.abstractmethod
    async def evaluate(
        self, prompt: str, models_data: list[dict[str, str]], api_key: str
    ) -> str:
        """Asynchronously evaluate model responses and return a Markdown verdict."""
        pass

class GeminiJudge(BaseJudge):
    """Gemini-based AI Judge implementation using non-blocking threaded I/O."""

    async def evaluate(
        self, prompt: str, models_data: list[dict[str, str]], api_key: str
    ) -> str:
        eval_prompt = self._build_prompt(prompt, models_data)

        url = (
            "https://generativelanguage.googleapis.com/v1beta/"
            f"models/gemini-2.5-flash:generateContent?key={api_key}"
        )
        data = {
            "contents": [
                {"parts": [{"text": eval_prompt}]}
            ]
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(data).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        def _blocking_request() -> str:
            print("Sending comparison request to Gemini Flash API...")
            try:
                with cast(HTTPResponse, urllib.request.urlopen(req, timeout=45)) as response:
                    res_bytes = response.read()
                    res_str = res_bytes.decode("utf-8")
                    res_data = cast(dict[str, object], json.loads(res_str))
                    candidates = cast(list[dict[str, object]], res_data.get("candidates", []))
                    if not candidates:
                        raise RuntimeError("Gemini API response has no candidates.")
                    first_candidate = candidates[0]
                    content = cast(dict[str, object], first_candidate.get("content", {}))
                    parts = cast(list[dict[str, object]], content.get("parts", []))
                    if not parts:
                        raise RuntimeError("Gemini API response candidate has no parts.")
                    return cast(str, parts[0].get("text", ""))
            except (urllib.error.URLError, HTTPException, OSError, ValueError, TimeoutError) as exc:
                raise RuntimeError(f"Gemini API request failed: {exc}") from exc

        return await asyncio.to_thread(_blocking_request)

    def _build_prompt(self, prompt: str, models_data: list[dict[str, str]]) -> str:
        eval_prompt = (
            "You are an expert software engineer and AI model evaluator.\n"
            "Your task is to analyze the following user prompt and compare "
            "the responses from different AI models.\n"
            "Determine the winner, rank the model responses from best to worst, "
            "point out the strengths and weaknesses of each, and provide a clear, "
            "technical reason for your verdict.\n\n"
            f"[User Prompt]\n{prompt}\n\n"
        )
        for model in models_data:
            eval_prompt += (
                f"\n\n==================== RESPONSE FROM "
                f"{model['name'].upper()} ====================\n"
            )
            eval_prompt += f"{model['response']}\n"
            eval_prompt += (
                f"==================== END OF RESPONSE FROM "
                f"{model['name'].upper()} ====================\n"
            )
        eval_prompt += (
            "\nPlease output your evaluation in Markdown format."
            " Your evaluation must be thorough and include:\n"
            "1. **Summary Table**: Compare the models across key dimensions"
            " (e.g. correctness, completeness, formatting, explanation quality).\n"
            "2. **Key Analysis**: A detailed review of the differences in the"
            " code, approach, or explanations.\n"
            "3. **Winner & Ranking**: Define a clear winner (or \"Tie\"), rank all"
            " the compared models from best to worst (e.g., 1st, 2nd, 3rd, etc.)"
            " with brief justifications, and explain why technically"
            " (e.g. why one code structure is better or handles edge cases better).\n"
            "4. **Optimal Merged Solution**: Synthesize a blueprint/strategy that"
            " combines all the advantages and best practices of the compared models"
            " while avoiding all their weaknesses and edge cases.\n"
            "5. **Prompt for the Coding Agent**: Write a precise, copy-pasteable"
            " prompt that the user can send to their AI coding agent"
            " (like Cursor, Windsurf, or Copilot) instructing it to implement"
            " the combined optimal solution based on the strengths of the analyzed models.\n"
            "Output the markdown content directly."
            " Do not wrap your response in an outer ```markdown block.\n"
        )
        return eval_prompt


# ---------------------------------------------------------------------------
# Model response collection (with notes support — Req 6, Edge case 7)
# ---------------------------------------------------------------------------


def collect_model_responses(
    arena_dir: Path,
    output_format: str = "md",
    model_count: int = 2,
) -> tuple[str, list[dict[str, str]]]:
    """Read model responses from a v3-prefixed flat arena directory.

    The v3-prefixed flat layout puts ``NNN-prompt.txt``, ``NNN-A.txt``,
    ``NNN-B.txt``, ... directly inside the arena directory — every file
    carries the arena's ``NNN-`` prefix. For each model file found
    (e.g. ``003-A.txt``), also checks for a corresponding notes file
    whose extension matches *output_format* (e.g. ``003-A_NOTES.md`` when
    *output_format* is ``"md"``). Notes content is stored in the
    ``"notes"`` key of each model dict — Edge case 7.

    Falls back to parsing ``llm.txt`` (at the arena's parent directory
    or CWD) if no model responses are found.

    Args:
        arena_dir: Arena directory containing prefixed ``NNN-prompt.txt`` /
                   ``NNN-A.txt`` / ``NNN-B.txt`` files.
        output_format: Extension for notes matching (``"md"`` or ``"txt"``).
        model_count: Number of model files to consider (A..).

    Returns:
        Tuple of ``(prompt_text, models_data)`` where each entry in
        *models_data* has keys ``name``, ``response``, and ``notes``.
    """
    from core.arena import arena_filenames, arena_model_filename

    llm_txt = arena_dir.parent.parent / "llm.txt"
    if not llm_txt.is_file():
        llm_txt = arena_dir.parent / "llm.txt"
    if not llm_txt.is_file():
        llm_txt = Path.cwd() / "llm.txt"

    filenames = arena_filenames(arena_dir, output_format)
    prompt_file = filenames["prompt"]

    prompt = ""
    if prompt_file.is_file():
        prompt = prompt_file.read_text(encoding="utf-8").strip()

    models_data: list[dict[str, str]] = []
    notes_ext = f".{output_format}"

    for i in range(model_count):
        letter = chr(ord("A") + i)
        model_file = arena_model_filename(arena_dir, letter)
        if not model_file.is_file():
            continue

        response = model_file.read_text(encoding="utf-8").strip()
        if not response:
            response = "[NO RESPONSE PROVIDED - FILE EMPTY]"

        name = f"Model {letter}"

        # Look for prefixed notes file matching the output format
        # (Req 6, EC7). Prefix mirrors the model-response filename.
        notes = ""
        prefix = arena_dir.name.partition("-")[0]
        notes_file = arena_dir / f"{prefix}-{letter}_NOTES{notes_ext}"
        if notes_file.is_file():
            notes = notes_file.read_text(encoding="utf-8").strip()

        models_data.append(
            {"name": name, "response": response, "notes": notes}
        )

    if models_data:
        return prompt, models_data

    if llm_txt.is_file():
        return _parse_llm_file(llm_txt)

    return "", []


def _parse_llm_file(llm_file: Path) -> tuple[str, list[dict[str, str]]]:
    """Parse legacy llm.txt with === markers into (prompt, models_data)."""
    content = llm_file.read_text(encoding="utf-8")
    prompt = ""
    models_data: list[dict[str, str]] = []

    sections = re.split(r"^===([A-Z:]+)===\s*$", content, flags=re.MULTILINE)

    i = 1
    while i < len(sections):
        marker = sections[i].strip()
        body = sections[i + 1].strip() if i + 1 < len(sections) else ""

        if marker == "PROMPT":
            prompt = body
        elif marker.startswith("MODEL:"):
            name = marker[len("MODEL:") :].strip()
            if not name:
                name = str(len(models_data) + 1)
            if not name.lower().startswith("model"):
                name = f"Model {name}"
            models_data.append(
                {"name": name, "response": body, "notes": ""}
            )

        i += 2

    return prompt, models_data


# ---------------------------------------------------------------------------
# Compare output generation (Req 6 — notes, compact mode)
# ---------------------------------------------------------------------------


def build_compare_markdown(
    prompt: str,
    models_data: list[dict[str, str]],
    output_file: Path,
    verdict: str | None = None,
    compact: bool = False,
) -> None:
    """Build and write the compare output from parsed LLM data.

    **Notes** (Req 6): If a model dict contains a non-empty ``notes``
    value and *compact* is ``False``, a ``### Notes`` section is
    inserted below that model's response.  If no notes exist, the
    section is omitted entirely.

    **Compact mode**: Removes Notes sections, collapses blank lines,
    and trims trailing whitespace — token saver for LMArena.

    Args:
        prompt: The user prompt text.
        models_data: List of dicts with ``name``, ``response``, ``notes``.
        output_file: Destination file path.
        verdict: Optional Gemini AI judge verdict text.
        compact: If True, removes Notes sections, collapses blank lines,
                 and trims trailing whitespace.
    """
    is_txt = output_file.suffix.lower() == ".txt"

    if is_txt:
        lines: list[str] = [
            f"Model Comparison (LMArena Style - {len(models_data)} Models)",
            "",
            "The Prompt:",
            prompt if prompt else "[No prompt provided]",
        ]
        if not compact:
            lines.append("")

        for data in models_data:
            response = data["response"].strip()
            notes = data.get("notes", "").strip()

            if compact:
                response = re.sub(r"\n\s*\n+", "\n", response)

            lines.append("=========================================")
            lines.append(data["name"])
            lines.append("Response:")
            lines.append(response)

            if not compact:
                lines.append("")
                # Only include Notes section when notes content exists (Req 6)
                if notes:
                    lines.append("Notes:")
                    lines.append(notes)
                    lines.append("")

        lines.append("=========================================")
        lines.append("Verdict:")
        if verdict:
            lines.append(verdict)
        else:
            lines.append("Winner: ")
            lines.append("Reasoning: ")
            lines.append("  1. ")

        if not compact:
            lines.append("")

        lines.append("=========================================")
        lines.append("Generated by File Aggregator Tool")
    else:
        # Markdown (.md)
        lines = [
            f"# Model Comparison (LMArena Style - {len(models_data)} Models)",
            "",
            "## The Prompt",
            f"> {prompt}" if prompt else "> [No prompt provided]",
        ]
        if not compact:
            lines.append("")

        for data in models_data:
            response = data["response"].strip()
            notes = data.get("notes", "").strip()

            if compact:
                response = re.sub(r"\n\s*\n+", "\n", response)

            lines.append("---")
            lines.append(f"## {data['name']}")
            lines.append("### Response")
            lines.append(response)

            if not compact:
                lines.append("")
                # Only include Notes section when notes content exists (Req 6)
                if notes:
                    lines.append("### Notes")
                    lines.append(notes)
                    lines.append("")

        lines.append("---")
        lines.append("## Verdict")
        if verdict:
            lines.append(verdict)
        else:
            lines.append("- **Winner:** ")
            lines.append("- **Reasoning:** ")
            lines.append("  1. ")

        if not compact:
            lines.append("")

        lines.append("---")
        lines.append("*Generated by File Aggregator Tool*")

    content = "\n".join(lines)

    if compact:
        # Compact: collapse consecutive blank lines, trim trailing whitespace
        content = re.sub(r"\n{2,}", "\n", content)
        content = re.sub(r"[ \t]+$", "", content, flags=re.MULTILINE)

    # Ensure output directory exists
    output_file.parent.mkdir(parents=True, exist_ok=True)
    _ = output_file.write_text(content, encoding="utf-8")


def generate_compare_template(
    output_file: Path, model_count: int = 2
) -> None:
    """Generate a template for model comparison (LMArena style).

    Args:
        output_file: Destination file path.
        model_count: Number of model sections to include in the template.
    """
    is_txt = output_file.suffix.lower() == ".txt"

    if is_txt:
        lines = [
            "Model Comparison (LMArena Style)",
            "",
            "Instructions:",
            "1. Use this document to compare outputs from different LLMs.",
            "2. Paste the responses in the designated sections.",
            "3. Vote for the winner based on accuracy, formatting, and instruction following.",
            "",
            "=========================================",
            "",
            "The Prompt:",
            "[Paste your prompt here]",
            "",
        ]

        for i in range(model_count):
            letter = chr(ord("A") + i)
            lines.extend(
                [
                    "=========================================",
                    "",
                    f"Model {letter}",
                    "Response:",
                    f"[Paste Response from Model {letter}]",
                    "",
                    "Notes:",
                    "- ",
                    "- ",
                    "",
                ]
            )

        lines.extend(
            [
                "=========================================",
                "",
                "Verdict:",
                "Winner: [Model A / Model B / Tie]",
                "Reasoning: ",
                "  1. ",
                "  2. ",
                "",
                "=========================================",
                "Generated by File Aggregator Tool",
            ]
        )
    else:
        # Markdown (.md)
        lines = [
            "# Model Comparison (LMArena Style)",
            "",
            "## Instructions",
            "1. Use this document to compare outputs from different LLMs.",
            "2. Paste the responses in the designated sections.",
            "3. Vote for the winner based on accuracy, formatting, and instruction following.",
            "",
            "---",
            "",
            "## The Prompt",
            "> [Paste your prompt here]",
            "",
        ]

        for i in range(model_count):
            letter = chr(ord("A") + i)
            lines.extend(
                [
                    "---",
                    "",
                    f"## Model {letter}",
                    "### Response",
                    f"[Paste Response from Model {letter}]",
                    "",
                    "### Notes",
                    "- ",
                    "- ",
                    "",
                ]
            )

        lines.extend(
            [
                "---",
                "",
                "## Verdict",
                "- **Winner:** [Model A / Model B / Tie]",
                "- **Reasoning:** ",
                "  1. ",
                "  2. ",
                "",
                "---",
                "*Generated by File Aggregator Tool*",
            ]
        )

    # Ensure output directory exists
    output_file.parent.mkdir(parents=True, exist_ok=True)
    _ = output_file.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# Archiving workflow (Req 5, Edge case 4)
# ---------------------------------------------------------------------------


def archive_model_responses(
    arena_dir: Path,
    archive_dir: str = "ARCHIVE",
) -> list[Path]:
    """Archive current model responses by copying them to *archive_dir* and
    clearing the active templates from the v3-prefixed flat arena directory.

    The v3-prefixed flat layout puts ``NNN-A.txt``, ``NNN-B.txt``, ``NNN-prompt.txt``
    directly inside *arena_dir*; archived copies are written to
    ``<arena_dir>/<archive_dir>/`` by default (or wherever the
    user-configured *archive_dir* resolves to).

    Copies active responses and notes with a timestamp suffix
    (e.g. ``003-A_YYYYMMDD_HHMMSS.txt``) and then deletes the active templates.

    Args:
        arena_dir: Arena directory whose prefixed model files are archived.
        archive_dir: Archive subfolder name (relative to *arena_dir*) or
            absolute path.

    Returns:
        List of paths that were cleared (copies live in *archive_dir*).
    """
    if not arena_dir.is_dir():
        print(
            f"Warning: arena directory not found at {arena_dir} — "
            "nothing to archive.",
            file=sys.stderr,
        )
        return []

    # Resolve archive_dir path dynamically.
    archive_path = Path(archive_dir)
    if archive_path.is_absolute():
        resolved_archive_dir = archive_path
    else:
        # If the path starts with "models" or "answers", strip it first to
        # avoid creating a nested models/ARCHIVE/ path.
        parts = list(archive_path.parts)
        if parts and parts[0] in ("models", "answers"):
            resolved_archive_dir = arena_dir / Path(*parts[1:])
        else:
            resolved_archive_dir = arena_dir / archive_path

    cleared: list[Path] = []

    # Identify prefixed model-response files and prefixed NOTES files.
    # v3 prefix pattern: ``NNN-A.txt`` where NNN is the arena's numeric
    # prefix (3 digits). Match the prefix dynamically so ``003-A.txt``,
    # ``003-B_NOTES.md`` etc. all qualify.
    prefix = arena_dir.name.partition("-")[0]
    if not prefix.isdigit():
        print(
            f"Warning: arena directory {arena_dir.name} has no numeric "
            "prefix — cannot archive.",
            file=sys.stderr,
        )
        return []

    model_re = re.compile(rf"^{re.escape(prefix)}-[A-Z]\.txt$")
    notes_re = re.compile(rf"^{re.escape(prefix)}-[A-Z]_NOTES\.(txt|md)$")
    # Also include the prefixed prompt file so its current content is
    # archived alongside the model responses (mirrors legacy behaviour).
    prompt_re = re.compile(rf"^{re.escape(prefix)}-prompt\.txt$")

    files_to_archive: list[Path] = []
    for f in arena_dir.iterdir():
        if not f.is_file():
            continue
        if model_re.match(f.name) or notes_re.match(f.name) or prompt_re.match(f.name):
            files_to_archive.append(f)

    if not files_to_archive:
        return []

    # Ensure archive directory exists
    resolved_archive_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # 1. Copy files to the archive directory
    for f in files_to_archive:
        stem = f.stem
        suffix = f.suffix
        dest_name = f"{stem}_{timestamp}{suffix}"
        dest_path = resolved_archive_dir / dest_name

        # Handle collision (append _1, _2, etc.)
        counter = 1
        while dest_path.exists():
            dest_name = f"{stem}_{timestamp}_{counter}{suffix}"
            dest_path = resolved_archive_dir / dest_name
            counter += 1

        try:
            shutil.copy2(f, dest_path)
        except OSError as e:
            print(
                f"Warning: Could not archive {f.name} to {dest_path} - {e}",
                file=sys.stderr,
            )

    # 2. Safely unlink active templates after copying
    for f in files_to_archive:
        try:
            f.unlink()
            cleared.append(f)
            print(f"Cleared active model file: {f.name}")
        except OSError as e:
            print(f"Warning: Could not clear {f.name} - {e}", file=sys.stderr)

    return cleared


# ---------------------------------------------------------------------------
# Model template management (Req 7, Edge case 3)
# ---------------------------------------------------------------------------


def ensure_model_templates(
    arena_dir: Path,
    model_count: int = 2,
) -> list[str]:
    """Ensure model template files exist in the v3-prefixed flat arena dir.

    Creates empty ``NNN-A.txt``, ``NNN-B.txt``, ... files inside *arena_dir*
    for every configured model letter that doesn't already have a file.
    Edge case 3: ``model_count=4`` but only ``NNN-A.txt`` exists → create
    empty ``NNN-B.txt``, ``NNN-C.txt``, ``NNN-D.txt``.

    Args:
        arena_dir: Arena directory (its name must start with ``NNN-``).
        model_count: Number of model files to ensure exist.

    Returns:
        List of letters for newly created files (e.g. ``['B', 'C', 'D']``).
    """
    from core.arena import arena_model_filename

    if not arena_dir.is_dir():
        arena_dir.mkdir(parents=True, exist_ok=True)

    prefix = arena_dir.name.partition("-")[0]
    model_re = re.compile(rf"^{re.escape(prefix)}-[A-Z]\.txt$")

    # Detect existing model response files (by letter).
    existing: set[str] = set()
    for f in arena_dir.iterdir():
        if f.is_file():
            m = model_re.match(f.name)
            if m:
                # Strip prefix to get the letter.
                existing.add(m.group(0).rsplit("-", 1)[-1][0])

    created: list[str] = []
    for i in range(model_count):
        letter = chr(ord("A") + i)
        if letter not in existing:
            model_file = arena_model_filename(arena_dir, letter)
            model_file.touch()
            created.append(letter)

    if created:
        names = ", ".join(f"{prefix}-{c}.txt" for c in created)
        print(
            f"Created empty {names}. Please paste their responses."
        )

    return created
