"""
CANoe .cfg Inspector
====================
A small Tkinter GUI that takes a CANoe .cfg file, discovers every referenced
engineering artifact (DBC, LDF, CDD, CAPL, vsysvar, panels, ...), and lists
them alongside a full folder inventory. Works for both zipped and legacy
binary .cfg formats.

Design notes
------------
- Binary .cfg is NOT officially parseable. We scrape file-path-looking strings
  out of it (UTF-16LE + Latin-1) using regex. This is robust enough in practice.
- Zipped .cfg is unzipped to a temp folder and walked.
- Every step is logged to the trace panel so the user sees what is happening.
- Results are exportable to CSV for downstream use (kb_builder, MCP tools, ...).
- Single file, stdlib only. No pip install required.

Run:  python canoe_cfg_inspector.py
"""

import csv
import queue
import re
import threading
import tkinter as tk
import zipfile
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
import xml.etree.ElementTree as ET

try:
    import cantools
    CANToolsAvailable = True
except ImportError:
    cantools = None
    CANToolsAvailable = False

try:
    import lxml.etree as lxmlET
    LxmlAvailable = True
except ImportError:
    lxmlET = None
    LxmlAvailable = False

# ---------------------------------------------------------------------------
# Config: extensions we care about, grouped by role
# ---------------------------------------------------------------------------
EXTENSION_ROLES = {
    "network":     {"dbc", "ldf", "arxml"},
    "diagnostic":  {"cdd", "odx", "odx-d", "pdx", "cbf"},
    "capl":        {"can", "cin"},
    "panel":       {"xvp", "cpa", "xvb"},
    "sysvar":      {"vsysvar"},
    "testmodule":  {"vtuexe", "vtt"},
    "nodelayer":   {"dll"},
    "logging":     {"blf", "asc", "mf4", "mdf4"},
    "spec":        {"xlsx", "xlsm", "docx", "pdf"},
    "config":      {"xml", "ini", "cfg"},
}
ALL_EXTS = sorted({e for s in EXTENSION_ROLES.values() for e in s})


def ext_role(ext: str) -> str:
    ext = ext.lower().lstrip(".")
    for role, exts in EXTENSION_ROLES.items():
        if ext in exts:
            return role
    return "other"


