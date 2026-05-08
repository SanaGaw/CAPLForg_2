"""Helper manager for CAPL Pipeline V2.2.

Manages .cin library includes and validates function signatures.
"""

from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
import re
import logging

logger = logging.getLogger(__name__)


class HelperValidator:
    """
    Validates CAPL helper function signatures.

    Ensures that function calls in generated code match
    the signatures defined in CIN library files.
    """

    # Valid CAPL return types
    VALID_RETURN_TYPES = {
        'void', 'int', 'long', 'double', 'float',
        'char', 'byte', 'word', 'dword', 'qword', 'int64'
    }

    # Valid CAPL parameter types
    VALID_PARAM_TYPES = {
        'void', 'int', 'long', 'double', 'float',
        'char', 'byte', 'word', 'dword', 'qword', 'int64',
        'char[]', 'byte[]', 'string'
    }

    def __init__(self) -> None:
        self.signatures: Dict[str, str] = {}  # name -> signature

    def parse_signature(self, signature: str) -> Tuple[str, str, List[Tuple[str, str]]]:
        """
        Parse a CAPL function signature.

        Args:
            signature: e.g., "void VerifySignal(int signalId, float threshold)"

        Returns:
            Tuple of (return_type, name, [(param_type, param_name), ...])
        """
        # Pattern: return_type name(params)
        pattern = re.compile(
            r'^(void|int|long|double|float|char|byte|word|dword|qword|int64)\s+'
            r'([A-Za-z0-9_]+)\s*\(([^)]*)\)\s*;?\s*$'
        )

        match = pattern.match(signature.strip())
        if not match:
            raise ValueError(f"Invalid signature format: {signature}")

        return_type = match.group(1)
        name = match.group(2)
        params_str = match.group(3)

        params: List[Tuple[str, str]] = []
        if params_str.strip():
            for param in params_str.split(','):
                param = param.strip()
                if param:
                    parts = param.split()
                    if len(parts) >= 2:
                        params.append((parts[0], parts[1]))
                    elif len(parts) == 1:
                        params.append(('unknown', parts[0]))

        return return_type, name, params

    def validate_signature(self, signature: str) -> Tuple[bool, Optional[str]]:
        """
        Validate a function signature.

        Args:
            signature: Function signature string

        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            return_type, name, params = self.parse_signature(signature)

            if return_type not in self.VALID_RETURN_TYPES:
                return False, f"Invalid return type: {return_type}"

            if not name.isidentifier():
                return False, f"Invalid function name: {name}"

            for param_type, param_name in params:
                if param_type not in self.VALID_PARAM_TYPES:
                    return False, f"Invalid parameter type: {param_type}"

            return True, None

        except ValueError as e:
            return False, str(e)

    def register_signature(self, signature: str) -> bool:
        """
        Register a function signature.

        Args:
            signature: Function signature string

        Returns:
            True if registered successfully
        """
        is_valid, error = self.validate_signature(signature)
        if not is_valid:
            logger.warning(f"Invalid signature not registered: {error}")
            return False

        _, name, _ = self.parse_signature(signature)
        self.signatures[name] = signature
        return True

    def get_signature(self, name: str) -> Optional[str]:
        """Get a registered signature by function name."""
        return self.signatures.get(name)

    def validate_call(
        self,
        name: str,
        return_type: str,
        param_types: List[str]
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate a function call against registered signature.

        Args:
            name: Function name
            return_type: Expected return type
            param_types: List of parameter types

        Returns:
            Tuple of (is_valid, error_message)
        """
        signature = self.get_signature(name)
        if not signature:
            return False, f"Function '{name}' not found in registered signatures"

        sig_return, sig_name, sig_params = self.parse_signature(signature)

        if sig_return != return_type:
            return False, f"Return type mismatch: expected {return_type}, got {sig_return}"

        if len(sig_params) != len(param_types):
            return False, f"Parameter count mismatch: expected {len(sig_params)}, got {len(param_types)}"

        for i, (sig_type, _) in enumerate(sig_params):
            if i < len(param_types) and sig_type != param_types[i]:
                return False, f"Parameter {i+1} type mismatch: expected {sig_type}, got {param_types[i]}"

        return True, None


class HelperManager:
    """
    Manages CIN library includes and helper functions.

    Handles:
    - Loading .cin files
    - Validating function signatures
    - Injecting includes into generated CAPL
    - Suggesting helper functions based on patterns
    """

    def __init__(
        self,
        cin_paths: Optional[List[Path]] = None,
        helper_dir: Optional[Path] = None
    ) -> None:
        self.cin_paths = cin_paths or []
        self.helper_dir = helper_dir or Path("templates/test_functions")
        self.validator = HelperValidator()
        self._loaded_signatures: Dict[str, str] = {}

    def load_cin_files(self) -> Dict[str, str]:
        """
        Load and parse CIN files.

        Returns:
            Dict mapping function names to signatures
        """
        from ..parsers.cin_parser import CinParser

        self._loaded_signatures = {}

        for cin_path in self.cin_paths:
            if not cin_path.exists():
                logger.warning(f"CIN file not found: {cin_path}")
                continue

            parser = CinParser(cin_path)
            functions = parser.parse()

            for name, func in functions.items():
                param_str = ', '.join(f"{t} {n}" for t, n in func.parameters)
                signature = f"{func.return_type} {name}({param_str});"
                self.validator.register_signature(signature)
                self._loaded_signatures[name] = signature

        logger.info(f"Loaded {len(self._loaded_signatures)} helper signatures")
        return self._loaded_signatures

    def validate_includes(self, includes: List[str]) -> Tuple[List[str], List[str]]:
        """
        Validate that all includes exist.

        Args:
            includes: List of include file names

        Returns:
            Tuple of (valid_includes, missing_includes)
        """
        valid = []
        missing = []

        for include in includes:
            include_path = self.helper_dir / include
            if include_path.exists():
                valid.append(include)
            else:
                missing.append(include)

        return valid, missing

    def suggest_helper(
        self,
        pattern: List[str],
        min_frequency: int = 2
    ) -> Optional[Dict[str, Any]]:
        """
        Suggest a helper function based on repeated patterns.

        Args:
            pattern: List of action descriptions
            min_frequency: Minimum frequency to suggest

        Returns:
            Dict with helper suggestion or None
        """
        if len(pattern) < min_frequency:
            return None

        # Generate a descriptive name
        action_verbs = [step.split()[0] if step else "Unknown" for step in pattern[:3]]
        name = "Helper" + "".join(v.title() for v in action_verbs[:2])

        return {
            "name": name,
            "signature": f"void {name}(void);",
            "pattern": pattern,
            "frequency": min_frequency  # This would come from pattern analyzer
        }

    def get_all_signatures(self) -> List[str]:
        """Get all registered function signatures."""
        return list(self._loaded_signatures.values())

    def export_signature_file(self, output_path: Path) -> None:
        """
        Export signatures to a file for reference.

        Args:
            output_path: Path to output file
        """
        lines = [
            "// Helper Function Signatures",
            "// Generated by CAPL Pipeline",
            "",
        ]

        for name, signature in sorted(self._loaded_signatures.items()):
            lines.append(f"// {signature}")

        output_path.write_text('\n'.join(lines), encoding='utf-8')
        logger.info(f"Exported signatures to {output_path}")
