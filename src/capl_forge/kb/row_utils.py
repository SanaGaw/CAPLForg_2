"""Row coercion, normalization, and insertion utilities for the knowledge base.

Contains TABLE_COLUMNS definitions, type coercion, and INSERT helpers.
These are used by ingest.py during the build flow.
"""
import sqlite3
from pathlib import Path


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


def coerce_value(table: str, col: str, value):
    """Convert string values to appropriate types based on schema."""
    if value is None or value == "":
        return None

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

    real_cols = {
        "signals": {"factor", "offset", "minimum", "maximum"},
        "sysvars": {"min", "max", "default_val"},
        "env_vars": {"min", "max", "initial"},
    }

    if col in int_cols.get(table, set()):
        try:
            if isinstance(value, bool):
                return 1 if value else 0
            if isinstance(value, str):
                if value.lower() == "true":
                    return 1
                if value.lower() == "false":
                    return 0
            return int(float(value))
        except (ValueError, TypeError):
            return None

    if col in real_cols.get(table, set()):
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    return value


def row_values_for_table(table: str, row: dict) -> tuple:
    """Extract and normalize values from a data row for a given table."""
    if table == "sysvars":
        normalized = dict(row)
        normalized["default_val"] = row.get("default", row.get("default_val", ""))
        values = []
        for col in TABLE_COLUMNS[table]:
            val = coerce_value(table, col, normalized.get(col, ""))
            values.append(val if val is not None else "")
        return tuple(values)

    if table == "capl_sysvar_mappings":
        normalized = dict(row)
        normalized["sysvar_path"] = row.get("sysvar", row.get("sysvar_path", ""))
        return tuple(
            coerce_value(table, col, normalized.get(col, "")) or ""
            for col in TABLE_COLUMNS[table]
        )

    values = []
    for col in TABLE_COLUMNS[table]:
        val = coerce_value(table, col, row.get(col, ""))
        values.append(val if val is not None else "")
    return tuple(values)


def insert_rows(conn: sqlite3.Connection, table: str, rows: list[dict], basename: str, log) -> int:
    """Insert data rows into a table, returning the count inserted."""
    if not rows:
        return 0
    columns = TABLE_COLUMNS[table]
    placeholders = ", ".join("?" for _ in columns)
    sql = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})"
    inserted = 0
    for index, row in enumerate(rows, start=1):
        try:
            values = row_values_for_table(table, row)
            conn.execute(sql, values)
            inserted += 1
        except Exception as exc:
            log(f"KB: error inserting into {table} from {basename} row {index}: {exc}")
    if inserted:
        log(f"KB:   {table}: +{inserted} rows from {basename}")
    return inserted


def resolve_row_source_path(row: dict) -> Path | None:
    """Try to resolve a full file path from various row keys."""
    for key in ("resolved_path", "full_path", "path", "source_path"):
        value = row.get(key)
        if not value:
            continue
        try:
            return Path(value).resolve()
        except OSError:
            continue
    return None


def effective_source_for_row(row: dict, basename_map: dict, path_map: dict) -> str | None:
    """Find the effective source_file name for a data row."""
    row_path = resolve_row_source_path(row)
    if row_path is not None and row_path in path_map:
        return path_map[row_path]
    source_file = row.get("source_file")
    if source_file in basename_map:
        return basename_map[source_file]
    return None


def ingest_source(
    conn: sqlite3.Connection,
    source_file: str,
    full_path: Path,
    kind: str,
    inspection_result: dict,
    log,
    path_to_effective_source_file: dict,
) -> int:
    """Ingest all data rows belonging to a single source file."""
    basename_to_effective = {}
    for path, effective_name in path_to_effective_source_file.items():
        basename_to_effective.setdefault(path.name, effective_name)

    def map_rows(rows):
        mapped_rows = []
        for row in rows:
            mapped_source = effective_source_for_row(
                row, basename_to_effective, path_to_effective_source_file
            )
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

    row_count = 0
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
        row_count += insert_rows(conn, table, rows, source_file, log)

    return row_count
