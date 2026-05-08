"""
CAPL Forge - Module 1 Entry Point
=================================

Main CLI for CAPL Forge: CANoe Project Knowledge Extraction and Resolution System.

Usage:
    python main.py --config <path-to-cfg> [--db <output-db-path>]

Environment Variables:
    CAPL_FORGE_CFG: Path to CANoe .cfg file (alternative to --config)
"""

import json
import os
import sys
from pathlib import Path

import click


def _get_capl_forge_cfg():
    """Get config path from CAPL_FORGE_CFG environment variable."""
    return os.environ.get("CAPL_FORGE_CFG")


@click.group()
@click.version_option(version="0.1.0", prog_name="capl-forge")
def cli():
    """
    CAPL Forge - CANoe Project Knowledge Extraction and Resolution System.

    Module 1: Extract knowledge from CANoe projects.
    Module 2: Generate CAPL from resolved test suites (not yet implemented).
    """
    pass


@cli.command()
@click.option(
    "--config",
    "-c",
    type=click.Path(exists=True),
    help="Path to CANoe .cfg file",
)
@click.option(
    "--db",
    "-d",
    "db_path",
    type=click.Path(),
    default="dcu_knowledge.db",
    help="Output SQLite database path",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Enable verbose output",
)
def scan_project(config, db_path, verbose):
    """
    Scan a CANoe project and build the knowledge database.

    Extracts all engineering artifacts (DBC, CDD, vsysvar, CAPL, etc.)
    and builds a SQLite knowledge base with semantic linking.
    """
    # Import here to avoid circular imports
    try:
        from canoe_cfg_inspector import CfgInspector
        from kb_builder import build_knowledge_base
    except ImportError as e:
        click.echo(f"Error: Required module not found: {e}", err=True)
        sys.exit(1)

    # Resolve config path
    if not config:
        env_val = _get_capl_forge_cfg()
        if env_val:
            config = env_val
        else:
            click.echo("Error: --config required or set CAPL_FORGE_CFG environment variable", err=True)
            sys.exit(1)

    config_path = Path(config)
    if not config_path.exists():
        click.echo(f"Error: Config file not found: {config}", err=True)
        sys.exit(1)

    def log(msg):
        if verbose:
            click.echo(f"  {msg}")
        else:
            # Always show summary
            if "summary:" in msg or "done in" in msg or "error" in msg.lower():
                click.echo(f"  {msg}")

    click.echo(f"Inspecting: {config_path}")
    inspector = CfgInspector(log=log)
    result = inspector.inspect(config_path)

    click.echo(f"Building knowledge base: {db_path}")
    summary = build_knowledge_base(result, db_path, log=log, verbose=verbose)

    click.echo(f"\nKnowledge base built successfully!")
    click.echo(f"  Database: {summary['db_path']}")
    click.echo(f"  Sources: {len(summary['new_sources'])} new, "
               f"{len(summary['changed_sources'])} changed, "
               f"{len(summary['unchanged_sources'])} unchanged, "
               f"{len(summary['deleted_sources'])} removed")
    click.echo(f"  Row counts: {summary['row_counts']}")
    click.echo(f"  Time: {summary['elapsed_seconds']:.2f}s")


