"""STO drop gate for CAPL Pipeline V2.2.

Applies drop gate logic to disable STO data if inconsistency
rate exceeds threshold.
"""

from typing import List, Optional, Tuple, Any
import logging
import os

logger = logging.getLogger(__name__)


def apply_drop_gate(
    signal_registry: Any,
    sto_signals: List[Any],
    drop_threshold: Optional[float] = None
) -> Tuple[bool, float, str]:
    """
    Apply drop gate to STO data based on inconsistency rate.

    Args:
        signal_registry: SignalRegistry instance
        sto_signals: List of StoSignal objects to validate
        drop_threshold: Inconsistency rate threshold (default from env)

    Returns:
        Tuple of (accepted: bool, inconsistency_rate: float, message: str)
    """
    from .sto_cross_validator import StoCrossValidator

    if drop_threshold is None:
        drop_threshold = float(os.getenv("STO_DROP_THRESHOLD", "0.20"))

    validator = StoCrossValidator(signal_registry, drop_threshold)
    validator.validate_signals(sto_signals)

    rate = validator.calculate_inconsistency_rate()
    should_drop, reason = validator.should_drop_sto()

    if should_drop:
        logger.warning(
            f"STO DROP GATE TRIGGERED: {reason}\n"
            f"Inconsistency rate: {rate:.2%}\n"
            f"Threshold: {drop_threshold:.2%}\n"
            f"Signals affected: {len(sto_signals)}"
        )
        return (False, rate, reason)
    else:
        logger.info(
            f"STO DROP GATE PASSED: Inconsistency rate {rate:.2%} below threshold {drop_threshold:.2%}"
        )
        return (True, rate, "STO data passed drop gate")


def get_drop_gate_status(
    signal_registry: Any,
    recent_sto_signals: List[Any]
) -> dict:
    """
    Get current drop gate status without applying it.

    Args:
        signal_registry: SignalRegistry instance
        recent_sto_signals: Recent STO signals for analysis

    Returns:
        Dict with drop gate status information
    """
    from .sto_cross_validator import StoCrossValidator

    drop_threshold = float(os.getenv("STO_DROP_THRESHOLD", "0.20"))

    validator = StoCrossValidator(signal_registry, drop_threshold)
    validator.validate_signals(recent_sto_signals)

    rate = validator.calculate_inconsistency_rate()
    should_drop, reason = validator.should_drop_sto()

    return {
        "inconsistency_rate": rate,
        "threshold": drop_threshold,
        "would_drop": should_drop,
        "reason": reason,
        "signals_analyzed": len(recent_sto_signals),
        "conflicts_found": sum(
            len(r.conflicts) for r in validator.validation_results.values()
        )
    }
