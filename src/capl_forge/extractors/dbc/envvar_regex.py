"""DBC environment variable regex parser."""
import re
from pathlib import Path


EV_PATTERN = re.compile(
    r'^EV_\s+(?P<name>\w+)\s*:\s*(?P<dtype>\d+)\s+'
    r'\[(?P<min>[-\d\.]+)\|(?P<max>[-\d\.]+)\]\s*'
    r'"(?P<unit>[^"]*)"\s+(?P<init>[-\d\.]+)\s+'
    r'(?P<ev_id>\d+)\s+(?P<access>\w+)',
    re.MULTILINE,
)
CLASS_PATTERN = re.compile(r'BA_\s+"GenEnvVarClassName"\s+EV_\s+(\w+)\s+"([^"]*)"')


def parse_env_variables(file_path: Path, log=None) -> list[dict]:
    """Parse environment variable definitions from a .dbc file.
    
    Extracts EV_ definitions and their GenEnvVarClassName attributes
    using regex-based text parsing.
    """
    _log = log or (lambda msg: None)
    rows = []
    try:
        text = file_path.read_text(encoding="latin-1", errors="ignore")
        class_map = {}
        for m in CLASS_PATTERN.finditer(text):
            class_map[m.group(1)] = m.group(2)
        count = 0
        for m in EV_PATTERN.finditer(text):
            rows.append({
                "source_file": file_path.name,
                "name": m.group("name"),
                "dtype_raw": m.group("dtype"),
                "min": m.group("min"),
                "max": m.group("max"),
                "unit": m.group("unit"),
                "initial": m.group("init"),
                "ev_id": m.group("ev_id"),
                "access": m.group("access"),
                "env_class": class_map.get(m.group("name"), ""),
            })
            count += 1
        _log(f"  env: {file_path.name} -> {count} env variables")
    except Exception as e:
        _log(f"  env: {file_path.name} -> ERROR: {e}")
    return rows
