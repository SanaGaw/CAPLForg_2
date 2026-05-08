"""
CLI Tests for CAPL Forge Module 1
==================================

Tests the Click CLI structure using CliRunner.
These tests verify the stabilization fixes for the CLI.

Synthetic fixtures only - no real automotive files.
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import click
import pytest
from click.testing import CliRunner

# Add parent directory to path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from main import cli


class TestCLIHelp:
    """Tests for CLI help command outputs."""

    def test_root_help(self):
        """Root CLI --help should return exit code 0."""
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "CAPL Forge" in result.output

    def test_llm_help(self):
        """llm --help should return exit code 0."""
        runner = CliRunner()
        result = runner.invoke(cli, ["llm", "--help"])
        assert result.exit_code == 0
        assert "setup" in result.output or "Subcommands" in result.output

    def test_llm_setup_help(self):
        """llm setup --help should return exit code 0."""
        runner = CliRunner()
        result = runner.invoke(cli, ["llm", "setup", "--help"])
        assert result.exit_code == 0

    def test_llm_test_help(self):
        """llm test --help should return exit code 0."""
        runner = CliRunner()
        result = runner.invoke(cli, ["llm", "test", "--help"])
        assert result.exit_code == 0

    def test_llm_status_help(self):
        """llm status --help should return exit code 0."""
        runner = CliRunner()
        result = runner.invoke(cli, ["llm", "status", "--help"])
        assert result.exit_code == 0

    def test_scan_project_help(self):
        """scan-project --help should return exit code 0."""
        runner = CliRunner()
        result = runner.invoke(cli, ["scan-project", "--help"])
        assert result.exit_code == 0
        assert "--config" in result.output

    def test_coverage_report_help(self):
        """coverage-report --help should return exit code 0."""
        runner = CliRunner()
        result = runner.invoke(cli, ["coverage-report", "--help"])
        assert result.exit_code == 0

    def test_stats_help(self):
        """stats --help should return exit code 0."""
        runner = CliRunner()
        result = runner.invoke(cli, ["stats", "--help"])
        assert result.exit_code == 0

    def test_query_signal_help(self):
        """query-signal --help should return exit code 0."""
        runner = CliRunner()
        result = runner.invoke(cli, ["query-signal", "--help"])
        assert result.exit_code == 0


class TestCLIStructure:
    """Tests for CLI command group structure."""

    def test_llm_is_group_not_command(self):
        """llm should be a group allowing subcommands, not a simple command."""
        runner = CliRunner()

        # This should work if llm is a group
        result = runner.invoke(cli, ["llm", "status"])
        # Should not fail with "no such option" if llm is properly a group

        # Verify llm has subcommands
        help_result = runner.invoke(cli, ["llm", "--help"])
        assert "setup" in help_result.output
        assert "test" in help_result.output
        assert "status" in help_result.output

    def test_llm_subcommands_work(self):
        """LLM subcommands should execute without errors."""
        runner = CliRunner()

        # status should work even without config
        result = runner.invoke(cli, ["llm", "status"])
        # Should execute (may show "not configured" message)
        assert result.exit_code == 0

    def test_version_option(self):
        """--version flag should work."""
        runner = CliRunner()
        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0


class TestCAPLForgeCFGEnvVar:
    """Tests for CAPL_FORGE_CFG environment variable handling."""

    def test_reads_from_environ_not_file(self):
        """CAPL_FORGE_CFG should be read from os.environ, not local file."""
        # The _get_capl_forge_cfg function should use os.environ.get
        from main import _get_capl_forge_cfg

        # When env var is not set, should return None
        with patch.dict(os.environ, {}, clear=True):
            result = _get_capl_forge_cfg()
            assert result is None

    def test_reads_environ_value(self):
        """Should read CAPL_FORGE_CFG from environment."""
        from main import _get_capl_forge_cfg

        with patch.dict(os.environ, {"CAPL_FORGE_CFG": "/path/to/config.cfg"}):
            result = _get_capl_forge_cfg()
            assert result == "/path/to/config.cfg"

    def test_missing_env_var_reported(self):
        """Missing CAPL_FORGE_CFG should be reported clearly."""
        runner = CliRunner()

        with patch.dict(os.environ, {}, clear=True):
            result = runner.invoke(cli, ["scan-project"], input="")
            # Should fail with clear error about missing config
            assert result.exit_code != 0
            assert "CAPL_FORGE_CFG" in result.output or "--config" in result.output

    def test_does_not_read_local_file_named_capl_forge_cfg(self):
        """Should not read a local file named CAPL_FORGE_CFG."""
        # This test verifies the fix: we no longer check for a local file
        from main import _get_capl_forge_cfg

        # Create a local file named CAPL_FORGE_CFG
        with tempfile.TemporaryDirectory() as tmpdir:
            local_file = Path(tmpdir) / "CAPL_FORGE_CFG"
            local_file.write_text("/fake/path.cfg")

            # Change to that directory
            original_cwd = os.getcwd()
            os.chdir(tmpdir)

            try:
                # Should still return None (not read from local file)
                result = _get_capl_forge_cfg()
                # The function should NOT read from local file
                # It should only read from environment
                with patch.dict(os.environ, {}, clear=True):
                    result = _get_capl_forge_cfg()
                    assert result is None
            finally:
                os.chdir(original_cwd)


class TestSQLiteRowAccess:
    """Tests for SQLite row access with row_factory."""

    def test_coverage_report_uses_row_factory(self):
        """coverage_report should set row_factory = sqlite3.Row."""
        runner = CliRunner()

        # Create a minimal test database
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"

            # Create minimal schema
            import sqlite3
            conn = sqlite3.connect(db_path)
            conn.execute("""
                CREATE TABLE sources (
                    source_file TEXT PRIMARY KEY,
                    file_role TEXT,
                    sha256 TEXT,
                    preferred INTEGER DEFAULT 0
                )
            """)
            conn.execute("""
                CREATE TABLE signals (
                    name TEXT,
                    message TEXT,
                    source_file TEXT,
                    start_bit INTEGER,
                    length INTEGER,
                    is_signed INTEGER
                )
            """)
            conn.execute("""
                CREATE TABLE messages (
                    name TEXT,
                    frame_id_hex TEXT,
                    dlc INTEGER
                )
            """)
            conn.execute("""
                CREATE TABLE capl_env_bindings (
                    signal TEXT,
                    env_var TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE capl_sysvar_mappings (
                    signal TEXT,
                    sysvar_path TEXT
                )
            """)
            conn.commit()
            conn.close()

            # Run coverage report
            result = runner.invoke(cli, ["coverage-report", "--db", str(db_path)])

            # Should execute without attribute errors
            # If row_factory is not set, accessing sig["name"] would fail
            assert result.exit_code == 0


class TestModuleBoundary:
    """Tests for Module 1 boundary enforcement."""

    def test_canoe_parser_does_not_expose_generate_capl(self):
        """canoe_parser.__all__ should not include generate_capl."""
        import canoe_parser

        # generate_capl should NOT be in __all__
        assert "generate_capl" not in canoe_parser.__all__

    def test_importing_module_1_does_not_suggest_capl_generation(self):
        """Module 1 imports should not imply CAPL generation."""
        import canoe_parser

        # Only these should be exported
        expected_exports = [
            "parse_config",
            "parse_config_to_json",
            "get_supported_extensions",
            "ext_role",
            "CfgInspector",
        ]

        for export in expected_exports:
            assert export in canoe_parser.__all__, f"{export} should be in __all__"

        # generate_capl should NOT be exported
        assert "generate_capl" not in canoe_parser.__all__

    def test_generate_capl_still_exists_for_future(self):
        """generate_capl function should still exist (for Module 2) but not exported."""
        from canoe_parser import generate_capl

        # Function should exist but raise NotImplementedError
        with pytest.raises(NotImplementedError):
            generate_capl("dummy_plan")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])