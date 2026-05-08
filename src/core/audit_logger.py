"""Audit logger for CAPL Pipeline V2.2.

JSON-LD structured logging for all decisions and actions.
"""

from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime
import json
import hashlib
import logging
from contextlib import contextmanager

logger = logging.getLogger(__name__)


class AuditLogger:
    """
    Structured audit logging with JSON-LD format.

    Captures all decisions, signal resolutions, and configuration changes
    with full traceability including input/output hashes.
    """

    def __init__(
        self,
        log_path: Optional[Path] = None,
        retention_days: Optional[int] = None
    ) -> None:
        from dotenv import load_dotenv
        load_dotenv()

        self.log_path = log_path or Path("logs/decisions.jsonl")
        self.retention_days = retention_days or int(
            __import__('os').getenv("AUDIT_RETENTION_DAYS", "90")
        )
        self._ensure_log_dir()
        self._session_id = self._generate_session_id()
        self._buffer: List[Dict] = []

    def _ensure_log_dir(self) -> None:
        """Ensure log directory exists."""
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def _generate_session_id(self) -> str:
        """Generate unique session ID."""
        timestamp = datetime.utcnow().isoformat()
        return hashlib.sha256(timestamp.encode()).hexdigest()[:16]

    def _compute_hash(self, data: Any) -> str:
        """Compute SHA-256 hash of data."""
        serialized = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(serialized.encode()).hexdigest()

    def log(
        self,
        action: str,
        category: str,
        details: Dict[str, Any],
        signal_name: Optional[str] = None,
        confidence: Optional[float] = None,
        metadata: Optional[Dict] = None
    ) -> str:
        """
        Log an audit entry.

        Args:
            action: Action type (e.g., 'signal_resolved', 'gap_identified')
            category: Category (e.g., 'signal', 'config', 'validation')
            details: Dictionary with action-specific details
            signal_name: Optional signal name for signal-related actions
            confidence: Optional confidence score
            metadata: Optional additional metadata

        Returns:
            Entry ID (hash of entry content)
        """
        entry = {
            "@context": "https://capl-pipeline.example.com/audit/v1",
            "@type": "AuditEntry",
            "sessionId": self._session_id,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "action": action,
            "category": category,
            "details": details,
        }

        if signal_name:
            entry["signalName"] = signal_name

        if confidence is not None:
            entry["confidence"] = confidence

        if metadata:
            entry["metadata"] = metadata

        # Compute input/output hashes for traceability
        entry["inputHash"] = self._compute_hash({
            "action": action,
            "category": category,
            "details": details
        })
        entry["entryHash"] = self._compute_hash(entry)

        # Write to log
        self._write_entry(entry)

        logger.debug(f"Audit log: {action} - {category}")
        return entry["entryHash"]

    def _write_entry(self, entry: Dict) -> None:
        """Write entry to log file."""
        self._buffer.append(entry)

        # Flush buffer periodically
        if len(self._buffer) >= 100:
            self._flush_buffer()

    def _flush_buffer(self) -> None:
        """Flush buffered entries to disk."""
        if not self._buffer:
            return

        with open(self.log_path, 'a', encoding='utf-8') as f:
            for entry in self._buffer:
                f.write(json.dumps(entry, default=str) + '\n')

        self._buffer = []

    def log_signal_resolution(
        self,
        signal_name: str,
        resolution_type: str,
        sources: List[str],
        confidence: float,
        final_value: Any
    ) -> str:
        """Log a signal resolution event."""
        return self.log(
            action="signal_resolved",
            category="signal",
            details={
                "resolutionType": resolution_type,
                "sources": sources,
                "finalValue": final_value
            },
            signal_name=signal_name,
            confidence=confidence
        )

    def log_gap_identified(
        self,
        gap_id: str,
        gap_type: str,
        context: Dict[str, Any]
    ) -> str:
        """Log identification of a configuration gap."""
        return self.log(
            action="gap_identified",
            category="config",
            details={
                "gapType": gap_type,
                "context": context
            },
            metadata={"gapId": gap_id}
        )

    def log_gap_resolution(
        self,
        gap_id: str,
        resolution: str,
        user_action: str
    ) -> str:
        """Log resolution of a configuration gap."""
        return self.log(
            action="gap_resolved",
            category="config",
            details={
                "resolution": resolution,
                "userAction": user_action
            },
            metadata={"gapId": gap_id}
        )

    def log_capl_generation(
        self,
        test_case_id: str,
        file_path: str,
        line_count: int,
        signals_used: List[str]
    ) -> str:
        """Log CAPL file generation."""
        return self.log(
            action="capl_generated",
            category="generation",
            details={
                "testCaseId": test_case_id,
                "filePath": file_path,
                "lineCount": line_count,
                "signalsUsed": signals_used
            }
        )

    def log_validation(
        self,
        entity_type: str,
        entity_name: str,
        passed: bool,
        issues: List[str]
    ) -> str:
        """Log validation result."""
        return self.log(
            action="validation",
            category="validation",
            details={
                "entityType": entity_type,
                "passed": passed,
                "issues": issues
            },
            signal_name=entity_name
        )

    def log_llm_call(
        self,
        task: str,
        model: str,
        tokens_used: int,
        success: bool,
        error: Optional[str] = None
    ) -> str:
        """Log LLM API call."""
        return self.log(
            action="llm_call",
            category="llm",
            details={
                "task": task,
                "model": model,
                "tokensUsed": tokens_used,
                "success": success,
                "error": error
            }
        )

    @contextmanager
    def audit_section(self, section_name: str):
        """Context manager for audit sections."""
        start_time = datetime.utcnow()
        self.log(
            action="section_start",
            category="session",
            details={"sectionName": section_name}
        )

        try:
            yield
            self.log(
                action="section_end",
                category="session",
                details={
                    "sectionName": section_name,
                    "duration_ms": (datetime.utcnow() - start_time).total_seconds() * 1000
                }
            )
        except Exception as e:
            self.log(
                action="section_error",
                category="session",
                details={
                    "sectionName": section_name,
                    "error": str(e)
                }
            )
            raise

    def flush(self) -> None:
        """Flush any buffered entries to disk."""
        self._flush_buffer()

    def get_recent_entries(
        self,
        limit: int = 100,
        category: Optional[str] = None
    ) -> List[Dict]:
        """Get recent log entries."""
        if not self.log_path.exists():
            return []

        entries = []
        with open(self.log_path, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    entry = json.loads(line)
                    if category is None or entry.get("category") == category:
                        entries.append(entry)
                except json.JSONDecodeError:
                    continue

        return entries[-limit:]

    def close(self) -> None:
        """Close logger and flush buffers."""
        self._flush_buffer()
        logger.info(f"Audit log session {self._session_id} closed")
