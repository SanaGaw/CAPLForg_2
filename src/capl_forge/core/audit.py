"""Audit event writer for CAPL Forge runs."""
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Optional
import sqlite3

def new_run_id() -> str:
    """Generate a new run ID based on timestamp."""
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%SZ")

def write_audit_event(
    conn: sqlite3.Connection,
    run_id: str,
    event_type: str,
    source_file: Optional[str] = None,
    entity_type: Optional[str] = None,
    entity_name: Optional[str] = None,
    action: Optional[str] = None,
    details: Optional[str] = None,
) -> None:
    """Write an audit event to the audit_events table.
    
    This is the documented INSERT call site for the audit_events table.
    Reachable in the standard scan-project → build-db flow.
    """
    timestamp = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO audit_events (run_id, timestamp, event_type, source_file, "
        "entity_type, entity_name, action, details) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (run_id, timestamp, event_type, source_file, entity_type, entity_name,
         action, details),
    )

def write_run_manifest(
    manifest_dir: Path,
    run_id: str,
    config_path: str,
    db_path: str,
    summary: dict,
) -> Path:
    """Write a run_manifest.json file for the run."""
    manifest_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "run_id": run_id,
        "config_path": str(config_path),
        "db_path": str(db_path),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
    }
    manifest_path = manifest_dir / f"run_manifest_{run_id}.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, default=str))
    return manifest_path
