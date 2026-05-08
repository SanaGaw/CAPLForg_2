"""CDD (Candela) diagnostic file parser.

Extracted from canoe_cfg_inspector.py CfgInspector._parse_cdds and
helper methods (_local_tag, _find_service). Parses .cdd XML files
for DID definitions and their fields.
"""
import xml.etree.ElementTree as ET
from pathlib import Path


def _local_tag(elem) -> str:
    """Strip namespace from XML tag."""
    return elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag


def _find_service(node):
    """Recursively find the first SERVICE child element."""
    for child in node:
        if _local_tag(child) == "DIAGINST":
            continue
        if _local_tag(child) == "SERVICE":
            return child
        found = _find_service(child)
        if found is not None:
            return found
    return None


def _find_staticvalue(node, depth=0):
    """Find the STATICVALUE child and return its integer value."""
    for child in node:
        if _local_tag(child) == "DIAGINST":
            continue
        if _local_tag(child) == "STATICVALUE":
            v = child.get("v", "")
            try:
                return int(v)
            except (ValueError, TypeError):
                return None
        if depth < 1:
            found = _find_staticvalue(child, depth + 1)
            if found is not None:
                return found
    return None


def _collect_dataobjs(node, in_service=False):
    """Yield DATAOBJ elements that are not inside a SERVICE."""
    if _local_tag(node) == "SERVICE":
        in_service = True
    if _local_tag(node) == "DATAOBJ" and not in_service:
        yield node
    for child in node:
        if _local_tag(child) == "DIAGINST":
            continue
        yield from _collect_dataobjs(child, in_service)


def _text_from_n(node) -> str:
    """Extract the en-US text from a <n><TUV> element."""
    n_elem = node.find("./n")
    if n_elem is None:
        return ""
    for tuv in n_elem.findall("./TUV"):
        if tuv.attrib.get("{http://www.w3.org/XML/1998/namespace}lang", "") == "en-US":
            return tuv.text or ""
    return ""


def _extract_did_info(elem):
    """Extract DID info from element attributes and children."""
    did_hex = ""
    name = ""
    length = ""

    # Try attributes
    for attr in ["ID", "Id", "DID", "shortname-ref"]:
        val = elem.get(attr)
        if val:
            try:
                did_hex = f"0x{int(val, 16):04X}"
                break
            except ValueError:
                pass

    # Try child elements
    for child in elem:
        local = _local_tag(child)
        if local.upper() in ("SHORT-NAME", "LONGNAME"):
            name = child.text or ""
        elif local.lower() in ("length", "byte-length", "bitlength"):
            try:
                length = str(int(child.text or ""))
            except ValueError:
                pass

    return did_hex, name, length


def _extract_field_info(elem):
    """Extract field info from element attributes."""
    field_name = elem.get("name", "")
    start_bit = elem.get("start-bit", "")
    length_bits = elem.get("bit-length", "")
    ftype = elem.get("type", "")
    return field_name, start_bit, length_bits, ftype


def parse_cdd(file_path: Path, log=None) -> tuple[list[dict], list[dict]]:
    """Parse a .cdd file for DID definitions and fields.
    
    Walks the XML tree looking for DIAGINST elements with SERVICE children
    whose SEMANTIC matches known UDS service categories. Extracts DID
    identifiers and their constituent fields from SIMPLECOMPCONT containers.
    
    Args:
        file_path: Path to the .cdd file
        log: Optional logging callable
    
    Returns:
        Tuple of (dids_rows, did_fields_rows) where each is a list of dicts.
    """
    _log = log or (lambda msg: None)
    semantic_values = {
        "CURRENTDATA", "STOREDDATAREAD", "STOREDDATAWRITE",
        "IDENTIFICATION", "CONTROL", "MEMORY", "ROUTINE",
    }

    dids_rows = []
    did_fields_rows = []
    try:
        tree = ET.parse(file_path)
        root = tree.getroot()
        did_count = 0
        field_count = 0
        for diag in root.iter():
            if _local_tag(diag) != "DIAGINST":
                continue
            service = _find_service(diag)
            if service is None:
                continue
            semantic = service.findtext("./SEMANTIC", "") or ""
            if semantic not in semantic_values:
                continue
            did_decimal = _find_staticvalue(diag)
            if did_decimal is None:
                continue
            did_hex = f"0x{did_decimal:04X}"
            qual = diag.findtext("./QUAL", "") or ""
            name_en = _text_from_n(diag)
            dids_rows.append({
                "source_file": file_path.name,
                "did_hex": did_hex,
                "qual": qual,
                "name": name_en,
                "semantic": semantic,
                "length_bytes": "",
                "session_required": "",
            })
            did_count += 1
            for simplecont in diag.findall(".//SIMPLECOMPCONT"):
                for dataobj in _collect_dataobjs(simplecont):
                    field_qual = dataobj.findtext("./QUAL", "") or ""
                    field_name = _text_from_n(dataobj)
                    dtref = dataobj.attrib.get("dtref", "")
                    default_value = dataobj.attrib.get("v", "")
                    did_fields_rows.append({
                        "source_file": file_path.name,
                        "did_hex": did_hex,
                        "field_qual": field_qual,
                        "field_name": field_name,
                        "dtref": dtref,
                        "default_value": default_value,
                    })
                    field_count += 1
        _log(f"  cdd: {file_path.name} -> {did_count} DIDs, {field_count} fields")
    except Exception as e:
        _log(f"  cdd: {file_path.name} -> ERROR: {e}")
    return dids_rows, did_fields_rows
