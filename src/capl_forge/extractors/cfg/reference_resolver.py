"""Resolve raw file references against the project directory tree."""
from pathlib import Path

from .binary_scraper import ext_role


def resolve_references(cfg_dir: Path, refs: list[str], log=None) -> list[dict]:
    """Resolve a list of raw path strings against the project directory.
    
    For each reference, tries multiple candidate locations:
    1. Exact path as given
    2. Relative to cfg_dir
    3. Just the filename in cfg_dir
    4. Recursive search by basename (last resort)
    
    Returns a list of dicts with resolution metadata.
    """
    _log = log or (lambda msg: None)
    resolved = []
    for raw in refs:
        p = Path(raw)
        candidates = [p, cfg_dir / p, cfg_dir / p.name]
        found_path = None
        for c in candidates:
            try:
                if c.exists() and c.is_file():
                    found_path = c.resolve()
                    break
            except OSError:
                continue
        if found_path is None:
            try:
                for match in cfg_dir.rglob(p.name):
                    if match.is_file():
                        found_path = match.resolve()
                        break
            except OSError:
                pass

        role = ext_role(p.suffix)
        resolved.append({
            "raw": raw,
            "basename": p.name,
            "extension": p.suffix.lower().lstrip("."),
            "role": role,
            "exists": found_path is not None,
            "resolved_path": str(found_path) if found_path else "",
        })
    return resolved
