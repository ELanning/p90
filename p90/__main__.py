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


@app.command
def config():
    """Opens the model and sampler config in the default editor."""
    config_path = Path("p90/config.json")
    if not config_path.exists():
        config_path.parent.mkdir(parents=True, exist_ok=True)
        default_config = get_config()
        with open(config_path, 'w') as f:
            json.dump(default_config, f, indent=4)
    
    editor = os.environ.get('EDITOR', 'nano')
    subprocess.run([editor, str(config_path)])


@app.command
def reset():
    """Resets the config and system prompt back to the defaults."""
    # Impl note: does not reset the stored API key.
    config_path = Path("p90/config.json")
    system_prompt_path = Path("p90/system_prompt.md")
    
    # Preserve API key if it exists
    api_key = None
    if config_path.exists():
        try:
            with open(config_path) as f:
                current_config = json.load(f)
                api_key = current_config.get("openrouter_api_key")
        except:
            pass
    
    # Copy defaults
    default_config_path = Path("p90/defaults/config.json")
    default_system_prompt_path = Path("p90/defaults/system_prompt.md")
    
    with open(default_config_path) as f:
        default_config = json.load(f)
    
    # Add back API key if it existed
    if api_key:
        default_config["openrouter_api_key"] = api_key
        
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, 'w') as f:
        json.dump(default_config, f, indent=4)
    
    system_prompt_path.parent.mkdir(parents=True, exist_ok=True)
    with open(default_system_prompt_path) as f:
        content = f.read()
    with open(system_prompt_path, 'w') as f:
        f.write(content)
    
    print("Config and system prompt reset to defaults (API key preserved)")

@app.command
def scripts():
    """Lists all available scripts in the `~/.p90/scripts/` directory."""
    # Use rich to make a nice scrollable list.
    scripts_dir = Path.home() / ".p90" / "scripts"
    console = Console()
    
    # Ensure the scripts directory exists
    scripts_dir.mkdir(parents=True, exist_ok=True)
    
    scripts = list(scripts_dir.glob("*.py"))
    
    if not scripts:
        console.print("[yellow]No scripts found[/yellow]")
        return
    
    table = Table(title="Available Scripts")
    table.add_column("Name", style="cyan")
    table.add_column("Size", style="magenta")
    table.add_column("Modified", style="green")
    
    for script in sorted(scripts):
        stat = script.stat()
        size = f"{stat.st_size} bytes"
        modified = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
        table.add_row(script.name, size, modified)
    
    console.print(table)

@app.command
def delete(script_name: str):
    """Deletes the script with the given name from the `~/.p90/scripts/` directory."""
    # Impl note: if the script does not exist, print message.
    # If the script exists, delete it and print a success message.
    scripts_dir = Path.home() / ".p90" / "scripts"
    
    # Add .py extension if not present
    if not script_name.endswith('.py'):
        script_name += '.py'
    
    script_path = scripts_dir / script_name
    
    if not script_path.exists():
        print(f"Script '{script_name}' does not exist in ~/.p90/scripts/")
        return
    
    script_path.unlink()
    print(f"Successfully deleted script '{script_name}'")

@app.default
def default_action(*args):
    # Args can be:
    #   - A single string, eg "Hello world".
    #   - A bunch of strings, eg "Hello", "world", which should be joined with a space.
    #   - Empty, which should open the users editor and then get the input from there.

    # Check if API key is configured
    headers = get_openrouter_headers()
    if not headers:
        print("OpenRouter API key not configured. Please run 'p90 config' to set your openrouter_api_key.")
        return

    if args:
        user_input = " ".join(args)
    else:
        # Open editor to get input
        with tempfile.NamedTemporaryFile(mode='w+', suffix='.txt', delete=False) as f:
            temp_path = f.name
        
        editor = os.environ.get('EDITOR', 'nano')
        subprocess.run([editor, temp_path])
        
        with open(temp_path) as f:
            user_input = f.read().strip()
        
        os.unlink(temp_path)
        
        if not user_input:
            print("No input provided")
            return
    
    response = call_openrouter_api(user_input)
    parsed_response = parse_model_response(response)
    
    console = Console()
    
    if parsed_response.response_type == "response":
        # Simple text response
        markdown = Markdown(parsed_response.content)
        console.print(markdown)
    elif parsed_response.response_type == "cli":
        # Execute CLI command
        print(f"Executing: {parsed_response.content}")
        result = subprocess.run(parsed_response.content, shell=True, capture_output=True, text=True)
        if result.stdout:
            print(result.stdout)
        if result.stderr:
            console.print(f"[red]{result.stderr}[/red]")
    elif parsed_response.response_type == "python-script":
        # Save and execute python script
        scripts_dir = Path.home() / ".p90" / "scripts"
        scripts_dir.mkdir(parents=True, exist_ok=True)
        
        script_path = scripts_dir / parsed_response.script_name
        with open(script_path, 'w') as f:
            f.write(parsed_response.script_body)
        
        print(f"Saved script to {script_path}")
        print(f"Executing: python {script_path}")
        
        result = subprocess.run(["python", str(script_path)], capture_output=True, text=True)
        if result.stdout:
            print(result.stdout)
        if result.stderr:
            console.print(f"[red]{result.stderr}[/red]")


