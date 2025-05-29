import httpx
from cyclopts import App
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass
import re
from datetime import datetime
from rich.console import Console
from rich.table import Table
from rich.markdown import Markdown

app = App()
console = Console()

# Constants
USER_CONFIG_DIR = Path.home() / ".p90"
CONFIG_PATH = USER_CONFIG_DIR / "config.json"
SYSTEM_PROMPT_PATH = USER_CONFIG_DIR / "system_prompt.md"
SCRIPTS_DIR = USER_CONFIG_DIR / "scripts"
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"


@dataclass
class ParsedResponse:
    response_type: str
    content: str = ""
    script_name: str = ""
    script_body: str = ""


# ===== COMMANDS =====


@app.default
def default_action(*args):
    """Main command handler."""
    # Check API key
    if not get_api_headers():
        print(
            "OpenRouter API key not configured. Please run 'p90 config' to set your openrouter_api_key."
        )
        return

    # Get user input
    user_input = get_user_input(args)
    if not user_input:
        print("No input provided")
        return

    # Get and parse response
    try:
        response = call_openrouter_api(user_input)
        parsed = parse_model_response(response)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        return

    # Handle response types
    if parsed.response_type == "response":
        console.print(Markdown(parsed.content))

    elif parsed.response_type == "cli":
        execute_command(parsed.content)

    elif parsed.response_type == "python-script":
        SCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
        script_path = SCRIPTS_DIR / parsed.script_name

        with open(script_path, "w") as f:
            f.write(parsed.script_body)

        print(f"Saved script to {script_path}")
        execute_command(f"python {script_path}")


@app.command
def config():
    """Opens the model and sampler config in the default editor."""
    ensure_config_exists()
    subprocess.run([get_editor(), str(CONFIG_PATH)])


@app.command
def reset():
    """Resets the config and system prompt back to the defaults."""
    # Preserve API key if it exists
    api_key = None
    if CONFIG_PATH.exists():
        try:
            api_key = load_json(CONFIG_PATH).get("openrouter_api_key")
        except:
            pass

    # Copy defaults
    default_config = json.loads(app_config)
    if api_key:
        default_config["openrouter_api_key"] = api_key

    ensure_config_exists()
    save_json(CONFIG_PATH, default_config)

    # Copy system prompt
    with open(SYSTEM_PROMPT_PATH, "w") as f:
        f.write(app_system_prompt)

    print("Config and system prompt reset to defaults (API key preserved)")


@app.command
def scripts():
    """Lists all available scripts in the `~/.p90/scripts/` directory."""
    SCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
    scripts = list(SCRIPTS_DIR.glob("*.py"))

    if not scripts:
        console.print("[yellow]No scripts found[/yellow]")
        return

    table = Table(title="Available Scripts")
    table.add_column("Name", style="cyan")
    table.add_column("Size", style="magenta")
    table.add_column("Modified", style="green")

    for script in sorted(scripts):
        stat = script.stat()
        table.add_row(
            script.name,
            f"{stat.st_size} bytes",
            datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
        )

    console.print(table)


@app.command
def delete(script_name: str):
    """Deletes the script with the given name from the `~/.p90/scripts/` directory."""
    if not script_name.endswith(".py"):
        script_name += ".py"

    script_path = SCRIPTS_DIR / script_name

    if not script_path.exists():
        print(f"Script '{script_name}' does not exist in ~/.p90/scripts/")
        return

    script_path.unlink()
    print(f"Successfully deleted script '{script_name}'")


# ===== HELPER FUNCTIONS =====


def ensure_config_exists():
    """Ensure config directory and files exist, recreating from defaults if needed."""
    USER_CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    # Handle config.json
    if not CONFIG_PATH.exists():
        try:
            default_config = json.loads(app_config)
            save_json(CONFIG_PATH, default_config)
        except Exception as e:
            print(f"Failed to create config from defaults: {e}")
            raise SystemExit(1)

    # Handle system_prompt.md
    if not SYSTEM_PROMPT_PATH.exists():
        try:
            with open(SYSTEM_PROMPT_PATH, "w") as f:
                f.write(app_system_prompt)
        except Exception as e:
            print(f"Failed to create system prompt from defaults: {e}")
            raise SystemExit(1)


def load_json(path: Path) -> Dict[str, Any]:
    """Load JSON file."""
    with open(path) as f:
        return json.load(f)


def save_json(path: Path, data: Dict[str, Any]):
    """Save JSON file."""
    with open(path, "w") as f:
        json.dump(data, f, indent=4)


def get_editor() -> str:
    """Get the user's preferred editor."""
    return os.environ.get("EDITOR", "nano")


