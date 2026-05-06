"""CANoe .cfg file parser for CAPL Pipeline V2.2.

Extracts references to DBC, LDF, .can files, and other configuration
elements from CANoe configuration files using pattern-based extraction.
"""

from pathlib import Path
from typing import Dict, List, Optional
import re
import mmap
import logging

logger = logging.getLogger(__name__)


class CfgVersionDetector:
    """Detects CANoe version from .cfg file header/metadata."""

    VERSION_PATTERNS = {
        '16+': [rb'CANoe\s+1[6-9]\.', rb'CANoe\s+[2-9][0-9]\.'],
        '14': [rb'CANoe\s+14\.'],
        '11': [rb'CANoe\s+11\.'],
    }

    @staticmethod
    def detect_version(cfg_path: Path) -> Optional[str]:
        """Returns '11', '14', '16+', or None if unknown."""
        try:
            content = cfg_path.read_bytes()[:4096]  # Check first 4KB
            for version, patterns in CfgVersionDetector.VERSION_PATTERNS.items():
                if any(re.search(p, content) for p in patterns):
                    return version
            return None
        except FileNotFoundError:
            logger.error(f"CFG file not found: {cfg_path}")
            return None
        except PermissionError:
            logger.error(f"Permission denied: {cfg_path}")
            return None
        except Exception as e:
            logger.warning(f"Unexpected error reading {cfg_path}: {e}")
            return None


class CfgParser:
    """
    Pattern-based extraction of references from CANoe .cfg files.
    Does NOT attempt to parse the proprietary binary/structured format.
    Instead, extracts known reference patterns (DBC, LDF, .can paths, etc.).
    Uses mmap for memory-efficient scanning of large .cfg files.
    """

    REFERENCE_PATTERNS = {
        'dbc': re.compile(
            rb'(?i)(?:database|dbc)[\s:=]+["\']?([^"\'\s,;]+\.dbc)["\']?',
            re.MULTILINE
        ),
        'ldf': re.compile(
            rb'(?i)(?:lin_database|ldf)[\s:=]+["\']?([^"\'\s,;]+\.ldf)["\']?',
            re.MULTILINE
        ),
        'can_file': re.compile(
            rb'(?i)(?:capl_file|source)[\s:=]+["\']?([^"\'\s,;]+\.can)["\']?',
            re.MULTILINE
        ),
        'vsysvar': re.compile(
            rb'(?i)(?:sysvar_file|vsysvar)[\s:=]+["\']?([^"\'\s,;]+\.vsysvar)["\']?',
            re.MULTILINE
        ),
        'cdd': re.compile(
            rb'(?i)(?:cdd_file|diagnostic)[\s:=]+["\']?([^"\'\s,;]+\.cdd)["\']?',
            re.MULTILINE
        ),
        'cin': re.compile(
            rb'(?i)(?:cin_file|library)[\s:=]+["\']?([^"\'\s,;]+\.cin)["\']?',
            re.MULTILINE
        ),
    }

    def __init__(self, cfg_path: Path, version: Optional[str] = None) -> None:
        self.cfg_path = cfg_path
        self.version = version or CfgVersionDetector.detect_version(cfg_path)

    def extract_references(self) -> Dict[str, List[str]]:
        """
        Extract file references from .cfg using regex patterns.
        Uses mmap for memory-efficient scanning of large files.
        Returns: {
            'dbc': ['path/to/file.dbc', ...],
            'ldf': [...],
            'can_file': [...],
            'vsysvar': [...],
            'cdd': [...],
            'cin': [...]
        }
        """
        result: Dict[str, List[str]] = {}
        try:
            with open(self.cfg_path, 'rb') as f:
                # Use mmap for large file support; fall back to read if file is empty
                file_size = self.cfg_path.stat().st_size
                if file_size == 0:
                    logger.warning(f"Empty CFG file: {self.cfg_path}")
                    return {key: [] for key in self.REFERENCE_PATTERNS}

                with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as content:
                    for key, pattern in self.REFERENCE_PATTERNS.items():
                        matches = pattern.findall(content)
                        result[key] = [
                            m.decode('utf-8', errors='ignore').strip() for m in matches
                        ]
        except FileNotFoundError:
            logger.error(f"CFG file not found: {self.cfg_path}")
            result = {key: [] for key in self.REFERENCE_PATTERNS}
        except Exception as e:
            logger.error(f"Error reading CFG file {self.cfg_path}: {e}")
            result = {key: [] for key in self.REFERENCE_PATTERNS}
        return result

    def get_supported_version(self) -> str:
        """Returns human-readable version support note."""
        if self.version in ('11', '14', '16+'):
            return f"CANoe v{self.version} (supported)"
        return "CANoe version unknown (pattern extraction attempted)"
