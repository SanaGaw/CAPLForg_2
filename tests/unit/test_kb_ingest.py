"""Tests for KB ingestion — schema, helpers, and build_knowledge_base integration."""
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from capl_forge.kb.row_utils import (
    TABLE_COLUMNS,
    SOURCE_TABLES,
    coerce_value as _coerce_value,
    row_values_for_table as _row_values_for_table,
)
from capl_forge.kb.ingest import build_knowledge_base
from capl_forge.kb.schema import SCHEMA_SQL
from capl_forge.kb.source_registry import family_key, determine_kind


class TestFamilyKey:
    """Tests for version stripping logic."""

    def test_wip_suffix(self):
        assert family_key("TestFile_wip_01.dbc") == "testfile"
        assert family_key("TestFile_wip_42.dbc") == "testfile"
        assert family_key("TestFile-wip_99.dbc") == "testfile"

    def test_version_suffix(self):
        assert family_key("TestFile_v1.dbc") == "testfile"
        assert family_key("TestFile_v2.dbc") == "testfile"

    def test_date_suffix(self):
        assert family_key("TestFile_20240101.dbc") == "testfile"
        assert family_key("TestFile_20241231.dbc") == "testfile"

    def test_number_suffix(self):
        assert family_key("TestFile-001.dbc") == "testfile"
        assert family_key("TestFile-999.dbc") == "testfile"

    def test_no_version(self):
        assert family_key("TestFile.dbc") == "testfile"
        assert family_key("FOO_SIGNAL_X.dbc") == "foo_signal_x"


class TestDetermineKind:
    """Tests for file kind determination."""

    def test_dbc_with_messages(self):
        counts = {"Test.dbc": {"messages": 10, "signals": 50}}
        result = determine_kind("Test.dbc", Path("Test.dbc"), counts)
        assert result == "dbc"

    def test_dbc_with_envvars_only(self):
        counts = {"EnvTest.dbc": {"env_vars": 5}}
        result = determine_kind("EnvTest.dbc", Path("EnvTest.dbc"), counts)
        assert result == "envdbc"

    def test_cdd(self):
        result = determine_kind("Test.cdd", Path("Test.cdd"), {})
        assert result == "cdd"

    def test_vsysvar(self):
        result = determine_kind("Test.vsysvar", Path("Test.vsysvar"), {})
        assert result == "vsysvar"

    def test_capl(self):
        assert determine_kind("Test.can", Path("Test.can"), {}) == "capl"
        assert determine_kind("Test.cin", Path("Test.cin"), {}) == "capl"

    def test_panel(self):
        result = determine_kind("Test.xvp", Path("Test.xvp"), {})
        assert result == "panel"


class TestCoerceValue:
    """Tests for type coercion."""

    def test_integer_columns(self):
        assert _coerce_value("signals", "is_signed", "True") == 1
        assert _coerce_value("signals", "is_signed", "False") == 0
        assert _coerce_value("signals", "start_bit", "5") == 5
        assert _coerce_value("signals", "length", "8") == 8

    def test_boolean_to_integer(self):
        assert _coerce_value("signals", "is_signed", True) == 1
        assert _coerce_value("signals", "is_signed", False) == 0

    def test_real_columns(self):
        assert _coerce_value("signals", "factor", "1.5") == 1.5
        assert _coerce_value("signals", "offset", "-2.0") == -2.0
        assert _coerce_value("sysvars", "min", "0.0") == 0.0

    def test_invalid_integer(self):
        assert _coerce_value("signals", "start_bit", "not_a_number") is None

    def test_invalid_real(self):
        assert _coerce_value("signals", "factor", "not_a_float") is None

    def test_empty_string(self):
        assert _coerce_value("signals", "is_signed", "") is None

    def test_none_value(self):
        assert _coerce_value("signals", "is_signed", None) is None


