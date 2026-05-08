"""CANoe .cfg format detection: zip vs binary."""
from pathlib import Path

def detect_format(cfg_path: Path) -> str:
    """Detect whether a .cfg file is a zip archive or binary format.
    
    CANoe .cfg files can be either zip archives (containing XML) or
    legacy binary files. The first 4 bytes determine the format.
    """
    with cfg_path.open("rb") as f:
        head = f.read(4)
    if head[:4] == b"PK\x03\x04":
        return "zip"
    return "binary"