@cli.command()
@click.option(
    "--db",
    "-d",
    "db_path",
    type=click.Path(exists=True),
    default="dcu_knowledge.db",
    help="SQLite knowledge base path",
)
@click.argument("signal_name")
def query_signal(db_path, signal_name):
    """
    Query a signal and show its full context.

    Returns signal definition, message, value tables, env var links,
    sysvar links, and DID associations.
    """
    import sqlite3

    db = Path(db_path)
    if not db.exists():
        click.echo(f"Error: Database not found: {db_path}", err=True)
        click.echo("Run 'capl-forge scan-project' first.", err=True)
        sys.exit(1)

    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row

    # Query signal
    signal = conn.execute("""
        SELECT * FROM signals WHERE name = ? AND source_file IN (
            SELECT source_file FROM sources WHERE preferred = 1
        )
    """, (signal_name,)).fetchone()

    if not signal:
        click.echo(f"Signal not found: {signal_name}", err=True)
        conn.close()
        sys.exit(1)

    # Query message
    message = conn.execute("""
        SELECT * FROM messages WHERE name = ? AND source_file IN (
            SELECT source_file FROM sources WHERE preferred = 1
        )
    """, (signal["message"],)).fetchone()

    # Query env var links
    env_links = conn.execute("""
        SELECT * FROM capl_env_bindings WHERE signal = ?
    """, (signal_name,)).fetchall()

    # Query sysvar links
    sysvar_links = conn.execute("""
        SELECT * FROM capl_sysvar_mappings WHERE signal = ?
    """, (signal_name,)).fetchall()

    # Display results
    click.echo(f"\n=== Signal: {signal_name} ===\n")

    if message:
        click.echo(f"Message: {message['name']}")
        click.echo(f"  Frame ID: {message['frame_id_hex']}")
        click.echo(f"  DLC: {message['dlc']}")
        click.echo(f"  Cycle: {message['cycle_ms']} ms")

    click.echo(f"\nSignal Properties:")
    click.echo(f"  Start Bit: {signal['start_bit']}")
    click.echo(f"  Length: {signal['length']} bits")
    click.echo(f"  Byte Order: {signal['byte_order']}")
    click.echo(f"  Signed: {'Yes' if signal['is_signed'] else 'No'}")
    click.echo(f"  Factor: {signal['factor']}")
    click.echo(f"  Offset: {signal['offset']}")
    if signal['unit']:
        click.echo(f"  Unit: {signal['unit']}")
    if signal['minimum'] and signal['maximum']:
        click.echo(f"  Range: {signal['minimum']} to {signal['maximum']}")

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


@cli.group()
@click.version_option(version="0.1.0", prog_name="capl-forge")
def llm():
    """
    LLM management commands.

    Run 'capl-forge llm --help' for subcommands.
    Run 'capl-forge llm setup' to configure your LLM provider.
    """
    pass


@llm.command("setup")
def llm_setup():
    """Configure LLM provider for CAPL generation."""
    click.echo("LLM Setup - Interactive Configuration")
    click.echo("=" * 50)

    provider = click.prompt("Provider label (e.g., OpenAI, Anthropic)")
    base_url = click.prompt("Base URL (e.g., https://api.openai.com/v1)")
    api_key_env = click.prompt("API key environment variable name (e.g., OPENAI_API_KEY)")
    model = click.prompt("Model name (e.g., gpt-4)")
    max_tokens = click.prompt("Max context tokens", default=4096)
    json_mode = click.confirm("Supports JSON mode?", default=True)

    config = {
        "provider": provider,
        "base_url": base_url,
        "api_key_env": api_key_env,
        "model": model,
        "max_context_tokens": max_tokens,
        "supports_json_mode": json_mode,
    }

    config_path = Path("llm_config.yaml")
    import yaml
    with open(config_path, 'w') as f:
        yaml.dump(config, f)

    click.echo(f"\nLLM configuration saved to: {config_path}")
    click.echo("Run 'capl-forge llm test' to verify the configuration.")


