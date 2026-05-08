"""CANoe .vsysvar XML parser."""
import xml.etree.ElementTree as ET
from pathlib import Path


def parse_vsysvar(file_path: Path, log=None) -> list[dict]:
    """Parse a .vsysvar file for system variable definitions.
    
    Walks the XML namespace tree and extracts variable attributes.
    """
    _log = log or (lambda msg: None)
    rows = []
    try:
        tree = ET.parse(file_path)
        root = tree.getroot()
        count = _walk_namespace(root, "", file_path.name, rows)
        _log(f"  vsysvar: {file_path.name} -> {count} variables")
    except Exception as e:
        _log(f"  vsysvar: {file_path.name} -> ERROR: {e}")
    return rows


def _walk_namespace(elem, current_ns: str, source_file: str, rows: list) -> int:
    """Recursively walk XML namespace/variable elements."""
    count = 0
    for child in elem:
        tag = child.tag.lower() if child.tag else ""
        if tag in ("namespace", "variable"):
            if tag == "namespace":
                ns_name = child.get("name", child.get("Name", ""))
                new_ns = f"{current_ns}::{ns_name}" if current_ns else ns_name
                count += _walk_namespace(child, new_ns, source_file, rows)
            else:
                var_name = child.get("name", child.get("Name", ""))
                full_path = f"{current_ns}::{var_name}" if current_ns else var_name
                rows.append({
                    "source_file": source_file,
                    "namespace": current_ns,
                    "name": var_name,
                    "full_path": full_path,
                    "type": child.get("type", child.get("Type", "")),
                    "unit": child.get("unit", child.get("Unit", "")),
                    "min": child.get("minvalue", child.get("MinValue", "")),
                    "max": child.get("maxvalue", child.get("MaxValue", "")),
                    "default": child.get("startvalue", child.get("StartValue", "")),
                    "comment": child.get("comment", child.get("Comment", "")),
                })
                count += 1
    return count
