"""Performance profiler for CAPL Pipeline V2.2.

Monitors execution performance and enforces memory limits.
"""

from pathlib import Path
from typing import Dict, Optional, Any
from dataclasses import dataclass, field
import time
import logging
import os
import psutil

logger = logging.getLogger(__name__)


@dataclass
class PerformanceReport:
    """Structured performance profiling report."""
    total_duration_s: float
    peak_memory_mb: float
    cache_hit_rate: float
    steps_per_second: float
    phase_durations: Dict[str, float] = field(default_factory=dict)
    memory_snapshots: Dict[str, float] = field(default_factory=dict)
    within_targets: bool = True


class PerformanceProfiler:
    """
    Monitors execution performance and enforces memory limits.
    Graceful abort if limits exceeded, with partial audit export.
    """

    def __init__(self, max_memory_mb: Optional[int] = None) -> None:
        self.max_memory_mb = max_memory_mb or int(
            os.getenv("MAX_MEMORY_MB", "2048")
        )
        self._start_time: Optional[float] = None
        self._phase_times: Dict[str, float] = {}
        self._memory_snapshots: Dict[str, float] = {}
        self._cache_hits = 0
        self._cache_misses = 0

    def start(self) -> None:
        """Start performance monitoring."""
        self._start_time = time.monotonic()
        self._take_memory_snapshot("start")

    def checkpoint(self, phase_name: str) -> None:
        """Record a timing checkpoint."""
        if self._start_time is not None:
            elapsed = time.monotonic() - self._start_time
            self._phase_times[phase_name] = elapsed
            logger.debug(f"Checkpoint '{phase_name}': {elapsed:.2f}s")

    def _take_memory_snapshot(self, label: str) -> None:
        """Take a memory usage snapshot."""
        process = psutil.Process()
        memory_mb = process.memory_info().rss / (1024 * 1024)
        self._memory_snapshots[label] = memory_mb

    def check_memory(self) -> bool:
        """
        Check if memory is within limits.

        Returns:
            True if within limits, False if exceeded
        """
        process = psutil.Process()
        memory_mb = process.memory_info().rss / (1024 * 1024)

        if memory_mb > self.max_memory_mb:
            logger.error(
                f"Memory limit exceeded: {memory_mb:.0f}MB > {self.max_memory_mb}MB. "
                f"Initiating graceful abort."
            )
            self._take_memory_snapshot("limit_exceeded")
            return False

        self._take_memory_snapshot(f"checkpoint_{len(self._phase_times)}")
        return True

    def enforce_limits(self) -> None:
        """
        Enforce memory limits. If exceeded, trigger graceful abort.

        This method should be called periodically during batch processing.
        """
        if not self.check_memory():
            self._initiate_graceful_abort()

    def _initiate_graceful_abort(self) -> None:
        """Initiate graceful abort due to resource limits."""
        logger.critical(
            f"Graceful abort initiated due to memory limit exceeded. "
            f"Peak: {self.get_peak_memory():.0f}MB, Limit: {self.max_memory_mb}MB"
        )
        # Generate partial audit export
        report = self.generate_report(0)
        logger.info(f"Partial audit report: {report}")

        # In a real implementation, this would raise a special exception
        # that gets caught by the main loop to export partial results
        raise MemoryError(f"Memory limit {self.max_memory_mb}MB exceeded")

    def record_cache_hit(self) -> None:
        """Record a cache hit."""
        self._cache_hits += 1

    def record_cache_miss(self) -> None:
        """Record a cache miss."""
        self._cache_misses += 1

    def get_cache_hit_rate(self) -> float:
        """Calculate cache hit rate."""
        total = self._cache_hits + self._cache_misses
        if total == 0:
            return 0.0
        return self._cache_hits / total

    def get_peak_memory(self) -> float:
        """Get peak memory usage."""
        if not self._memory_snapshots:
            self._take_memory_snapshot("current")
        return max(self._memory_snapshots.values()) if self._memory_snapshots else 0.0

    def generate_report(self, total_steps: int) -> PerformanceReport:
        """
        Generate performance report.

        Args:
            total_steps: Total number of steps processed

        Returns:
            PerformanceReport with all metrics
        """
        total_duration = time.monotonic() - self._start_time if self._start_time else 0
        process = psutil.Process()
        peak_memory = process.memory_info().rss / (1024 * 1024)

        return PerformanceReport(
            total_duration_s=round(total_duration, 2),
            peak_memory_mb=round(peak_memory, 1),
            cache_hit_rate=round(self.get_cache_hit_rate(), 3),
            steps_per_second=round(total_steps / total_duration, 1) if total_duration > 0 else 0,
            phase_durations=self._phase_times,
            memory_snapshots=self._memory_snapshots,
            within_targets=(peak_memory <= self.max_memory_mb),
        )

    def format_report(self, report: PerformanceReport) -> str:
        """Format performance report as string."""
        lines = [
            "# Performance Report",
            "",
            f"Total Duration: {report.total_duration_s:.2f}s",
            f"Peak Memory: {report.peak_memory_mb:.1f}MB",
            f"Cache Hit Rate: {report.cache_hit_rate:.1%}",
            f"Steps/Second: {report.steps_per_second:.1f}",
            f"Within Targets: {'Yes' if report.within_targets else 'No'}",
            "",
            "## Phase Durations",
        ]

        for phase, duration in report.phase_durations.items():
            lines.append(f"  {phase}: {duration:.2f}s")

        return "\n".join(lines)
