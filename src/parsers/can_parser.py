"""CANoe .can file content parser for CAPL Pipeline V2.2.

Parses .can file CONTENTS to extract signal-to-environment-variable mappings,
sysvar references, VTS parameter usage, and include dependencies.

This is the PRIMARY source for populating Signal.env_var_name and
Signal.sys_var_path in the SignalRegistry.
"""

from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
import re
import logging

logger = logging.getLogger(__name__)


@dataclass
class CanFileExtract:
    """Structured extraction from a single .can file."""
    filepath: Path
    # Signal references found in CAPL code
    sysvar_refs: List[str] = field(default_factory=list)       # ["sysvar::Lighting::LF_DRL_Cmd", ...]
    signal_refs: List[str] = field(default_factory=list)       # ["BCM_DoorLock", "DoorLock_FL_Status", ...]
    envvar_refs: List[str] = field(default_factory=list)       # ["EnvLF_DRL_Cmd", "EnvDoorLock_FL", ...]
    # Mapped pairs: signal name -> environment variable / sysvar path
    signal_to_envvar: Dict[str, str] = field(default_factory=dict)    # {"DoorLock_FL": "EnvDoorLock_FL"}
    signal_to_sysvar: Dict[str, str] = field(default_factory=dict)    # {"LF_DRL_Cmd": "sysvar::Lighting::LF_DRL_Cmd"}
    # VTS parameter usage
    vts_usage: Dict[str, List[str]] = field(default_factory=dict)     # {"DoorLock_FL": ["avg", "pmwdc"]}
    # Include dependencies
    includes: List[str] = field(default_factory=list)                  # ["helpers.cin", "constants.cin"]
    # on-handler envVar/sysvar bindings
    on_envvar_handlers: List[Tuple[str, str]] = field(default_factory=list)  # [("EnvDoorLock_FL", "on_envVar_EnvDoorLock_FL")]
    on_sysvar_handlers: List[Tuple[str, str]] = field(default_factory=list)  # [("sysvar::Lighting::LF_DRL_Cmd", "on_sysvar_LF_DRL_Cmd")]


