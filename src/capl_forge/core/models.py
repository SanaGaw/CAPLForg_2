"""Shared data models for CAPL Forge."""
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class ParserCapability:
    """Describes a parser's capability."""
    name: str
    file_extensions: list[str]
    description: str = ""
    is_optional: bool = False

@dataclass
class ParserWarning:
    """A non-fatal parsing warning."""
    source_file: str
    message: str
    line_number: Optional[int] = None
    category: str = "general"

@dataclass
class Issue:
    """A parsing or linking issue."""
    severity: str  # "error", "warning", "info"
    category: str
    message: str
    source_file: Optional[str] = None
    entity_name: Optional[str] = None
    resolution: Optional[str] = None
