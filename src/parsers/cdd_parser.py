"""CANdela Diagnostic Definition (.cdd) parser for CAPL Pipeline V2.2.

Parses CDD files to extract diagnostic trouble codes (DTCs) and
diagnostic session/communication parameters.
"""

from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, field
import re
import logging
from xml.etree import ElementTree as ET

logger = logging.getLogger(__name__)


@dataclass
class CddDiagnostic:
    """Represents a diagnostic trouble code definition."""
    code: str  # e.g., "P0x00" or decimal
    name: Optional[str] = None
    description: Optional[str] = None
    severity: Optional[str] = None  # 'fault', 'warning', 'info'
    ecu: Optional[str] = None
    session_required: Optional[str] = None
    data_bytes: List[int] = field(default_factory=list)


@dataclass
class CddSession:
    """Represents a diagnostic session type."""
    id: int
    name: str
    timeout_ms: Optional[int] = None
    P2_server_max_ms: Optional[int] = None


class CddParser:
    """
    Parse CANdela Diagnostic Definition (.cdd) files.

    CDD files are XML-based diagnostic database files used by Vector tools.
    Extracts DTC definitions, session parameters, and protocol settings.
    """

    def __init__(self, cdd_path: Path) -> None:
        self.cdd_path = cdd_path
        self._tree: Optional[ET.Element] = None
        self.dtcs: Dict[str, CddDiagnostic] = {}
        self.sessions: Dict[int, CddSession] = {}

    def _parse_tree(self) -> ET.Element:
        """Parse and cache the XML tree."""
        if self._tree is None:
            self._tree = ET.parse(self.cdd_path).getroot()
        return self._tree

    def parse(self) -> Dict[str, CddDiagnostic]:
        """
        Parse CDD file and return DTCs keyed by code.

        Returns:
            Dict mapping DTC codes to CddDiagnostic objects
        """
        self.dtcs = {}
        self.sessions = {}

        try:
            root = self._parse_tree()

            # Try to find DTC-related elements
            # CDD format varies, so we try multiple approaches

            # Approach 1: Look for diagnostic trouble code elements
            for elem in root.iter():
                tag = elem.tag.lower()
                if 'dtc' in tag or 'fault' in tag or 'trouble' in tag:
                    dtc = self._parse_dtc_element(elem)
                    if dtc:
                        self.dtcs[dtc.code] = dtc

            # Approach 2: Look for any element with code-like attributes
            if not self.dtcs:
                for elem in root.iter():
                    code_attr = elem.get('Code') or elem.get('ID') or elem.get('FaultCode')
                    if code_attr:
                        dtc = CddDiagnostic(
                            code=code_attr,
                            name=elem.get('Name') or elem.get('Description'),
                            description=elem.get('Description')
                        )
                        self.dtcs[dtc.code] = dtc

            # Parse sessions if present
            for elem in root.iter():
                if 'session' in elem.tag.lower():
                    session = self._parse_session_element(elem)
                    if session:
                        self.sessions[session.id] = session

        except ET.ParseError as e:
            logger.error(f"Failed to parse CDD XML: {e}")
        except Exception as e:
            logger.error(f"Error parsing CDD file: {e}")

        logger.info(
            f"Parsed {self.cdd_path.name}: "
            f"{len(self.dtcs)} DTCs"
        )
        return self.dtcs

    def _parse_dtc_element(self, elem: ET.Element) -> Optional[CddDiagnostic]:
        """Parse a DTC element."""
        code = elem.get('Code') or elem.get('ID') or elem.get('FaultCode')
        if not code:
            return None

        return CddDiagnostic(
            code=str(code),
            name=elem.get('Name'),
            description=elem.get('Description'),
            severity=elem.get('Severity'),
            ecu=elem.get('ECU')
        )

    def _parse_session_element(self, elem: ET.Element) -> Optional[CddSession]:
        """Parse a session element."""
        session_id = elem.get('ID') or elem.get('SessionId')
        if not session_id:
            return None

        try:
            return CddSession(
                id=int(session_id),
                name=elem.get('Name', 'Unknown'),
                timeout_ms=int(elem.get('Timeout', 0)) if elem.get('Timeout') else None,
                P2_server_max_ms=int(elem.get('P2ServerMax')) if elem.get('P2ServerMax') else None
            )
        except ValueError:
            return None

    def get_dtc(self, code: str) -> Optional[CddDiagnostic]:
        """Get a DTC by code."""
        if not self.dtcs:
            self.parse()
        return self.dtcs.get(code)

    def get_all_codes(self) -> List[str]:
        """Get all DTC codes."""
        if not self.dtcs:
            self.parse()
        return list(self.dtcs.keys())

    def search_by_name(self, name_substring: str) -> List[CddDiagnostic]:
        """Search DTCs by name substring."""
        if not self.dtcs:
            self.parse()

        results = []
        search_lower = name_substring.lower()
        for dtc in self.dtcs.values():
            if dtc.name and search_lower in dtc.name.lower():
                results.append(dtc)
        return results
