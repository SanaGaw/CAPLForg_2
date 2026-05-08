"""Source file registry: NEW/CHANGED/UNCHANGED/REMOVED + SHA-256 dedup."""
from pathlib import Path
from typing import Optional

from .hashing import compute_sha256  # will be in core


def compute_file_hash(path: Path) -> str:
    """Compute SHA-256 hash of a file."""
    import hashlib
    hasher = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


VERSION_STRIP = __import__("re").compile(
    r"(_wip_\d+|-wip_\d+|_v\d+|-\d{3,}|_\d{8})$", __import__("re").IGNORECASE
)


def family_key(basename: str) -> str:
    """Strip version suffixes to find the family stem."""
    name = basename.rsplit(".", 1)[0]
    while True:
        new_name = VERSION_STRIP.sub("", name)
        if new_name == name:
            break
        name = new_name
    return name.lower()


def determine_kind(source_file: str, path: Path, contribution_counts: dict) -> str:
    """Determine the kind of a source file based on extension and contributions."""
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
