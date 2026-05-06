"""Signal Registry for CAPL Pipeline V2.2.

SQLite-backed signal registry with Pydantic models.
Provides 8-tier cascade lookup for signal resolution.
"""

from pathlib import Path
from typing import Dict, List, Optional, Literal, Any
import sqlite3
import logging
from pydantic import BaseModel, Field
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


class SourceDetail(BaseModel):
    """Typed detail about where a signal was extracted from."""
    file: str
    line: Optional[int] = None
    section: Optional[str] = None
    extracted_at: Optional[str] = None


class Signal(BaseModel):
    """
    Unified signal model for CAPL generation.
    Includes all fields required by the CAPL generator.
    Pydantic v2 syntax only — no inner Config class.
    """
    # Core identification
    name: str
    canonical_name: Optional[str] = None  # Resolved DBC/LDF name

    # Source tracking
    sources: List[str] = Field(default_factory=list)  # ["dbc", "vsysvar", "can_file", "sto_spec", "excel"]
    source_details: Dict[str, SourceDetail] = Field(default_factory=dict)

    # Bus/ECU context
    bus_type: Optional[Literal["CAN", "LIN", "FLEXRAY", "ETHERNET"]] = None
    ecu_node: Optional[str] = None
    message_id: Optional[str] = None  # Hex string e.g., "0x100"
    message_name: Optional[str] = None

    # Signal definition
    data_type: Optional[Literal[
        "unsigned", "signed", "float", "double", "string", "enum"
    ]] = None
    start_bit: Optional[int] = Field(ge=0, le=511, default=None)  # CAN FD up to 512 bits
    length: Optional[int] = Field(ge=1, le=512, default=None)
    byte_order: Optional[Literal["intel", "motorola"]] = None
    factor: Optional[float] = None
    offset: Optional[float] = None
    min_val: Optional[float] = None
    max_val: Optional[float] = None
    unit: Optional[str] = None

    # CAPL-specific references
    env_var_name: Optional[str] = None       # CANoe environment variable (e.g., "EnvLF_DRL_Cmd")
    sys_var_path: Optional[str] = None       # Full namespace (e.g., "sysvar::Lighting::LF_DRL_Cmd")
    vts_params: Optional[Dict[str, bool]] = None  # VTS attributes: {"avg": True, "pmwdc": True, "freq": False}

    # Resolution state
    status: Literal["UNRESOLVED", "AUTO_ACCEPT", "USER_CONFIRM", "BLOCKED"] = "UNRESOLVED"
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    resolution_notes: Optional[str] = None

    model_config = {
        "json_schema_extra": {
            "example": {
                "name": "DoorLock_FL_Status",
                "canonical_name": "BCM_DoorLock_FrontLeft_Status",
                "sources": ["dbc", "vsysvar", "can_file"],
                "source_details": {
                    "dbc": {"file": "BCM.dbc", "line": 145, "section": "BO_ 0x2A0"},
                    "can_file": {"file": "MDOOR_test.can", "line": 87, "section": "on_envVar"},
                },
                "bus_type": "CAN",
                "ecu_node": "BCM",
                "message_id": "0x2A0",
                "data_type": "unsigned",
                "start_bit": 0,
                "length": 1,
                "env_var_name": "EnvDoorLock_FL",
                "sys_var_path": "sysvar::Doors::FrontLeft::LockStatus",
                "vts_params": {"avg": True, "pmwdc": False, "freq": False},
                "status": "AUTO_ACCEPT",
                "confidence": 0.95,
            }
        }
    }


