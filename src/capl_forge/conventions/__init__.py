"""Convention discovery package."""
from .prefix_discovery import discover_prefixes, discover_suffixes, strip_affixes
from .file_role_discovery import classify_dbc_bus_role
from .stimulus_dominance import classify_stimulus_dominance
from .conventions_writer import (
    write_conventions_json,
    insert_conventions_to_db,
    insert_issue_to_db,
)

__all__ = [
    "discover_prefixes",
    "discover_suffixes",
    "strip_affixes",
    "classify_dbc_bus_role",
    "classify_stimulus_dominance",
    "write_conventions_json",
    "insert_conventions_to_db",
    "insert_issue_to_db",
]
