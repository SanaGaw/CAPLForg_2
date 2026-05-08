"""Tests for CFG format detector."""
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from capl_forge.extractors.cfg.detector import detect_format


class TestDetectFormat:
    def test_zip_format(self, tmp_path):
        """PK header should be detected as zip."""
        import zipfile
        cfg = tmp_path / "test.cfg"
        with zipfile.ZipFile(cfg, "w") as zf:
            zf.writestr("test.xml", "<root/>")
        assert detect_format(cfg) == "zip"

    def test_binary_format(self, tmp_path):
        """Non-PK header should be detected as binary."""
        cfg = tmp_path / "test.cfg"
        cfg.write_bytes(b"\x00\x01\x02\x03 some binary content")
        assert detect_format(cfg) == "binary"

    def test_nonexistent_file(self, tmp_path):
        """Nonexistent file should raise."""
        cfg = tmp_path / "missing.cfg"
        with pytest.raises(Exception):
            detect_format(cfg)
