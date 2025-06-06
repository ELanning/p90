# P90

A powerful CLI tool that provides an AI-powered assistant for software engineering tasks. P90 leverages OpenRouter's API to execute commands, generate Python scripts, and provide intelligent responses based on your queries.

## Features

- **Natural Language Interface**: Ask questions or request tasks in plain English
- **Multiple Response Types**: Get text responses, CLI commands, or Python scripts
- **Script Management**: Save, list, and execute generated Python scripts
- **Interactive Script Selection**: Browse and execute saved scripts with keyboard navigation
- **Configurable**: Customize model parameters and system prompts
- **Context Awareness**: System context (OS, CWD, date, shell) is automatically provided

## Installation

1. Clone the repository
2. Install dependencies: `uv sync` or `pip install -r requirements.txt`
3. Set up your OpenRouter API key (see Configuration section)

## Configuration

### Initial Setup

Run `p90 config` to open the configuration file in your default editor. You'll need to set your OpenRouter API key:

```json
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
    "openrouter_api_key": "your_api_key_here"
}
```

### System Prompt

The system prompt is located at `p90/system_prompt.md` and can be customized. It supports variable interpolation:

- `${{OS}}` - Operating system
- `${{CWD}}` - Current working directory  
- `${{DATE}}` - Current date and time
- `${{SHELL}}` - Current shell

## Usage

### Basic Usage

```bash
# Ask a question
p90 "How do I list files in the current directory?"

# Request a task
p90 "Create a Python script to resize images"

# Open editor for multi-line input
p90
```

### Available Commands

- `p90` - Main command (default action)
- `p90 config` - Open configuration file in editor
- `p90 reset` - Reset config and system prompt to defaults (preserves API key)
- `p90 scripts` - List and interactively select from saved scripts
- `p90 delete <script_name>` - Delete a saved script

### Response Types

P90 can respond in three different formats:

#### 1. Text Response
```xml
<response>
Here's how to list files: use the `ls` command for basic listing, 
or `ls -la` for detailed information including hidden files.
</response>
```

#### 2. CLI Command
```xml
<cli>ls -la</cli>
```

#### 3. Python Script
```xml
<python-script>
    <script-name>resize_images.py</script-name>
    <script-body>
#!/usr/bin/env python3
"""Resize images in the current directory."""
from PIL import Image
import os

def resize_images():
    for filename in os.listdir('.'):
        if filename.lower().endswith(('.png', '.jpg', '.jpeg')):
            # Resize logic here
            pass

if __name__ == "__main__":
    resize_images()
    </script-body>
</python-script>
```

### Script Management

Generated Python scripts are automatically saved to `~/.p90/scripts/` and can be:

- **Listed and executed** via `p90 scripts` (interactive menu)
- **Deleted** via `p90 delete script_name`
- **Executed manually** from the scripts directory

## Environment Variables

- `EDITOR` - Preferred text editor (defaults to `nano`)

## Examples

```bash
# Get system information
p90 "Show me system info"

# File operations
p90 "Find all Python files larger than 1MB"

# Development tasks
p90 "Create a FastAPI hello world server"

# Interactive script browsing
p90 scripts
```

## API Requirements

- OpenRouter API account and key
- Internet connection for API calls

## Error Handling

- Invalid API key: Clear error message with setup instructions
- Network issues: HTTP errors are displayed
- Script execution: Both stdout and stderr are shown
- Keyboard interrupts: Gracefully handled in interactive modes

## License

MIT
