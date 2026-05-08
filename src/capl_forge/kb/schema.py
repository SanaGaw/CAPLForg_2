"""Database schema definitions — all 16 tables + 3 views.

This module defines the SQL DDL for creating tables and views
in the CAPL Forge knowledge base.
"""

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
    resolution      TEXT
);
CREATE INDEX IF NOT EXISTS idx_issues_severity ON issues(severity);


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
