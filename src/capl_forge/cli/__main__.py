"""CAPL Forge CLI entry point."""
import click

from .scan_project import scan_project
from .query_signal import query_signal
from .coverage_report import coverage_report
from .stats import stats


@click.group()
@click.version_option(version="0.1.0", prog_name="capl-forge")
def cli():
    """CAPL Forge - CANoe Project Knowledge Extraction and Resolution System."""
    pass


# Register commands
cli.add_command(scan_project)
cli.add_command(query_signal)
cli.add_command(coverage_report)
cli.add_command(stats)

# LLM sub-group
from .llm_setup import llm  # noqa: E402
cli.add_command(llm)


if __name__ == "__main__":
    cli()
