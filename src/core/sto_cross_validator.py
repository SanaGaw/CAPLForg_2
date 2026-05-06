"""STO-specific cross-validation for CAPL Pipeline V2.2.

Validates STO-extracted signals and applies drop gate logic
based on inconsistency rates.
"""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
import logging
import os

logger = logging.getLogger(__name__)


@dataclass
class StoConflict:
    """Represents a conflict between STO and other sources."""
    signal: str
    conflict_type: str  # "value_mismatch", "type_conflict", "missing_in_registry"
    sto_value: Optional[Any] = None
    registry_value: Optional[Any] = None
    details: str = ""


@dataclass
class StoValidationResult:
    """Result of STO signal validation."""
    signal: str
    valid: bool
    confidence: float
    conflicts: List[StoConflict] = field(default_factory=list)
    source_override: Optional[str] = None  # Which source should take precedence


class StoCrossValidator:
    """
    Cross-validates STO-extracted signals against registry.

    Handles conflicts between STO requirements and other sources,
    applying precedence rules based on source reliability.
    """

    def __init__(
        self,
        signal_registry: Any,
        drop_threshold: Optional[float] = None
    ) -> None:
        self.registry = signal_registry
        self.drop_threshold = drop_threshold or float(
            os.getenv("STO_DROP_THRESHOLD", "0.20")
        )
        self.validation_results: Dict[str, StoValidationResult] = {}

    def validate_signals(
        self,
        sto_signals: List[Any]
    ) -> List[StoValidationResult]:
        """
        Validate STO signals against the registry.

        Args:
            sto_signals: List of StoSignal objects from sto_spec_parser

        Returns:
            List of StoValidationResult objects
        """
        results = []
        total_conflicts = 0

        for sto_signal in sto_signals:
            result = self._validate_signal(sto_signal)
            results.append(result)
            self.validation_results[sto_signal.name] = result

            if result.conflicts:
                total_conflicts += len(result.conflicts)

        # Calculate overall inconsistency rate
        inconsistency_rate = total_conflicts / len(sto_signals) if sto_signals else 0.0

        logger.info(
            f"STO validation: {len(sto_signals)} signals, "
            f"{total_conflicts} conflicts, "
            f"inconsistency rate: {inconsistency_rate:.2%}"
        )

        return results

    def _validate_signal(self, sto_signal: Any) -> StoValidationResult:
        """Validate a single STO signal."""
        registry_signal = self.registry.lookup(sto_signal.name)

        if registry_signal is None:
            # Signal not in registry - conflict
            return StoValidationResult(
                signal=sto_signal.name,
                valid=False,
                confidence=0.3,  # Low confidence for new signal
                conflicts=[
                    StoConflict(
                        signal=sto_signal.name,
                        conflict_type="missing_in_registry",
                        details=f"Signal from STO ({sto_signal.sto_table_type}) not found in registry"
                    )
                ]
            )

        conflicts: List[StoConflict] = []

        # Check data type
        if sto_signal.value and registry_signal.data_type:
            # Type validation would go here
            pass

        # Check unit consistency
        if sto_signal.unit and registry_signal.unit:
            if sto_signal.unit != registry_signal.unit:
                conflicts.append(StoConflict(
                    signal=sto_signal.name,
                    conflict_type="unit_mismatch",
                    details=f"STO unit '{sto_signal.unit}' differs from registry '{registry_signal.unit}'"
                ))

        # Determine validity and confidence
        valid = len(conflicts) == 0
        confidence = 0.8 if valid else 0.5

        return StoValidationResult(
            signal=sto_signal.name,
            valid=valid,
            confidence=confidence,
            conflicts=conflicts
        )

    def calculate_inconsistency_rate(self) -> float:
        """Calculate the inconsistency rate across all validated signals."""
        if not self.validation_results:
            return 0.0

        total_conflicts = sum(
            len(r.conflicts) for r in self.validation_results.values()
        )
        return total_conflicts / len(self.validation_results)

    def should_drop_sto(self) -> Tuple[bool, str]:
        """
        Determine if STO data should be dropped based on inconsistency rate.

        Returns:
            Tuple of (should_drop: bool, reason: str)
        """
        rate = self.calculate_inconsistency_rate()

        if rate > self.drop_threshold:
            return True, f"Inconsistency rate {rate:.2%} exceeds threshold {self.drop_threshold:.2%}"
        elif rate > 0.1:
            return True, f"Moderate inconsistency rate {rate:.2%} warrants caution"

        return False, ""

    def merge_sto_signals(self, sto_signals: List[Any], force: bool = False) -> Dict[str, Any]:
        """
        Merge validated STO signals into the registry.

        Args:
            sto_signals: List of StoSignal objects
            force: If True, ignore drop gate check

        Returns:
            Dict with merge results
        """
        should_drop, reason = self.should_drop_sto()

        if should_drop and not force:
            logger.warning(f"STO data dropped: {reason}")
            return {
                "merged": 0,
                "skipped": len(sto_signals),
                "reason": reason
            }

        merged_count = 0
        for sto_signal in sto_signals:
            result = self.validation_results.get(sto_signal.name)
            if result and result.valid:
                self.registry.register(
                    name=sto_signal.name,
                    sources=["sto_spec"],
                    sys_var_path=sto_signal.value,
                    ecu_node=sto_signal.ecu,
                    confidence=result.confidence
                )
                merged_count += 1

        return {
            "merged": merged_count,
            "skipped": len(sto_signals) - merged_count
        }


def apply_drop_gate(
    sto_signals: List[Any],
    signal_registry: Any,
    drop_threshold: Optional[float] = None
) -> Tuple[bool, float]:
    """
    Apply drop gate to STO data.

    Returns:
        Tuple of (data_accepted: bool, inconsistency_rate: float)
    """
    validator = StoCrossValidator(signal_registry, drop_threshold)
    validator.validate_signals(sto_signals)

    rate = validator.calculate_inconsistency_rate()
    should_drop, _ = validator.should_drop_sto()

    return (not should_drop, rate)
