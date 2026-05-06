#!/usr/bin/env python3
"""CLI tool for validating configuration files against JSON schemas.

Usage:
    python -m config_schemas validate <file> [--schema <schema_name>]
    python -m config_schemas list
"""

import json
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from config_schemas import SCHEMA_FILES, validate, get_schema

app = typer.Typer(help="Config schema validation tool")
console = Console()


@app.command()
def validate_file(
    file_path: str = typer.Argument(..., help="Path to the configuration file to validate"),
    schema_name: Optional[str] = typer.Option(
        None, "--schema", "-s", help="Schema name to validate against"
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed errors"),
) -> None:
    """Validate a configuration file against a schema."""
    path = Path(file_path)
    if not path.exists():
        console.print(f"[red]Error:[/red] File not found: {path}")
        raise typer.Exit(1)

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        console.print(f"[red]Error:[/red] Invalid JSON: {e}")
        raise typer.Exit(1)

    # Auto-detect schema if not specified
    if schema_name is None:
        schema_name = _auto_detect_schema(data)
        if schema_name is None:
            console.print("[red]Error:[/red] Could not auto-detect schema. Please specify with --schema")
            raise typer.Exit(1)

    try:
        is_valid, errors = validate(data, schema_name)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if is_valid:
        console.print(f"[green]Valid:[/green] {path} against {schema_name}")
    else:
        console.print(f"[red]Invalid:[/red] {path} against {schema_name}")
        if verbose:
            for i, error in enumerate(errors, 1):
                console.print(f"  {i}. {error}")
        else:
            console.print(f"  {len(errors)} error(s) found. Use --verbose for details.")
        raise typer.Exit(1)


@app.command()
def list_schemas() -> None:
    """List all available schemas."""
    table = Table(title="Available Schemas")
    table.add_column("Name", style="cyan")
    table.add_column("File", style="green")

    for name, filename in SCHEMA_FILES.items():
        table.add_row(name, filename)

    console.print(table)


@app.command()
def info(
    schema_name: str = typer.Argument(..., help="Schema name to display info for"),
) -> None:
    """Display information about a specific schema."""
    try:
        schema = get_schema(schema_name)
        console.print(f"\n[cyan]Schema:[/cyan] {schema_name}")
        console.print(f"[cyan]Title:[/cyan] {schema.get('title', 'N/A')}")
        console.print(f"[cyan]Version:[/cyan] {schema.get('$schema', 'N/A')}")

        if "properties" in schema:
            console.print("\n[cyan]Properties:[/cyan]")
            for prop_name, prop_def in schema["properties"].items():
                prop_type = prop_def.get("type", "unknown")
                console.print(f"  - {prop_name}: {prop_type}")
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


def _auto_detect_schema(data: dict) -> Optional[str]:
    """Auto-detect schema based on version field in data."""
    version = data.get("version", "")

    if version == "1.0":
        if "aliases" in data:
            return "signal_aliases_v1"
        if "helpers" in data:
            return "helper_definitions"
        if "proposed_resolution" in data:
            return "chat_resolution"
    elif version == "2.0":
        if "aliases" in data:
            return "signal_aliases_v2"
    elif version == "1.1":
        if "signals" in data:
            return "sto_extract"

    if "status" in data and "generated_at" in data:
        return "config_status"
    if "template" in data:
        return "test_template"
    if "compliance_mode" in data or "files" in data:
        return "compliance_bundle"

    return None


if __name__ == "__main__":
    app()
