"""
CANoe Parser Module
===================

Provides parsing and analysis functions for CANoe project files.
Re-exports key functionality from canoe_cfg_inspector.
"""

import json
import sys
from pathlib import Path
from typing import Optional

try:
    from ..canoe_cfg_inspector import CfgInspector
    _INSPECTOR_AVAILABLE = True
except ImportError:
    CfgInspector = None
    _INSPECTOR_AVAILABLE = False


def parse_config(config_path: str, log=print) -> dict:
    """
    Parse a CANoe configuration file and extract all referenced engineering artifacts.

    Args:
        config_path: Path to the .cfg file
        log: Optional logging function

    Returns:
        dict with keys: references, inventory, sysvars, dbc_messages, dbc_signals,
                       env_vars, capl_bindings, capl_sysvar_mappings, dids, did_fields

    Raises:
        FileNotFoundError: If config file does not exist
        RuntimeError: If parsing fails
    """
    if not _INSPECTOR_AVAILABLE:
        raise RuntimeError(
            "canoe_cfg_inspector module not available. "
            "Ensure canoe_cfg_inspector.py is in the project root."
        )

    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    def _log(msg: str):
        if log:
            log(msg)

    inspector = CfgInspector(log=_log)
    result = inspector.inspect(path)
    return result


def parse_config_to_json(config_path: str, output_path: str, log=print) -> None:
    """
    Parse a CANoe configuration and save result to JSON file.

    Args:
        config_path: Path to the .cfg file
        output_path: Path to write JSON output
        log: Optional logging function
    """
    result = parse_config(config_path, log=log)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, default=str)
    if log:
        log(f"Wrote inspection result to {output_path}")


def generate_capl(test_plan: str, **kwargs) -> str:
    """
    Generate CAPL code from a test plan.

    NOTE: This is a placeholder. Actual LLM-powered CAPL generation is deferred
    until deterministic extraction is validated. The BYO LLM lifecycle must be
    configured first via: capl-forge llm setup

    Args:
        test_plan: Path to test plan file or test plan content
        **kwargs: Additional options (future use)

    Returns:
        str: Generated CAPL code (currently raises NotImplementedError)

    Raises:
        NotImplementedError: LLM integration not yet configured
    """
    # Check for LLM configuration
    llm_config_path = Path("llm_config.yaml")
    llm_health_path = Path("llm_health.json")

    if not llm_config_path.exists():
        raise NotImplementedError(
            "LLM not configured. Run 'capl-forge llm setup' first to configure "
            "your LLM provider. Python-only mode does not support CAPL generation."
        )

    if not llm_health_path.exists():
        raise NotImplementedError(
            "LLM health check not run. Run 'capl-forge llm test' first to verify "
            "your LLM endpoint is working."
        )

    # Load health check
    try:
        with open(llm_health_path, 'r') as f:
            health = json.load(f)
        if health.get("status") != "ok":
            raise NotImplementedError(
                f"LLM health check failed: {health.get('error', 'Unknown error')}. "
                "Fix the LLM configuration before generating CAPL."
            )
    except json.JSONDecodeError:
        raise NotImplementedError(
            "LLM health file is corrupted. Run 'capl-forge llm test' again."
        )

    raise NotImplementedError(
        "CAPL generation requires Module 2 implementation. "
        "Module 1 provides deterministic knowledge extraction only."
    )


def get_supported_extensions() -> dict:
    """
    Get the mapping of file roles to their extensions.

    Returns:
        dict: Extension roles mapping
    """
    return {
        "network": ["dbc", "ldf", "arxml"],
        "diagnostic": ["cdd", "odx", "odx-d", "pdx", "cbf"],
        "capl": ["can", "cin"],
        "panel": ["xvp", "cpa", "xvb"],
        "sysvar": ["vsysvar"],
        "testmodule": ["vtuexe", "vtt"],
        "nodelayer": ["dll"],
        "logging": ["blf", "asc", "mf4", "mdf4"],
        "spec": ["xlsx", "xlsm", "docx", "pdf"],
        "config": ["xml", "ini", "cfg"],
    }


def ext_role(extension: str) -> str:
    """
    Determine the role/category of a file based on its extension.

    Args:
        extension: File extension (with or without leading dot)

    Returns:
        str: Role category (network, diagnostic, capl, panel, sysvar, etc.)
    """
    ext = extension.lower().lstrip(".")

    roles = get_supported_extensions()
    for role, extensions in roles.items():
        if ext in extensions:
            return role

    return "other"


__all__ = [
    "parse_config",
    "parse_config_to_json",
    "get_supported_extensions",
    "ext_role",
    "CfgInspector",
]
