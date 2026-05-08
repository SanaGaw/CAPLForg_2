"""Write discovered conventions to conventions.json and the DB conventions table."""
import json
from pathlib import Path
from typing import Optional
import sqlite3


def write_conventions_json(
    output_dir: Path,
    prefixes: list[str],
    suffixes: list[str],
    bus_roles: dict[str, list[str]],
    stimulus_dominance: str,
) -> Path:
    """Write discovered conventions to a JSON file."""
    output_dir.mkdir(parents=True, exist_ok=True)
    conventions = {
        "prefixes": prefixes,
        "suffixes": suffixes,
        "bus_roles": bus_roles,
        "stimulus_dominance": stimulus_dominance,
    }
    path = output_dir / "conventions.json"
    path.write_text(json.dumps(conventions, indent=2))
    return path


def insert_conventions_to_db(
    conn: sqlite3.Connection,
    source_file: Optional[str],
    conventions: dict,
) -> int:
    """Insert discovered conventions into the conventions table.
    
    This is the documented INSERT call site for the conventions table.
    Reachable in the standard scan-project → build-db flow.
    
    Args:
        conn: SQLite connection
        source_file: Source file that produced these conventions (optional)
        conventions: Dict with keys: prefixes, suffixes, bus_roles
    
    Returns:
        Number of rows inserted
    """
    inserted = 0
    for prefix in conventions.get("prefixes", []):
        conn.execute(
            "INSERT INTO conventions (source_file, category, pattern, description, confidence) "
            "VALUES (?, ?, ?, ?, ?)",
            (source_file, "prefix", prefix, f"Discovered prefix: {prefix}", 1.0),
        )
        inserted += 1
    for suffix in conventions.get("suffixes", []):
        conn.execute(
            "INSERT INTO conventions (source_file, category, pattern, description, confidence) "
            "VALUES (?, ?, ?, ?, ?)",
            (source_file, "suffix", suffix, f"Discovered suffix: {suffix}", 1.0),
        )
        inserted += 1
    for role, patterns in conventions.get("bus_roles", {}).items():
        for pattern in patterns:
            conn.execute(
                "INSERT INTO conventions (source_file, category, pattern, description, confidence) "
                "VALUES (?, ?, ?, ?, ?)",
                (source_file, "bus_role", pattern, f"File pattern '{pattern}' → bus_role '{role}'", 0.8),
            )
            inserted += 1
    return inserted


def insert_issue_to_db(
    conn: sqlite3.Connection,
    severity: str,
    category: str,
    message: str,
    source_file: Optional[str] = None,
    entity_name: Optional[str] = None,
    resolution: Optional[str] = None,
) -> None:
    """Insert a parsing/linking issue into the issues table.
    
    This is the documented INSERT call site for the issues table.
    Reachable in the standard scan-project → build-db flow.
    """
    conn.execute(
        "INSERT INTO issues (severity, category, message, source_file, entity_name, resolution) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (severity, category, message, source_file, entity_name, resolution),
    )
