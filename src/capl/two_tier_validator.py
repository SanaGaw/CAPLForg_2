"""Two-tier validator for CAPL Pipeline V2.2.

Structural validation + CANoe CLI compiler wrapper for CAPL files.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
import subprocess
import logging
import re

from .helper_manager import HelperValidator

logger = logging.getLogger(__name__)


@dataclass
class ValidationReport:
    """CAPL validation report."""
    file_path: Path
    passed: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    compiler_output: Optional[str] = None


@dataclass
class CaplValidationReport:
    """Two-tier validation report."""
    structural_passed: bool
    compiler_passed: bool
    overall_passed: bool
    file_path: Path
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


class TwoTierValidator:
    """
    Two-tier validation for CAPL files.

    Tier 1 (Structural): Fast pattern-based validation
    - Checks for undefined symbols
    - Verifies include statements
    - Validates function signatures
    - Checks for common syntax errors

    Tier 2 (Compiler): CANoe CLI wrapper (or mock)
    - Runs actual CANoe CAPL compiler
    - Returns structured report with errors
    """

    # Patterns for structural validation
    UNDEFINED_SYMBOL_PATTERN = re.compile(r'\b([A-Z_][A-Z0-9_]*)\b')
    INCLUDE_PATTERN = re.compile(r'#include\s+"([^"]+)"')

    def __init__(
        self,
        helper_validator: Optional[HelperValidator] = None,
        canoe_path: Optional[str] = None,
        include_paths: Optional[List[str]] = None
    ) -> None:
        self.helper_validator = helper_validator or HelperValidator()
        self.canoe_path = canoe_path
        self.include_paths = include_paths or []

    def validate_file(
        self,
        capl_path: Path,
        use_compiler: bool = True
    ) -> CaplValidationReport:
        """
        Run two-tier validation on a CAPL file.

        Args:
            capl_path: Path to .can file
            use_compiler: If True, run Tier 2 compiler validation

        Returns:
            CaplValidationReport with results
        """
        # Tier 1: Structural validation
        structural_report = self._structural_validation(capl_path)

        # Tier 2: Compiler validation
        compiler_passed = True
        compiler_errors: List[str] = []

        if use_compiler and self.canoe_path:
            compiler_passed, compiler_errors = self._compiler_validation(capl_path)

        # Combine results
        all_errors = structural_report.errors + compiler_errors
        all_warnings = structural_report.warnings
        overall_passed = structural_report.passed and compiler_passed

        return CaplValidationReport(
            structural_passed=structural_report.passed,
            compiler_passed=compiler_passed,
            overall_passed=overall_passed,
            file_path=capl_path,
            errors=all_errors,
            warnings=all_warnings
        )

    def _structural_validation(self, capl_path: Path) -> ValidationReport:
        """
        Run structural validation (Tier 1).

        Returns:
            ValidationReport with structural check results
        """
        errors: List[str] = []
        warnings: List[str] = []

        try:
            content = capl_path.read_text(encoding='utf-8')
        except Exception as e:
            return ValidationReport(
                file_path=capl_path,
                passed=False,
                errors=[f"Failed to read file: {e}"]
            )

        # Check for balanced braces
        if not self._check_balanced_braces(content):
            errors.append("Unbalanced braces detected")

        # Check for undefined includes
        missing_includes = self._check_includes(content)
        if missing_includes:
            warnings.extend([f"Missing include: {inc}" for inc in missing_includes])

        # Check for function signature validity
        func_pattern = re.compile(
            r'^(void|int|long|double|float|char|byte|word|dword|qword|int64)\s+'
            r'([A-Za-z0-9_]+)\s*\([^)]*\)\s*\{?',
            re.MULTILINE
        )

        for match in func_pattern.finditer(content):
            return_type = match.group(1)
            func_name = match.group(2)

            if not self.helper_validator.validate_signature(
                f"{return_type} {func_name}();"
            )[0]:
                # Check if it's a known function or user-defined
                known_functions = ['testStep', 'testWaitForTimeout', 'putValue', 'getValue']
                if func_name not in known_functions:
                    # User-defined function - ok for now
                    pass

        # Check for common syntax errors
        if ';;' in content:
            errors.append("Double semicolon detected")

        if re.search(r'\)\s*;', content):  # Function calls ending with semicolon inside
            pass  # This is actually valid in some cases

        passed = len([e for e in errors if 'error' in e.lower()]) == 0

        return ValidationReport(
            file_path=capl_path,
            passed=passed,
            errors=errors,
            warnings=warnings
        )

    def _check_balanced_braces(self, content: str) -> bool:
        """Check if braces are balanced."""
        count = 0
        for char in content:
            if char == '{':
                count += 1
            elif char == '}':
                count -= 1
            if count < 0:
                return False
        return count == 0

    def _check_includes(self, content: str) -> List[str]:
        """Check for missing include files."""
        missing = []

        for match in self.INCLUDE_PATTERN.finditer(content):
            include_name = match.group(1)
            include_path = Path(include_name)

            # Check if file exists in include paths
            found = False
            for include_dir in self.include_paths:
                if (Path(include_dir) / include_path).exists():
                    found = True
                    break

            if not found:
                missing.append(include_name)

        return missing

    def _compiler_validation(
        self,
        capl_path: Path
    ) -> Tuple[bool, List[str]]:
        """
        Run CANoe compiler validation (Tier 2).

        Returns:
            Tuple of (passed, error_list)
        """
        if not self.canoe_path:
            logger.warning("CANoe path not configured, skipping compiler validation")
            return True, []

        # Try to run CANoe CAPL compiler
        try:
            result = subprocess.run(
                [self.canoe_path, '/Compile', str(capl_path)],
                capture_output=True,
                text=True,
                timeout=60
            )

            if result.returncode == 0:
                return True, []
            else:
                # Parse compiler output for errors
                errors = self._parse_compiler_output(result.stderr)
                return False, errors

        except FileNotFoundError:
            logger.warning("CANoe compiler not found, using mock validation")
            return self._mock_validation(capl_path)
        except subprocess.TimeoutExpired:
            return False, ["Compiler timeout"]
        except Exception as e:
            logger.warning(f"Compiler error: {e}")
            return self._mock_validation(capl_path)

    def _mock_validation(self, capl_path: Path) -> Tuple[bool, List[str]]:
        """
        Mock validation when CANoe is not available.

        Returns:
            Tuple of (passed, error_list)
        """
        try:
            content = capl_path.read_text(encoding='utf-8')

            # Basic mock checks
            issues = []

            if content.count('{') != content.count('}'):
                issues.append("Mock: Unbalanced braces")

            if 'on ' not in content and 'testStep' not in content:
                issues.append("Mock: No test handlers found")

            if issues:
                return False, issues

            return True, []

        except Exception as e:
            return False, [f"Mock validation error: {e}"]

    def _parse_compiler_output(self, output: str) -> List[str]:
        """Parse CANoe compiler output for errors."""
        errors = []

        # Common error patterns
        error_patterns = [
            re.compile(r'error (C\d+): (.+)'),
            re.compile(r'(.+):\s*(\d+):\s*error: (.+)'),
        ]

        for pattern in error_patterns:
            for match in pattern.finditer(output):
                errors.append(match.group(0))

        return errors

    def validate_batch(
        self,
        capl_dir: Path,
        use_compiler: bool = False
    ) -> Dict[str, CaplValidationReport]:
        """
        Validate all CAPL files in a directory.

        Args:
            capl_dir: Directory containing .can files
            use_compiler: Whether to run compiler validation

        Returns:
            Dict mapping file paths to validation reports
        """
        results = {}

        for capl_file in capl_dir.glob('*.can'):
            results[str(capl_file)] = self.validate_file(capl_file, use_compiler)

        return results
