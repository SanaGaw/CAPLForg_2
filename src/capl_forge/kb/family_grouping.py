"""Preferred version logic: (kind, family_stem) grouping."""
from typing import Optional
import sqlite3

from .source_registry import family_key


def apply_preferred_version_logic(conn: sqlite3.Connection, log=None) -> tuple[int, int]:
    """Apply preferred version logic to the sources table.

    For versioned file kinds (dbc, cdd, vsysvar), groups files by
    family stem and keeps only the most recent version.

    Returns:
        (family_count, demoted_count)
    """
    _log = log or (lambda msg: None)
    cursor = conn.execute("SELECT source_file, full_path, kind, mtime FROM sources")
    records = cursor.fetchall()
    always_preferred_kinds = {"capl", "panel", "config", "nodelayer", "envdbc"}
    versioned_kinds = {"dbc", "cdd", "vsysvar"}

    conn.execute(
        "UPDATE sources SET preferred = 1 WHERE kind IN (?, ?, ?, ?, ?)",
        tuple(always_preferred_kinds),
    )

    families: dict[tuple, list] = {}
    for source_file, full_path, kind, mtime in records:
        if kind not in versioned_kinds:
            continue
        key = (kind, family_key(source_file))
        families.setdefault(key, []).append((source_file, full_path, mtime))

    family_count = 0
    demoted = 0
    for family_key_val, members in families.items():
        if len(members) <= 1:
            continue
        family_count += 1
        preferred = max(members, key=lambda item: item[2])
        kept, kept_path, kept_mtime = preferred
        older = [m for m in members if m[0] != kept]
        if older:
            conn.execute("UPDATE sources SET preferred = 1 WHERE source_file = ?", (kept,))
            demoted += len(older)
            for other, *_ in older:
                conn.execute("UPDATE sources SET preferred = 0 WHERE source_file = ?", (other,))
            kind, stem = family_key_val
            _log(f"KB:   family ({kind}) {stem}: kept {kept}, demoted {len(older)} older")
    return family_count, demoted
