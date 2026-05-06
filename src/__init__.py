"""CAPL Pipeline V2.2

CANoe CAPL Test Case Generation Pipeline.

A deterministic-first, explainable system for generating CAPL test cases
from Excel test plans with multi-source signal validation.

Core Philosophy:
- Deterministic-first, explainable-always
- GUI-only for end-users
- LLM bounded to config/chat
- Zero probabilistic generation
"""

__version__ = "2.2.0"

from . import parsers
from . import core
from . import capl
from . import llm
from . import web
from . import cli
from . import compliance

__all__ = [
    "parsers",
    "core",
    "capl",
    "llm",
    "web",
    "cli",
    "compliance",
]