@llm.command("test")
def llm_test():
    """Test LLM provider connectivity and response."""
    config_path = Path("llm_config.yaml")

    if not config_path.exists():
        click.echo("Error: llm_config.yaml not found", err=True)
        click.echo("Run 'capl-forge llm setup' first.", err=True)
        sys.exit(1)

    import os
    import yaml

    with open(config_path) as f:
        config = yaml.safe_load(f)

    api_key = os.environ.get(config["api_key_env"])
    if not api_key:
        click.echo(f"Error: Environment variable {config['api_key_env']} not set", err=True)
        sys.exit(1)

    click.echo("Testing LLM connectivity...")

    try:
        import requests

        response = requests.post(
            f"{config['base_url']}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": config["model"],
                "messages": [{"role": "user", "content": "Say 'OK' if you can read this."}],
                "max_tokens": 10,
            },
            timeout=30,
        )

        if response.status_code == 200:
            health = {
                "status": "ok",
                "provider": config["provider"],
                "model": config["model"],
                "tested_at": __import__('datetime').datetime.utcnow().isoformat(),
            }
            with open("llm_health.json", 'w') as f:
                json.dump(health, f, indent=2)
            click.echo("LLM test successful!")
            click.echo(f"Health report saved to: llm_health.json")
        else:
            click.echo(f"Error: LLM returned status {response.status_code}", err=True)
            click.echo(response.text)
            sys.exit(1)

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@llm.command("status")
def llm_status():
    """Show LLM configuration and health status."""
    config_path = Path("llm_config.yaml")
    health_path = Path("llm_health.json")

    if not config_path.exists():
        click.echo("LLM not configured. Run 'capl-forge llm setup'.")
        return

    import yaml
    with open(config_path) as f:
        config = yaml.safe_load(f)

    click.echo("LLM Configuration:")
    click.echo(f"  Provider: {config['provider']}")
    click.echo(f"  Base URL: {config['base_url']}")
    click.echo(f"  Model: {config['model']}")
    click.echo(f"  API Key Env: {config['api_key_env']}")
    click.echo(f"  Max Tokens: {config['max_context_tokens']}")
    click.echo(f"  JSON Mode: {config['supports_json_mode']}")

    import os
    api_key = os.environ.get(config["api_key_env"])
    click.echo(f"\nAPI Key: {'Set' if api_key else 'NOT SET'}")

    if health_path.exists():
        with open(health_path) as f:
            health = json.load(f)
        click.echo(f"\nHealth Status: {health.get('status', 'unknown')}")
        click.echo(f"Last Tested: {health.get('tested_at', 'unknown')}")
    else:
        click.echo("\nHealth Status: NOT TESTED (run 'capl-forge llm test')")


@cli.command()
@click.option(
    "--db",
    "-d",
    "db_path",
    type=click.Path(exists=True),
    default="dcu_knowledge.db",
    help="SQLite knowledge base path",
)
def coverage_report(db_path):
    """
    Generate a coverage report for the knowledge base.

    Tests signal lookup, signal -> message, signal -> env var,
    signal -> sysvar, and full context chain queries.
    """
    import sqlite3

    db = Path(db_path)
    if not db.exists():
        click.echo(f"Error: Database not found: {db_path}", err=True)
        sys.exit(1)

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

        # Signal lookup
        if sig_name:
            report["signal_lookup"]["PASS"] += 1
        else:
            report["signal_lookup"]["FAIL"] += 1

        # Signal -> message
        if sig["message"]:
            msg = conn.execute("SELECT * FROM messages WHERE name = ?", (sig["message"],)).fetchone()
            if msg:
                report["signal_to_message"]["PASS"] += 1
            else:
                report["signal_to_message"]["PARTIAL"] += 1
        else:
            report["signal_to_message"]["FAIL"] += 1

        # Signal -> env var
        env_links = conn.execute(
            "SELECT * FROM capl_env_bindings WHERE signal = ?", (sig_name,)
        ).fetchall()
        if len(env_links) > 0:
            report["signal_to_envvar"]["PASS"] += 1
        else:
            report["signal_to_envvar"]["PARTIAL"] += 1

        # Signal -> sysvar
        sysvar_links = conn.execute(
            "SELECT * FROM capl_sysvar_mappings WHERE signal = ?", (sig_name,)
        ).fetchall()
        if len(sysvar_links) > 0:
            report["signal_to_sysvar"]["PASS"] += 1
        else:
            report["signal_to_sysvar"]["PARTIAL"] += 1

        # Full context chain
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


@cli.command()
@click.option(
    "--db",
    "-d",
    "db_path",
    type=click.Path(exists=True),
    default="dcu_knowledge.db",
    help="SQLite knowledge base path",
)
def stats(db_path):
    """Show knowledge base statistics."""
    import sqlite3

    db = Path(db_path)
    if not db.exists():
        click.echo(f"Error: Database not found: {db_path}", err=True)
        sys.exit(1)

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


if __name__ == "__main__":
    cli()
