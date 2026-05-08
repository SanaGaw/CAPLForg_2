"""coverage-report command."""
import sqlite3
from pathlib import Path

import click


@click.command()
@click.option("--db", "-d", "db_path", type=click.Path(exists=True), default="dcu_knowledge.db")
def coverage_report(db_path):
    """Generate a coverage report for the knowledge base."""
    db = Path(db_path)
    if not db.exists():
        click.echo(f"Error: Database not found: {db_path}", err=True)
        return

    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row

    report = {
        "signal_lookup": {"PASS": 0, "PARTIAL": 0, "FAIL": 0},
        "signal_to_message": {"PASS": 0, "PARTIAL": 0, "FAIL": 0},
        "signal_to_envvar": {"PASS": 0, "PARTIAL": 0, "FAIL": 0},
        "signal_to_sysvar": {"PASS": 0, "PARTIAL": 0, "FAIL": 0},
        "full_context_chain": {"PASS": 0, "PARTIAL": 0, "FAIL": 0},
    }

    signals = conn.execute("""
        SELECT name, message, source_file FROM signals
        WHERE source_file IN (SELECT source_file FROM sources WHERE preferred = 1)
        LIMIT 100
    """).fetchall()

    for sig in signals:
        sig_name = sig["name"]

        if sig_name:
            report["signal_lookup"]["PASS"] += 1
        else:
            report["signal_lookup"]["FAIL"] += 1

        if sig["message"]:
            msg = conn.execute("SELECT * FROM messages WHERE name = ?", (sig["message"],)).fetchone()
            if msg:
                report["signal_to_message"]["PASS"] += 1
            else:
                report["signal_to_message"]["PARTIAL"] += 1
        else:
            report["signal_to_message"]["FAIL"] += 1

        env_links = conn.execute(
            "SELECT * FROM capl_env_bindings WHERE signal = ?", (sig_name,)
        ).fetchall()
        if len(env_links) > 0:
            report["signal_to_envvar"]["PASS"] += 1
        else:
            report["signal_to_envvar"]["PARTIAL"] += 1

        sysvar_links = conn.execute(
            "SELECT * FROM capl_sysvar_mappings WHERE signal = ?", (sig_name,)
        ).fetchall()
        if len(sysvar_links) > 0:
            report["signal_to_sysvar"]["PASS"] += 1
        else:
            report["signal_to_sysvar"]["PARTIAL"] += 1

        if sig["message"] and (len(env_links) > 0 or len(sysvar_links) > 0):
            report["full_context_chain"]["PASS"] += 1
        elif sig["message"]:
            report["full_context_chain"]["PARTIAL"] += 1
        else:
            report["full_context_chain"]["FAIL"] += 1

    conn.close()

    click.echo("\n=== Coverage Report ===\n")
    for query_type, results in report.items():
        total = sum(results.values())
        pass_rate = (results["PASS"] / total * 100) if total > 0 else 0
        click.echo(f"{query_type}:")
        click.echo(f"  PASS: {results['PASS']}, PARTIAL: {results['PARTIAL']}, FAIL: {results['FAIL']}")
        click.echo(f"  Pass Rate: {pass_rate:.1f}%\n")
