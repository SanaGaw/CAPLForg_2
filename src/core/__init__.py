"""Core module for CAPL Pipeline V2.2.

This module contains the core functionality:
- Signal registry with SQLite-backed storage
- Cross-validation and confidence scoring
- Configuration building and gap detection
- Pattern analysis and matching
- Audit logging and performance profiling
"""

from .signal_registry import SignalRegistry, Signal
from .cross_validator import CrossValidator, ValidationReport
from .config_builder import ConfigBuilderOrchestrator, GapQuestion, GapResolution
from .pattern_matcher import PatternMatcher
from .pattern_analyzer import PatternAnalyzer, SequenceCandidate
from .audit_logger import AuditLogger
from .capl_fingerprinter import CaplStructuralFingerprinter
from .config_loader import ConfigLoader
from .batch_processor import BatchProcessor
from .performance import PerformanceProfiler, PerformanceReport

__all__ = [
    "SignalRegistry",
    "Signal",
    "CrossValidator",
    "ValidationReport",
    "ConfigBuilderOrchestrator",
    "GapQuestion",
    "GapResolution",
    "PatternMatcher",
    "PatternAnalyzer",
    "SequenceCandidate",
    "AuditLogger",
    "CaplStructuralFingerprinter",
    "ConfigLoader",
    "BatchProcessor",
    "PerformanceProfiler",
    "PerformanceReport",
]
