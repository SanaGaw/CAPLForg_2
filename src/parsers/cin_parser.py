"""CIN (CAPL Include) library parser for CAPL Pipeline V2.2.

Parses .cin files to extract function signatures and constants
defined in CANoe CAPL library include files.
"""

from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, field
import re
import logging

logger = logging.getLogger(__name__)


@dataclass
class CinFunction:
    """Represents a function signature from CIN library."""
    name: str
    return_type: str  # 'void', 'int', 'float', 'byte', etc.
    parameters: List[tuple[str, str]] = field(default_factory=list)  # [(type, name), ...]
    global_apply: bool = False
    comment: Optional[str] = None
    line_number: Optional[int] = None


@dataclass
class CinConstant:
    """Represents a constant definition from CIN library."""
    name: str
    value: str
    type: str = "int"
    comment: Optional[str] = None


class CinParser:
    """
    Parse CIN (CAPL Include) library files.

    Extracts function signatures, constants, and global definitions
    for validation of helper function references.
    """

    # Function signature pattern: return_type name(params);
    FUNCTION_PATTERN = re.compile(
        r'^(void|int|long|double|float|char|byte|word|dword|qword|int64)\s+'
        r'([A-Za-z0-9_]+)\s*\(([^)]*)\)\s*;?\s*(?://.*)?$',
        re.MULTILINE
    )

    # Constant definition: #define NAME value
    CONSTANT_PATTERN = re.compile(
        r'^#define\s+([A-Za-z0-9_]+)\s+([^\s]+)',
        re.MULTILINE
    )

    # Global variable pattern
    GLOBAL_PATTERN = re.compile(
        r'^(?:var|message|timer)\s+([A-Za-z0-9_]+)',
        re.MULTILINE
    )

    # Comment extraction
    COMMENT_PATTERN = re.compile(
        r'//\s*(.+?)$',
        re.MULTILINE
    )

    def __init__(self, cin_path: Path) -> None:
        self.cin_path = cin_path
        self._content: Optional[str] = None
        self.functions: Dict[str, CinFunction] = {}
        self.constants: Dict[str, CinConstant] = {}
        self.globals: List[str] = []

    def _read_content(self) -> str:
        """Read and cache CIN file content."""
        if self._content is None:
            self._content = self.cin_path.read_text(encoding='utf-8', errors='replace')
        return self._content

    def parse(self) -> Dict[str, CinFunction]:
        """
        Parse CIN file and return functions keyed by name.

        Returns:
            Dict mapping function names to CinFunction objects
        """
        content = self._read_content()
        self.functions = {}
        self.constants = {}
        self.globals = []

        lines = content.split('\n')

        for i, line in enumerate(lines, 1):
            line_stripped = line.strip()
            original_line = line

            # Extract function signatures
            func_match = self.FUNCTION_PATTERN.search(line)
            if func_match:
                return_type = func_match.group(1)
                func_name = func_match.group(2)
                params_str = func_match.group(3)

                # Parse parameters
                params: List[tuple[str, str]] = []
                if params_str.strip():
                    for param in params_str.split(','):
                        param = param.strip()
                        if param:
                            # Handle patterns like "byte data" or just "data"
                            parts = param.split()
                            if len(parts) >= 2:
                                params.append((parts[0], parts[1]))
                            elif len(parts) == 1:
                                params.append(('unknown', parts[0]))

                # Extract inline comment
                comment = None
                comment_match = self.COMMENT_PATTERN.search(original_line)
                if comment_match:
                    comment = comment_match.group(1)

                function = CinFunction(
                    name=func_name,
                    return_type=return_type,
                    parameters=params,
                    comment=comment,
                    line_number=i
                )
                self.functions[func_name] = function
                continue

            # Extract constants
            const_match = self.CONSTANT_PATTERN.search(line)
            if const_match:
                const_name = const_match.group(1)
                const_value = const_match.group(2)
                self.constants[const_name] = CinConstant(
                    name=const_name,
                    value=const_value
                )
                continue

            # Extract global variables
            global_match = self.GLOBAL_PATTERN.match(line_stripped)
            if global_match:
                self.globals.append(global_match.group(1))

        logger.info(
            f"Parsed {self.cin_path.name}: "
            f"{len(self.functions)} functions, "
            f"{len(self.constants)} constants"
        )
        return self.functions

    def get_function(self, name: str) -> Optional[CinFunction]:
        """Get a function by name."""
        if not self.functions:
            self.parse()
        return self.functions.get(name)

    def get_constant(self, name: str) -> Optional[CinConstant]:
        """Get a constant by name."""
        if not self.constants:
            self.parse()
        return self.constants.get(name)

    def validate_signature(self, name: str, return_type: str, param_types: List[str]) -> bool:
        """
        Validate if a signature matches a function in the library.

        Args:
            name: Function name
            return_type: Expected return type
            param_types: List of expected parameter types

        Returns:
            True if signature matches
        """
        func = self.get_function(name)
        if not func:
            return False

        if func.return_type != return_type:
            return False

        if len(func.parameters) != len(param_types):
            return False

        for i, (expected_type, _) in enumerate(func.parameters):
            if i < len(param_types) and expected_type != param_types[i]:
                return False

        return True

    def get_all_signatures(self) -> List[str]:
        """Get all function signatures as strings."""
        if not self.functions:
            self.parse()

        signatures = []
        for func in self.functions.values():
            param_str = ', '.join(f"{t} {n}" for t, n in func.parameters)
            signatures.append(f"{func.return_type} {func.name}({param_str});")
        return signatures
