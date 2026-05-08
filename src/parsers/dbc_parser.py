"""CANdb++ .dbc file parser for CAPL Pipeline V2.2.

Parses DBC (CAN database) files to extract messages, signals, and their properties.
Supports standard DBC format used by Vector CANdb++ and compatible tools.
"""

from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, field
import re
import logging

logger = logging.getLogger(__name__)


@dataclass
class DbcSignal:
    """Represents a signal definition from DBC."""
    name: str
    start_bit: int
    length: int
    byte_order: str  # 'little_endian' (Intel) or 'big_endian' (Motorola)
    value_type: str  # 'unsigned' or 'signed'
    factor: float = 1.0
    offset: float = 0.0
    min_val: Optional[float] = None
    max_val: Optional[float] = None
    unit: Optional[str] = None
    receivers: List[str] = field(default_factory=list)
    comment: Optional[str] = None


@dataclass
class DbcMessage:
    """Represents a message/frame definition from DBC."""
    id_hex: str
    name: str
    dlc: int
    transmitter: Optional[str] = None
    signals: List[DbcSignal] = field(default_factory=list)
    comment: Optional[str] = None


class DbcParser:
    """
    Parse CANdb++ .dbc files.

    Handles standard DBC format including:
    - BIT_TIMING, NS_, CM_, BA_, BA_DEF_, BA_DEF_DEF_, VAL_, SIG_VALTYPE_
    - BS_, BU_, BO_, SG_, SG_DEF_
    """

    # Pattern for message definition: BO_ <id> <name>: <dlc> <transmitter>
    MESSAGE_PATTERN = re.compile(
        r'^BO_ (\w+) (\w+): (\d+) (\w+)$',
        re.MULTILINE
    )

    # Pattern for signal definition: SG_ <name> : <start_bit|startbit@byte_order value_type (factor, offset) [min max] [unit] <receivers>
    SIGNAL_PATTERN = re.compile(
        r'^\s*SG_ (\w+) : (\d+)\|(\d+)@([12]) ([+|-]) \(([^,]+),([^)]+)\) \[([^\]]+)\] "([^"]*)" ([^;]*);?$',
        re.MULTILINE
    )

    # Simpler signal pattern for cases without complex format
    SIGNAL_SIMPLE = re.compile(
        r'^\s*SG_ (\w+)\s*:?\s*(\d+)\s*@?\s*([12])?\s*([+-])?\s*.*;',
        re.MULTILINE
    )

    # Pattern for value definition (signal names map to text values)
    VALUE_PATTERN = re.compile(
        r'^VAL_ (\w+) (\w+) "([^"]+)" ?(.*);$',
        re.MULTILINE
    )

    # Pattern for comments
    COMMENT_PATTERN = re.compile(
        r'^CM_ (?:BO_|SG_|BU_)\s+(\w+)\s*(?:\w+\s*)? "([^"]+)"',
        re.MULTILINE
    )

    def __init__(self, dbc_path: Path) -> None:
        self.dbc_path = dbc_path
        self._content: Optional[str] = None
        self.messages: Dict[str, DbcMessage] = {}
        self.signals_by_name: Dict[str, DbcSignal] = {}

    def _read_content(self) -> str:
        """Read and cache DBC file content."""
        if self._content is None:
            self._content = self.dbc_path.read_text(encoding='utf-8', errors='replace')
        return self._content

    def parse(self) -> Dict[str, DbcMessage]:
        """
        Parse DBC file and return messages keyed by message ID.

        Returns:
            Dict mapping hex IDs (e.g., '0x100') to DbcMessage objects
        """
        content = self._read_content()
        self.messages = {}
        self.signals_by_name = {}

        # Find all messages first
        for match in self.MESSAGE_PATTERN.finditer(content):
            msg_id = int(match.group(1))
            msg_name = match.group(2)
            dlc = int(match.group(3))
            transmitter = match.group(4) if match.group(4) != '' else None

            self.messages[msg_name] = DbcMessage(
                id_hex=f"0x{msg_id:X}" if msg_id >= 0 else f"0x{msg_id & 0xFFFFFFFF:X}",
                name=msg_name,
                dlc=dlc,
                transmitter=transmitter
            )

        # Parse signals for each message
        lines = content.split('\n')
        current_msg = None

        for line in lines:
            line = line.strip()

            # Message start
            if line.startswith('BO_ '):
                msg_match = re.match(r'^BO_ \w+ (\w+):', line)
                if msg_match:
                    current_msg = msg_match.group(1)

            # Signal definition
            elif line.startswith('SG_ ') and current_msg:
                signal = self._parse_signal(line, current_msg)
                if signal and current_msg in self.messages:
                    self.messages[current_msg].signals.append(signal)
                    self.signals_by_name[signal.name] = signal

        logger.info(
            f"Parsed {self.dbc_path.name}: "
            f"{len(self.messages)} messages, "
            f"{len(self.signals_by_name)} signals"
        )
        return self.messages

    def _parse_signal(self, line: str, msg_name: str) -> Optional[DbcSignal]:
        """Parse a signal line from DBC format."""
        # Try to match the full format first
        # SG_ SignalName : startBit|startBit@ByteOrder valueType (factor, offset) [min|max] "unit" receivers;

        # Pattern for standard DBC format
        pattern = re.compile(
            r'SG_\s+(\w+)\s*:?\s*(\d+)\s*@([12])\s*([+-])\s*\(([^,]+),([^)]+)\)\s*\[([^\]]+)\]\s*"([^"]*)"\s*([^;]*);'
        )

        match = pattern.search(line)
        if match:
            name = match.group(1)
            bit_position = int(match.group(2))
            byte_order = match.group(3)
            sign = match.group(4)
            factor = float(match.group(5))
            offset = float(match.group(6))
            range_str = match.group(7)
            unit = match.group(8)
            receivers = match.group(9).strip()

            # Parse range [min|max]
            range_match = re.match(r'([^\|]+)\|([^\|]+)', range_str)
            min_val, max_val = None, None
            if range_match:
                min_val = float(range_match.group(1))
                max_val = float(range_match.group(2))

            # Parse receivers
            receiver_list = receivers.split() if receivers else []

            return DbcSignal(
                name=name,
                start_bit=bit_position,
                length=8,  # Will be updated if we have length info
                byte_order='big_endian' if byte_order == '2' else 'little_endian',
                value_type='signed' if sign == '-' else 'unsigned',
                factor=factor,
                offset=offset,
                min_val=min_val,
                max_val=max_val,
                unit=unit if unit else None,
                receivers=receiver_list
            )

        # Fallback: simple parsing
        simple = re.search(r'SG_\s+(\w+)', line)
        if simple:
            return DbcSignal(
                name=simple.group(1),
                start_bit=0,
                length=1,
                byte_order='little_endian',
                value_type='unsigned'
            )

        return None

    def get_signal(self, name: str) -> Optional[DbcSignal]:
        """Get a signal by name."""
        if not self.signals_by_name:
            self.parse()
        return self.signals_by_name.get(name)

    def get_message(self, name: str) -> Optional[DbcMessage]:
        """Get a message by name."""
        if not self.messages:
            self.parse()
        return self.messages.get(name)

    def get_all_signals(self) -> List[DbcSignal]:
        """Get all signals from all messages."""
        if not self.signals_by_name:
            self.parse()
        return list(self.signals_by_name.values())
