"""Materialized views for the knowledge base."""
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
