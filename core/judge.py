import os
import sys
import json
import urllib.request
import re
from pathlib import Path
from typing import List, Optional, Tuple

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
                            os.environ[key.strip()] = val.strip().strip('"').strip("'")
            except Exception as e:
                print(f"Warning: Failed to read .env at {env_path}: {e}", file=sys.stderr)
            break
        parent = current.parent
        if parent == current:
            break
        current = parent

def get_api_key(root_dir: Optional[Path] = None) -> Optional[str]:
    """Retrieve GEMINI_API_KEY from environment, .env, or prompt the user."""
    if root_dir:
        load_dotenv(root_dir)
    load_dotenv(Path.cwd())
    load_dotenv(Path(__file__).parent.parent) # check aggregator folder
    
    api_key = os.environ.get("GEMINI_API_KEY")
    if api_key:
        return api_key

    # Prompt user in terminal
    print("\n[Gemini AI Judge] GEMINI_API_KEY not found in environment or .env files.")
    try:
        key_input = input("Please enter your GEMINI_API_KEY (or press Enter to skip): ").strip()
        if not key_input:
            return None
        
        # Ask if they want to save it
        save_input = input("Would you like to save this key to a .env file in the aggregator directory? [y/N]: ").strip().lower()
        if save_input == 'y':
            script_dir = Path(__file__).resolve().parent.parent
            env_path = script_dir / ".env"
            try:
                with env_path.open("a", encoding="utf-8") as f:
                    f.write(f"\nGEMINI_API_KEY={key_input}\n")
                print(f"API key successfully saved to {env_path}")
            except Exception as e:
                print(f"Error saving to .env: {e}", file=sys.stderr)
                
        os.environ["GEMINI_API_KEY"] = key_input
        return key_input
    except (KeyboardInterrupt, EOFError):
        print("\nSkipping Gemini AI Judge.")
        return None

def get_gemini_verdict(prompt: str, models_data: List[dict], api_key: str) -> str:
    """Call Gemini Flash API to compare the model responses and return evaluation markdown."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    
    eval_prompt = f"""You are an expert software engineer and AI model evaluator.
Your task is to analyze the following user prompt and compare the responses from different AI models.
Determine the winner, rank the model responses from best to worst, point out the strengths and weaknesses of each, and provide a clear, technical reason for your verdict.

[User Prompt]
{prompt}

"""
    for model in models_data:
        eval_prompt += f"\n\n==================== RESPONSE FROM {model['name'].upper()} ====================\n"
        eval_prompt += f"{model['response']}\n"
        eval_prompt += f"==================== END OF RESPONSE FROM {model['name'].upper()} ====================\n"

    eval_prompt += """
Please output your evaluation in Markdown format. Your evaluation must be thorough and include:
1. **Summary Table**: Compare the models across key dimensions (e.g. correctness, completeness, formatting, explanation quality).
2. **Key Analysis**: A detailed review of the differences in the code, approach, or explanations.
3. **Winner & Ranking**: Define a clear winner (or "Tie"), rank all the compared models from best to worst (e.g., 1st, 2nd, 3rd, etc.) with brief justifications, and explain why technically (e.g. why one code structure is better or handles edge cases better).
4. **Optimal Merged Solution**: Synthesize a blueprint/strategy that combines all the advantages and best practices of the compared models while avoiding all their weaknesses and edge cases.
5. **Prompt for the Coding Agent**: Write a precise, copy-pasteable prompt that the user can send to their AI coding agent (like Cursor, Windsurf, or Copilot) instructing it to implement the combined optimal solution based on the strengths of the analyzed models.