class TestRowValuesForTable:
    """Tests for row value extraction and normalization."""

    def test_sysvars_normalizes_default(self):
        row = {
            "source_file": "test.vsysvar",
            "namespace": "NS",
            "name": "Var",
            "full_path": "NS::Var",
            "default": "5",
            "type": "int",
        }
        values = _row_values_for_table("sysvars", row)
        cols = TABLE_COLUMNS["sysvars"]
        default_val_idx = cols.index("default_val")
        assert values[default_val_idx] == 5.0

    def test_capl_sysvar_mappings_normalizes_sysvar(self):
        row = {
            "source_file": "test.can",
            "sysvar": "NS::Var",
            "signal": "TestSignal",
        }
        values = _row_values_for_table("capl_sysvar_mappings", row)
        cols = TABLE_COLUMNS["capl_sysvar_mappings"]
        sysvar_path_idx = cols.index("sysvar_path")
        assert values[sysvar_path_idx] == "NS::Var"


class TestSchemaCreation:
    """Tests for database schema creation."""

    def test_all_tables_created(self):
        conn = sqlite3.connect(":memory:")
        conn.executescript(SCHEMA_SQL)
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

    def test_indexes_created(self):
        conn = sqlite3.connect(":memory:")
        conn.executescript(SCHEMA_SQL)
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
        conn = sqlite3.connect(":memory:")
        conn.executescript(SCHEMA_SQL)

        for table, columns in TABLE_COLUMNS.items():
            cursor = conn.execute(f"PRAGMA table_info({table})")
            schema_cols = {row[1] for row in cursor.fetchall()}
            assert set(columns).issubset(schema_cols), \
                f"TABLE_COLUMNS['{table}'] has columns not in schema: {set(columns) - schema_cols}"

        conn.close()

    def test_source_tables_complete(self):
        expected = {
            "messages", "signals", "sysvars", "env_vars", "value_tables",
            "capl_env_bindings", "capl_sysvar_mappings", "dids", "did_fields",
            "dtcs", "calibrations", "requirements"
        }
        assert set(SOURCE_TABLES) == expected


class TestAuditEventsAndIssues:
    """Tests for audit_events and issues INSERT during build."""

    @pytest.fixture
    def temp_db(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        yield db_path
        try:
            os.unlink(db_path)
        except FileNotFoundError:
            pass

    def test_audit_event_written_on_build(self, temp_db):
        """build_knowledge_base should write audit_events."""
        dbc_file = Path(tempfile.gettempdir()) / "TestFrame_42.dbc"
        dbc_file.write_text("VERSION ''")

        inspection = {
            "references": [
                {
                    "basename": "TestFrame_42.dbc",
                    "resolved_path": str(dbc_file),
                    "exists": True,
                    "extension": "dbc",
                    "role": "network",
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
            "sysvars": [], "env_vars": [], "value_tables": [],
            "capl_bindings": [], "capl_sysvar_mappings": [],
            "dids": [], "did_fields": [],
        }

        summary = build_knowledge_base(
            inspection, temp_db, log=lambda m: None, run_id="test-audit-001"
        )

        conn = sqlite3.connect(temp_db)
        events = conn.execute("SELECT * FROM audit_events WHERE run_id = ?", ("test-audit-001",)).fetchall()
        assert len(events) >= 2  # schema_created + build_complete
        event_types = [e[3] for e in events]
        assert "schema_created" in event_types
        assert "build_complete" in event_types
        conn.close()

    def test_issue_written_for_orphan_source(self, temp_db):
        """Orphan data sources should generate issue records."""
        inspection = {
            "references": [],
            "inventory": [],
            "dbc_messages": [
                {
                    "source_file": "missing_file.dbc",
                    "name": "OrphanMsg",
                }
            ],
            "dbc_signals": [], "sysvars": [], "env_vars": [], "value_tables": [],
            "capl_bindings": [], "capl_sysvar_mappings": [],
            "dids": [], "did_fields": [],
        }

        build_knowledge_base(
            inspection, temp_db, log=lambda m: None, run_id="test-orphan-001"
        )

        conn = sqlite3.connect(temp_db)
        issues = conn.execute(
            "SELECT * FROM issues WHERE category = 'orphan_source'"
        ).fetchall()
        assert len(issues) == 1
        assert "missing_file.dbc" in issues[0][4]  # message column
        conn.close()


class TestSyntheticFixtures:
    """Tests using synthetic fixture patterns."""

    def test_synthetic_signal_extraction(self):
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
