"""Project-root detection + ``.env`` bootstrap for the server.

The ``.env`` file lives in the **tool root** (where ``aggregator.py`` lives),
NOT the project root — matching edge case 6 from the spec. A missing
``GEMINI_API_KEY`` never crashes; it just disables the Gemini judge step.
"""

import os
import sys
from pathlib import Path

from dotenv import dotenv_values

# Tool root = repo root containing aggregator.py + core/ + gui/
TOOL_ROOT = Path(__file__).resolve().parents[2]
if str(TOOL_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOL_ROOT))


def get_tool_root() -> Path:
    """Return the directory the context tool package is installed/run from."""
    return TOOL_ROOT


def get_project_root() -> Path:
    """Detect the project root the server should operate on.

    Strategy (mirrors the CLI's behaviour in ``aggregator.py``):
      1. Read the first file path from ``.context/inputs/*.txt`` or CWD
         ``files.txt`` and run ``core.parser.find_project_root`` on it.
      2. Fall back to walking up from CWD looking for root markers.
      3. Final fallback: CWD.
    """
    from core.parser import find_project_root, read_file_entries  # type: ignore

    cwd = Path.cwd()

    # 1. Try the first entry from any input file.
    candidate_inputs: list[Path] = []
    inputs_dir = cwd / ".context" / "inputs"
    if inputs_dir.is_dir():
        candidate_inputs.extend(sorted(inputs_dir.glob("*.txt")))
    cwd_files = cwd / "files.txt"
    if cwd_files.is_file():
        candidate_inputs.append(cwd_files)

    for inp in candidate_inputs:
        try:
            entries = read_file_entries(inp)
        except (OSError, Exception):  # noqa: BLE001 — best-effort detection
            entries = []
        if entries:
            root = find_project_root(entries[0][0])
            if root is not None:
                return root

    # 2. Walk up from CWD looking for markers directly.
    root = find_project_root(cwd / "_probe")
    if root is not None:
        return root

    # 3. Final fallback.
    return cwd


def bootstrap_env() -> Path:
    """Ensure ``.env`` exists in the tool root (edge case 6).

    Returns the path to the ``.env`` file.
    """
    env_path = TOOL_ROOT / ".env"
    if not env_path.exists():
        env_path.write_text(
            "# Environment variables for context tool\nGEMINI_API_KEY=\n",
            encoding="utf-8",
        )
    return env_path


def get_gemini_key() -> bool:
    """Check whether ``GEMINI_API_KEY`` is set (tool-root ``.env`` or environ).

    Returns ``True`` if a non-empty key is present. Never raises.
    """
    env_path = TOOL_ROOT / ".env"
    env_vars = dotenv_values(env_path)
    key = env_vars.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")
    return bool(key and key.strip())


def set_gemini_key(api_key: str) -> None:
    """Write ``GEMINI_API_KEY`` into the tool-root ``.env`` file."""
    env_path = TOOL_ROOT / ".env"
    lines: list[str] = []
    found = False
    if env_path.exists():
        lines = env_path.read_text(encoding="utf-8").splitlines()
        for i, line in enumerate(lines):
            if line.startswith("GEMINI_API_KEY="):
                lines[i] = f"GEMINI_API_KEY={api_key}"
                found = True
                break
    if not found:
        lines.append(f"GEMINI_API_KEY={api_key}")
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
