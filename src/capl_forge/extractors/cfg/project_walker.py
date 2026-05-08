"""Walk a project directory and inventory all relevant files."""
from pathlib import Path

from .binary_scraper import ALL_EXTS, ext_role


def walk_project(cfg_dir: Path, log=None) -> list[dict]:
    """Walk the project directory and collect all relevant files.
    
    Returns a list of dicts with file metadata for every file
    whose extension matches a known engineering artifact type.
    """
    _log = log or (lambda msg: None)
    _log(f"Walking project folder: {cfg_dir}")
    inventory = []
    relevant_exts = {"." + e for e in ALL_EXTS}
    try:
        for p in cfg_dir.rglob("*"):
            if not p.is_file():
                continue
            if p.suffix.lower() in relevant_exts:
                try:
                    size = p.stat().st_size
                except OSError:
                    size = 0
                inventory.append({
                    "path": str(p),
                    "basename": p.name,
                    "extension": p.suffix.lower().lstrip("."),
                    "role": ext_role(p.suffix),
                    "size_bytes": size,
                })
    except Exception as e:
        _log(f"Walk error: {e}")
    return inventory