# ---------------------------------------------------------------------------
# CaplParser: Battle-tested CAPL signal/sysvar/envvar extraction
# ---------------------------------------------------------------------------
class CaplParser:
    """Parses CAPL (.can) scripts to extract signal/sysvar/envvar mappings."""
    
    # Pattern: on sysvar sysvar::NAMESPACE::VAR_NAME { ... setSignal(SIGNAL, @this); ... }
    SYSVAR_HANDLER = re.compile(
        r'on\s+sysvar(?:_change)?\s+(sysvar::[\w:]+)\s*\{([^}]*)\}',
        re.DOTALL
    )
    
    # Pattern: on envVar VAR_NAME { ... }
    ENVVAR_HANDLER = re.compile(
        r'on\s+envVar\s+(\w+)\s*\{([^}]*(?:\{[^}]*\}[^}]*)*)\}',
        re.DOTALL
    )
    
    # setSignal(signal_name, value) or setSignal(signal_name, @this)
    SET_SIGNAL = re.compile(r'setSignal\s*\(\s*([\w]+)\s*,\s*([^)]+)\)')
    
    # getSignal(signal_name)
    GET_SIGNAL = re.compile(r'getSignal\s*\(\s*([\w]+)')
    
    # M_MSG.SIGNAL = value (CAN message signal assignment)
    MSG_SIGNAL_ASSIGN = re.compile(r'(M_\w+)\.(\w+)\s*=\s*([^;]+)')
    
    # putvalue/putValue(EV_xxx, value) or putvalue(EV_xxx, value)
    PUT_VALUE = re.compile(r'put[Vv]alue\s*\(\s*(EV_\w+|[\w]+)\s*,\s*([^)]+)\)')
    
    # getvalue/getValue(EV_xxx)
    GET_VALUE = re.compile(r'get[Vv]alue\s*\(\s*(EV_\w+|[\w]+)\s*\)')
    
    # @EV_xxx = value (CAPL shorthand direct envvar write)
    ENVVAR_DIRECT_WRITE = re.compile(r'@(EV_[\w]+)\s*=\s*([^;]+)')
    
    # @EV_xxx in expressions (read, without = after)
    ENVVAR_DIRECT_READ = re.compile(r'@(EV_[\w]+)(?!\s*=)')
    
    # @sysvar:: references in code (both read and write)
    SYSVAR_REF = re.compile(r'@sysvar::([\w:]+)')
    
    # @sysvar::NS::var = value (direct sysvar write)
    SYSVAR_DIRECT_WRITE = re.compile(r'@sysvar::([\w:]+)\s*=\s*([^;]+)')
    
    # testWaitForSignalAvailable/Match/Change patterns
    TEST_SIGNAL_WAIT = re.compile(r'testWaitForSignal\w+\s*\(\s*([\w]+)')
    
    # testcase definitions
    TESTCASE_DEF = re.compile(r'testcase\s+(\w+)')
    
    # message declarations: message 0xID NAME;
    MSG_DECL = re.compile(r'message\s+(0x[0-9A-Fa-f]+)\s+(\w+)\s*;')
    
    def __init__(self):
        self.mappings = []           # sysvar → signal direct mappings
        self.envvar_usages = []      # environment variable usages
        self.sysvar_references = []  # @sysvar:: read references
        self.message_declarations = []
        self.testcases = []          # testcase definitions with their references
        
    def parse(self, filepath):
        """Parse a CAPL .can file."""
        try:
            with open(filepath, 'r', encoding='latin-1') as f:
                content = f.read()
        except Exception as e:
            raise RuntimeError(f"Cannot read CAPL file {filepath}: {e}")
        
        source_file = Path(filepath).name
        
        # 1. Extract on sysvar → setSignal mappings
        self._parse_sysvar_handlers(content, source_file)
        
        # 2. Extract on envVar handlers
        self._parse_envvar_handlers(content, source_file)
        
        # 3. Extract @sysvar:: references
        self._parse_sysvar_references(content, source_file)
        
        # 4. Extract message declarations
        self._parse_message_declarations(content, source_file)
        
        # 5. Extract putvalue/getvalue for environment variables
        self._parse_envvar_usages(content, source_file)
        
        return self.mappings
    
    def _parse_sysvar_handlers(self, content, source_file):
        """Parse 'on sysvar' handlers with setSignal calls AND M_MSG.SIGNAL assignments."""
        pattern = re.compile(
            r'on\s+sysvar(?:_change)?\s+([\w:]+(?:::[\w]+)*)\s*\{',
            re.MULTILINE
        )
        
        for match in pattern.finditer(content):
            # Skip if inside a block comment
            pre = content[max(0, match.start()-200):match.start()]
            if '/*' in pre and '*/' not in pre[pre.rfind('/*'):]:
                continue
            
            sysvar_path = match.group(1).strip()
            # Find the matching closing brace - correctly handles nested braces
            start = match.end()
            brace_count = 1
            pos = start
            while pos < len(content) and brace_count > 0:
                if content[pos] == '{':
                    brace_count += 1
                elif content[pos] == '}':
                    brace_count -= 1
                pos += 1
            
            block = content[start:pos-1]
            
            # Find setSignal calls in this block
            for sig_match in self.SET_SIGNAL.finditer(block):
                signal_name = sig_match.group(1).strip()
                value = sig_match.group(2).strip()
                
                self.mappings.append({
                    'sysvar_path': sysvar_path,
                    'signal_name': signal_name,
                    'mapping_type': 'sysvar_to_signal',
                    'direction': 'write',
                    'value_expr': value,
                    'source_file': source_file,
                    'capl_handler': f'on sysvar {sysvar_path}',
                    'message_name': '',
                    'bus_type': 'LIN'
                })
            
            # Find M_MSG.SIGNAL = value patterns (CAN signal assignments)
            for msg_match in self.MSG_SIGNAL_ASSIGN.finditer(block):
                msg_name = msg_match.group(1).strip()
                signal_name = msg_match.group(2).strip()
                value_expr = msg_match.group(3).strip()
                
                self.mappings.append({
                    'sysvar_path': sysvar_path,
                    'signal_name': signal_name,
                    'mapping_type': 'sysvar_to_can_signal',
                    'direction': 'write',
                    'value_expr': value_expr,
                    'source_file': source_file,
                    'capl_handler': f'on sysvar {sysvar_path}',
                    'message_name': msg_name,
                    'bus_type': 'CAN'
                })
            
            # Find @sysvar::XXX = value patterns (VT-System / direct sysvar writes)
            for sv_match in self.SYSVAR_DIRECT_WRITE.finditer(block):
                sysvar_target = sv_match.group(1).strip()
                value_expr = sv_match.group(2).strip()
                
                self.mappings.append({
                    'sysvar_path': sysvar_path,
                    'signal_name': sysvar_target,
                    'mapping_type': 'sysvar_to_sysvar',
                    'direction': 'write',
                    'value_expr': value_expr,
                    'source_file': source_file,
                    'capl_handler': f'on sysvar {sysvar_path}',
                    'message_name': '',
                    'bus_type': 'VTS' if 'VTS::' in sysvar_target else 'SYSVAR'
                })
    
    def _parse_envvar_handlers(self, content, source_file):
        """Parse 'on envVar' handlers - correctly handles nested braces."""
        pattern = re.compile(r'on\s+envVar\s+(\w+)\s*\{', re.MULTILINE)
        
        for match in pattern.finditer(content):
            # Skip if inside a block comment
            pre = content[max(0, match.start()-200):match.start()]
            if '/*' in pre and '*/' not in pre[pre.rfind('/*'):]:
                continue
            
            envvar_name = match.group(1).strip()
            start = match.end()
            brace_count = 1
            pos = start
            while pos < len(content) and brace_count > 0:
                if content[pos] == '{':
                    brace_count += 1
                elif content[pos] == '}':
                    brace_count -= 1
                pos += 1
            
            block = content[start:pos-1]
            
            # Find setSignal in envvar handler (LIN signals)
            for sig_match in self.SET_SIGNAL.finditer(block):
                self.mappings.append({
                    'sysvar_path': envvar_name,
                    'signal_name': sig_match.group(1).strip(),
                    'mapping_type': 'envvar_to_signal',
                    'direction': 'write',
                    'value_expr': sig_match.group(2).strip(),
                    'source_file': source_file,
                    'capl_handler': f'on envVar {envvar_name}',
                    'message_name': '',
                    'bus_type': 'LIN'
                })
            
            # Find M_MSG.SIGNAL = value patterns (CAN signal assignments)
            for msg_match in self.MSG_SIGNAL_ASSIGN.finditer(block):
                msg_name = msg_match.group(1).strip()
                signal_name = msg_match.group(2).strip()
                value_expr = msg_match.group(3).strip()
                
                self.mappings.append({
                    'sysvar_path': envvar_name,
                    'signal_name': signal_name,
                    'mapping_type': 'envvar_to_can_signal',
                    'direction': 'write',
                    'value_expr': value_expr,
                    'source_file': source_file,
                    'capl_handler': f'on envVar {envvar_name}',
                    'message_name': msg_name,
                    'bus_type': 'CAN'
                })
            
            # Find @sysvar::XXX = value patterns (VT-System / direct sysvar writes)
            for sv_match in self.SYSVAR_DIRECT_WRITE.finditer(block):
                sysvar_target = sv_match.group(1).strip()
                value_expr = sv_match.group(2).strip()
                
                self.mappings.append({
                    'sysvar_path': envvar_name,
                    'signal_name': sysvar_target,
                    'mapping_type': 'envvar_to_sysvar',
                    'direction': 'write',
                    'value_expr': value_expr,
                    'source_file': source_file,
                    'capl_handler': f'on envVar {envvar_name}',
                    'message_name': '',
                    'bus_type': 'VTS' if 'VTS::' in sysvar_target else 'SYSVAR'
                })
            
            # Track the envvar handler itself
            self.envvar_usages.append({
                'name': envvar_name,
                'usage_type': 'handler',
                'source_file': source_file,
                'context': f'on envVar {envvar_name}'
            })
    
    def _parse_sysvar_references(self, content, source_file):
        """Extract @sysvar:: read references."""
        for match in self.SYSVAR_REF.finditer(content):
            ref_path = match.group(1)
            line_start = content.rfind('\n', 0, match.start()) + 1
            line_end = content.find('\n', match.end())
            context_line = content[line_start:line_end].strip()
            
            self.sysvar_references.append({
                'sysvar_path': f"sysvar::{ref_path}",
                'usage_type': 'read',
                'source_file': source_file,
                'context': context_line[:200]
            })
    
    def _parse_message_declarations(self, content, source_file):
        """Extract message declarations."""
        for match in self.MSG_DECL.finditer(content):
            self.message_declarations.append({
                'msg_id': match.group(1),
                'msg_name': match.group(2),
                'source_file': source_file
            })
    
    def _parse_envvar_usages(self, content, source_file):
        """Extract putvalue/getvalue environment variable usages."""
        for match in self.PUT_VALUE.finditer(content):
            self.envvar_usages.append({
                'name': match.group(1),
                'usage_type': 'putvalue',
                'source_file': source_file,
                'context': f'putvalue({match.group(1)}, {match.group(2).strip()})'
            })
        
        for match in self.GET_VALUE.finditer(content):
            self.envvar_usages.append({
                'name': match.group(1),
                'usage_type': 'getvalue',
                'source_file': source_file,
                'context': f'getvalue({match.group(1)})'
            })
        
        # Also capture @EV_xxx = value (direct envvar writes)
        for match in self.ENVVAR_DIRECT_WRITE.finditer(content):
            self.envvar_usages.append({
                'name': match.group(1),
                'usage_type': 'direct_write',
                'source_file': source_file,
                'context': f'@{match.group(1)} = {match.group(2).strip()[:50]}'
            })
        
        # @EV_xxx reads (used in expressions without =)
        for match in self.ENVVAR_DIRECT_READ.finditer(content):
            self.envvar_usages.append({
                'name': match.group(1),
                'usage_type': 'direct_read',
                'source_file': source_file,
                'context': f'@{match.group(1)} (read)'
            })