def get_api_headers() -> Optional[Dict[str, str]]:
    """Get OpenRouter API headers."""
    try:
        ensure_config_exists()
        config = load_json(CONFIG_PATH)
        api_key = config.get("openrouter_api_key")
        if not api_key:
            return None

        return {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
    except (json.JSONDecodeError, IOError) as e:
        print(f"Failed to read config: {e}")
        raise SystemExit(1)


def get_system_prompt() -> str:
    """Get system prompt with hydrated variables."""
    try:
        ensure_config_exists()
        with open(SYSTEM_PROMPT_PATH) as f:
            content = f.read()
    except (IOError, OSError) as e:
        print(f"Failed to read system prompt: {e}")
        raise SystemExit(1)

    # Hydrate variables
    replacements = {
        "${{OS}}": os.name,
        "${{CWD}}": os.getcwd(),
        "${{DATE}}": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "${{SHELL}}": os.environ.get("SHELL", "unknown"),
    }

    for old, new in replacements.items():
        content = content.replace(old, new)

    return content


def get_model_config() -> Dict[str, Any]:
    """Get model configuration without API key."""
    try:
        ensure_config_exists()
        config = load_json(CONFIG_PATH)
        config.pop("openrouter_api_key", None)
        return config
    except Exception as e:
        print(f"Failed to read model config: {e}")
        raise SystemExit(1)


def get_user_input(args) -> Optional[str]:
    """Get user input from args or editor."""
    if args:
        return " ".join(args)

    with tempfile.NamedTemporaryFile(mode="w+", suffix=".txt", delete=False) as f:
        temp_path = f.name

    subprocess.run([get_editor(), temp_path])

    with open(temp_path) as f:
        user_input = f.read().strip()

    os.unlink(temp_path)
    return user_input if user_input else None


def call_openrouter_api(user_input: str) -> str:
    """Make API call to OpenRouter."""
    payload = {
        "messages": [
            {"role": "system", "content": get_system_prompt()},
            {"role": "user", "content": user_input},
        ],
        **get_model_config(),
    }

    response = httpx.post(
        OPENROUTER_API_URL,
        headers=get_api_headers(),
        json=payload,
        timeout=40,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


def parse_model_response(response: str) -> ParsedResponse:
    """Parse model response based on XML format."""
    patterns = [
        (
            r"<response>(.*?)</response>",
            lambda m: ParsedResponse("response", m.group(1).strip()),
        ),
        (r"<cli>(.*?)</cli>", lambda m: ParsedResponse("cli", m.group(1).strip())),
    ]

    for pattern, handler in patterns:
        match = re.search(pattern, response, re.DOTALL)
        if match:
            return handler(match)

    # Handle python-script format
    script_match = re.search(
        r"<python-script>(.*?)</python-script>", response, re.DOTALL
    )
    if script_match:
        content = script_match.group(1)
        name_match = re.search(r"<script-name>(.*?)</script-name>", content, re.DOTALL)
        body_match = re.search(r"<script-body>(.*?)</script-body>", content, re.DOTALL)

        if name_match and body_match:
            return ParsedResponse(
                "python-script",
                script_name=name_match.group(1).strip(),
                script_body=body_match.group(1).strip(),
            )

    return ParsedResponse("response", response)


def execute_command(command: str):
    """Execute a shell command and display output."""
    print(f"Executing: {command}")
    result = subprocess.run(command, shell=True, capture_output=True, text=True)
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        console.print(f"[red]{result.stderr}[/red]")


def main():
    app()

app_config = r"""
{
    "model": "anthropic/claude-sonnet-4",
    "temperature": 0.7,
    "top_p": 1.0,
    "top_k": 0,
    "frequency_penalty": 0.0,
    "presence_penalty": 0.0,
    "repetition_penalty": 1.0,
    "min_p": 0.0,
    "top_a": 0.0,
    "openrouter_api_key": ""
}
"""

app_system_prompt = r"""
You are an interactive CLI tool that helps users with software engineering tasks. Use the instructions below and to assist the user.

# Context

```handlebars
OS: ${{OS}}
CWD: ${{CWD}}
DATE: ${{DATE}}
SHELL: ${{SHELL}}
```

# Instructions

A user may query you to execute a task or ask a question.  
Questions may be:

- General, such as "When was the US founded?".
- System context specific, such as "How many pngs are in the cwd?"

Tasks may be complicated or simple. If the task can be executed via standard CLI commands, use those. Otherwise, use a python script.

Return the result in one, and only one, of the following formats:

1. response Format
   ```xml
   <response>assistant response</response>
   ```
2. cli Format
   ```xml
   <cli>CLI command</cli>
   ```
3. python-script Format
   ```xml
   <python-script>
       <script-name>concise_example_name.py<script-name>
       <script-body>Generated python script</script-body>
   </python-script>
   ```

# response Format

- Wrap the lines appropriately for a CLI context.
- Keep replies concise, factual, and simple.

# cli Format

- Wrap the CLI line appropriately for a CLI context.
- You may pipe and chain multiple CLI commands, but keep it as a single CLI command.
- Only use standard CLI commands that fit the OS and shell context, unless the user has implied a certain command is installed, eg `docker`.
- Ensure proper quoting of inputs.

# python-script Format

- Write the high level steps of the python command at the top of the file in plain and concise English. Good example:
  ```python
  \"""Resizes every JPG image in the CWD to 400x400.
  1. Iterate every image in the CWD.
  2. Open and resize the image using PIL.
  3. Save the result.
  4. Print a status message to the user.
  \"""
  ```
- The implementation should match the top level action plan as close as reasonable.
- Break each step into simple and concise functions.

# all Formats

- The reply should be a single top level element of {response, cli, or python-script} and nothing else.
- Add no extra helper prose or fluff.
"""

if __name__ == "__main__":
    app()
