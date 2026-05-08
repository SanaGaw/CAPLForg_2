"""
Tests for CAPL Forge Knowledge Base Builder
===========================================

These tests verify the kb_builder module functionality using synthetic fixtures.
Real automotive files must never be committed to the repository.
"""

import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from kb_builder import (
    SCHEMA_SQL,
    TABLE_COLUMNS,
    SOURCE_TABLES,
    _family_key,
    _determine_kind,
    _row_values_for_table,
    _coerce_value,
    build_knowledge_base,
)


class TestFamilyKey:
    """Tests for version stripping logic."""

    def test_wip_suffix(self):
        """WIP suffixes should be stripped."""
        assert _family_key("TestFile_wip_01.dbc") == "testfile"
        assert _family_key("TestFile_wip_42.dbc") == "testfile"
        assert _family_key("TestFile-wip_99.dbc") == "testfile"

    def test_version_suffix(self):
        """Version suffixes should be stripped."""
        assert _family_key("TestFile_v1.dbc") == "testfile"
        assert _family_key("TestFile_v2.dbc") == "testfile"

    def test_date_suffix(self):
        """Date suffixes should be stripped."""
        assert _family_key("TestFile_20240101.dbc") == "testfile"
        assert _family_key("TestFile_20241231.dbc") == "testfile"

    def test_number_suffix(self):
        """Number suffixes should be stripped."""
        assert _family_key("TestFile-001.dbc") == "testfile"
        assert _family_key("TestFile-999.dbc") == "testfile"

    def test_no_version(self):
        """Files without version markers should be unchanged."""
        assert _family_key("TestFile.dbc") == "testfile"
        assert _family_key("FOO_SIGNAL_X.dbc") == "foo_signal_x"


class TestDetermineKind:
    """Tests for file kind determination."""

    def test_dbc_with_messages(self):
        """DBC with messages should be kind 'dbc'."""
        counts = {"Test.dbc": {"messages": 10, "signals": 50}}
        result = _determine_kind("Test.dbc", Path("Test.dbc"), counts)
        assert result == "dbc"

    def test_dbc_with_envvars_only(self):
        """DBC with only env vars should be kind 'envdbc'."""
        counts = {"EnvTest.dbc": {"env_vars": 5}}
        result = _determine_kind("EnvTest.dbc", Path("EnvTest.dbc"), counts)
        assert result == "envdbc"

    def test_cdd(self):
        """CDD files should be kind 'cdd'."""
        result = _determine_kind("Test.cdd", Path("Test.cdd"), {})
        assert result == "cdd"

    def test_vsysvar(self):
        """VSYSVAR files should be kind 'vsysvar'."""
        result = _determine_kind("Test.vsysvar", Path("Test.vsysvar"), {})
        assert result == "vsysvar"

    def test_capl(self):
        """CAN/CIN files should be kind 'capl'."""
        assert _determine_kind("Test.can", Path("Test.can"), {}) == "capl"
        assert _determine_kind("Test.cin", Path("Test.cin"), {}) == "capl"

    def test_panel(self):
        """XVP files should be kind 'panel'."""
        result = _determine_kind("Test.xvp", Path("Test.xvp"), {})
        assert result == "panel"


class TestCoerceValue:
    """Tests for type coercion."""

    def test_integer_columns(self):
        """Integer columns should convert to int."""
        assert _coerce_value("signals", "is_signed", "True") == 1
        assert _coerce_value("signals", "is_signed", "False") == 0
        assert _coerce_value("signals", "start_bit", "5") == 5
        assert _coerce_value("signals", "length", "8") == 8

    def test_boolean_to_integer(self):
        """Boolean values should convert to 1/0 for integer columns."""
        assert _coerce_value("signals", "is_signed", True) == 1
        assert _coerce_value("signals", "is_signed", False) == 0

    def test_real_columns(self):
        """Real columns should convert to float."""
        assert _coerce_value("signals", "factor", "1.5") == 1.5
        assert _coerce_value("signals", "offset", "-2.0") == -2.0
        assert _coerce_value("sysvars", "min", "0.0") == 0.0

    def test_invalid_integer(self):
        """Invalid values should return None for integer columns."""
        assert _coerce_value("signals", "start_bit", "not_a_number") is None

    def test_invalid_real(self):
        """Invalid values should return None for real columns."""
        assert _coerce_value("signals", "factor", "not_a_float") is None

    def test_empty_string(self):
        """Empty strings should return None."""
        assert _coerce_value("signals", "is_signed", "") is None

    def test_none_value(self):
        """None values should return None."""
        assert _coerce_value("signals", "is_signed", None) is None


