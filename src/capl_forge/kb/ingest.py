"""Knowledge base builder — main ingestion flow.

Orchestrates the scan-project → build-db flow with:
- SHA-256 deduplication and incremental updates
- Audit event recording (audit_events table)
- Issue tracking (issues table)
- Convention discovery and persistence (conventions table)
- Preferred version logic
"""
import hashlib
import sqlite3
from datetime import datetime
from pathlib import Path

from capl_forge.core.audit import write_audit_event
from capl_forge.conventions.prefix_discovery import discover_prefixes, discover_suffixes
from capl_forge.conventions.conventions_writer import (
    insert_conventions_to_db,
    insert_issue_to_db,
)
from capl_forge.kb.source_registry import determine_kind
from capl_forge.kb.schema import SCHEMA_SQL
from capl_forge.kb.row_utils import (
    TABLE_COLUMNS,
    insert_rows,
    ingest_source,
)
from capl_forge.kb.views import VIEW_SQL


def _compute_sha256(path: Path) -> str:
    """Compute SHA-256 hash of a file."""
    hasher = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _ensure_schema(conn, log):
    """Create all tables and indexes if they do not exist."""
    conn.executescript(SCHEMA_SQL)
    log("KB: schema ensured (16 tables)")


def _ensure_views(conn, log):
    """Drop and recreate materialized views."""
    conn.executescript(VIEW_SQL)
    log("KB: refreshing views")


def _normalize_source_map(inspection_result, log):
    """Build {basename: [resolved_paths]} from references and inventory."""
    source_map = {}
    seen = {}

    def add_entry(source_file, raw_path):
        if not source_file or not raw_path:
            return
        try:
            resolved_path = Path(raw_path).resolve()
        except OSError:
            return
        seen[source_file] = seen.get(source_file, 0) + 1
        source_map.setdefault(source_file, [])
        if resolved_path in source_map[source_file]:
            return
        source_map[source_file].append(resolved_path)

    for ref in inspection_result.get("references", []):
        if ref.get("exists") and ref.get("resolved_path"):
            add_entry(ref.get("basename"), ref.get("resolved_path"))
    for inv in inspection_result.get("inventory", []):
        add_entry(inv.get("basename"), inv.get("path"))

    for key, count in seen.items():
        if count > 1:
            log(f"KB: warning basename conflict {key} seen {count} times")

    return source_map, seen


def _find_orphan_data_sources(source_map, inspection_result, log):
    """Find source_files in data rows but not in source_map."""
    known = set(source_map)
    missing = set()
    data_keys = [
        "dbc_messages", "dbc_signals", "sysvars", "env_vars",
        "value_tables", "capl_bindings", "capl_sysvar_mappings",
        "dids", "did_fields", "dtcs", "calibrations", "requirements",
    ]
    for table in data_keys:
        for row in inspection_result.get(table, []):
            source_file = row.get("source_file")
            if source_file and source_file not in known:
                missing.add(source_file)
    for source_file in sorted(missing):
        log(f"KB: warning source {source_file} referenced in data but missing path mapping")
    return missing


def _group_counts_by_source(inspection_result):
    """Count contributions per source file by table."""
    counts = {}

    def bump(source_file, key):
        if not source_file:
            return
        counts.setdefault(source_file, {}).setdefault(key, 0)
        counts[source_file][key] += 1

    mapping = {
        "dbc_messages": "messages", "dbc_signals": "signals",
        "env_vars": "env_vars", "capl_bindings": "capl_env_bindings",
        "capl_sysvar_mappings": "capl_sysvar_mappings", "sysvars": "sysvars",
        "dids": "dids", "did_fields": "did_fields",
        "value_tables": "value_tables", "dtcs": "dtcs",
        "calibrations": "calibrations", "requirements": "requirements",
    }
    for key, table in mapping.items():
        for row in inspection_result.get(key, []):
            bump(row.get("source_file"), table)
    return counts


def _discover_and_insert_conventions(conn, inspection_result, log):
    """Discover naming conventions and persist to conventions table."""
    signal_names = [r["name"] for r in inspection_result.get("dbc_signals", []) if r.get("name")]
    envvar_names = [r["name"] for r in inspection_result.get("env_vars", []) if r.get("name")]
    sysvar_names = [r.get("name", "") for r in inspection_result.get("sysvars", []) if r.get("name")]
    all_names = signal_names + envvar_names + sysvar_names

    if not all_names:
        log("KB: no names to discover conventions from")
        return

    try:
        prefixes = discover_prefixes(all_names, min_frequency=0.3)
        suffixes = discover_suffixes(all_names, min_frequency=0.3)

        if prefixes or suffixes:
            conventions = {"prefixes": prefixes, "suffixes": suffixes}
            insert_conventions_to_db(conn, source_file=None, conventions=conventions)
            log(f"KB: conventions: {len(prefixes)} prefixes, {len(suffixes)} suffixes discovered")
    except Exception as exc:
        log(f"KB: convention discovery failed: {exc}")


