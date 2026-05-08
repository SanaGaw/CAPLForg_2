"""Integration test: scan-project → build-db → query."""
import sys
import os
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))


class TestScanToDb:
    def test_end_to_end_scan_and_build(self, tmp_path):
        """Full scan → build-db → query chain."""
        from capl_forge.kb.ingest import build_knowledge_base

        db_path = tmp_path / "test.db"
        inspection = {
            "references": [
                {
                    "basename": "FOO_SIGNAL_X.dbc",
                    "resolved_path": str(tmp_path / "FOO_SIGNAL_X.dbc"),
                    "exists": True,
                    "extension": "dbc",
                    "role": "network",
                }
            ],
            "inventory": [],
            "dbc_messages": [
                {
                    "source_file": "FOO_SIGNAL_X.dbc",
                    "name": "TestFrame_42",
                    "frame_id_hex": "0x123",
                    "dlc": 8,
                    "bus_role": "vehicle",
                }
            ],
            "dbc_signals": [
                {
                    "source_file": "FOO_SIGNAL_X.dbc",
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
            "value_tables": [],
            "capl_bindings": [],
            "capl_sysvar_mappings": [],
            "dids": [],
            "did_fields": [],
        }

        # Create the referenced DBC file
        (tmp_path / "FOO_SIGNAL_X.dbc").write_text("VERSION ''")

        summary = build_knowledge_base(
            inspection, str(db_path), log=lambda m: None, run_id="test-001"
        )
        assert summary["new_sources"] == ["FOO_SIGNAL_X.dbc"]

        # Query back
        import sqlite3
        conn = sqlite3.connect(str(db_path))
        signals = conn.execute("SELECT * FROM signals").fetchall()
        assert len(signals) == 1
        assert signals[0][2] == "FOO_SIGNAL_X"
        conn.close()
