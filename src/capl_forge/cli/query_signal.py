"""query-signal command."""
import sqlite3
from pathlib import Path

import click


@click.command()
@click.option("--db", "-d", "db_path", type=click.Path(exists=True), default="dcu_knowledge.db")
@click.argument("signal_name")
def query_signal(db_path, signal_name):
    """Query a signal and show its full context."""
    db = Path(db_path)
    if not db.exists():
        click.echo(f"Error: Database not found: {db_path}", err=True)
        click.echo("Run 'capl-forge scan-project' first.", err=True)
        return

    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row

    signal = conn.execute("""
        SELECT * FROM signals WHERE name = ? AND source_file IN (
            SELECT source_file FROM sources WHERE preferred = 1
        )
    """, (signal_name,)).fetchone()

    if not signal:
        click.echo(f"Signal not found: {signal_name}", err=True)
        conn.close()
        return

    message = conn.execute("""
        SELECT * FROM messages WHERE name = ? AND source_file IN (
            SELECT source_file FROM sources WHERE preferred = 1
        )
    """, (signal["message"],)).fetchone()

    env_links = conn.execute("SELECT * FROM capl_env_bindings WHERE signal = ?", (signal_name,)).fetchall()
    sysvar_links = conn.execute("SELECT * FROM capl_sysvar_mappings WHERE signal = ?", (signal_name,)).fetchall()

    click.echo(f"\n=== Signal: {signal_name} ===\n")
    if message:
        click.echo(f"Message: {message['name']}")
        click.echo(f"  Frame ID: {message['frame_id_hex']}")
        click.echo(f"  DLC: {message['dlc']}")
    click.echo(f"\nSignal Properties:")
    click.echo(f"  Start Bit: {signal['start_bit']}")
    click.echo(f"  Length: {signal['length']} bits")
    click.echo(f"  Byte Order: {signal['byte_order']}")

    if env_links:
        click.echo(f"\nEnv Var Bindings ({len(env_links)}):")
        for link in env_links:
            click.echo(f"  {link['env_var']} -> {link['signal']} ({link['bus_type']})")

    if sysvar_links:
        click.echo(f"\nSysvar Mappings ({len(sysvar_links)}):")
        for link in sysvar_links:
            click.echo(f"  {link['sysvar_path']} -> {link['signal']} ({link['bus_type']})")

    click.echo(f"\nSource: {signal['source_file']}")
    conn.close()
