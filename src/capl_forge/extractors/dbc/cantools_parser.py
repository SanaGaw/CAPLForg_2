"""DBC file parser using cantools."""
from pathlib import Path

try:
    import cantools
    CANTOOLS_AVAILABLE = True
except ImportError:
    cantools = None
    CANTOOLS_AVAILABLE = False


def parse_dbc(
    file_path: Path,
    bus_role: str = "vehicle",
    log=None,
) -> tuple[list[dict], list[dict]]:
    """Parse a .dbc file for messages and signals using cantools.
    
    Args:
        file_path: Path to the .dbc file
        bus_role: Bus role assigned by Layer 2 convention discovery.
                  Must NOT be hardcoded here — the caller (CfgInspector)
                  must obtain this from conventions.file_role_discovery.
        log: Optional logging callable
    
    Returns:
        Tuple of (messages, signals) where each is a list of dicts.
    """
    _log = log or (lambda msg: None)
    if not CANTOOLS_AVAILABLE:
        _log("WARNING: cantools not available, skipping DBC parsing")
        return [], []

    messages_rows = []
    signals_rows = []
    try:
        db = cantools.database.load_file(file_path)
        msg_count = 0
        sig_count = 0
        for msg in db.messages:
            messages_rows.append({
                "source_file": file_path.name,
                "bus_role": bus_role,
                "name": msg.name,
                "frame_id_hex": f"0x{msg.frame_id:X}",
                "dlc": msg.length,
                "cycle_ms": getattr(msg, "cycle_time", ""),
                "senders": ", ".join(msg.senders) if msg.senders else "",
                "comment": msg.comment or "",
            })
            msg_count += 1
            for sig in msg.signals:
                signals_rows.append({
                    "source_file": file_path.name,
                    "bus_role": bus_role,
                    "message": msg.name,
                    "name": sig.name,
                    "start_bit": sig.start,
                    "length": sig.length,
                    "byte_order": "little_endian" if sig.byte_order == "little_endian" else "big_endian",
                    "is_signed": 1 if sig.is_signed else 0,
                    "factor": sig.scale,
                    "offset": sig.offset,
                    "minimum": sig.minimum if sig.minimum is not None else "",
                    "maximum": sig.maximum if sig.maximum is not None else "",
                    "unit": sig.unit or "",
                    "receivers": ", ".join(sig.receivers) if sig.receivers else "",
                    "comment": sig.comment or "",
                })
                sig_count += 1
        _log(f"  dbc: {file_path.name} ({bus_role}) -> {msg_count} msgs, {sig_count} signals")
    except Exception as e:
        _log(f"  dbc: {file_path.name} -> ERROR: {e}")
    return messages_rows, signals_rows
