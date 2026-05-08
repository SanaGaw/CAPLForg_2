"""Tests for CAPL parser — invoke real CaplParser class on fixture files."""
import sys
from pathlib import Path

import pytest

# Ensure src/ is on path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from capl_forge.extractors.capl.parser import CaplParser

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "synthetic_project"


class TestCaplParserWithFixtures:
    """Tests that actually invoke CaplParser.parse() on synthetic fixtures."""

    @pytest.fixture
    def synthetic_can(self):
        path = FIXTURES_DIR / "synthetic.can"
        if not path.exists():
            pytest.skip("synthetic.can fixture not found")
        return path

    def test_parse_returns_mappings(self, synthetic_can):
        """CaplParser.parse() should return a non-empty list of mappings."""
        parser = CaplParser()
        result = parser.parse(synthetic_can)
        assert isinstance(result, list)
        assert len(result) > 0

    def test_envvar_handler_extracted(self, synthetic_can):
        """CaplParser should extract envvar_to_signal mapping from on envVar handler."""
        parser = CaplParser()
        parser.parse(synthetic_can)
        envvar_mappings = [
            m for m in parser.mappings
            if m["mapping_type"] == "envvar_to_signal"
        ]
        assert len(envvar_mappings) > 0, "Expected at least one envvar_to_signal mapping"
        signal_names = [m["signal_name"] for m in envvar_mappings]
        assert "FOO_SIGNAL_X" in signal_names

    def test_sysvar_handler_extracted(self, synthetic_can):
        """CaplParser should extract sysvar_to_signal mapping from on sysvar handler."""
        parser = CaplParser()
        parser.parse(synthetic_can)
        sysvar_mappings = [
            m for m in parser.mappings
            if m["mapping_type"] == "sysvar_to_signal"
        ]
        assert len(sysvar_mappings) > 0, "Expected at least one sysvar_to_signal mapping"

    def test_message_declaration_extracted(self, synthetic_can):
        """CaplParser should extract message declarations."""
        parser = CaplParser()
        parser.parse(synthetic_can)
        assert len(parser.message_declarations) > 0

    def test_envvar_usages_putvalue(self, synthetic_can):
        """CaplParser should extract putValue usages."""
        parser = CaplParser()
        parser.parse(synthetic_can)
        putvalue_usages = [
            u for u in parser.envvar_usages
            if u["usage_type"] == "putvalue"
        ]
        assert len(putvalue_usages) > 0

    def test_envvar_usages_direct_write(self, synthetic_can):
        """CaplParser should extract @EV_xxx = value direct writes."""
        parser = CaplParser()
        parser.parse(synthetic_can)
        direct_writes = [
            u for u in parser.envvar_usages
            if u["usage_type"] == "direct_write"
        ]
        assert len(direct_writes) > 0

    def test_envvar_usages_direct_read(self, synthetic_can):
        """CaplParser should extract @EV_xxx read references."""
        parser = CaplParser()
        parser.parse(synthetic_can)
        direct_reads = [
            u for u in parser.envvar_usages
            if u["usage_type"] == "direct_read"
        ]
        assert len(direct_reads) > 0

    def test_can_signal_assignment(self, synthetic_can):
        """CaplParser should extract M_MSG.SIGNAL = value patterns."""
        parser = CaplParser()
        parser.parse(synthetic_can)
        can_mappings = [
            m for m in parser.mappings
            if m["mapping_type"] == "envvar_to_can_signal"
        ]
        assert len(can_mappings) > 0
        assert can_mappings[0]["message_name"] == "msg_test"
        assert can_mappings[0]["signal_name"] == "FOO_SIGNAL_X"

    def test_nested_brace_handling(self, tmp_path):
        """CaplParser should correctly handle nested braces in handlers."""
        can_file = tmp_path / "nested.can"
        can_file.write_text("""
on envVar EV_NESTED {
    if (1) {
        if (2) {
            setSignal(DeepSignal, @this);
        }
    }
    setSignal(OuterSignal, @this);
}
""")
        parser = CaplParser()
        parser.parse(can_file)
        envvar_mappings = [
            m for m in parser.mappings
            if m["mapping_type"].startswith("envvar_")
        ]
        signal_names = [m["signal_name"] for m in envvar_mappings]
        assert "DeepSignal" in signal_names, "Should extract signal from nested braces"
        assert "OuterSignal" in signal_names, "Should extract signal from outer scope"

    def test_source_file_set(self, synthetic_can):
        """All extracted mappings should have source_file set."""
        parser = CaplParser()
        parser.parse(synthetic_can)
        for mapping in parser.mappings:
            assert mapping["source_file"] == "synthetic.can"


class TestCaplParserSabotageProbe:
    """Sabotage probe: verify tests depend on real CaplParser logic."""

    def test_sabotage_parse_returns_empty(self, synthetic_can, monkeypatch):
        """Sabotage probe: if parse() returns [], envvar test should FAIL."""
        parser = CaplParser()
        monkeypatch.setattr(parser, "_parse_envvar_handlers", lambda c, s: None)
        monkeypatch.setattr(parser, "_parse_sysvar_handlers", lambda c, s: None)
        result = parser.parse(synthetic_can)
        assert len(result) == 0  # Sabotage works

    def test_sabotage_sysvar_missing(self, synthetic_can, monkeypatch):
        """Sabotage: removing sysvar parsing should make sysvar test fail."""
        parser = CaplParser()
        monkeypatch.setattr(parser, "_parse_sysvar_handlers", lambda c, s: None)
        parser.parse(synthetic_can)
        sysvar_mappings = [
            m for m in parser.mappings
            if m["mapping_type"] == "sysvar_to_signal"
        ]
        assert len(sysvar_mappings) == 0  # Sabotage confirmed