Output the markdown content directly. Do not wrap your response in an outer ```markdown block.
"""

    data = {
        "contents": [
            {
                "parts": [
                    {
                        "text": eval_prompt
                    }
                ]
            }
        ]
    }
    
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    
    try:
        print("Sending comparison request to Gemini Flash API...")
        with urllib.request.urlopen(req, timeout=45) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            verdict = res_data["candidates"][0]["content"]["parts"][0]["text"]
            return verdict
    except Exception as exc:
        raise RuntimeError(f"Gemini API request failed: {exc}")

def collect_model_responses(root: Optional[Path]) -> Tuple[str, List[dict]]:
    """Auto-discover model responses from the models/ directory."""
    target_root = root if root is not None else Path.cwd()
    models_dir = target_root / "models"
    llm_txt = target_root / "llm.txt"

    if models_dir.is_dir():
        prompt = ""
        prompt_file = models_dir / "prompt.txt"
        if prompt_file.is_file():
            prompt = prompt_file.read_text(encoding="utf-8").strip()

        models_data: List[dict] = []
        for f in sorted(models_dir.iterdir()):
            if f.name == "prompt.txt" or not f.is_file():
                continue
            
            response = f.read_text(encoding="utf-8").strip()
            if not response:
                continue

            name = f.stem
            if not name.lower().startswith("model"):
                name = f"Model {name}"
            
            models_data.append({"name": name, "response": response})

        if models_data:
            return prompt, models_data

    if llm_txt.is_file():
        return _parse_llm_file(llm_txt)

    return "", []

def _parse_llm_file(llm_file: Path) -> Tuple[str, List[dict]]:
    """Parse legacy llm.txt with === markers into (prompt, models_data)."""
    content = llm_file.read_text(encoding="utf-8")
    prompt = ""
    models_data: List[dict] = []

    sections = re.split(r"^===([A-Z:]+)===\s*$", content, flags=re.MULTILINE)

    i = 1
    while i < len(sections):
        marker = sections[i].strip()
        body = sections[i + 1].strip() if i + 1 < len(sections) else ""

        if marker == "PROMPT":
            prompt = body
        elif marker.startswith("MODEL:"):
            name = marker[len("MODEL:"):].strip()
            if not name:
                name = str(len(models_data) + 1)
            
            if not name.lower().startswith("model"):
                name = f"Model {name}"
                
            models_data.append({"name": name, "response": body})

        i += 2

    return prompt, models_data

def build_compare_markdown(
    prompt: str, models_data: List[dict], output_file: Path, verdict: Optional[str] = None, compact: bool = False
) -> None:
    """Build and write the compare.md from parsed LLM data."""
    md = [f"# Model Comparison (LMArena Style - {len(models_data)} Models)", ""]
    md.append("## The Prompt")
    md.append(f"> {prompt}" if prompt else "> [No prompt provided]")
    
    if not compact:
        md.append("")

    for data in models_data:
        response = data["response"].strip()
        if compact:
            response = re.sub(r'\n\s*\n+', '\n', response)

        md.append("---")
        md.append(f"## {data['name']}")
        md.append("### Response")
        md.append(response)
        
        if not compact:
            md.append("")
            md.append("### Notes")
            md.append("- ")
            md.append("")

    md.append("---")
    md.append("## Verdict")
    if verdict:
        md.append(verdict)
    else:
        md.append("- **Winner:** ")
        md.append("- **Reasoning:** ")
        md.append("  1. ")
    
    if not compact:
        md.append("")
    
    md.append("---")
    md.append("*Generated by File Aggregator Tool*")

    content = "\n".join(md)
    if compact:
        content = re.sub(r'\n---\n', '\n---\n', content)
        content = re.sub(r'\n+', '\n', content)
        content = re.sub(r'(\n---)', r'\n\1', content)
        content = re.sub(r'[ \t]+$', '', content, flags=re.MULTILINE)

    output_file.write_text(content, encoding="utf-8")

def generate_compare_template(output_file: Path) -> None:
    """Generate a markdown template for model comparison (LMArena style)."""
    template = """# Model Comparison (LMArena Style)

## Instructions
1. Use this document to compare outputs from different LLMs.
2. Paste the responses in the designated sections.
3. Vote for the winner based on accuracy, formatting, and instruction following.

---

## The Prompt
> [Paste your prompt here]

---

## Model A
### Response
[Paste Response from Model A]

### Notes
- 
- 

---

## Model B
### Response
[Paste Response from Model B]

### Notes
- 
- 

---

## Verdict
- **Winner:** [Model A / Model B / Tie]
- **Reasoning:** 
  1. 
  2. 

---
*Generated by File Aggregator Tool*
"""
    output_file.write_text(template, encoding="utf-8")
