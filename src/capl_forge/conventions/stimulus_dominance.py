"""Stimulus dominance detection: envvar vs sysvar vs direct signal access."""
from collections import Counter
from typing import Optional


def classify_stimulus_dominance(
    envvar_binding_count: int,
    sysvar_mapping_count: int,
    direct_signal_count: int,
) -> str:
    """Classify the dominant stimulus mechanism in a project.
    
    Returns:
        "envvar" if env var bindings dominate,
        "sysvar" if sysvar mappings dominate,
        "direct" if direct signal access dominates,
        "mixed" if no clear dominant
    """
    counts = {
        "envvar": envvar_binding_count,
        "sysvar": sysvar_mapping_count,
        "direct": direct_signal_count,
    }
    total = sum(counts.values())
    if total == 0:
        return "unknown"
    for kind, count in counts.items():
        if count / total > 0.6:
            return kind
    return "mixed"
