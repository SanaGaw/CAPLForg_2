"""scan-project command."""
import os
import sys
from pathlib import Path

import click

from capl_forge.core.audit import new_run_id, write_audit_event
from capl_forge.extractors.cfg.detector import detect_format
from capl_forge.extractors.cfg.binary_scraper import BinaryScraper
from capl_forge.extractors.cfg.reference_resolver import resolve_references
from capl_forge.extractors.cfg.project_walker import walk_project
from capl_forge.kb.ingest import build_knowledge_base


@click.command()
@click.option("--config", "-c", type=click.Path(exists=True), help="Path to CANoe .cfg file")
@click.option("--db", "-d", "db_path", type=click.Path(), default="dcu_knowledge.db", help="Output SQLite database path")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose output")
def scan_project(config, db_path, verbose):
    """Scan a CANoe project and build the knowledge database."""
    if not config:
        config = os.environ.get("CAPL_FORGE_CFG")
        if not config:
            click.echo("Error: --config required or set CAPL_FORGE_CFG", err=True)
            sys.exit(1)

    config_path = Path(config)
    run_id = new_run_id()

    def log(msg):
        if verbose:
            click.echo(f"  {msg}")
        elif "summary:" in msg or "done in" in msg or "error" in msg.lower():
            click.echo(f"  {msg}")

    click.echo(f"Inspecting: {config_path}")

    # Detect format and scrape references
    fmt = detect_format(config_path)
    scraper = BinaryScraper(log=log)
    if fmt == "zip":
        refs = scraper.scrape_zip(config_path)
    else:
        refs = scraper.scrape_binary(config_path)

    log(f"Extracted {len(refs)} candidate references")

    # Resolve and walk
    resolved = resolve_references(config_path.parent, refs, log=log)
    found = sum(1 for r in resolved if r["exists"])
    log(f"Resolved: {found} found, {len(resolved) - found} missing")

    inventory = walk_project(config_path.parent, log=log)
    log(f"Project inventory: {len(inventory)} relevant files")

    # Build inspection result (simplified - no sub-parsing in CLI)
    inspection_result = {
        "references": resolved,
        "inventory": inventory,
        "dbc_messages": [],
        "dbc_signals": [],
        "sysvars": [],
        "env_vars": [],
        "value_tables": [],
        "capl_bindings": [],
        "capl_sysvar_mappings": [],
        "dids": [],
        "did_fields": [],
    }

    click.echo(f"Building knowledge base: {db_path}")
    summary = build_knowledge_base(
        inspection_result, db_path, log=log, verbose=verbose, run_id=run_id
    )

    click.echo(f"\nKnowledge base built! (run_id: {run_id})")
    click.echo(f"  Database: {summary['db_path']}")
    click.echo(f"  Sources: {len(summary['new_sources'])} new, "
               f"{len(summary['changed_sources'])} changed, "
               f"{len(summary['unchanged_sources'])} unchanged, "
               f"{len(summary['deleted_sources'])} removed")
    click.echo(f"  Time: {summary['elapsed_seconds']:.2f}s")
