"""SHA-256 file hashing utilities."""
from pathlib import Path


def compute_sha256(path: Path) -> str:
    """Compute SHA-256 hash of a file in 64KB chunks."""
    import hashlib
    hasher = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()
