"""CAPL Pipeline CLI for CAPL Pipeline V2.2.

Typer-based command-line interface for CI/CD and headless usage.
"""

from pathlib import Path
from typing import Optional, List
import typer
import asyncio
import logging
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn

from ..core.config_loader import ConfigLoader
from ..core.signal_registry import SignalRegistry
from ..core.batch_processor import BatchProcessor
from ..core.performance import PerformanceProfiler
from ..parsers.excel_parser import ExcelParser
from ..capl.generator import CaplGenerator

# Create app
app = typer.Typer(
    name="capl-pipeline",
    help="CAPL Pipeline V2.2 - CANoe CAPL Test Case Generation"
)

console = Console()


@app.command()
def version():
    """Show version information."""
    console.print("[cyan]CAPL Pipeline V2.2.0[/cyan]")
    console.print("CANoe CAPL Test Case Generation Pipeline")


@app.command()
def init(
    output_dir: Path = typer.Option(Path("."), "--output", "-o", help="Output directory for config files"),
    cfg_file: Optional[Path] = typer.Option(None, "--cfg", help="CANoe .cfg file to scaffold from"),
):
    """Initialize a new project with scaffold configuration."""
    from ..core.config_scaffold import ConfigScaffold

    output_dir.mkdir(parents=True, exist_ok=True)

    if cfg_file and cfg_file.exists():
        console.print(f"[cyan]Generating scaffold from {cfg_file}...[/cyan]")
        scaffold = ConfigScaffold(output_dir)
        config = scaffold.generate_from_canoe_project(cfg_file)
        output_path = scaffold.write_scaffold_config(config, output_dir / "scaffold_config.yaml")
        console.print(f"[green]Scaffold generated: {output_path}[/green]")
    else:
        console.print("[yellow]No .cfg file provided. Creating empty config...[/yellow]")
        config = {
            "version": "1.0",
            "signals": [],
            "aliases": {}
        }
        output_path = output_dir / "signal_aliases.yaml"
        import yaml
        with open(output_path, 'w') as f:
            yaml.dump(config, f)
        console.print(f"[green]Empty config created: {output_path}[/green]")


