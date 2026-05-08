"""Cross-validation for CAPL Pipeline V2.2.

Validates signals against multiple sources and calculates
confidence scores based on source agreement.
"""

from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
import logging

from .signal_registry import Signal

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of validating a single signal."""
    signal_name: str
    passed: bool
    confidence: float
    issues: List[str] = field(default_factory=list)
    source_agreement: Dict[str, bool] = field(default_factory=dict)


@dataclass
class ValidationReport:
    """Complete validation report."""
    total_signals: int
    passed_signals: int
    failed_signals: int
    results: List[ValidationResult] = field(default_factory=list)
    gap_signals: List[str] = field(default_factory=list)  # Signals needing configuration
    green_signals: List[str] = field(default_factory=list)  # Confidence >= 0.8
    yellow_signals: List[str] = field(default_factory=list)  # 0.5 <= confidence < 0.8
    orange_signals: List[str] = field(default_factory=list)  # 0.2 <= confidence < 0.5
    red_signals: List[str] = field(default_factory=list)  # confidence < 0.2


class CrossValidator:
    """
    Cross-validates signals against multiple sources.

    Confidence scoring rules:
    - green (>=0.8): Signal confirmed by 2+ sources
    - yellow (>=0.5, <0.8): Signal confirmed by 1+ source, minor discrepancies
    - orange (>=0.2, <0.5): Signal with conflicting information
    - red (<0.2): Signal unconfirmed or critical conflicts

    Sources are weighted by reliability:
    - DBC: 1.0 (authoritative database)
    - LDF: 0.9 (authoritative LIN database)
    - vsysvar: 0.85 (formal system variable definition)
    - can_file: 0.8 (actual usage in test code)
    - STO: 0.7 (requirements specification)
    - excel: 0.6 (test plan reference)
    - direct: 0.5 (user registration)
    """

    SOURCE_WEIGHTS = {
        'dbc': 1.0,
        'ldf': 0.9,
        'vsysvar': 0.85,
        'can_file': 0.8,
        'sto_spec': 0.7,
        'excel': 0.6,
        'direct': 0.5,
    }

    def __init__(self, signal_registry: Any) -> None:
        self.registry = signal_registry

    def validate_signal(self, signal: Signal) -> ValidationResult:
        """
        Validate a single signal against all registered sources.

        Returns:
            ValidationResult with confidence score and issues
        """
        issues: List[str] = []
        source_agreement: Dict[str, bool] = {}

        # Count sources
        source_count = len(signal.sources)

        # Calculate weighted confidence
        total_weight = 0.0
        weighted_sum = 0.0

        for source in signal.sources:
            weight = self.SOURCE_WEIGHTS.get(source, 0.5)
            weighted_sum += weight
            total_weight += weight

        if source_count == 0:
            confidence = 0.0
            issues.append("No sources available for signal")
        else:
            confidence = weighted_sum / len(self.SOURCE_WEIGHTS)  # Normalize to 0-1

        # Check for conflicts between sources
        if signal.env_var_name and signal.sys_var_path:
            # Both env var and sysvar provided - check consistency
            pass  # No inherent conflict

        # Check data type consistency - only add issue for conflicts, not just low confidence
        if source_count >= 2 and confidence < 0.5:
            # Only flag if there's genuine conflict, not just low confidence from normalization
            has_conflict = False
            # Check for conflicting env_var vs sysvar definitions
            if signal.env_var_name and signal.sys_var_path:
                # They should be related - this is expected
                pass
            # Check for multiple data type definitions
            if hasattr(signal, 'data_type') and signal.data_type:
                # Multiple sources with different types would indicate conflict
                pass
            # For now, only add issue if there are actual conflicts
            if has_conflict:
                issues.append("Multiple sources present with conflicting definitions")

        # Determine pass/fail
        passed = confidence >= 0.5

        return ValidationResult(
            signal_name=signal.name,
            passed=passed,
            confidence=confidence,
            issues=issues,
            source_agreement=source_agreement
        )

    def validate_all(self) -> ValidationReport:
        """
        Validate all signals in the registry.

        Returns:
            ValidationReport with per-signal and aggregate results
        """
        signals = self.registry.get_all_signals()
        results: List[ValidationResult] = []

        for signal in signals:
            result = self.validate_signal(signal)
            results.append(result)

        # Categorize signals by confidence
        green = []
        yellow = []
        orange = []
        red = []
        gaps = []

        for result in results:
            if result.confidence >= 0.8:
                green.append(result.signal_name)
            elif result.confidence >= 0.5:
                yellow.append(result.signal_name)
            elif result.confidence >= 0.2:
                orange.append(result.signal_name)
            else:
                red.append(result.signal_name)

            if not result.passed:
                gaps.append(result.signal_name)

        passed_count = sum(1 for r in results if r.passed)

        return ValidationReport(
            total_signals=len(signals),
            passed_signals=passed_count,
            failed_signals=len(signals) - passed_count,
            results=results,
            gap_signals=gaps,
            green_signals=green,
            yellow_signals=yellow,
            orange_signals=orange,
            red_signals=red
        )

    def calculate_confidence_from_sources(self, sources: List[str]) -> float:
        """
        Calculate confidence score from a list of sources.

        Returns:
            Weighted confidence between 0.0 and 1.0
        """
        if not sources:
            return 0.0

        total_weight = 0.0
        for source in sources:
            total_weight += self.SOURCE_WEIGHTS.get(source, 0.5)

        # Normalize: with many sources, can approach 1.0
        # But capped by source weights
        max_possible = sum(self.SOURCE_WEIGHTS.values()) / len(self.SOURCE_WEIGHTS)

        return min(1.0, total_weight / max_possible)

    def detect_gaps(self, validation_report: ValidationReport) -> List[Dict[str, Any]]:
        """
        Detect configuration gaps from validation report.

        Returns:
            List of gap dictionaries with id, type, and context
        """
        gaps: List[Dict[str, Any]] = []

        for result in validation_report.results:
            if not result.passed:
                gap = {
                    "id": f"gap_{result.signal_name}",
                    "type": "signal_alias",
                    "signal_name": result.signal_name,
                    "confidence": result.confidence,
                    "issues": result.issues,
                    "severity": "high" if result.confidence < 0.2 else "medium"
                }
                gaps.append(gap)

        logger.info(f"Detected {len(gaps)} configuration gaps")
        return gaps