def build_knowledge_base(
    inspection_result: dict,
    db_path: str | Path,
    log=print,
    verbose: bool = False,
    run_id: str = "unknown",
) -> dict:
    """Build (or incrementally update) the SQLite knowledge base.

    Parameters
    ----------
    inspection_result : dict
        Full inspection dictionary from CfgInspector.
    db_path : str | Path
        Path to the SQLite database file.
    log : callable
        Logging function (default: print).
    verbose : bool
        If True, log every unchanged source.
    run_id : str
        Unique run identifier for audit trail.
    """
    start = datetime.utcnow()
    db_path = Path(db_path)
    log(f"KB: opening database at {db_path}")

    source_map, seen_counts = _normalize_source_map(inspection_result, log)
    orphans = _find_orphan_data_sources(source_map, inspection_result, log)

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        _ensure_schema(conn, log)
        write_audit_event(conn, run_id, "schema_created")

        # Record orphan issues
        for orphan_source in sorted(orphans):
            insert_issue_to_db(
                conn, severity="warning", category="orphan_source",
                message=f"Source '{orphan_source}' has no path mapping",
                source_file=orphan_source,
            )

        for basename, count in seen_counts.items():
            if count > 1:
                insert_issue_to_db(
                    conn, severity="warning", category="basename_conflict",
                    message=f"basename '{basename}' seen {count} times",
                    source_file=basename,
                )
        conn.commit()

        log("KB: scanning sources for changes...")
        contribution_counts = _group_counts_by_source(inspection_result)
        new_sources, changed_sources, unchanged_sources = [], [], []
        source_states = {}
        path_to_effective = {}
        current_sources = set()
        existing_by_name = {
            row[0]: row[1]
            for row in conn.execute("SELECT source_file, sha256 FROM sources").fetchall()
        }
        seen_sha = dict(existing_by_name)

        for basename in sorted(source_map):
            for full_path in sorted(source_map[basename], key=lambda p: str(p)):
                if not full_path.exists():
                    log(f"KB: warning source path missing for {basename}")
                    continue
                sha256 = _compute_sha256(full_path)
                effective = basename
                existing_sha = seen_sha.get(basename)
                if existing_sha is not None:
                    if existing_sha == sha256:
                        path_to_effective[full_path] = basename
                        log(f"KB:   SKIP duplicate  {basename}  (same sha256)")
                        continue
                    stem = Path(basename).stem
                    ext = Path(basename).suffix
                    effective = f"{stem}__{sha256[:8]}{ext}"
                    log(f"KB:   COLLISION  {basename} renamed to {effective}")
                seen_sha[effective] = sha256
                path_to_effective[full_path] = effective
                current_sources.add(effective)

        for full_path, source_file in sorted(
            path_to_effective.items(), key=lambda item: item[1]
        ):
            sha256 = _compute_sha256(full_path)
            mtime = full_path.stat().st_mtime
            parsed_at = datetime.utcnow().isoformat()
            existing = conn.execute(
                "SELECT sha256 FROM sources WHERE source_file = ?", (source_file,)
            ).fetchone()
            if existing is None:
                log(f"KB:   NEW      {source_file}  (sha256={sha256[:8]})")
                kind = determine_kind(source_file, full_path, contribution_counts)
                conn.execute(
                    "INSERT INTO sources VALUES(?,?,?,?,?,?,?,?)",
                    (source_file, str(full_path), sha256, kind, mtime, parsed_at, 1, 0),
                )
                inserted = ingest_source(
                    conn, source_file, full_path, kind,
                    inspection_result, log, path_to_effective,
                )
                conn.execute("UPDATE sources SET row_count=? WHERE source_file=?", (inserted, source_file))
                new_sources.append(source_file)
                source_states[source_file] = "new"
            elif existing[0] != sha256:
                log(f"KB:   CHANGED  {source_file}  (sha256={sha256[:8]})")
                kind = determine_kind(source_file, full_path, contribution_counts)
                conn.execute("DELETE FROM sources WHERE source_file=?", (source_file,))
                conn.execute(
                    "INSERT INTO sources VALUES(?,?,?,?,?,?,?,?)",
                    (source_file, str(full_path), sha256, kind, mtime, parsed_at, 1, 0),
                )
                inserted = ingest_source(
                    conn, source_file, full_path, kind,
                    inspection_result, log, path_to_effective,
                )
                conn.execute("UPDATE sources SET row_count=? WHERE source_file=?", (inserted, source_file))
                changed_sources.append(source_file)
                source_states[source_file] = "changed"
            else:
                if verbose:
                    log(f"KB:   unchanged {source_file}")
                unchanged_sources.append(source_file)
                source_states[source_file] = "unchanged"

        conn.commit()

        # Remove stale sources
        existing_set = {r[0] for r in conn.execute("SELECT source_file FROM sources").fetchall()}
        removed = sorted(existing_set - current_sources)
        deleted = []
        for sf in removed:
            conn.execute("DELETE FROM sources WHERE source_file=?", (sf,))
            log(f"KB:   REMOVED  {sf}  (no longer in project)")
            deleted.append(sf)
        conn.commit()

        log(f"KB: summary: {len(new_sources)} new, {len(changed_sources)} changed, "
             f"{len(unchanged_sources)} unchanged, {len(deleted)} removed")

        # Preferred version logic
        from capl_forge.kb.family_grouping import apply_preferred_version_logic
        family_count, demoted = apply_preferred_version_logic(conn, log)
        conn.commit()

        _ensure_views(conn, log)
        conn.commit()

        # Convention discovery
        _discover_and_insert_conventions(conn, inspection_result, log)

        elapsed = (datetime.utcnow() - start).total_seconds()
        summary_str = (
            f"new={len(new_sources)} changed={len(changed_sources)} "
            f"unchanged={len(unchanged_sources)} removed={len(deleted)} "
            f"families={family_count} demoted={demoted} time={elapsed:.2f}s"
        )
        write_audit_event(conn, run_id, "build_complete", details=summary_str)
        conn.commit()

        log(f"KB: done in {elapsed:.2f}s")

        row_counts = {}
        for table in TABLE_COLUMNS:
            row_counts[table] = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

        return {
            "db_path": str(db_path),
            "new_sources": new_sources,
            "changed_sources": changed_sources,
            "unchanged_sources": unchanged_sources,
            "deleted_sources": deleted,
            "row_counts": row_counts,
            "preferred_families": family_count,
            "non_preferred_sources": demoted,
            "elapsed_seconds": elapsed,
        }
    finally:
        conn.close()
