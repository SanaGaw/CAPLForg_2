"""CANoe system variables (.vsysvar) parser for CAPL Pipeline V2.2.

Parses .vsysvar files to extract system variable definitions including
namespace, name, data type, and VTS (Vector Test Signal) parameters.
"""

from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, field
import re
import logging

logger = logging.getLogger(__name__)


@dataclass
class VsysvarEntry:
    """Represents a system variable definition."""
    namespace: str
    name: str
    sys_var_path: str  # Full path e.g., "sysvar::Doors::FrontLeft::LockStatus"
    data_type: str  # 'int', 'float', 'double', 'byte', 'word', etc.
    initial_value: Optional[str] = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    unit: Optional[str] = None
    description: Optional[str] = None
    # VTS parameters (Vector Test Signal)
    vts_params: Dict[str, bool] = field(default_factory=dict)
    # File location
    source_file: str = ""
    line_number: Optional[int] = None


class VsysvarParser:
    """
    Parse CANoe .vsysvar (system variables) files.

    Supports CANoe 11, 14, and 16+ formats.
    Extracts namespaces, variable names, types, and VTS parameters.
    """

    # Pattern for namespace start
    NAMESPACE_PATTERN = re.compile(
        r'^\s*(?:namespace|"namespace")\s*["\']?([A-Za-z0-9_:]+)["\']?',
        re.MULTILINE
    )

    # Pattern for system variable definition
    # Various formats: name = value, name: type, etc.
    VAR_PATTERN = re.compile(
        r'^\s*(?:variable|"variable"|var)\s+["\']?([A-Za-z0-9_:]+)["\']?\s*',
        re.MULTILINE
    )

    # Pattern for type declaration
    TYPE_PATTERN = re.compile(
        r'(?:type|"type")\s*[:=]\s*["\']?([A-Za-z0-9_]+)',
        re.MULTILINE
    )

    # Pattern for initial value
    VALUE_PATTERN = re.compile(
        r'(?:value|init|initial)\s*[:=]\s*["\']?([^\'",;]+)',
        re.MULTILINE
    )

    # Pattern for min/max range
    RANGE_PATTERN = re.compile(
        r'(?:min|max|range)\s*[:=]\s*["\']?(-?[\d.]+)',
        re.MULTILINE
    )

    # Pattern for VTS parameters
    VTS_PATTERN = re.compile(
        r'@sysvar::[A-Za-z0-9_:]+::(avg|pmwdc|freq|min|max)',
        re.MULTILINE
    )

    # Alternative simple format: variable name type
    SIMPLE_VAR = re.compile(
        r'^\s*([A-Za-z0-9_]+)\s+([A-Za-z0-9_]+)\s*(?:=.*)?;?',
        re.MULTILINE
    )

    def __init__(self, vsysvar_path: Path) -> None:
        self.vsysvar_path = vsysvar_path
        self._content: Optional[str] = None
        self.entries: List[VsysvarEntry] = []
        self.entries_by_path: Dict[str, VsysvarEntry] = {}

    def _read_content(self) -> str:
        """Read and cache vsysvar file content."""
        if self._content is None:
            self._content = self.vsysvar_path.read_text(encoding='utf-8', errors='replace')
        return self._content

    def parse(self) -> List[VsysvarEntry]:
        """
        Parse vsysvar file and return list of system variable entries.

        Returns:
            List of VsysvarEntry objects
        """
        content = self._read_content()
        self.entries = []
        self.entries_by_path = {}

        current_namespace = "Global"
        lines = content.split('\n')

        for i, line in enumerate(lines, 1):
            line_stripped = line.strip()
            original_line = line

            # Detect namespace changes
            ns_match = re.match(r'^\s*namespace\s+([A-Za-z0-9_:]+)', line_stripped, re.IGNORECASE)
            if ns_match:
                current_namespace = ns_match.group(1)
                continue

            # Parse variable definitions
            # Try different patterns

            # Pattern 1: name = value (simple)
            simple_match = re.match(
                r'^\s*([A-Za-z0-9_]+)\s*=\s*"?([^";]+)"?\s*;?\s*(?://.*)?$',
                line_stripped
            )

            if simple_match:
                var_name = simple_match.group(1)
                var_value = simple_match.group(2)
                var_type = self._infer_type(var_value)

                entry = self._create_entry(
                    namespace=current_namespace,
                    name=var_name,
                    data_type=var_type,
                    initial_value=var_value,
                    line_number=i
                )
                self._add_entry(entry)
                continue

            # Pattern 2: type: name format
            type_name_match = re.match(
                r'^\s*(?:int|float|double|byte|word|dword|string|bool)\s+([A-Za-z0-9_]+)',
                line_stripped,
                re.IGNORECASE
            )

            if type_name_match:
                var_type = type_name_match.group(0).split()[0].lower()
                var_name = type_name_match.group(1)

                entry = self._create_entry(
                    namespace=current_namespace,
                    name=var_name,
                    data_type=var_type,
                    line_number=i
                )
                self._add_entry(entry)
                continue

        logger.info(
            f"Parsed {self.vsysvar_path.name}: "
            f"{len(self.entries)} system variables"
        )
        return self.entries

    def _infer_type(self, value: str) -> str:
        """Infer data type from value string."""
        value = value.strip()

        # Try integer
        try:
            int(value)
            return 'int'
        except ValueError:
            pass

        # Try float
        try:
            float(value)
            return 'float'
        except ValueError:
            pass

        # Boolean
        if value.lower() in ('true', 'false', 'on', 'off'):
            return 'bool'

        # String
        return 'string'

    def _create_entry(
        self,
        namespace: str,
        name: str,
        data_type: str,
        initial_value: Optional[str] = None,
        line_number: Optional[int] = None
    ) -> VsysvarEntry:
        """Create a VsysvarEntry with computed path."""
        sys_var_path = f"sysvar::{namespace}::{name}"

        # Extract VTS params from initial value if present
        vts_params: Dict[str, bool] = {}
        if initial_value:
            vts_matches = self.VTS_PATTERN.findall(initial_value)
            for param in ['avg', 'pmwdc', 'freq', 'min', 'max']:
                vts_params[param] = param in vts_matches

        return VsysvarEntry(
            namespace=namespace,
            name=name,
            sys_var_path=sys_var_path,
            data_type=data_type,
            initial_value=initial_value,
            vts_params=vts_params,
            source_file=str(self.vsysvar_path),
            line_number=line_number
        )

    def _add_entry(self, entry: VsysvarEntry) -> None:
        """Add entry to internal collections."""
        self.entries.append(entry)
        self.entries_by_path[entry.sys_var_path] = entry

    def get_by_path(self, path: str) -> Optional[VsysvarEntry]:
        """Get entry by full sys_var_path."""
        if not self.entries:
            self.parse()
        return self.entries_by_path.get(path)

    def get_by_name(self, name: str) -> List[VsysvarEntry]:
        """Get all entries with a given name (across namespaces)."""
        if not self.entries:
            self.parse()
        return [e for e in self.entries if e.name == name]

    def get_all_paths(self) -> List[str]:
        """Get all sys_var_paths."""
        if not self.entries:
            self.parse()
        return list(self.entries_by_path.keys())