def call_openrouter_api(user_input) -> str:
    """Make API call to OpenRouter and process the response."""
    json_payload = {
        "messages": [
            {"role": "system", "content": get_system_prompt()},
            {"role": "user", "content": user_input},
        ],
    }

    app_config = get_config()

    # Merge config into the JSON payload.
    json_payload.update(app_config)

    response = httpx.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers=get_openrouter_headers(),
        json=json_payload,
        timeout=40,
    )
    response.raise_for_status()
    model_response = response.json()["choices"][0]["message"]["content"]

    return model_response


@dataclass
class ParsedResponse:
    response_type: str
    content: str = ""
    script_name: str = ""
    script_body: str = ""

def parse_model_response(model_response: str) -> ParsedResponse:
    """model response can be one of the following
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
    """
    # Try response format
    response_match = re.search(r'<response>(.*?)</response>', model_response, re.DOTALL)
    if response_match:
        return ParsedResponse("response", response_match.group(1).strip())
    
    # Try cli format
    cli_match = re.search(r'<cli>(.*?)</cli>', model_response, re.DOTALL)
    if cli_match:
        return ParsedResponse("cli", cli_match.group(1).strip())
    
    # Try python-script format
    script_match = re.search(r'<python-script>(.*?)</python-script>', model_response, re.DOTALL)
    if script_match:
        script_content = script_match.group(1)
        name_match = re.search(r'<script-name>(.*?)</script-name>', script_content, re.DOTALL)
        body_match = re.search(r'<script-body>(.*?)</script-body>', script_content, re.DOTALL)
        
        if name_match and body_match:
            return ParsedResponse(
                "python-script",
                script_name=name_match.group(1).strip(),
                script_body=body_match.group(1).strip()
            )
    
    # Fallback to response format
    return ParsedResponse("response", model_response)

def get_openrouter_headers() -> Optional[Dict[str, str]]:
    # Get the apiKey from the "./config.json"
    # and return as `Bearer <API_KEY>`
    # If the file does not exist or cannot be read, return `None`.
    config_path = Path("p90/config.json")
    
    if not config_path.exists():
        return None
    
    try:
        with open(config_path) as f:
            config = json.load(f)
        
        api_key = config.get("openrouter_api_key")
        if not api_key:
            return None
        
        return {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
    except (json.JSONDecodeError, IOError):
        return None

def get_system_prompt() -> str:
    # Get the system prompt from "./system_prompt.md"
    # If it does not exist, return the default system prompt.
    """ Also hydrate these variables: with find+replace.
    OS: ${{OS}}
    CWD: ${{CWD}}
    DATE: ${{DATE}}
    SHELL: ${{SHELL}}
    """
    system_prompt_path = Path("p90/system_prompt.md")
    default_system_prompt_path = Path("p90/defaults/system_prompt.md")
    
    if system_prompt_path.exists():
        with open(system_prompt_path) as f:
            content = f.read()
    else:
        with open(default_system_prompt_path) as f:
            content = f.read()
    
    # Hydrate variables
    content = content.replace("${{OS}}", os.name)
    content = content.replace("${{CWD}}", os.getcwd())
    content = content.replace("${{DATE}}", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    content = content.replace("${{SHELL}}", os.environ.get("SHELL", "unknown"))
    
    return content

def get_config() -> Dict[str, Any]:
    # Get the config from "./config.json"
    # If it does not exist or cannot be read, return the default config.
    # Remove the "openrouter_api_key" field from the config if it exists.
    config_path = Path("p90/config.json")
    default_config_path = Path("p90/defaults/config.json")
    
    # Try to read the config
    if config_path.exists():
        with open(config_path) as f:
            config = json.load(f)
    else:
        # Fall back to default
        with open(default_config_path) as f:
            config = json.load(f)
    
    # Remove openrouter_api_key field
    config.pop("openrouter_api_key", None)
    
    return config

if __name__ == "__main__":
    app()