@app.command()
def generate(
    excel_file: Path = typer.Argument(..., help="Excel test plan file"),
    output_dir: Path = typer.Option(Path("output"), "--output", "-o", help="Output directory for generated CAPL files"),
    db_path: Optional[Path] = typer.Option(None, "--db", help="Signal registry database path"),
    batch: bool = typer.Option(False, "--batch", help="Use batch processing for parallel generation"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be generated without writing files"),
    compliance: bool = typer.Option(False, "--compliance", help="Run in compliance mode (offline)"),
):
    """Generate CAPL test cases from Excel test plan."""
    console.print(f"[cyan]Generating CAPL from {excel_file}...[/cyan]")

    # Initialize components
    config_loader = ConfigLoader()
    config_loader.load()

    registry = SignalRegistry(db_path)
    generator = CaplGenerator(signal_registry=registry)

    # Parse Excel file
    parser = ExcelParser(excel_file)
    test_cases = parser.parse()

    console.print(f"[cyan]Parsed {len(test_cases)} test cases[/cyan]")

    # Process test cases
    output_dir.mkdir(parents=True, exist_ok=True)

    if batch:
        processor = BatchProcessor(output_dir=output_dir, dry_run=dry_run)
        test_case_dicts = [
            {
                "test_case_id": tc.test_id,
                "description": tc.description,
                "steps": [{"step_id": s.step_id, "action": s.action, "description": s.description} for s in tc.steps],
                "signals": tc.signals
            }
            for tc in test_cases.values()
        ]
        result = asyncio.run(processor.process_batch(test_case_dicts))
        console.print(f"[green]Processed {result['total']} test cases[/green]")
        console.print(f"  Successful: {result['successful']}")
        console.print(f"  Failed: {result['failed']}")
    else:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task("Generating CAPL files...", total=len(test_cases))
            for tc in test_cases.values():
                test_case_dict = {
                    "test_case_id": tc.test_id,
                    "description": tc.description,
                    "steps": [{"step_id": s.step_id, "action": s.action, "description": s.description} for s in tc.steps],
                    "signals": tc.signals
                }
                content = generator.generate_from_test_case(test_case_dict)
                output_path = output_dir / f"{tc.test_id}.can"
                if not dry_run:
                    output_path.write_text(content, encoding='utf-8')
                progress.update(task, advance=1)

        console.print(f"[green]Generated {len(test_cases)} CAPL files to {output_dir}[/green]")


@app.command()
def validate(
    capl_file: Path = typer.Argument(..., help="CAPL file to validate"),
    use_compiler: bool = typer.Option(False, "--compiler", help="Run CANoe compiler validation"),
):
    """Validate a CAPL file."""
    from ..capl.two_tier_validator import TwoTierValidator

    console.print(f"[cyan]Validating {capl_file}...[/cyan]")

    validator = TwoTierValidator()
    result = validator.validate_file(capl_file, use_compiler)

    if result.overall_passed:
        console.print(f"[green]Validation PASSED[/green]")
    else:
        console.print(f"[red]Validation FAILED[/red]")

    if result.errors:
        console.print("\n[red]Errors:[/red]")
        for error in result.errors:
            console.print(f"  - {error}")

    if result.warnings:
        console.print("\n[yellow]Warnings:[/yellow]")
        for warning in result.warnings:
            console.print(f"  - {warning}")


@app.command()
def compare(
    golden_dir: Path = typer.Argument(..., help="Directory with golden/reference CAPL files"),
    generated_dir: Path = typer.Argument(..., help="Directory with generated CAPL files"),
    tolerance: float = typer.Option(0.95, "--tolerance", "-t", help="Similarity tolerance (0.0-1.0)"),
):
    """Compare generated CAPL files against golden references."""
    from ..core.capl_fingerprinter import CaplStructuralFingerprinter

    console.print(f"[cyan]Comparing files...[/cyan]")

    fingerprinter = CaplStructuralFingerprinter()
    report = fingerprinter.generate_golden_diff(golden_dir, generated_dir)

    console.print(report)

    # Count results
    passed = report.count("PASS")
    failed = report.count("FAIL")

    console.print(f"\n[cyan]Summary:[/cyan] {passed} passed, {failed} failed")


@app.command()
def audit(
    action: str = typer.Argument(..., help="Audit action (show, export)"),
    output_file: Optional[Path] = typer.Option(None, "--output", "-o", help="Output file for export"),
    limit: int = typer.Option(100, "--limit", "-n", help="Number of entries to show"),
):
    """View or export audit logs."""
    from ..core.audit_logger import AuditLogger

    logger = AuditLogger()

    if action == "show":
        entries = logger.get_recent_entries(limit=limit)

        table = Table(title=f"Audit Log ({len(entries)} entries)")
        table.add_column("Timestamp", style="cyan")
        table.add_column("Action", style="green")
        table.add_column("Category")

        for entry in entries:
            table.add_row(
                entry.get("timestamp", "")[:19],
                entry.get("action", ""),
                entry.get("category", "")
            )

        console.print(table)

    elif action == "export":
        if not output_file:
            console.print("[red]Output file required for export[/red]")
            raise typer.Exit(1)

        entries = logger.get_recent_entries(limit=10000)
        import json
        with open(output_file, 'w') as f:
            json.dump(entries, f, indent=2)

        console.print(f"[green]Exported {len(entries)} entries to {output_file}[/green]")


@app.command()
def serve(
    host: str = typer.Option("0.0.0.0", "--host", help="Host to bind to"),
    port: int = typer.Option(8000, "--port", "-p", help="Port to bind to"),
    reload: bool = typer.Option(False, "--reload", help="Enable auto-reload"),
):
    """Start the web server."""
    import uvicorn

    console.print(f"[cyan]Starting CAPL Pipeline web server on {host}:{port}...[/cyan]")

    # Initialize app with dependencies
    from ..web.api import init_app
    from ..core.signal_registry import SignalRegistry
    from ..llm.router import LLMRouter

    registry = SignalRegistry()
    llm_router = LLMRouter()
    init_app(registry=registry, llm_router=llm_router)

    uvicorn.run(
        "src.web.api:app",
        host=host,
        port=port,
        reload=reload,
        log_level="info"
    )


@app.command()
def config_validate(
    config_file: Path = typer.Argument(..., help="Configuration file to validate"),
):
    """Validate a configuration file against schema."""
    import json
    import yaml

    console.print(f"[cyan]Validating {config_file}...[/cyan]")

    # Try to determine file type and validate
    try:
        if config_file.suffix in ['.json']:
            with open(config_file, 'r') as f:
                data = json.load(f)
        else:
            with open(config_file, 'r') as f:
                data = yaml.safe_load(f)

        from config_schemas import validate
        is_valid, errors = validate(data, _auto_detect_schema(data))

        if is_valid:
            console.print(f"[green]Configuration is VALID[/green]")
        else:
            console.print(f"[red]Configuration is INVALID[/red]")
            for error in errors:
                console.print(f"  - {error}")
            raise typer.Exit(1)

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


def _auto_detect_schema(data: dict) -> str:
    """Auto-detect schema based on data structure."""
    version = data.get("version", "")

    if version == "1.0":
        if "aliases" in data:
            return "signal_aliases_v1"
        if "helpers" in data:
            return "helper_definitions"
    elif version == "2.0":
        if "aliases" in data:
            return "signal_aliases_v2"

    if "status" in data:
        return "config_status"
    if "template" in data:
        return "test_template"

    return "signal_aliases_v1"


if __name__ == "__main__":
    app()
