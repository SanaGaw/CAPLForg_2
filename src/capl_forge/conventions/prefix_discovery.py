"""Empirical prefix/suffix discovery from signal and env var names.

This module replaces the hardcoded prefix list ("env_", "ENV_", etc.)
with frequency-based discovery from actual project data.
"""
import re
from collections import Counter
from typing import Optional


def discover_prefixes(
    names: list[str],
    min_frequency: float = 0.1,
    max_prefix_length: int = 10,
) -> list[str]:
    """Discover common prefixes from a list of names using frequency analysis.
    
    Scans names for underscore-delimited prefix segments that appear
    in more than min_fraction of the names. Returns prefixes sorted
    by frequency (most common first).
    """
    if not names:
        return []
    prefix_counter = Counter()
    for name in names:
        parts = name.split("_")
        if len(parts) > 1:
            candidate = parts[0] + "_"
            if len(candidate) <= max_prefix_length:
                prefix_counter[candidate] += 1
    threshold = len(names) * min_frequency
    return [p for p, c in prefix_counter.most_common() if c >= threshold]


def discover_suffixes(
    names: list[str],
    min_frequency: float = 0.1,
    max_suffix_length: int = 10,
) -> list[str]:
    """Discover common suffixes from a list of names using frequency analysis."""
    if not names:
        return []
    suffix_counter = Counter()
    for name in names:
        parts = name.split("_")
        if len(parts) > 1:
            candidate = "_" + parts[-1]
            if len(candidate) <= max_suffix_length:
                suffix_counter[candidate] += 1
    threshold = len(names) * min_frequency
    return [s for s, c in suffix_counter.most_common() if c >= threshold]


def strip_affixes(
    name: str,
    prefixes: Optional[list[str]] = None,
    suffixes: Optional[list[str]] = None,
) -> tuple[str, str]:
    """Strip discovered prefixes and suffixes from a name.
    
    Returns (stripped_name, original_name).
    Prefixes and suffixes are applied in order; first match wins.
    If no prefixes/suffixes are provided, returns the name unchanged.
    """
    prefixes = prefixes or []
    suffixes = suffixes or []
    n = name
    for prefix in prefixes:
        if n.lower().startswith(prefix.lower()):
            n = n[len(prefix):]
            break
    for suffix in suffixes:
        if n.lower().endswith(suffix.lower()):
            n = n[: -len(suffix)]
            break
    return n.lower(), name
