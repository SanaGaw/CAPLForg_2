"""Unit tests for core modules."""

import pytest
from pathlib import Path
import tempfile
import os
from src.core.signal_registry import SignalRegistry, Signal
from src.core.cross_validator import CrossValidator
from src.core.pattern_matcher import PatternMatcher
from src.core.capl_fingerprinter import CaplStructuralFingerprinter


class TestSignalRegistry:
    """Tests for SignalRegistry."""

    def test_register_signal(self, tmp_path):
        """Test signal registration."""
        db_path = tmp_path / "test.db"
        registry = SignalRegistry(db_path)

        signal = registry.register(
            name="TestSignal",
            bus_type="CAN",
            ecu_node="BCM",
            env_var_name="EnvTestSignal"
        )

        assert signal.name == "TestSignal"
        assert signal.bus_type == "CAN"

        # Verify lookup
        found = registry.lookup("TestSignal")
        assert found is not None
        assert found.name == "TestSignal"

        registry.close()

    def test_add_alias(self, tmp_path):
        """Test signal aliasing."""
        db_path = tmp_path / "test.db"
        registry = SignalRegistry(db_path)

        registry.register(name="CanonicalSignal", bus_type="CAN")
        registry.add_alias("AliasSignal", "CanonicalSignal", "user")

        alias_resolved = registry.lookup("AliasSignal")
        assert alias_resolved is not None
        assert alias_resolved.name == "CanonicalSignal"

        registry.close()

    def test_export_report(self, tmp_path):
        """Test registry report export."""
        db_path = tmp_path / "test.db"
        registry = SignalRegistry(db_path)

        registry.register(name="Signal1", status="AUTO_ACCEPT")
        registry.register(name="Signal2", status="UNRESOLVED")

        report = registry.export_report()

        assert report["total_signals"] == 2
        assert "AUTO_ACCEPT" in report["by_status"]

        registry.close()


class TestCrossValidator:
    """Tests for CrossValidator."""

    def test_validate_signal_no_sources(self, tmp_path):
        """Test validation of signal with no sources."""
        db_path = tmp_path / "test.db"
        registry = SignalRegistry(db_path)
        validator = CrossValidator(registry)

        signal = Signal(name="TestSignal", sources=[])
        result = validator.validate_signal(signal)

        assert result.confidence == 0.0
        assert not result.passed

        registry.close()

    def test_validate_signal_with_sources(self, tmp_path):
        """Test validation of signal with multiple sources."""
        db_path = tmp_path / "test.db"
        registry = SignalRegistry(db_path)
        validator = CrossValidator(registry)

        signal = Signal(name="TestSignal", sources=["dbc", "can_file"])
        result = validator.validate_signal(signal)

        assert result.confidence > 0.0
        assert len(result.issues) == 0

        registry.close()


class TestPatternMatcher:
    """Tests for PatternMatcher."""

    def test_match_signal_reference(self):
        """Test signal reference matching."""
        matcher = PatternMatcher()

        text = "$DoorLockStatus = 1"
        matches = matcher.match(text)

        signal_matches = [m for m in matches if m['action'] == 'signal_reference']
        assert len(signal_matches) > 0
        assert 'DoorLockStatus' in signal_matches[0]['groups']

    def test_extract_signals(self):
        """Test signal extraction from text."""
        matcher = PatternMatcher()

        text = "Check $DoorLock_FL and $DoorLock_FR status"
        signals = matcher.extract_signals(text)

        assert "DoorLock_FL" in signals
        assert "DoorLock_FR" in signals


class TestCaplFingerprinter:
    """Tests for CaplStructuralFingerprinter."""

    def test_extract_fingerprint(self, tmp_path):
        """Test fingerprint extraction from CAPL file."""
        can_file = tmp_path / "test.can"
        can_file.write_text('''
void ECUWakeUp(void) {
    // comment
    testStep("TC_001", "Wake up ECU");
}

void VerifyDoorLock(int status) {
    if ($DoorLock_FL != status) {
        testStep("TC_002", "Verify lock status");
    }
}
''')

        fingerprinter = CaplStructuralFingerprinter()
        fp = fingerprinter.extract_fingerprint(can_file)

        assert "ECUWakeUp" in fp['function']
        assert "VerifyDoorLock" in fp['function']
        assert len(fp['testStep_call']) > 0
        assert "DoorLock_FL" in fp['signal_ref']

    def test_compare_identical(self, tmp_path):
        """Test comparison of identical files."""
        content = '''
void Test() {
    testStep("TC_001", "Test");
}
'''
        file1 = tmp_path / "test1.can"
        file2 = tmp_path / "test2.can"
        file1.write_text(content)
        file2.write_text(content)

        fingerprinter = CaplStructuralFingerprinter()
        passed, diff = fingerprinter.compare(file1, file2)

        assert passed
        assert diff['overall_similarity'] == 1.0

    def test_compare_whitespace_ignored(self, tmp_path):
        """Test that whitespace is ignored in comparison."""
        file1 = tmp_path / "test1.can"
        file2 = tmp_path / "test2.can"
        file1.write_text('void Test() { testStep("TC","A"); }')
        file2.write_text('void Test() {\n    testStep("TC","A");\n}')

        fingerprinter = CaplStructuralFingerprinter()
        passed, diff = fingerprinter.compare(file1, file2)

        assert passed
        assert diff['overall_similarity'] == 1.0
