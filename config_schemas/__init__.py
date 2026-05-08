"""Config schemas module for CAPL Pipeline V2.2.

This module provides JSON schema definitions and validation utilities
for configuration files used throughout the pipeline.
"""

import json
from pathlib import Path
from typing import Dict, Optional

import jsonschema

# Schema registry mapping schema names to their file paths
SCHEMA_DIR = Path(__file__).parent
SCHEMA_FILES: Dict[str, str] = {
    "signal_aliases_v1": "signal_aliases.v1.schema.json",
    "signal_aliases_v2": "signal_aliases.v2.schema.json",
    "helper_definitions": "helper_definitions.schema.json",
    "config_status": "config_status.schema.json",
    "test_template": "test_template.schema.json",
    "chat_resolution": "chat_resolution.schema.json",
    "sto_extract": "sto_extract.schema.json",
    "compliance_bundle": "compliance_bundle.schema.json",
}

# Cache for loaded schemas
_schema_cache: Dict[str, dict] = {}


def get_schema(name: str) -> dict:
    """Load and cache a JSON schema by name."""
    if name not in _schema_cache:
        schema_file = SCHEMA_FILES.get(name)
        if schema_file is None:
            raise ValueError(f"Unknown schema: {name}")
        schema_path = SCHEMA_DIR / schema_file
        if not schema_path.exists():
            raise FileNotFoundError(f"Schema file not found: {schema_path}")
        with open(schema_path, "r", encoding="utf-8") as f:
            _schema_cache[name] = json.load(f)
    return _schema_cache[name]


def validate(data: dict, schema_name: str) -> tuple[bool, list[str]]:
    """Validate data against a named schema.

    Returns:
        Tuple of (is_valid, list_of_errors)
    """
    schema = get_schema(schema_name)
    validator = jsonschema.Draft7Validator(schema)
    errors = list(validator.iter_errors(data))
    if errors:
        return False, [e.message for e in errors]
    return True, []


def validate_or_raise(data: dict, schema_name: str) -> None:
    """Validate data against a named schema, raising on failure."""
    schema = get_schema(schema_name)
    jsonschema.validate(instance=data, schema=schema)


__all__ = [
    "SCHEMA_FILES",
    "get_schema",
    "validate",
    "validate_or_raise",
]
