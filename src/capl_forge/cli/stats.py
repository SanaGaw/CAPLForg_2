"""stats command."""
import sqlite3
from pathlib import Path

import click


@click.command()
@click.option("--db", "-d", "db_path", type=click.Path(exists=True), default="dcu_knowledge.db")
def stats(db_path):
    """Show knowledge base statistics."""
    db = Path(db_path)
    if not db.exists():
        click.echo(f"Error: Database not found: {db_path}", err=True)
        return

    conn = sqlite3.connect(db)

    tables = [
        "sources", "messages", "signals", "sysvars", "env_vars",
        "value_tables", "capl_env_bindings", "capl_sysvar_mappings",
        "dids", "did_fields", "dtcs", "calibrations", "requirements"
    ]

    click.echo("\n=== Knowledge Base Statistics ===\n")
    for table in tables:
        try:
            count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            click.echo(f"  {table}: {count}")
        except sqlite3.OperationalError:
            click.echo(f"  {table}: (table not found)")

    conn.close()
