"""Config commands."""

import json

import rich_click as click
from rich.syntax import Syntax

from ..config import get_config_path, load_config, save_config
from ._console import console


@click.group()
def config():
    """Manage configuration."""
    pass


@config.command("show")
def config_show():
    """Show current configuration."""
    cfg = load_config()
    json_str = json.dumps(cfg, indent=2)
    syntax = Syntax(json_str, "json", theme="monokai")
    console.print(syntax)


@config.command("path")
def config_path():
    """Show configuration file path."""
    console.print(str(get_config_path()))


@config.command("set")
@click.argument("key")
@click.argument("value")
def config_set(key: str, value: str):
    """Set a configuration value (e.g., llm.model sonnet)."""
    cfg = load_config()

    # Parse key path
    parts = key.split(".")
    target = cfg
    for part in parts[:-1]:
        if part not in target:
            target[part] = {}
        target = target[part]

    # Parse value (try as JSON, fall back to string)
    try:
        parsed_value = json.loads(value)
    except json.JSONDecodeError:
        parsed_value = value

    target[parts[-1]] = parsed_value
    save_config(cfg)
    console.print(f"Set {key} = {parsed_value}")