# ---------------------------------------------------------------------------
# Core logic (no GUI code in here, easy to reuse from a CLI or agent)
# ---------------------------------------------------------------------------
class CfgInspector:
    """Inspects a CANoe .cfg and reports what it references."""

    # Absolute Windows path: C:\... ending in a known extension
    _ABS_PATTERN = re.compile(
        r"[A-Za-z]:\\[^\x00<>\"|?*\r\n]{1,400}?\.(?:" + "|".join(ALL_EXTS) + r")",
        re.IGNORECASE,
    )
    # Relative path: starts with .\ ..\ or a folder segment
    _REL_PATTERN = re.compile(
        r"(?:\.{1,2}\\|[\w\-\. ]+\\)[^\x00<>\"|?*\r\n]{1,400}?\.(?:" + "|".join(ALL_EXTS) + r")",
        re.IGNORECASE,
    )

    def __init__(self, log):
        """log: callable(str) that accepts a trace line."""
        self.log = log

    # -- public entry point -------------------------------------------------
    def inspect(self, cfg_path: Path):
        self.log(f"=== Inspecting {cfg_path.name} ===")
        self.log(f"Full path: {cfg_path}")
        if not cfg_path.exists():
            self.log("ERROR: file does not exist")
            return {"references": [], "inventory": []}

        size_kb = cfg_path.stat().st_size / 1024
        self.log(f"Size: {size_kb:,.1f} KiB")

        fmt = self._detect_format(cfg_path)
        self.log(f"Detected format: {fmt}")

        if fmt == "zip":
            refs = self._inspect_zip(cfg_path)
        else:
            refs = self._inspect_binary(cfg_path)

        self.log(f"Extracted {len(refs)} candidate references")

        resolved = self._resolve_references(cfg_path.parent, refs)
        found = sum(1 for r in resolved if r["exists"])
        self.log(f"Resolved: {found} found, {len(resolved) - found} missing")

        inventory = self._walk_project(cfg_path.parent)
        self.log(f"Project inventory: {len(inventory)} relevant files in tree")

        self._summarize(resolved, inventory)

        self.log("--- Parsing vsysvar files ---")
        sysvars = self._parse_vsysvars(resolved, inventory)
        self.log(f"Total sysvars extracted: {len(sysvars)}")

        self.log("--- Parsing DBC files ---")
        dbc_messages, dbc_signals = self._parse_dbcs(resolved, inventory)
        self.log(f"Total DBC messages: {len(dbc_messages)}, signals: {len(dbc_signals)}")

        self.log("--- Parsing Environment Variables ---")
        env_vars = self._parse_env_variables(resolved, inventory)
        self.log(f"Total env variables: {len(env_vars)}")

        self.log("--- Scanning CAPL for env↔signal bindings ---")
        capl_bindings = self._parse_capl_bindings(resolved, inventory)
        self.log(f"Explicit CAPL bindings: {len(capl_bindings)}")

        self.log("--- Extracting sysvar↔signal mappings from CAPL ---")
        capl_sysvar_mappings = self._parse_capl_sysvar_mappings(resolved, inventory)
        self.log(f"sysvar↔signal mappings from CAPL: {len(capl_sysvar_mappings)}")

        self.log("--- Building env↔signal linkage ---")
        env_links = self._build_env_signal_links(env_vars, dbc_signals, capl_bindings)
        self.log(f"Total env↔signal links: {len(env_links)}")

        self.log("--- Parsing CDD files ---")
        dids, did_fields = self._parse_cdds(resolved, inventory)
        self.log(f"Total DIDs: {len(dids)}, fields: {len(did_fields)}")

        self.log("=== Done ===")

        return {
            "references": resolved,
            "inventory": inventory,
            "sysvars": sysvars,
            "dbc_messages": dbc_messages,
            "dbc_signals": dbc_signals,
            "env_vars": env_vars,
            "capl_bindings": capl_bindings,
            "capl_sysvar_mappings": capl_sysvar_mappings,
            "env_links": env_links,
            "dids": dids,
            "did_fields": did_fields,
        }

    # -- format detection ---------------------------------------------------
    def _detect_format(self, cfg_path: Path) -> str:
        with cfg_path.open("rb") as f:
            head = f.read(4)
        if head[:4] == b"PK\x03\x04":
            return "zip"
        return "binary"

    # -- zipped cfg path ----------------------------------------------------
    def _inspect_zip(self, cfg_path: Path):
        self.log("Opening as zip archive...")
        refs = set()
        try:
            with zipfile.ZipFile(cfg_path) as z:
                for name in z.namelist():
                    self.log(f"  entry: {name}")
                    if name.lower().endswith((".xml", ".cfg", ".ini")):
                        try:
                            content = z.read(name).decode("utf-8", errors="ignore")
                        except Exception as e:
                            self.log(f"    (skip, read error: {e})")
                            continue
                        refs.update(self._scrape_paths(content))
        except zipfile.BadZipFile:
            self.log("BadZipFile — falling back to binary scrape")
            return self._inspect_binary(cfg_path)
        return sorted(refs)

    # -- binary cfg path ----------------------------------------------------
    def _inspect_binary(self, cfg_path: Path):
        self.log("Reading bytes for string extraction...")
        data = cfg_path.read_bytes()
        self.log(f"Loaded {len(data):,} bytes")

        self.log("Decoding as UTF-16LE (Vector's usual encoding)...")
        text_utf16 = data.decode("utf-16-le", errors="ignore")
        self.log("Decoding as Latin-1 (ASCII-embedded fallback)...")
        text_ascii = data.decode("latin-1", errors="ignore")

        refs = set()
        self.log("Scanning UTF-16 text for path patterns...")
        refs.update(self._scrape_paths(text_utf16))
        self.log(f"  UTF-16 hits so far: {len(refs)}")

        self.log("Scanning Latin-1 text for path patterns...")
        refs.update(self._scrape_paths(text_ascii))
        self.log(f"  total hits: {len(refs)}")

        return sorted(refs)

    def _scrape_paths(self, text: str):
        hits = set()
        for m in self._ABS_PATTERN.findall(text):
            hits.add(m.strip())
        for m in self._REL_PATTERN.findall(text):
            hits.add(m.strip())
        # Clean obvious junk: paths with control chars or absurd length
        cleaned = set()
        for h in hits:
            if len(h) > 400:
                continue
            if any(ord(c) < 32 for c in h):
                continue
            cleaned.add(h)
        return cleaned

    # -- path resolution ----------------------------------------------------
    def _resolve_references(self, cfg_dir: Path, refs):
        resolved = []
        for raw in refs:
            p = Path(raw)
            candidates = [p, cfg_dir / p, cfg_dir / p.name]
            # also try walking cfg_dir subfolders for just the filename
            found_path = None
            for c in candidates:
                try:
                    if c.exists() and c.is_file():
                        found_path = c.resolve()
                        break
                except OSError:
                    continue
            if found_path is None:
                # last resort: recursive search by basename (capped)
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

    # -- project tree walk --------------------------------------------------
    def _walk_project(self, cfg_dir: Path):
        self.log(f"Walking project folder: {cfg_dir}")
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
            self.log(f"Walk error: {e}")
        return inventory

    # -- summary ------------------------------------------------------------
    def _summarize(self, resolved, inventory):
        self.log("--- Summary by role (referenced) ---")
        by_role = {}
        for r in resolved:
            by_role.setdefault(r["role"], []).append(r)
        for role, items in sorted(by_role.items()):
            found = sum(1 for i in items if i["exists"])
            self.log(f"  {role:12s}: {len(items):4d} referenced, {found:4d} found on disk")

        self.log("--- Summary by role (project inventory) ---")
        inv_by_role = {}
        for i in inventory:
            inv_by_role.setdefault(i["role"], 0)
            inv_by_role[i["role"]] += 1
        for role, count in sorted(inv_by_role.items()):
            self.log(f"  {role:12s}: {count:4d} files present in project tree")

    # -- new parsers -------------------------------------------------------
    def _parse_vsysvars(self, resolved, inventory) -> list[dict]:
        """Parse .vsysvar files for system variables."""
        all_files = set()
        for r in resolved:
            if r["exists"]:
                all_files.add(r["resolved_path"])
        for i in inventory:
            all_files.add(i["path"])
        
        rows = []
        for file_path in sorted(all_files):
            p = Path(file_path)
            if p.suffix.lower() == ".vsysvar":
                try:
                    tree = ET.parse(p)
                    root = tree.getroot()
                    count = self._walk_vsysvar_namespace(root, "", p.name, rows)
                    self.log(f"  vsysvar: {p.name} -> {count} variables")
                except Exception as e:
                    self.log(f"  vsysvar: {p.name} -> ERROR: {e}")
        return rows

    def _walk_vsysvar_namespace(self, elem, current_ns, source_file, rows):
        count = 0
        for child in elem:
            if child.tag.lower() in ("namespace", "variable"):
                if child.tag.lower() == "namespace":
                    ns_name = child.get("name", child.get("Name", ""))
                    new_ns = f"{current_ns}::{ns_name}" if current_ns else ns_name
                    count += self._walk_vsysvar_namespace(child, new_ns, source_file, rows)
                else:  # variable
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

    def _parse_dbcs(self, resolved, inventory) -> tuple[list[dict], list[dict]]:
        """Parse .dbc files for messages and signals."""
        if not CANToolsAvailable:
            self.log("WARNING: cantools not available, skipping DBC parsing")
            return [], []
        
        all_files = set()
        for r in resolved:
            if r["exists"]:
                all_files.add(r["resolved_path"])
        for i in inventory:
            all_files.add(i["path"])
        
        messages_rows = []
        signals_rows = []
        for file_path in sorted(all_files):
            p = Path(file_path)
            if p.suffix.lower() == ".dbc":
                try:
                    db = cantools.database.load_file(p)
                    bus_role = self._classify_dbc_bus_role(p.name)
                    msg_count = 0
                    sig_count = 0
                    for msg in db.messages:
                        messages_rows.append({
                            "source_file": p.name,
                            "bus_role": bus_role,
                            "name": msg.name,
                            "frame_id_hex": f"0x{msg.frame_id:X}",
                            "dlc": msg.length,
                            "cycle_ms": getattr(msg, 'cycle_time', ""),
                            "senders": ", ".join(msg.senders) if msg.senders else "",
                            "comment": msg.comment or "",
                        })
                        msg_count += 1
                        for sig in msg.signals:
                            signals_rows.append({
                                "source_file": p.name,
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
                    self.log(f"  dbc: {p.name} ({bus_role}) -> {msg_count} msgs, {sig_count} signals")
                except Exception as e:
                    self.log(f"  dbc: {p.name} -> ERROR: {e}")
        return messages_rows, signals_rows

    def _parse_env_variables(self, resolved, inventory) -> list[dict]:
        """Parse environment variable definitions from DBC files."""
        EV_PATTERN = re.compile(
            r'^EV_\s+(?P<name>\w+)\s*:\s*(?P<dtype>\d+)\s+'
            r'\[(?P<min>[-\d\.]+)\|(?P<max>[-\d\.]+)\]\s*'
            r'"(?P<unit>[^"]*)"\s+(?P<init>[-\d\.]+)\s+'
            r'(?P<ev_id>\d+)\s+(?P<access>\w+)',
            re.MULTILINE,
        )
        CLASS_PATTERN = re.compile(r'BA_\s+"GenEnvVarClassName"\s+EV_\s+(\w+)\s+"([^"]*)"')

        all_files = set()
        for r in resolved:
            if r["exists"]:
                all_files.add(r["resolved_path"])
        for i in inventory:
            all_files.add(i["path"])

        rows = []
        for file_path in sorted(all_files):
            p = Path(file_path)
            if p.suffix.lower() == ".dbc":
                try:
                    text = p.read_text(encoding="latin-1", errors="ignore")
                    class_map = {}
                    for m in CLASS_PATTERN.finditer(text):
                        class_map[m.group(1)] = m.group(2)
                    count = 0
                    for m in EV_PATTERN.finditer(text):
                        rows.append({
                            "source_file": p.name,
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
                    self.log(f"  env: {p.name} -> {count} env variables")
                except Exception as e:
                    self.log(f"  env: {p.name} -> ERROR: {e}")
        return rows

    def _parse_capl_bindings(self, resolved, inventory) -> list[dict]:
        """Parse CAPL files using CaplParser to extract envVar -> signal bindings."""
        all_files = set()
        for r in resolved:
            if r["exists"] and r["extension"] in {"can", "cin"}:
                all_files.add(r["resolved_path"])
        for i in inventory:
            if i["extension"] in {"can", "cin"}:
                all_files.add(i["path"])

        rows = []
        for file_path in sorted(all_files):
            p = Path(file_path)
            if p.suffix.lower() not in {".can", ".cin"}:
                continue
            try:
                parser = CaplParser()
                parser.parse(p)
                count_by_type = {}
                for mapping in parser.mappings:
                    # Only collect envvar mappings for env_links tab
                    if not mapping["mapping_type"].startswith("envvar_"):
                        continue
                    
                    bus_type = mapping.get("bus_type", "LIN")
                    count_by_type[bus_type] = count_by_type.get(bus_type, 0) + 1
                    
                    rows.append({
                        "source_file": mapping["source_file"],
                        "env_var": mapping["sysvar_path"],
                        "signal": mapping["signal_name"],
                        "message_name": mapping.get("message_name", ""),
                        "bus_type": bus_type,
                        "mapping_type": mapping["mapping_type"],
                        "value_expr": mapping.get("value_expr", ""),
                    })
                
                if count_by_type:
                    type_str = "/".join(f"{k}:{v}" for k, v in sorted(count_by_type.items()))
                    self.log(f"  capl: {p.name} -> {sum(count_by_type.values())} env mappings ({type_str})")
            except Exception as e:
                self.log(f"  capl: {p.name} -> ERROR: {e}")
        return rows

    def _parse_capl_sysvar_mappings(self, resolved, inventory) -> list[dict]:
        """Parse CAPL files to extract sysvar -> signal mappings (VT-System wiring)."""
        all_files_canon = set()
        for r in resolved:
            if r["exists"] and r["extension"] in {"can", "cin"}:
                try:
                    all_files_canon.add(Path(r["resolved_path"]).resolve())
                except OSError:
                    pass
        for i in inventory:
            if i["extension"] in {"can", "cin"}:
                try:
                    all_files_canon.add(Path(i["path"]).resolve())
                except OSError:
                    pass

        rows = []
        for file_path_canon in sorted(all_files_canon):
            p = file_path_canon
            if p.suffix.lower() not in {".can", ".cin"}:
                continue
            try:
                parser = CaplParser()
                parser.parse(p)
                count = 0
                for mapping in parser.mappings:
                    # Collect sysvar mappings only
                    if not mapping["mapping_type"].startswith("sysvar_"):
                        continue
                    
                    rows.append({
                        "source_file": mapping["source_file"],
                        "sysvar": mapping["sysvar_path"],
                        "signal": mapping["signal_name"],
                        "message_name": mapping.get("message_name", ""),
                        "bus_type": mapping.get("bus_type", "LIN"),
                        "mapping_type": mapping["mapping_type"],
                        "value_expr": mapping.get("value_expr", ""),
                    })
                    count += 1
                
                if count:
                    self.log(f"  capl_sysvar: {p.name} -> {count} mappings")
            except Exception as e:
                self.log(f"  capl_sysvar: {p.name} -> ERROR: {e}")
        return rows

    def _build_env_signal_links(self, env_rows, dbc_signals, capl_bindings) -> list[dict]:
        """Build combined env variable to signal linkage table."""
        # explicit CAPL links first (with new field schema)
        links = []
        explicit_set = set()
        for row in capl_bindings:
            bus_type = row.get("bus_type", "LIN")
            link_type = "capl_" + bus_type.lower()
            links.append({
                "env_var": row["env_var"],
                "env_source": row["source_file"],
                "signal": row["signal"],
                "signal_message": row.get("message_name", ""),
                "signal_source": "",
                "bus_role": "",
                "bus_type": bus_type,
                "value_expr": row.get("value_expr", ""),
                "link_type": link_type,
                "confidence": "high",
            })
            explicit_set.add((row["env_var"].lower(), row["signal"].lower()))

        # prepare vehicle signals by normalized name
        vehicle_signals = []
        for sig in dbc_signals:
            if sig.get("bus_role") == "vehicle":
                vehicle_signals.append(sig)

        def normalize(name):
            original = name
            n = name
            for prefix in ("env_", "ENV_", "sim_", "SIM_", "e_"):
                if n.startswith(prefix):
                    n = n[len(prefix):]
                    break
            for suffix in ("_req", "_Request", "_D", "_P"):
                if n.endswith(suffix):
                    n = n[: -len(suffix)]
                    break
            return n.lower(), original

        env_linked = 0
        name_linked = 0
        for env in env_rows:
            env_name = env["name"]
            if any(env_name.lower() == env_key for env_key, _ in explicit_set):
                continue
            stripped_env, _ = normalize(env_name)
            matches = []
            for sig in vehicle_signals:
                stripped_sig, _ = normalize(sig["name"])
                if stripped_env == stripped_sig:
                    matches.append(sig)
            if not matches:
                continue
            if len(matches) == 1:
                sig = matches[0]
                links.append({
                    "env_var": env_name,
                    "env_source": env["source_file"],
                    "signal": sig["name"],
                    "signal_message": sig.get("message", ""),
                    "signal_source": sig["source_file"],
                    "bus_role": sig.get("bus_role", ""),
                    "bus_type": "",
                    "value_expr": "",
                    "link_type": "name_exact",
                    "confidence": "medium",
                })
                name_linked += 1
            else:
                for sig in matches:
                    links.append({
                        "env_var": env_name,
                        "env_source": env["source_file"],
                        "signal": sig["name"],
                        "signal_message": sig.get("message", ""),
                        "signal_source": sig["source_file"],
                        "bus_role": sig.get("bus_role", ""),
                        "bus_type": "",
                        "value_expr": "",
                        "link_type": "name_ambiguous",
                        "confidence": "low",
                    })
                name_linked += len(matches)

        linked_envs = {row["env_var"] for row in links}
        unlinked = len([env for env in env_rows if env["name"] not in linked_envs])
        self.log(f"env↔signal links: {len(capl_bindings)} from CAPL, {name_linked} by name match, {unlinked} env vars unlinked")
        return links

    def _classify_dbc_bus_role(self, filename: str) -> str:
        """Classify DBC bus role based on filename."""
        fname_lower = filename.lower()
        if "env" in fname_lower or "environment" in fname_lower:
            return "env"
        elif "debug" in fname_lower:
            return "debug"
        elif "error" in fname_lower:
            return "errors"
        elif "endurance" in fname_lower:
            return "endurance"
        else:
            return "vehicle"

    def _parse_cdds(self, resolved, inventory) -> tuple[list[dict], list[dict]]:
        """Parse .cdd files for DIDs and fields."""
        all_files = set()
        for r in resolved:
            if r["exists"]:
                all_files.add(r["resolved_path"])
        for i in inventory:
            all_files.add(i["path"])

        semantic_values = {
            "CURRENTDATA", "STOREDDATAREAD", "STOREDDATAWRITE",
            "IDENTIFICATION", "CONTROL", "MEMORY", "ROUTINE",
        }

        def find_service(node):
            for child in node:
                if self._local_tag(child) == "DIAGINST":
                    continue
                if self._local_tag(child) == "SERVICE":
                    return child
                found = find_service(child)
                if found is not None:
                    return found
            return None

        def find_staticvalue(node, depth=0):
            for child in node:
                if self._local_tag(child) == "DIAGINST":
                    continue
                if self._local_tag(child) == "STATICVALUE":
                    v = child.get("v", "")
                    try:
                        return int(v)
                    except (ValueError, TypeError):
                        return None
                if depth < 1:
                    found = find_staticvalue(child, depth + 1)
                    if found is not None:
                        return found
            return None

        def collect_dataobjs(node, in_service=False):
            if self._local_tag(node) == "SERVICE":
                in_service = True
            if self._local_tag(node) == "DATAOBJ" and not in_service:
                yield node
            for child in node:
                if self._local_tag(child) == "DIAGINST":
                    continue
                yield from collect_dataobjs(child, in_service)

        def text_from_n(node):
            n_elem = node.find("./n")
            if n_elem is None:
                return ""
            for tuv in n_elem.findall("./TUV"):
                if tuv.attrib.get("{http://www.w3.org/XML/1998/namespace}lang", "") == "en-US":
                    return tuv.text or ""
            return ""

        dids_rows = []
        did_fields_rows = []
        for file_path in sorted(all_files):
            p = Path(file_path)
            if p.suffix.lower() == ".cdd":
                try:
                    tree = ET.parse(p)
                    root = tree.getroot()
                    did_count = 0
                    field_count = 0
                    for diag in root.iter():
                        if self._local_tag(diag) != "DIAGINST":
                            continue
                        service = find_service(diag)
                        if service is None:
                            continue
                        semantic = service.findtext("./SEMANTIC", "") or ""
                        if semantic not in semantic_values:
                            continue
                        did_decimal = find_staticvalue(diag)
                        if did_decimal is None:
                            continue
                        did_hex = f"0x{did_decimal:04X}"
                        qual = diag.findtext("./QUAL", "") or ""
                        name_en = text_from_n(diag)
                        dids_rows.append({
                            "source_file": p.name,
                            "did_hex": did_hex,
                            "qual": qual,
                            "name": name_en,
                            "semantic": semantic,
                            "length_bytes": "",
                            "session_required": "",
                        })
                        did_count += 1
                        for simplecont in diag.findall(".//SIMPLECOMPCONT"):
                            for dataobj in collect_dataobjs(simplecont):
                                field_qual = dataobj.findtext("./QUAL", "") or ""
                                field_name = text_from_n(dataobj)
                                dtref = dataobj.attrib.get("dtref", "")
                                default_value = dataobj.attrib.get("v", "")
                                did_fields_rows.append({
                                    "source_file": p.name,
                                    "did_hex": did_hex,
                                    "field_qual": field_qual,
                                    "field_name": field_name,
                                    "dtref": dtref,
                                    "default_value": default_value,
                                })
                                field_count += 1
                    self.log(f"  cdd: {p.name} -> {did_count} DIDs, {field_count} fields")
                except Exception as e:
                    self.log(f"  cdd: {p.name} -> ERROR: {e}")
        return dids_rows, did_fields_rows

    def _local_tag(self, elem):
        """Strip namespace from XML tag."""
        return elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag

    def _extract_did_info(self, elem):
        """Extract DID info from element."""
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
            local = self._local_tag(child)
            if local.upper() in ("SHORT-NAME", "LONGNAME"):
                name = child.text or ""
            elif local.lower() in ("length", "byte-length", "bitlength"):
                try:
                    length = str(int(child.text or ""))
                except ValueError:
                    pass
        
        return did_hex, name, length

    def _extract_field_info(self, elem):
        """Extract field info from element."""
        field_name = elem.get("name", "")
        start_bit = elem.get("start-bit", "")
        length_bits = elem.get("bit-length", "")
        ftype = elem.get("type", "")
        return field_name, start_bit, length_bits, ftype


# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("CANoe cfg Inspector")
        self.geometry("1100x720")

        self.cfg_path = tk.StringVar()
        self.log_queue = queue.Queue()
        self.last_result = None

        self._build_ui()
        self.after(100, self._drain_log_queue)

    def _build_ui(self):
        # top bar
        top = ttk.Frame(self, padding=8)
        top.pack(fill="x")
        ttk.Label(top, text=".cfg file:").pack(side="left")
        ttk.Entry(top, textvariable=self.cfg_path, width=80).pack(side="left", padx=4)
        ttk.Button(top, text="Browse...", command=self._browse).pack(side="left")
        ttk.Button(top, text="Inspect", command=self._run_inspection).pack(side="left", padx=4)
        ttk.Button(top, text="Export CSV", command=self._export_csv).pack(side="left")
        ttk.Button(top, text="Clear", command=self._clear).pack(side="left", padx=4)

        # notebook with results + trace
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=8, pady=4)

        # References tab
        self.ref_tree = self._make_tree(nb, ("role", "exists", "basename", "extension", "resolved_path", "raw"))
        nb.add(self.ref_tree.master, text="References")

        # Inventory tab
        self.inv_tree = self._make_tree(nb, ("role", "extension", "basename", "size_bytes", "path"))
        nb.add(self.inv_tree.master, text="Project Inventory")

        # Sysvars tab
        self.sysvar_tree = self._make_tree(nb, (
            "source_file", "namespace", "name", "type", "unit", "min", "max", "default"
        ))
        nb.add(self.sysvar_tree.master, text="Sysvars")

        # DBC Signals tab
        self.dbc_tree = self._make_tree(nb, (
            "source_file", "bus_role", "message", "name", "start_bit", "length",
            "factor", "offset", "unit"
        ))
        nb.add(self.dbc_tree.master, text="DBC Signals")

        # DIDs tab
        self.did_tree = self._make_tree(nb, (
            "source_file", "did_hex", "name", "length_bytes"
        ))
        nb.add(self.did_tree.master, text="DIDs")

        # Env Links tab
        self.envlink_tree = self._make_tree(nb, (
            "env_var", "signal", "signal_message", "bus_role",
            "link_type", "confidence", "bus_type", "value_expr", "env_source", "signal_source"
        ))
        nb.add(self.envlink_tree.master, text="Env Links")

        # Trace tab
        trace_frame = ttk.Frame(nb)
        self.trace = tk.Text(trace_frame, wrap="none", font=("Consolas", 9))
        vs = ttk.Scrollbar(trace_frame, orient="vertical", command=self.trace.yview)
        self.trace.configure(yscrollcommand=vs.set)
        self.trace.pack(side="left", fill="both", expand=True)
        vs.pack(side="right", fill="y")
        nb.add(trace_frame, text="Trace Log")

        # status bar
        self.status = tk.StringVar(value="Ready.")
        ttk.Label(self, textvariable=self.status, relief="sunken", anchor="w").pack(fill="x", side="bottom")

    def _make_tree(self, parent, columns):
        frame = ttk.Frame(parent)
        tree = ttk.Treeview(frame, columns=columns, show="headings")
        for c in columns:
            tree.heading(c, text=c)
            tree.column(c, width=140, stretch=True)
        vs = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        hs = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=vs.set, xscrollcommand=hs.set)
        tree.grid(row=0, column=0, sticky="nsew")
        vs.grid(row=0, column=1, sticky="ns")
        hs.grid(row=1, column=0, sticky="ew")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        return tree

    # -- actions ------------------------------------------------------------
    def _browse(self):
        path = filedialog.askopenfilename(
            title="Select CANoe .cfg",
            filetypes=[("CANoe config", "*.cfg"), ("All files", "*.*")],
        )
        if path:
            self.cfg_path.set(path)

    def _run_inspection(self):
        path = self.cfg_path.get().strip()
        if not path:
            messagebox.showwarning("No file", "Pick a .cfg file first.")
            return
        self._clear_results()
        self.status.set("Inspecting...")
        threading.Thread(target=self._worker, args=(Path(path),), daemon=True).start()

    def _worker(self, path: Path):
        try:
            inspector = CfgInspector(log=self._log)
            result = inspector.inspect(path)
            self.last_result = result
            self.after(0, lambda: self._populate(result))
            self.after(0, lambda: self.status.set("Done."))
        except Exception as e:
            self._log(f"FATAL: {e}")
            self.after(0, lambda: self.status.set(f"Error: {e}"))

    def _populate(self, result):
        for r in result["references"]:
            self.ref_tree.insert("", "end", values=(
                r["role"], "YES" if r["exists"] else "NO",
                r["basename"], r["extension"],
                r["resolved_path"], r["raw"],
            ))
        for i in result["inventory"]:
            self.inv_tree.insert("", "end", values=(
                i["role"], i["extension"], i["basename"],
                f"{i['size_bytes']:,}", i["path"],
            ))

        for s in result.get("sysvars", []):
            self.sysvar_tree.insert("", "end", values=(
                s["source_file"], s["namespace"], s["name"], s["type"],
                s["unit"], s["min"], s["max"], s["default"]
            ))
        for s in result.get("dbc_signals", []):
            self.dbc_tree.insert("", "end", values=(
                s["source_file"], s["bus_role"], s["message"], s["name"],
                s["start_bit"], s["length"], s["factor"], s["offset"], s["unit"]
            ))
        for d in result.get("dids", []):
            self.did_tree.insert("", "end", values=(
                d["source_file"], d["did_hex"], d["name"], d["length_bytes"]
            ))
        for link in result.get("env_links", []):
            self.envlink_tree.insert("", "end", values=(
                link["env_var"], link["signal"], link["signal_message"],
                link["bus_role"], link["link_type"], link["confidence"],
                link.get("bus_type", ""), link.get("value_expr", ""),
                link["env_source"], link["signal_source"]
            ))

    def _export_csv(self):
        if not self.last_result:
            messagebox.showinfo("Nothing to export", "Run an inspection first.")
            return
        folder = filedialog.askdirectory(title="Choose export folder")
        if not folder:
            return
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        ref_csv = Path(folder) / f"cfg_references_{stamp}.csv"
        inv_csv = Path(folder) / f"cfg_inventory_{stamp}.csv"
        sysvar_csv = Path(folder) / f"sysvars_{stamp}.csv"
        dbc_messages_csv = Path(folder) / f"dbc_messages_{stamp}.csv"
        dbc_signals_csv = Path(folder) / f"dbc_signals_{stamp}.csv"
        dids_csv = Path(folder) / f"dids_{stamp}.csv"
        did_fields_csv = Path(folder) / f"did_fields_{stamp}.csv"
        env_vars_csv = Path(folder) / f"env_vars_{stamp}.csv"
        capl_bindings_csv = Path(folder) / f"capl_bindings_{stamp}.csv"
        capl_sysvar_mappings_csv = Path(folder) / f"capl_sysvar_mappings_{stamp}.csv"
        env_links_csv = Path(folder) / f"env_links_{stamp}.csv"
        self._write_csv(ref_csv, self.last_result["references"])
        self._write_csv(inv_csv, self.last_result["inventory"])
        self._write_csv(sysvar_csv, self.last_result.get("sysvars", []))
        self._write_csv(dbc_messages_csv, self.last_result.get("dbc_messages", []))
        self._write_csv(dbc_signals_csv, self.last_result.get("dbc_signals", []))
        self._write_csv(dids_csv, self.last_result.get("dids", []))
        self._write_csv(did_fields_csv, self.last_result.get("did_fields", []))
        self._write_csv(env_vars_csv, self.last_result.get("env_vars", []))
        self._write_csv(capl_bindings_csv, self.last_result.get("capl_bindings", []))
        self._write_csv(capl_sysvar_mappings_csv, self.last_result.get("capl_sysvar_mappings", []))
        self._write_csv(env_links_csv, self.last_result.get("env_links", []))
        self._log(f"Exported: {ref_csv}")
        self._log(f"Exported: {inv_csv}")
        self._log(f"Exported: {sysvar_csv}")
        self._log(f"Exported: {dbc_messages_csv}")
        self._log(f"Exported: {dbc_signals_csv}")
        self._log(f"Exported: {dids_csv}")
        self._log(f"Exported: {did_fields_csv}")
        self._log(f"Exported: {env_vars_csv}")
        self._log(f"Exported: {capl_bindings_csv}")
        self._log(f"Exported: {capl_sysvar_mappings_csv}")
        self._log(f"Exported: {env_links_csv}")
        messagebox.showinfo("Exported", f"Saved CSVs to:\n{folder}")

    def _write_csv(self, path, rows):
        if not rows:
            return
        with path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)

    def _clear(self):
        self._clear_results()
        self.trace.delete("1.0", "end")
        self.status.set("Ready.")

    def _clear_results(self):
        for t in (self.ref_tree, self.inv_tree, self.sysvar_tree, self.dbc_tree, self.did_tree, self.envlink_tree):
            for item in t.get_children():
                t.delete(item)

    # -- logging (thread-safe) ---------------------------------------------
    def _log(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_queue.put(f"[{ts}] {msg}\n")

    def _drain_log_queue(self):
        try:
            while True:
                line = self.log_queue.get_nowait()
                self.trace.insert("end", line)
                self.trace.see("end")
        except queue.Empty:
            pass
        self.after(100, self._drain_log_queue)


if __name__ == "__main__":
    App().mainloop()