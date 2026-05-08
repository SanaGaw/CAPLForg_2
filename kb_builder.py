import hashlib
import json
import os
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path


SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS sources (
    source_file TEXT PRIMARY KEY,
    full_path   TEXT NOT NULL,
    sha256      TEXT NOT NULL,
    kind        TEXT NOT NULL,
    mtime       REAL NOT NULL,
    parsed_at   TEXT NOT NULL,
    preferred   INTEGER NOT NULL DEFAULT 1,
    row_count   INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS messages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source_file     TEXT NOT NULL,
    bus_role        TEXT,
    name            TEXT NOT NULL,
    frame_id_hex    TEXT,
    dlc             INTEGER,
    cycle_ms        TEXT,
    senders         TEXT,
    comment         TEXT,
    FOREIGN KEY (source_file) REFERENCES sources(source_file) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_messages_name ON messages(name);
CREATE INDEX IF NOT EXISTS idx_messages_source ON messages(source_file);
CREATE INDEX IF NOT EXISTS idx_messages_frame_id_hex ON messages(frame_id_hex);

CREATE TABLE IF NOT EXISTS signals (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    source_file  TEXT NOT NULL,
    bus_role     TEXT,
    message      TEXT,
    name         TEXT NOT NULL,
    start_bit    INTEGER,
    length       INTEGER,
    byte_order   TEXT,
    is_signed    INTEGER,
    factor       REAL,
    offset       REAL,
    minimum      REAL,
    maximum      REAL,
    unit         TEXT,
    receivers    TEXT,
    comment      TEXT,
    FOREIGN KEY (source_file) REFERENCES sources(source_file) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_signals_name ON signals(name);
CREATE INDEX IF NOT EXISTS idx_signals_source ON signals(source_file);
CREATE INDEX IF NOT EXISTS idx_signals_message ON signals(message);

CREATE TABLE IF NOT EXISTS sysvars (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    source_file TEXT NOT NULL,
    namespace   TEXT,
    name        TEXT NOT NULL,
    full_path   TEXT NOT NULL,
    type        TEXT,
    unit        TEXT,
    min         REAL,
    max         REAL,
    default_val REAL,
    comment     TEXT,
    FOREIGN KEY (source_file) REFERENCES sources(source_file) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_sysvars_name ON sysvars(name);
CREATE INDEX IF NOT EXISTS idx_sysvars_fullpath ON sysvars(full_path);
CREATE INDEX IF NOT EXISTS idx_sysvars_source ON sysvars(source_file);

CREATE TABLE IF NOT EXISTS env_vars (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    source_file TEXT NOT NULL,
    name        TEXT NOT NULL,
    dtype_raw   TEXT,
    min         REAL,
    max         REAL,
    unit        TEXT,
    initial     REAL,
    ev_id       INTEGER,
    access      TEXT,
    env_class   TEXT,
    FOREIGN KEY (source_file) REFERENCES sources(source_file) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_envvars_name ON env_vars(name);
CREATE INDEX IF NOT EXISTS idx_envvars_source ON env_vars(source_file);

CREATE TABLE IF NOT EXISTS value_tables (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source_file     TEXT NOT NULL,
    table_name      TEXT NOT NULL,
    value           INTEGER NOT NULL,
    text            TEXT,
    FOREIGN KEY (source_file) REFERENCES sources(source_file) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_valtables_name ON value_tables(table_name);
CREATE INDEX IF NOT EXISTS idx_valtables_source ON value_tables(source_file);

CREATE TABLE IF NOT EXISTS capl_env_bindings (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    source_file  TEXT NOT NULL,
    env_var      TEXT NOT NULL,
    signal       TEXT NOT NULL,
    message_name TEXT,
    bus_type     TEXT,
    value_expr   TEXT,
    FOREIGN KEY (source_file) REFERENCES sources(source_file) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_caplenv_envvar ON capl_env_bindings(env_var);
CREATE INDEX IF NOT EXISTS idx_caplenv_signal ON capl_env_bindings(signal);
CREATE INDEX IF NOT EXISTS idx_caplenv_source ON capl_env_bindings(source_file);

CREATE TABLE IF NOT EXISTS capl_sysvar_mappings (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    source_file  TEXT NOT NULL,
    sysvar_path  TEXT NOT NULL,
    signal       TEXT NOT NULL,
    message_name TEXT,
    bus_type     TEXT,
    value_expr   TEXT,
    FOREIGN KEY (source_file) REFERENCES sources(source_file) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_caplsv_sysvar ON capl_sysvar_mappings(sysvar_path);
CREATE INDEX IF NOT EXISTS idx_caplsv_signal ON capl_sysvar_mappings(signal);
CREATE INDEX IF NOT EXISTS idx_caplsv_source ON capl_sysvar_mappings(source_file);

CREATE TABLE IF NOT EXISTS dids (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source_file     TEXT NOT NULL,
    did_hex         TEXT NOT NULL,
    qual            TEXT,
    name            TEXT,
    semantic        TEXT,
    length_bytes    INTEGER,
    session_required TEXT,
    FOREIGN KEY (source_file) REFERENCES sources(source_file) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_dids_hex ON dids(did_hex);
CREATE INDEX IF NOT EXISTS idx_dids_source ON dids(source_file);

CREATE TABLE IF NOT EXISTS did_fields (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    source_file   TEXT NOT NULL,
    did_hex       TEXT NOT NULL,
    field_qual    TEXT,
    field_name    TEXT,
    dtref         TEXT,
    default_value TEXT,
    FOREIGN KEY (source_file) REFERENCES sources(source_file) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_didfields_did ON did_fields(did_hex);
CREATE INDEX IF NOT EXISTS idx_didfields_source ON did_fields(source_file);

CREATE TABLE IF NOT EXISTS dtcs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source_file     TEXT NOT NULL,
    dtc_hex         TEXT NOT NULL,
    name            TEXT,
    description     TEXT,
    FOREIGN KEY (source_file) REFERENCES sources(source_file) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_dtcs_hex ON dtcs(dtc_hex);
CREATE INDEX IF NOT EXISTS idx_dtcs_source ON dtcs(source_file);

CREATE TABLE IF NOT EXISTS calibrations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source_file     TEXT NOT NULL,
    name            TEXT NOT NULL,
    address         TEXT,
    dimension       INTEGER,
    type            TEXT,
    FOREIGN KEY (source_file) REFERENCES sources(source_file) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_calibrations_name ON calibrations(name);
CREATE INDEX IF NOT EXISTS idx_calibrations_source ON calibrations(source_file);

CREATE TABLE IF NOT EXISTS requirements (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source_file     TEXT NOT NULL,
    req_id          TEXT NOT NULL,
    text            TEXT,
    source_row      INTEGER,
    FOREIGN KEY (source_file) REFERENCES sources(source_file) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_requirements_reqid ON requirements(req_id);
CREATE INDEX IF NOT EXISTS idx_requirements_source ON requirements(source_file);

CREATE TABLE IF NOT EXISTS conventions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source_file     TEXT,
    category        TEXT NOT NULL,
    pattern         TEXT NOT NULL,
    description     TEXT,
    confidence      REAL,
    runner_up       TEXT,
    FOREIGN KEY (source_file) REFERENCES sources(source_file) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_conventions_category ON conventions(category);

CREATE TABLE IF NOT EXISTS issues (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    severity        TEXT NOT NULL,
    category        TEXT NOT NULL,
    message         TEXT NOT NULL,
    source_file     TEXT,
    entity_name     TEXT,
    resolution      TEXT,
    FOREIGN KEY (source_file) REFERENCES sources(source_file) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_issues_severity ON issues(severity);
CREATE INDEX IF NOT EXISTS idx_issues_source ON issues(source_file);

CREATE TABLE IF NOT EXISTS audit_events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          TEXT NOT NULL,
    timestamp       TEXT NOT NULL,
    event_type      TEXT NOT NULL,
    source_file     TEXT,
    entity_type     TEXT,
    entity_name     TEXT,
    action          TEXT,
    details         TEXT
);
CREATE INDEX IF NOT EXISTS idx_audit_run_id ON audit_events(run_id);
CREATE INDEX IF NOT EXISTS idx_audit_source ON audit_events(source_file);
"""

VIEW_SQL = """
DROP VIEW IF EXISTS v_signal_context;
DROP VIEW IF EXISTS v_signal_wiring;
DROP VIEW IF EXISTS v_sysvar_lookup;

CREATE VIEW v_signal_context AS
SELECT 
    s.name            AS signal_name,
    s.message         AS message_name,
    s.bus_role,
    s.unit,
    s.factor,
    s.offset,
    s.minimum,
    s.maximum,
    s.source_file     AS signal_source,
    src.preferred     AS preferred
FROM signals s
JOIN sources src ON src.source_file = s.source_file
WHERE src.preferred = 1;

CREATE VIEW v_signal_wiring AS
SELECT 
    signal,
    'env_binding'  AS wiring_type,
    env_var        AS source_entity,
    bus_type,
    message_name,
    source_file
FROM capl_env_bindings
UNION ALL
SELECT
    signal,
    'sysvar_mapping' AS wiring_type,
    sysvar_path      AS source_entity,
    bus_type,
    message_name,
    source_file
FROM capl_sysvar_mappings;

CREATE VIEW v_sysvar_lookup AS
SELECT 
    sv.name,
    sv.full_path,
    sv.namespace,
    sv.type,
    sv.unit,
    sv.min,
    sv.max,
    sv.default_val,
    sv.source_file
FROM sysvars sv;
"""

TABLE_COLUMNS = {
    "messages": [
        "source_file", "bus_role", "name", "frame_id_hex", "dlc",
        "cycle_ms", "senders", "comment"
    ],
    "signals": [
        "source_file", "bus_role", "message", "name", "start_bit",
        "length", "byte_order", "is_signed", "factor", "offset",
        "minimum", "maximum", "unit", "receivers", "comment"
    ],
    "sysvars": [
        "source_file", "namespace", "name", "full_path", "type",
        "unit", "min", "max", "default_val", "comment"
    ],
    "env_vars": [
        "source_file", "name", "dtype_raw", "min", "max", "unit",
        "initial", "ev_id", "access", "env_class"
    ],
    "value_tables": [
        "source_file", "table_name", "value", "text"
    ],
    "capl_env_bindings": [
        "source_file", "env_var", "signal", "message_name", "bus_type", "value_expr"
    ],
    "capl_sysvar_mappings": [
        "source_file", "sysvar_path", "signal", "message_name", "bus_type", "value_expr"
    ],
    "dids": [
        "source_file", "did_hex", "qual", "name", "semantic",
        "length_bytes", "session_required"
    ],
    "did_fields": [
        "source_file", "did_hex", "field_qual", "field_name", "dtref", "default_value"
    ],
    "dtcs": [
        "source_file", "dtc_hex", "name", "description"
    ],
    "calibrations": [
        "source_file", "name", "address", "dimension", "type"
    ],
    "requirements": [
        "source_file", "req_id", "text", "source_row"
    ],
}

SOURCE_TABLES = [
    "messages", "signals", "sysvars", "env_vars", "value_tables",
    "capl_env_bindings", "capl_sysvar_mappings", "dids", "did_fields",
    "dtcs", "calibrations", "requirements"
]

VERSION_STRIP = re.compile(r"(_wip_\d+|-wip_\d+|_v\d+|-\d{3,}|_\d{8})$", re.IGNORECASE)


def _compute_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _ensure_schema(conn, log):
    conn.executescript(SCHEMA_SQL)
    log("KB: schema ensured (10 tables)")


def _ensure_views(conn, log):
    conn.executescript(VIEW_SQL)
    log("KB: refreshing views")


def _normalize_source_map(inspection_result, log):
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

    return source_map


def _family_key(basename: str) -> str:
    name = basename.rsplit(".", 1)[0]
    while True:
        new_name = VERSION_STRIP.sub("", name)
        if new_name == name:
            break
        name = new_name
    return name.lower()


def _is_source_in_result(source_file, inspection_result):
    data_keys = [
        "dbc_messages", "dbc_signals", "sysvars", "env_vars", "value_tables",
        "capl_bindings", "capl_sysvar_mappings", "dids", "did_fields",
        "dtcs", "calibrations", "requirements"
    ]
    return any(
        row.get("source_file") == source_file
        for key in data_keys
        for row in inspection_result.get(key, [])
    )


def _group_counts_by_source(inspection_result):
    counts = {}

    def bump(source_file, key):
        if not source_file:
            return
        counts.setdefault(source_file, {}).setdefault(key, 0)
        counts[source_file][key] += 1

    mapping = {
        "dbc_messages": "messages",
        "dbc_signals": "signals",
        "env_vars": "env_vars",
        "capl_bindings": "capl_env_bindings",
        "capl_sysvar_mappings": "capl_sysvar_mappings",
        "sysvars": "sysvars",
        "dids": "dids",
        "did_fields": "did_fields",
        "value_tables": "value_tables",
        "dtcs": "dtcs",
        "calibrations": "calibrations",
        "requirements": "requirements",
    }

    for key, table in mapping.items():
        for row in inspection_result.get(key, []):
            bump(row.get("source_file"), table)
    return counts


def _determine_kind(source_file, path, contribution_counts):
    ext = path.suffix.lower()
    counts = contribution_counts.get(source_file, {})
    if ext == ".dbc":
        if counts.get("messages", 0) > 0 or counts.get("signals", 0) > 0:
            return "dbc"
        if counts.get("env_vars", 0) > 0:
            return "envdbc"
        return "dbc"
    if ext == ".cdd":
        return "cdd"
    if ext == ".vsysvar":
        return "vsysvar"
    if ext in {".can", ".cin"}:
        return "capl"
    if ext == ".xvp":
        return "panel"
    if ext in {".ini", ".cfg"}:
        return "config"
    if ext == ".dll":
        return "nodelayer"
    return ext.lstrip(".") or "unknown"


def _coerce_value(table: str, col: str, value) -> any:
    """Convert string values to appropriate types based on schema."""
    if value is None or value == "":
        return None

    # Integer columns
    int_cols = {
        "signals": {"start_bit", "length", "is_signed"},
        "messages": {"dlc"},
        "dids": {"length_bytes"},
        "did_fields": set(),
        "dtcs": set(),
        "calibrations": {"dimension"},
        "requirements": {"source_row"},
        "env_vars": {"ev_id"},
        "sysvars": set(),
    }

    # Real columns
    real_cols = {
        "signals": {"factor", "offset", "minimum", "maximum"},
        "sysvars": {"min", "max", "default_val"},
        "env_vars": {"min", "max", "initial"},
    }

    if col in int_cols.get(table, set()):
        try:
            if isinstance(value, bool):
                return 1 if value else 0
            # Handle string "True"/"False"
            if isinstance(value, str):
                if value.lower() == "true":
                    return 1
                if value.lower() == "false":
                    return 0
            return int(float(value))  # Handle "1" as int
        except (ValueError, TypeError):
            return None

    if col in real_cols.get(table, set()):
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    return value


def _row_values_for_table(table, row):
    if table == "sysvars":
        normalized = dict(row)
        normalized["default_val"] = row.get("default", row.get("default_val", ""))
        values = []
        for col in TABLE_COLUMNS[table]:
            val = _coerce_value(table, col, normalized.get(col, ""))
            values.append(val if val is not None else "")
        return tuple(values)

    if table == "capl_sysvar_mappings":
        normalized = dict(row)
        normalized["sysvar_path"] = row.get("sysvar", row.get("sysvar_path", ""))
        return tuple(_coerce_value(table, col, normalized.get(col, "")) or ""
                     for col in TABLE_COLUMNS[table])

    values = []
    for col in TABLE_COLUMNS[table]:
        val = _coerce_value(table, col, row.get(col, ""))
        values.append(val if val is not None else "")
    return tuple(values)


def _insert_rows(conn, table, rows, basename, log):
    if not rows:
        return 0
    columns = TABLE_COLUMNS[table]
    placeholders = ", ".join("?" for _ in columns)
    sql = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})"
    inserted = 0
    for index, row in enumerate(rows, start=1):
        try:
            values = _row_values_for_table(table, row)
            conn.execute(sql, values)
            inserted += 1
        except Exception as exc:
            log(f"KB: error inserting into {table} from {basename} row {index}: {exc}")
    if inserted:
        log(f"KB:   {table}: +{inserted} rows from {basename}")
    return inserted


def _resolve_row_source_path(row):
    for key in ("resolved_path", "full_path", "path", "source_path"):
        value = row.get(key)
        if not value:
            continue
        try:
            return Path(value).resolve()
        except OSError:
            continue
    return None


def _effective_source_for_row(row, basename_map, path_map):
    row_path = _resolve_row_source_path(row)
    if row_path is not None and row_path in path_map:
        return path_map[row_path]
    source_file = row.get("source_file")
    if source_file in basename_map:
        return basename_map[source_file]
    return None


def _ingest_source(conn, source_file, full_path, kind, inspection_result, log, path_to_effective_source_file):
    row_count = 0
    basename_to_effective = {}
    for path, effective_name in path_to_effective_source_file.items():
        basename_to_effective.setdefault(path.name, effective_name)

    def map_rows(rows):
        mapped_rows = []
        for row in rows:
            mapped_source = _effective_source_for_row(row, basename_to_effective, path_to_effective_source_file)
            if mapped_source is None:
                missing = row.get("source_file", "")
                log(f"KB:   warning: orphan row skipped, source not found: {missing}")
                continue
            if mapped_source != source_file:
                continue
            normalized = dict(row)
            normalized["source_file"] = mapped_source
            mapped_rows.append(normalized)
        return mapped_rows

    rows_by_table = {
        "messages": map_rows(inspection_result.get("dbc_messages", [])),
        "signals": map_rows(inspection_result.get("dbc_signals", [])),
        "sysvars": map_rows(inspection_result.get("sysvars", [])),
        "env_vars": map_rows(inspection_result.get("env_vars", [])),
        "value_tables": map_rows(inspection_result.get("value_tables", [])),
        "capl_env_bindings": map_rows(inspection_result.get("capl_bindings", [])),
        "capl_sysvar_mappings": map_rows(inspection_result.get("capl_sysvar_mappings", [])),
        "dids": map_rows(inspection_result.get("dids", [])),
        "did_fields": map_rows(inspection_result.get("did_fields", [])),
        "dtcs": map_rows(inspection_result.get("dtcs", [])),
        "calibrations": map_rows(inspection_result.get("calibrations", [])),
        "requirements": map_rows(inspection_result.get("requirements", [])),
    }

    for table, rows in rows_by_table.items():
        row_count += _insert_rows(conn, table, rows, source_file, log)

    return row_count


def _find_orphan_data_sources(source_map, inspection_result, log):
    known = set(source_map)
    missing = set()
    data_keys = [
        "dbc_messages", "dbc_signals", "sysvars", "env_vars",
        "value_tables", "capl_bindings", "capl_sysvar_mappings",
        "dids", "did_fields", "dtcs", "calibrations", "requirements"
    ]
    for table in data_keys:
        for row in inspection_result.get(table, []):
            source_file = row.get("source_file")
            if source_file and source_file not in known:
                missing.add(source_file)
    for source_file in sorted(missing):
        log(f"KB: warning source {source_file} referenced in data but missing path mapping")
    return missing


def _current_source_list(conn):
    cursor = conn.execute("SELECT source_file FROM sources")
    return {row[0] for row in cursor.fetchall()}


def _preferred_version_logic(conn, log):
    cursor = conn.execute("SELECT source_file, full_path, kind, mtime FROM sources")
    records = cursor.fetchall()
    always_preferred_kinds = {"capl", "panel", "config", "nodelayer", "envdbc"}
    versioned_kinds = {"dbc", "cdd", "vsysvar"}

    conn.execute("UPDATE sources SET preferred = 1 WHERE kind IN (?, ?, ?, ?, ?)", tuple(always_preferred_kinds))

    families = {}
    for source_file, full_path, kind, mtime in records:
        if kind not in versioned_kinds:
            continue
        key = (kind, _family_key(source_file))
        families.setdefault(key, []).append((source_file, full_path, mtime))

    family_count = 0
    demoted = 0
    for family_key, members in families.items():
        if len(members) <= 1:
            continue
        family_count += 1
        preferred = max(members, key=lambda item: item[2])
        kept, kept_path, kept_mtime = preferred
        older = [m for m in members if m[0] != kept]
        if older:
            # First ensure the kept source is preferred (1)
            conn.execute("UPDATE sources SET preferred = 1 WHERE source_file = ?", (kept,))
            # Then demote all older sources (0)
            demoted += len(older)
            for other, *_ in older:
                conn.execute("UPDATE sources SET preferred = 0 WHERE source_file = ?", (other,))
            kind, family_stem = family_key
            log(f"KB:   family ({kind}) {family_stem}: kept {kept}, demoted {len(older)} older")
    return family_count, demoted


def build_knowledge_base(inspection_result, db_path, log=print, verbose=False):
    start = datetime.utcnow()
    db_path = Path(db_path)
    log(f"KB: opening database at {db_path}")

    source_map = _normalize_source_map(inspection_result, log)
    _find_orphan_data_sources(source_map, inspection_result, log)

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        _ensure_schema(conn, log)

        log("KB: scanning sources for changes...")
        contribution_counts = _group_counts_by_source(inspection_result)
        new_sources = []
        changed_sources = []
        unchanged_sources = []
        source_states = {}
        path_to_effective_source_file = {}
        current_sources = set()
        existing_by_name = {
            row[0]: row[1]
            for row in conn.execute("SELECT source_file, sha256 FROM sources").fetchall()
        }
        seen_sha_by_name = dict(existing_by_name)

        for basename in sorted(source_map):
            for full_path in sorted(source_map[basename], key=lambda p: str(p)):
                if not full_path.exists():
                    log(f"KB: warning source path missing for {basename}")
                    continue
                sha256 = _compute_sha256(full_path)
                effective_source_file = basename
                existing_sha = seen_sha_by_name.get(basename)
                if existing_sha is not None:
                    if existing_sha == sha256:
                        path_to_effective_source_file[full_path] = basename
                        log(f"KB:   SKIP duplicate  {basename}  (same sha256, already ingested)")
                        continue
                    stem = Path(basename).stem
                    ext = Path(basename).suffix
                    effective_source_file = f"{stem}__{sha256[:8]}{ext}"
                    log(f"KB:   COLLISION  {basename} vs {full_path}, renamed to {effective_source_file}")
                seen_sha_by_name[effective_source_file] = sha256
                path_to_effective_source_file[full_path] = effective_source_file
                current_sources.add(effective_source_file)

        for full_path, source_file in sorted(path_to_effective_source_file.items(), key=lambda item: item[1]):
            sha256 = _compute_sha256(full_path)
            mtime = full_path.stat().st_mtime
            parsed_at = datetime.utcnow().isoformat()
            existing = conn.execute(
                "SELECT sha256 FROM sources WHERE source_file = ?",
                (source_file,),
            ).fetchone()
            if existing is None:
                log(f"KB:   NEW      {source_file}  (sha256={sha256[:8]})")
                kind = _determine_kind(source_file, full_path, contribution_counts)
                conn.execute(
                    "INSERT INTO sources(source_file, full_path, sha256, kind, mtime, parsed_at, preferred, row_count) VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
                    (source_file, str(full_path), sha256, kind, mtime, parsed_at, 1, 0),
                )
                inserted = _ingest_source(conn, source_file, full_path, kind, inspection_result, log, path_to_effective_source_file)
                conn.execute("UPDATE sources SET row_count = ? WHERE source_file = ?", (inserted, source_file))
                new_sources.append(source_file)
                source_states[source_file] = "new"
            elif existing[0] != sha256:
                log(f"KB:   CHANGED  {source_file}  (sha256={sha256[:8]})")
                kind = _determine_kind(source_file, full_path, contribution_counts)
                conn.execute("DELETE FROM sources WHERE source_file = ?", (source_file,))
                conn.execute(
                    "INSERT INTO sources(source_file, full_path, sha256, kind, mtime, parsed_at, preferred, row_count) VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
                    (source_file, str(full_path), sha256, kind, mtime, parsed_at, 1, 0),
                )
                inserted = _ingest_source(conn, source_file, full_path, kind, inspection_result, log, path_to_effective_source_file)
                conn.execute("UPDATE sources SET row_count = ? WHERE source_file = ?", (inserted, source_file))
                changed_sources.append(source_file)
                source_states[source_file] = "changed"
            else:
                if verbose:
                    log(f"KB:   unchanged {source_file}")
                unchanged_sources.append(source_file)
                source_states[source_file] = "unchanged"

        conn.commit()

        existing_sources = _current_source_list(conn)
        removed_sources = sorted(existing_sources - current_sources)
        deleted_sources = []
        for source_file in removed_sources:
            conn.execute("DELETE FROM sources WHERE source_file = ?", (source_file,))
            log(f"KB:   REMOVED  {source_file}  (no longer in project)")
            deleted_sources.append(source_file)
        conn.commit()

        log(
            f"KB: summary: {len(new_sources)} new, {len(changed_sources)} changed, {len(unchanged_sources)} unchanged, {len(deleted_sources)} removed"
        )

        log("KB: ingesting rows...")
        family_count, demoted = _preferred_version_logic(conn, log)
        log("KB: applying preferred-version logic...")
        conn.commit()

        _ensure_views(conn, log)
        conn.commit()

        elapsed = (datetime.utcnow() - start).total_seconds()
        log(f"KB: done in {elapsed:.2f}s")

        row_counts = {}
        for table in TABLE_COLUMNS:
            row_counts[table] = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

        return {
            "db_path": str(db_path),
            "new_sources": new_sources,
            "changed_sources": changed_sources,
            "unchanged_sources": unchanged_sources,
            "deleted_sources": deleted_sources,
            "row_counts": row_counts,
            "preferred_families": family_count,
            "non_preferred_sources": demoted,
            "elapsed_seconds": elapsed,
        }
    finally:
        conn.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python kb_builder.py <inspection.json> [db_path]")
        sys.exit(1)
    path = Path(sys.argv[1])
    with path.open() as f:
        result = json.load(f)
    db = sys.argv[2] if len(sys.argv) > 2 else "dcu_knowledge.db"
    summary = build_knowledge_base(result, db)
    print(json.dumps(summary, indent=2))
