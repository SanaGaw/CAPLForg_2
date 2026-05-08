"""LIN Description Format parser for CAPL Pipeline V2.2.

Parses LDF (LIN Description Format) files used to describe LIN bus configurations.
Supports standard LIN 2.x and newer formats.
"""

from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, field
import re
import logging

logger = logging.getLogger(__name__)


@dataclass
class LdfSignal:
    """Represents a signal in LIN frame."""
    name: str
    start_bit: int
    length: int
    init_value: Optional[str] = None


@dataclass
class LdfFrame:
    """Represents a LIN frame definition."""
    name: str
    id: int
    size: int  # In bytes
    publisher: Optional[str] = None
    subscriber: Optional[str] = None
    signals: List[LdfSignal] = field(default_factory=list)


@dataclass
class LdfNode:
    """Represents a LIN node (master or slave)."""
    name: str
    type: str  # 'master' or 'slave'
    config: Optional[str] = None


class LdfParser:
    """
    Parse LIN Description Format files.

    Handles:
    - Node definitions (master/slave)
    - Frame definitions
    - Signal definitions
    - Schedule tables
    - Diagnostic frames
    """

    # Section markers
    NODES_SECTION = re.compile(r'^nodes\s*$', re.MULTILINE | re.IGNORECASE)
    CHANNELS_SECTION = re.compile(r'^channels\s*$', re.MULTILINE | re.IGNORECASE)
    FRAMES_SECTION = re.compile(r'^frames\s*$', re.MULTILINE | re.IGNORECASE)
    SIGNALS_SECTION = re.compile(r'^signals\s*$', re.MULTILINE | re.IGNORECASE)

    # Node definition: node_name [master | slave]
    NODE_PATTERN = re.compile(
        r'^(\w+)\s+(?:node|configuration)\s*:\s*(master|slave)',
        re.MULTILINE | re.IGNORECASE
    )

    # Frame definition: frame_name frame_id frame_size [publisher subscriber]
    FRAME_PATTERN = re.compile(
        r'^(\w+)\s+(\d+)\s+(\d+)\s*(?:(\w+)\s+(\w+))?',
        re.MULTILINE | re.IGNORECASE
    )

    # Signal definition: signal_name : start_bit, length [init_value]
    SIGNAL_PATTERN = re.compile(
        r'^(\w+)\s*:\s*(\d+)\s*,\s*(\d+)(?:\s*,\s*(\w+))?',
        re.MULTILINE | re.IGNORECASE
    )

    # LIN 2.x format: frame_name frame_id frame_size [sender receiver]
    FRAME_LIN2 = re.compile(
        r'^(\w+)\s+(\d+)\s+(\d+)\s*(?:(\w+))?',
        re.MULTILINE | re.IGNORECASE
    )

    def __init__(self, ldf_path: Path) -> None:
        self.ldf_path = ldf_path
        self._content: Optional[str] = None
        self.nodes: Dict[str, LdfNode] = {}
        self.frames: Dict[str, LdfFrame] = {}
        self.signals: Dict[str, LdfSignal] = {}

    def _read_content(self) -> str:
        """Read and cache LDF file content."""
        if self._content is None:
            self._content = self.ldf_path.read_text(encoding='utf-8', errors='replace')
        return self._content

    def parse(self) -> Dict[str, LdfFrame]:
        """
        Parse LDF file and return frames keyed by name.

        Returns:
            Dict mapping frame names to LdfFrame objects
        """
        content = self._read_content()
        self.nodes = {}
        self.frames = {}
        self.signals = {}

        current_section = None
        current_frame = None
        lines = content.split('\n')

        for line in lines:
            line = line.strip()
            line_lower = line.lower()

            # Detect sections
            if 'nodes' in line_lower and '=' not in line:
                current_section = 'nodes'
                continue
            elif 'frames' in line_lower and '=' not in line:
                current_section = 'frames'
                continue
            elif 'signals' in line_lower and '=' not in line:
                current_section = 'signals'
                continue

            # Parse based on section
            if current_section == 'nodes':
                node_match = self.NODE_PATTERN.search(line)
                if node_match:
                    self.nodes[node_match.group(1)] = LdfNode(
                        name=node_match.group(1),
                        type=node_match.group(2)
                    )

            elif current_section == 'frames':
                frame_match = self.FRAME_PATTERN.search(line)
                if not frame_match:
                    frame_match = self.FRAME_LIN2.search(line)

                if frame_match:
                    groups = frame_match.groups()
                    frame_name = groups[0]
                    frame_id = int(groups[1])
                    frame_size = int(groups[2])

                    self.frames[frame_name] = LdfFrame(
                        name=frame_name,
                        id=frame_id,
                        size=frame_size
                    )
                    current_frame = frame_name

            elif current_section == 'signals' and current_frame:
                signal_match = self.SIGNAL_PATTERN.search(line)
                if signal_match:
                    sig_name = signal_match.group(1)
                    sig_start = int(signal_match.group(2))
                    sig_len = int(signal_match.group(3))
                    init_val = signal_match.group(4)

                    signal = LdfSignal(
                        name=sig_name,
                        start_bit=sig_start,
                        length=sig_len,
                        init_value=init_val
                    )
                    self.signals[sig_name] = signal

                    if current_frame and current_frame in self.frames:
                        self.frames[current_frame].signals.append(signal)

        logger.info(
            f"Parsed {self.ldf_path.name}: "
            f"{len(self.nodes)} nodes, "
            f"{len(self.frames)} frames, "
            f"{len(self.signals)} signals"
        )
        return self.frames

    def get_frame(self, name: str) -> Optional[LdfFrame]:
        """Get a frame by name."""
        if not self.frames:
            self.parse()
        return self.frames.get(name)

    def get_all_signals(self) -> List[LdfSignal]:
        """Get all signals from all frames."""
        if not self.signals:
            self.parse()
        return list(self.signals.values())