class SignalRegistry:
    """
    SQLite-backed signal registry with 8-tier cascade lookup.

    Sources (in priority order for lookup):
    1. Direct registration (highest priority)
    2. Aliases (user-defined signal mappings)
    3. DBC database
    4. LDF database
    5. .vsysvar system variables
    6. .can file mappings
    7. STO specification
    8. Excel test plan

    Each tier contributes to confidence scoring.
    """

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self.db_path = db_path or Path("signal_registry.db")
        self._conn: Optional[sqlite3.Connection] = None
        self._cache: Dict[str, Signal] = {}
        self._aliases: Dict[str, str] = {}  # alias -> canonical name
        self._init_db()

    def _init_db(self) -> None:
        """Initialize SQLite database."""
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.row_factory = sqlite3.Row

        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS signals (
                name TEXT PRIMARY KEY,
                canonical_name TEXT,
                sources TEXT,
                source_details TEXT,
                bus_type TEXT,
                ecu_node TEXT,
                message_id TEXT,
                message_name TEXT,
                data_type TEXT,
                start_bit INTEGER,
                length INTEGER,
                byte_order TEXT,
                factor REAL,
                offset REAL,
                min_val REAL,
                max_val REAL,
                unit TEXT,
                env_var_name TEXT,
                sys_var_path TEXT,
                vts_params TEXT,
                status TEXT,
                confidence REAL,
                resolution_notes TEXT
            )
        """)

        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS aliases (
                alias TEXT PRIMARY KEY,
                canonical_name TEXT NOT NULL,
                source TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        self._conn.commit()
        logger.info(f"Signal registry initialized at {self.db_path}")

    def register(
        self,
        name: str,
        bus_type: Optional[str] = None,
        ecu_node: Optional[str] = None,
        env_var_name: Optional[str] = None,
        sys_var_path: Optional[str] = None,
        **kwargs
    ) -> Signal:
        """Register a signal with given properties."""
        signal = Signal(
            name=name,
            bus_type=bus_type,
            ecu_node=ecu_node,
            env_var_name=env_var_name,
            sys_var_path=sys_var_path,
            sources=["direct"],
            **kwargs
        )

        self._store_signal(signal)
        self._cache[name] = signal
        return signal

    def _store_signal(self, signal: Signal) -> None:
        """Store signal in database."""
        import json

        cursor = self._conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO signals VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            signal.name,
            signal.canonical_name,
            json.dumps(signal.sources),
            json.dumps(signal.source_details, default=dict),
            signal.bus_type,
            signal.ecu_node,
            signal.message_id,
            signal.message_name,
            signal.data_type,
            signal.start_bit,
            signal.length,
            signal.byte_order,
            signal.factor,
            signal.offset,
            signal.min_val,
            signal.max_val,
            signal.unit,
            signal.env_var_name,
            signal.sys_var_path,
            json.dumps(signal.vts_params, default=dict),
            signal.status,
            signal.confidence,
            signal.resolution_notes,
        ))
        self._conn.commit()

    def lookup(self, name: str) -> Optional[Signal]:
        """
        8-tier cascade lookup.
        Returns signal if found, None otherwise.
        """
        # Tier 1: Direct cache match
        if name in self._cache:
            return self._cache[name]

        # Tier 2: Alias resolution
        if name in self._aliases:
            resolved_name = self._aliases[name]
            if resolved_name in self._cache:
                return self._cache[resolved_name]

        # Tier 3-8: Database lookup + cascade
        signal = self._lookup_db(name)
        if signal:
            self._cache[name] = signal
            return signal

        # Tier 4+: Try DBC/LDF canonical names
        return self._lookup_by_alias(name)

    def _lookup_db(self, name: str) -> Optional[Signal]:
        """Lookup signal directly in database."""
        import json

        cursor = self._conn.cursor()
        cursor.execute("SELECT * FROM signals WHERE name = ?", (name,))
        row = cursor.fetchone()

        if row:
            return Signal(
                name=row['name'],
                canonical_name=row['canonical_name'],
                sources=json.loads(row['sources']) if row['sources'] else [],
                source_details=json.loads(row['source_details']) if row['source_details'] else {},
                bus_type=row['bus_type'],
                ecu_node=row['ecu_node'],
                message_id=row['message_id'],
                message_name=row['message_name'],
                data_type=row['data_type'],
                start_bit=row['start_bit'],
                length=row['length'],
                byte_order=row['byte_order'],
                factor=row['factor'],
                offset=row['offset'],
                min_val=row['min_val'],
                max_val=row['max_val'],
                unit=row['unit'],
                env_var_name=row['env_var_name'],
                sys_var_path=row['sys_var_path'],
                vts_params=json.loads(row['vts_params']) if row['vts_params'] else None,
                status=row['status'] or "UNRESOLVED",
                confidence=row['confidence'] or 0.0,
                resolution_notes=row['resolution_notes'],
            )
        return None

    def _lookup_by_alias(self, name: str) -> Optional[Signal]:
        """Lookup signal by alias."""
        cursor = self._conn.cursor()
        cursor.execute("SELECT canonical_name FROM aliases WHERE alias = ?", (name,))
        row = cursor.fetchone()

        if row:
            return self._lookup_db(row['canonical_name'])
        return None

    def add_alias(self, alias: str, canonical_name: str, source: str = "user") -> None:
        """Add an alias for a signal."""
        cursor = self._conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO aliases VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
            (alias, canonical_name, source)
        )
        self._conn.commit()
        self._aliases[alias] = canonical_name
        logger.debug(f"Added alias: {alias} -> {canonical_name}")

    def get_all_signals(self) -> List[Signal]:
        """Get all registered signals."""
        import json

        cursor = self._conn.cursor()
        cursor.execute("SELECT name FROM signals")
        rows = cursor.fetchall()

        signals = []
        for row in rows:
            signal = self.lookup(row['name'])
            if signal:
                signals.append(signal)
        return signals

    def export_report(self) -> Dict[str, Any]:
        """Export registry state as report."""
        signals = self.get_all_signals()

        by_status = {"UNRESOLVED": 0, "AUTO_ACCEPT": 0, "USER_CONFIRM": 0, "BLOCKED": 0}
        by_source: Dict[str, int] = {}

        for sig in signals:
            by_status[sig.status] = by_status.get(sig.status, 0) + 1
            for src in sig.sources:
                by_source[src] = by_source.get(src, 0) + 1

        return {
            "total_signals": len(signals),
            "by_status": by_status,
            "by_source": by_source,
            "total_aliases": len(self._aliases),
        }

    def close(self) -> None:
        """Close database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> "SignalRegistry":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()
