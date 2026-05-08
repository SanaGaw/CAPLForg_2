"""Configuration scaffold generator for CAPL Pipeline V2.2.

Generates starter configurations from CANoe project files.
"""

from pathlib import Path
from typing import Dict, List, Optional, Any
import logging

logger = logging.getLogger(__name__)


class ConfigScaffold:
    """
    Generate starter configurations from CANoe project.

    Extracts signal information from DBC, LDF, and vsysvar files
    to create initial signal_aliases.yaml configurations.
    """

    def __init__(
        self,
        project_path: Path,
        output_dir: Optional[Path] = None
    ) -> None:
        self.project_path = project_path
        self.output_dir = output_dir or Path("config")

    def generate_from_canoe_project(self, cfg_path: Path) -> Dict[str, Any]:
        """
        Generate scaffold config from CANoe .cfg file.

        Args:
            cfg_path: Path to CANoe configuration file

        Returns:
            Dict with scaffold configuration data
        """
        from ..parsers.cfg_parser import CfgParser
        from ..parsers.dbc_parser import DbcParser
        from ..parsers.ldf_parser import LdfParser
        from ..parsers.vsysvar_parser import VsysvarParser

        parser = CfgParser(cfg_path)
        references = parser.extract_references()

        scaffold = {
            "version": "1.0",
            "source_cfg": str(cfg_path),
            "signals": [],
            "aliases": {},
            "missing_signals": []
        }

        # Parse DBC files
        for dbc_path_str in references.get('dbc', []):
            dbc_path = Path(dbc_path_str)
            if dbc_path.exists():
                dbc_parser = DbcParser(dbc_path)
                messages = dbc_parser.parse()
                for msg in messages.values():
                    for signal in msg.signals:
                        scaffold["signals"].append({
                            "name": signal.name,
                            "bus_type": "CAN",
                            "source": "dbc",
                            "message": msg.name,
                            "message_id": msg.id_hex,
                            "start_bit": signal.start_bit,
                            "length": signal.length,
                            "data_type": signal.value_type,
                            "factor": signal.factor,
                            "offset": signal.offset,
                            "unit": signal.unit
                        })

        # Parse LDF files
        for ldf_path_str in references.get('ldf', []):
            ldf_path = Path(ldf_path_str)
            if ldf_path.exists():
                ldf_parser = LdfParser(ldf_path)
                frames = ldf_parser.parse()
                for frame in frames.values():
                    for signal in frame.signals:
                        scaffold["signals"].append({
                            "name": signal.name,
                            "bus_type": "LIN",
                            "source": "ldf",
                            "frame": frame.name,
                            "frame_id": frame.id
                        })

        # Parse system variables
        for vsysvar_path_str in references.get('vsysvar', []):
            vsysvar_path = Path(vsysvar_path_str)
            if vsysvar_path.exists():
                vsysvar_parser = VsysvarParser(vsysvar_path)
                entries = vsysvar_parser.parse()
                for entry in entries:
                    scaffold["signals"].append({
                        "name": entry.name,
                        "bus_type": None,
                        "source": "vsysvar",
                        "sys_var_path": entry.sys_var_path,
                        "namespace": entry.namespace,
                        "data_type": entry.data_type
                    })

        logger.info(
            f"Generated scaffold from {cfg_path.name}: "
            f"{len(scaffold['signals'])} signals extracted"
        )
        return scaffold

    def write_scaffold_config(
        self,
        scaffold: Dict[str, Any],
        output_path: Optional[Path] = None
    ) -> Path:
        """
        Write scaffold configuration to YAML file.

        Args:
            scaffold: Scaffold data from generate_from_canoe_project
            output_path: Output file path

        Returns:
            Path to written file
        """
        import yaml

        output_path = output_path or self.output_dir / "scaffold_config.yaml"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w', encoding='utf-8') as f:
            yaml.dump(scaffold, f, default_flow_style=False, sort_keys=False)

        logger.info(f"Wrote scaffold config to {output_path}")
        return output_path

    def generate_signal_aliases_yaml(self, scaffold: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert scaffold to signal_aliases v1 format.

        Args:
            scaffold: Scaffold data

        Returns:
            signal_aliases v1 compatible dictionary
        """
        aliases = {}

        for signal in scaffold.get("signals", []):
            name = signal.get("name")
            if name:
                aliases[name] = {
                    "dbc_path": signal.get("message", name),
                    "bus_type": signal.get("bus_type"),
                    "confidence_source": "TEMPLATE"
                }

        return {
            "version": "1.0",
            "aliases": aliases
        }
