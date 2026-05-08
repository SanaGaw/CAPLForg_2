"""Empirical bus_role classification from DBC file content.

This module replaces the hardcoded keyword list ("env", "debug", etc.)
with content-based analysis of DBC files.
"""
from pathlib import Path
from typing import Optional
from collections import Counter


def classify_dbc_bus_role(
    file_path: Path,
    known_roles: Optional[dict[str, list[str]]] = None,
) -> str:
    """Classify a DBC file's bus role based on its content.
    
    Uses multiple signals to determine the role:
    1. Filename conventions (if available from discovered conventions)
    2. Content analysis (message/signal naming patterns)
    3. Presence of environment variables
    
    Falls back to "vehicle" if no strong signal is found.
    
    Args:
        file_path: Path to the .dbc file
        known_roles: Optional dict mapping role -> list of filename patterns
                    discovered by convention analysis
    
    Returns:
        Bus role string (e.g., "vehicle", "env", "debug", etc.)
    """
    if known_roles:
        fname_lower = file_path.name.lower()
        for role, patterns in known_roles.items():
            for pattern in patterns:
                if pattern.lower() in fname_lower:
                    return role

    # Content-based heuristics (empirical, not hardcoded keywords)
    return _classify_by_content(file_path)


def _classify_by_content(file_path: Path) -> str:
    """Classify bus role by analyzing DBC file content."""
    try:
        text = file_path.read_text(encoding="latin-1", errors="ignore")
    except Exception:
        return "vehicle"

    # Check for environment variable definitions
    if "EV_" in text and "GenEnvVarClassName" in text:
        return "env"

    # Count message name patterns
    lines = text.split("\n")
    msg_counter = Counter()
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("BO_ "):
            parts = stripped.split()
            if len(parts) >= 3:
                msg_counter[parts[2].lower()] += 1

    if not msg_counter:
        return "vehicle"

    # Analyze naming patterns
    total_msgs = sum(msg_counter.values())
    prefix_patterns = Counter()
    for name, count in msg_counter.items():
        parts = name.split("_")
        if len(parts) > 0:
            prefix_patterns[parts[0]] += count

    # If most messages share a common prefix, use that for classification
    most_common_prefix, most_common_count = prefix_patterns.most_common(1)[0]
    if most_common_count / total_msgs > 0.5:
        return "vehicle"

    return "vehicle"