class TestRowValuesForTable:
    """Tests for row value extraction and normalization."""

    def test_sysvars_normalizes_default(self):
        """sysvars table should normalize 'default' to 'default_val'."""
        row = {
            "source_file": "test.vsysvar",
            "namespace": "NS",
            "name": "Var",
            "full_path": "NS::Var",
            "default": "5",  # Old key
            "type": "int",
        }
        values = _row_values_for_table("sysvars", row)
        # Check that default_val column gets the value (will be coerced to float)
        cols = TABLE_COLUMNS["sysvars"]
        default_val_idx = cols.index("default_val")
        assert values[default_val_idx] == 5.0

    def test_capl_sysvar_mappings_normalizes_sysvar(self):
        """capl_sysvar_mappings should normalize 'sysvar' to 'sysvar_path'."""
        row = {
            "source_file": "test.can",
            "sysvar": "NS::Var",  # Old key from inspector
            "signal": "TestSignal",
        }
        values = _row_values_for_table("capl_sysvar_mappings", row)
        cols = TABLE_COLUMNS["capl_sysvar_mappings"]
        sysvar_path_idx = cols.index("sysvar_path")
        assert values[sysvar_path_idx] == "NS::Var"


class TestBuildKnowledgeBase:
    """Integration tests for build_knowledge_base function."""

    @pytest.fixture
    def temp_db(self):
        """Create a temporary database file."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        yield db_path
        # Cleanup
        try:
            os.unlink(db_path)
        except FileNotFoundError:
            pass

    @pytest.fixture
    def minimal_inspection_result(self):
        """Create a minimal inspection result for testing."""
        return {
            "references": [
                {
                    "basename": "TestFrame_42.dbc",
                    "resolved_path": str(Path(tempfile.gettempdir()) / "TestFrame_42.dbc"),
                    "exists": True,
                }
            ],
            "inventory": [],
            "dbc_messages": [
                {
                    "source_file": "TestFrame_42.dbc",
                    "name": "TestFrame_42",
                    "frame_id_hex": "0x123",
                    "dlc": 8,
                    "bus_role": "vehicle",
                }
            ],
            "dbc_signals": [
                {
                    "source_file": "TestFrame_42.dbc",
                    "name": "FOO_SIGNAL_X",
                    "message": "TestFrame_42",
                    "start_bit": 0,
                    "length": 8,
                    "is_signed": 0,
                    "factor": 1.0,
                    "offset": 0.0,
                    "bus_role": "vehicle",
                }
            ],
            "sysvars": [],
            "env_vars": [],
            "capl_bindings": [],
            "capl_sysvar_mappings": [],
            "dids": [],
            "did_fields": [],
        }

    def test_schema_creation(self, temp_db):
        """Database schema should be created with all required tables."""
        conn = sqlite3.connect(temp_db)
        conn.executescript(SCHEMA_SQL)
        conn.close()

        conn = sqlite3.connect(temp_db)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = {row[0] for row in cursor.fetchall()}

        required_tables = {
            "sources", "messages", "signals", "sysvars", "env_vars",
            "value_tables", "capl_env_bindings", "capl_sysvar_mappings",
            "dids", "did_fields", "dtcs", "calibrations", "requirements",
            "conventions", "issues", "audit_events"
        }
        assert required_tables.issubset(tables)
        conn.close()

    def test_indexes_created(self, temp_db):
        """Required indexes should be created."""
        conn = sqlite3.connect(temp_db)
        conn.executescript(SCHEMA_SQL)
        conn.close()

        conn = sqlite3.connect(temp_db)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%'"
        )
        indexes = {row[0] for row in cursor.fetchall()}

        required_indexes = {
            "idx_messages_name", "idx_messages_frame_id_hex",
            "idx_signals_name", "idx_signals_message",
            "idx_sysvars_name", "idx_sysvars_fullpath",
            "idx_envvars_name",
            "idx_dids_hex", "idx_didfields_did",
            "idx_caplsv_sysvar", "idx_caplsv_signal",
            "idx_caplenv_envvar", "idx_caplenv_signal",
        }
        assert required_indexes.issubset(indexes)
        conn.close()

    def test_table_columns_match_schema(self):
        """TABLE_COLUMNS should match actual schema columns."""
        conn = sqlite3.connect(":memory:")
        conn.executescript(SCHEMA_SQL)

        for table, columns in TABLE_COLUMNS.items():
            cursor = conn.execute(f"PRAGMA table_info({table})")
            schema_cols = {row[1] for row in cursor.fetchall()}
            assert set(columns).issubset(schema_cols), \
                f"TABLE_COLUMNS['{table}'] has columns not in schema: {set(columns) - schema_cols}"

        conn.close()

    def test_source_tables_complete(self):
        """SOURCE_TABLES should contain all tables with source_file column."""
        expected = {
            "messages", "signals", "sysvars", "env_vars", "value_tables",
            "capl_env_bindings", "capl_sysvar_mappings", "dids", "did_fields",
            "dtcs", "calibrations", "requirements"
        }
        assert set(SOURCE_TABLES) == expected


class TestSyntheticFixtures:
    """Tests using synthetic fixture patterns."""

    def test_synthetic_signal_extraction(self):
        """Synthetic signals like FOO_SIGNAL_X should be extractable."""
        row = {
            "source_file": "TestFrame_42.dbc",
            "name": "FOO_SIGNAL_X",
            "message": "TestFrame_42",
            "start_bit": 0,
            "length": 8,
            "is_signed": 0,
            "factor": 1.0,
            "offset": 0.0,
            "bus_role": "vehicle",
        }
        values = _row_values_for_table("signals", row)
        cols = TABLE_COLUMNS["signals"]
        name_idx = cols.index("name")
        assert values[name_idx] == "FOO_SIGNAL_X"

    def test_synthetic_message_extraction(self):
        """Synthetic messages like TestFrame_42 should be extractable."""
        row = {
            "source_file": "TestFrame_42.dbc",
            "name": "TestFrame_42",
            "frame_id_hex": "0x123",
            "dlc": 8,
            "bus_role": "vehicle",
        }
        values = _row_values_for_table("messages", row)
        cols = TABLE_COLUMNS["messages"]
        name_idx = cols.index("name")
        assert values[name_idx] == "TestFrame_42"

    def test_synthetic_did_extraction(self):
        """Synthetic DIDs like 0xDEAD should be extractable."""
        row = {
            "source_file": "Test.cdd",
            "did_hex": "0xDEAD",
            "qual": "CURRENTDATA",
            "name": "TestDID",
        }
        values = _row_values_for_table("dids", row)
        cols = TABLE_COLUMNS["dids"]
        did_hex_idx = cols.index("did_hex")
        assert values[did_hex_idx] == "0xDEAD"


class TestCaplParser:
    """Tests for CAPL parser patterns."""

    def test_envvar_handler_pattern(self):
        """Environment variable handlers should be detected."""
        import re

        content = '''
        on envVar EV_TEST_SIGNAL {
            setSignal(TestSignal, @this);
        }
        '''
        pattern = re.compile(r'on\s+envVar\s+(\w+)\s*\{')
        match = pattern.search(content)
        assert match is not None
        assert match.group(1) == "EV_TEST_SIGNAL"

    def test_sysvar_handler_pattern(self):
        """System variable handlers should be detected."""
        import re

        content = '''
        on sysvar sysvar::Namespace::TestVar {
            setSignal(TestSignal, @this);
        }
        '''
        pattern = re.compile(r'on\s+sysvar(?:_change)?\s+([\w:]+(?:::[\w]+)*)\s*\{')
        match = pattern.search(content)
        assert match is not None
        assert "Namespace" in match.group(1)

    def test_set_signal_pattern(self):
        """setSignal calls should be detected."""
        import re

        pattern = re.compile(r'setSignal\s*\(\s*([\w]+)\s*,\s*([^)]+)\)')
        content = 'setSignal(TestSignal, @this);'
        match = pattern.search(content)
        assert match is not None
        assert match.group(1) == "TestSignal"


class TestDbcParser:
    """Tests for DBC parser patterns."""

    def test_env_var_pattern(self):
        """DBC environment variables should be detected."""
        import re

        # Pattern that matches DBC EV_ lines
        # Note: DBC format has EV_ directly followed by name without space
        ev_pattern = re.compile(
            r'^EV_(?P<name>\w+)\s*:\s*(?P<dtype>\d+)\s+'
            r'\[(?P<min>[-\d\.]+)\|(?P<max>[-\d\.]+)\]\s*'
            r'"(?P<unit>[^"]*)"\s+(?P<init>\d+)\s+'
            r'(?P<ev_id>\d+)\s+(?P<access>\w+)',
            re.MULTILINE,
        )

        content = 'EV_TEST_VAR: 1 [-100|100] "km/h" 0 1 readwrite'
        match = ev_pattern.search(content)
        assert match is not None
        assert match.group("name") == "TEST_VAR"
        assert match.group("unit") == "km/h"
        assert match.group("ev_id") == "1"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
