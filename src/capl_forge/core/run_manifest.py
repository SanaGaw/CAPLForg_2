"""Run manifest writer."""
from datetime import datetime, timezone
import json
from pathlib import Path

def new_run_id() -> str:
    """Generate a new run ID based on UTC timestamp."""
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%SZ")

def write_run_manifest(
    manifest_dir: Path,
    run_id: str,
    config_path: str,
    db_path: str,
    summary: dict,
) -> Path:
    """Write run_manifest.json for reproducibility."""
    manifest_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "run_id": run_id,
        "config_path": str(config_path),
        "db_path": str(db_path),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
    }
    path = manifest_dir / f"run_manifest_{run_id}.json"
    path.write_text(json.dumps(manifest, indent=2, default=str))
    return path
