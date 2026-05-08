"""LLM management commands with full lifecycle support."""
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import click
import yaml
import requests

from capl_forge.llm.token_counter import estimate_tokens


@click.group()
def llm():
    """LLM management commands."""
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
    max_tokens = click.prompt("Max context tokens", default=4096, type=int)
    json_mode = click.confirm("Supports JSON mode?", default=True)

    config = {
        "provider": provider,
        "base_url": base_url.rstrip("/"),
        "api_key_env": api_key_env,
        "model": model,
        "max_context_tokens": max_tokens,
        "supports_json_mode": json_mode,
        "retry_max_attempts": 3,
        "retry_backoff_seconds": 2,
        "staleness_threshold_seconds": 3600,
    }

    config_path = Path("llm_config.yaml")
    with open(config_path, "w") as f:
        yaml.dump(config, f)

    click.echo(f"\nLLM configuration saved to: {config_path}")
    click.echo("Run 'capl-forge llm test' to verify.")


@llm.command("test")
def llm_test():
    """Test LLM provider connectivity and response with retry + staleness check."""
    config_path = Path("llm_config.yaml")
    health_path = Path("llm_health.json")

    if not config_path.exists():
        click.echo("Error: llm_config.yaml not found. Run 'llm setup' first.", err=True)
        return

    with open(config_path) as f:
        config = yaml.safe_load(f)

    # Staleness check
    if health_path.exists():
        try:
            with open(health_path) as f:
                health = json.load(f)
            tested_at_str = health.get("tested_at", "")
            if tested_at_str:
                tested_at = datetime.fromisoformat(tested_at_str)
                age_seconds = (datetime.now(timezone.utc) - tested_at).total_seconds()
                threshold = config.get("staleness_threshold_seconds", 3600)
                if age_seconds < threshold:
                    click.echo(f"LLM health check is fresh ({age_seconds:.0f}s old, threshold {threshold}s)")
                    click.echo(f"Last test: {health.get('status')} ({health.get('provider')} - {health.get('model')})")
                    click.echo("Force re-test with: rm llm_health.json && capl-forge llm test")
                    return
        except (json.JSONDecodeError, ValueError):
            pass

    api_key = os.environ.get(config["api_key_env"])
    if not api_key:
        click.echo(f"Error: Environment variable {config['api_key_env']} not set", err=True)
        return

    click.echo("Testing LLM connectivity...")

    # Retry logic
    max_attempts = config.get("retry_max_attempts", 3)
    backoff = config.get("retry_backoff_seconds", 2)
    last_error = None

    for attempt in range(1, max_attempts + 1):
        try:
            response = requests.post(
                f"{config['base_url']}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": config["model"],
                    "messages": [{"role": "user", "content": "Say OK"}],
                    "max_tokens": 10,
                },
                timeout=30,
            )

            if response.status_code == 200:
                token_count = estimate_tokens("Say OK")
                health = {
                    "status": "ok",
                    "provider": config["provider"],
                    "model": config["model"],
                    "tested_at": datetime.now(timezone.utc).isoformat(),
                    "token_estimate": token_count,
                    "latency_ms": response.elapsed.total_seconds() * 1000,
                }
                with open(health_path, "w") as f:
                    json.dump(health, f, indent=2)
                click.echo("LLM test successful!")
                click.echo(f"Health report saved to: {health_path}")
                return
            else:
                last_error = f"HTTP {response.status_code}: {response.text[:200]}"
                click.echo(f"Attempt {attempt}/{max_attempts} failed: {last_error}")
        except requests.exceptions.Timeout:
            last_error = "Request timed out"
            click.echo(f"Attempt {attempt}/{max_attempts}: {last_error}")
        except Exception as e:
            last_error = str(e)
            click.echo(f"Attempt {attempt}/{max_attempts}: {last_error}")

        if attempt < max_attempts:
            wait = backoff * attempt
            click.echo(f"Retrying in {wait}s...")
            time.sleep(wait)

    health = {
        "status": "error",
        "provider": config["provider"],
        "model": config["model"],
        "tested_at": datetime.now(timezone.utc).isoformat(),
        "error": last_error,
    }
    with open(health_path, "w") as f:
        json.dump(health, f, indent=2)
    click.echo(f"Error: All {max_attempts} attempts failed: {last_error}", err=True)


@llm.command("status")
def llm_status():
    """Show LLM configuration and health status with staleness check."""
    config_path = Path("llm_config.yaml")
    health_path = Path("llm_health.json")

    if not config_path.exists():
        click.echo("LLM not configured. Run 'llm setup'.")
        return

    with open(config_path) as f:
        config = yaml.safe_load(f)

    click.echo("LLM Configuration:")
    click.echo(f"  Provider: {config['provider']}")
    click.echo(f"  Base URL: {config['base_url']}")
    click.echo(f"  Model: {config['model']}")
    click.echo(f"  API Key Env: {config['api_key_env']}")
    click.echo(f"  Max Tokens: {config['max_context_tokens']}")

    api_key = os.environ.get(config["api_key_env"])
    click.echo(f"\nAPI Key: {'Set' if api_key else 'NOT SET'}")

    if health_path.exists():
        with open(health_path) as f:
            health = json.load(f)
        click.echo(f"\nHealth Status: {health.get('status', 'unknown')}")

        # Staleness check
        tested_at_str = health.get("tested_at", "")
        if tested_at_str:
            try:
                tested_at = datetime.fromisoformat(tested_at_str)
                age = (datetime.now(timezone.utc) - tested_at).total_seconds()
                threshold = config.get("staleness_threshold_seconds", 3600)
                staleness = "FRESH" if age < threshold else "STALE"
                click.echo(f"Last Tested: {tested_at_str} ({age:.0f}s ago, {staleness})")
            except ValueError:
                click.echo(f"Last Tested: {tested_at_str}")
    else:
        click.echo("\nHealth Status: NOT TESTED (run 'llm test')")