class CanParser:
    """
    Parse .can file CONTENTS to extract signal-to-environment-variable mappings,
    sysvar references, VTS parameter usage, and include dependencies.
    """

    # Pattern: @sysvar::Namespace::SubNamespace::VarName
    SYSVAR_PATTERN = re.compile(
        r'@sysvar::([A-Za-z0-9_:]+)',
        re.MULTILINE
    )

    # Pattern: $SignalName (CAN signal reference)
    SIGNAL_PATTERN = re.compile(
        r'\$([A-Za-z0-9_]+)',
        re.MULTILINE
    )

    # Pattern: Environment variable read/write via getValue/putValue
    ENVVAR_GET_PATTERN = re.compile(
        r'getValue\s*\(\s*(?:EnvVariable\s*\?\s*)?["\']?([A-Za-z0-9_]+)["\']?\s*\)',
        re.MULTILINE
    )
    ENVVAR_PUT_PATTERN = re.compile(
        r'putValue\s*\(\s*(?:EnvVariable\s*\?\s*)?["\']?([A-Za-z0-9_]+)["\']?\s*,',
        re.MULTILINE
    )

    # Pattern: on envVar handler binding
    ON_ENVVAR_PATTERN = re.compile(
        r'^on\s+envVar\s+([A-Za-z0-9_]+)\s*\{?',
        re.MULTILINE
    )

    # Pattern: on sysvar handler binding
    ON_SYSVAR_PATTERN = re.compile(
        r'^on\s+sysvar\s+([A-Za-z0-9_:]+)\s*\{?',
        re.MULTILINE
    )

    # Pattern: VTS parameter usage — @sysvar::...::avg, @sysvar::...::pmwdc, etc.
    VTS_PARAM_PATTERN = re.compile(
        r'@sysvar::([A-Za-z0-9_:]+)::(avg|pmwdc|freq|min|max)',
        re.MULTILINE
    )

    # Pattern: Direct assignment linking signal to env var
    # e.g., putValue(EnvDoorLock_FL, $DoorLock_FL_Status);
    SIGNAL_ENVVAR_ASSIGN = re.compile(
        r'putValue\s*\(\s*([A-Za-z0-9_]+)\s*,\s*\$([A-Za-z0-9_]+)\s*\)',
        re.MULTILINE
    )

    # Pattern: #include directive
    INCLUDE_PATTERN = re.compile(
        r'#include\s+["\']([^"\']+)["\']',
        re.MULTILINE
    )

    def __init__(self, can_path: Path) -> None:
        self.can_path = can_path
        self._content: Optional[str] = None

    def _read_content(self) -> str:
        """Read and cache .can file content."""
        if self._content is None:
            self._content = self.can_path.read_text(encoding='utf-8', errors='replace')
        return self._content

    def parse(self) -> CanFileExtract:
        """
        Full parse of .can file contents.
        Returns CanFileExtract with all extracted mappings and references.
        """
        content = self._read_content()
        extract = CanFileExtract(filepath=self.can_path)

        # 1. Extract @sysvar:: references
        extract.sysvar_refs = list(set(self.SYSVAR_PATTERN.findall(content)))

        # 2. Extract $Signal references
        extract.signal_refs = list(set(self.SIGNAL_PATTERN.findall(content)))

        # 3. Extract env var usage (getValue/putValue)
        envvar_gets = self.ENVVAR_GET_PATTERN.findall(content)
        envvar_puts = self.ENVVAR_PUT_PATTERN.findall(content)
        extract.envvar_refs = list(set(envvar_gets + envvar_puts))

        # 4. Extract signal→env_var direct assignments
        for env_var, signal in self.SIGNAL_ENVVAR_ASSIGN.findall(content):
            extract.signal_to_envvar[signal] = env_var

        # 5. Build signal→sysvar mapping from @sysvar references
        for sysvar_path in extract.sysvar_refs:
            # Extract the leaf name as potential signal name
            # e.g., "sysvar::Lighting::LF_DRL_Cmd" -> "LF_DRL_Cmd"
            parts = sysvar_path.split('::')
            leaf_name = parts[-1] if parts else sysvar_path
            extract.signal_to_sysvar[leaf_name] = f"sysvar::{sysvar_path}"

        # 6. Extract VTS parameter usage
        for signal_path, param in self.VTS_PARAM_PATTERN.findall(content):
            if signal_path not in extract.vts_usage:
                extract.vts_usage[signal_path] = []
            if param not in extract.vts_usage[signal_path]:
                extract.vts_usage[signal_path].append(param)

        # 7. Extract on-handler bindings
        for env_var in self.ON_ENVVAR_PATTERN.findall(content):
            handler_name = f"on_envVar_{env_var}"
            extract.on_envvar_handlers.append((env_var, handler_name))

        for sysvar_path in self.ON_SYSVAR_PATTERN.findall(content):
            leaf = sysvar_path.split('::')[-1]
            handler_name = f"on_sysvar_{leaf}"
            extract.on_sysvar_handlers.append((sysvar_path, handler_name))

        # 8. Extract includes
        extract.includes = self.INCLUDE_PATTERN.findall(content)

        logger.info(
            f"Parsed {self.can_path.name}: "
            f"{len(extract.signal_refs)} signals, "
            f"{len(extract.envvar_refs)} env vars, "
            f"{len(extract.sysvar_refs)} sysvars, "
            f"{len(extract.signal_to_envvar)} signal→env mappings, "
            f"{len(extract.vts_usage)} VTS params"
        )
        return extract

    @staticmethod
    def parse_can_directory(can_dir: Path) -> Dict[str, CanFileExtract]:
        """
        Parse all .can files in a directory (typically the conf/ folder).
        Returns: {filename: CanFileExtract}
        """
        results = {}
        for can_file in can_dir.glob("**/*.can"):
            parser = CanParser(can_file)
            results[can_file.name] = parser.parse()
        return results
