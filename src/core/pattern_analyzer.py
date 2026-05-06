"""Pattern analyzer for CAPL Pipeline V2.2.

Detects repetitive sequences across test cases for
suggesting reusable helper functions.
"""

from pathlib import Path
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field
import os
import logging
from collections import Counter

logger = logging.getLogger(__name__)


@dataclass
class SequenceCandidate:
    """Represents a detected repetitive sequence candidate."""
    pattern_name: str
    steps: List[str]
    frequency: int
    confidence: float
    suggested_params: List[str] = field(default_factory=list)
    affected_test_cases: List[str] = field(default_factory=list)


class PatternAnalyzer:
    """
    Analyzes test plans for repetitive action sequences.

    Identifies patterns that appear frequently enough to warrant
    extraction into reusable helper functions.
    """

    def __init__(
        self,
        min_frequency: Optional[int] = None,
        min_frequency_global: int = 1,
        similarity_threshold: float = 0.75
    ) -> None:
        """
        Args:
            min_frequency: Min occurrences to suggest as helper (default: from env or 2)
            min_frequency_global: Min for "always-apply" helpers (default: 1)
        """
        self.min_frequency = min_frequency or int(
            os.getenv("PATTERN_MIN_FREQUENCY", "2")
        )
        self.min_frequency_global = min_frequency_global
        self.similarity_threshold = similarity_threshold

    def scan_test_plan(
        self,
        test_cases: List[Any]
    ) -> List[SequenceCandidate]:
        """
        Scan test plan for repeated sequences.

        Args:
            test_cases: List of TestCase objects from Excel parser

        Returns:
            List of SequenceCandidate objects for potential helpers
        """
        # Extract all step actions
        all_sequences: List[tuple] = []
        step_by_tc: Dict[str, List[str]] = {}

        for test_case in test_cases:
            tc_id = test_case.test_id
            actions = [step.action or step.description for step in test_case.steps]
            step_by_tc[tc_id] = actions

            # Generate sliding window sequences (length 2-4)
            for seq_len in range(2, 5):
                for i in range(len(actions) - seq_len + 1):
                    seq = tuple(actions[i:i + seq_len])
                    all_sequences.append((tc_id, seq))

        # Count sequence frequencies
        seq_counter = Counter(seq for _, seq in all_sequences)

        # Generate candidates
        candidates: List[SequenceCandidate] = []

        for seq, count in seq_counter.items():
            if count >= self.min_frequency:
                # Find affected test cases
                affected = list(set(
                    tc_id for tc_id, s in all_sequences if s == seq
                ))

                candidate = SequenceCandidate(
                    pattern_name=self._generate_name(seq),
                    steps=list(seq),
                    frequency=count,
                    confidence=min(1.0, count / 10.0),  # Confidence increases with frequency
                    affected_test_cases=affected,
                    suggested_params=self._extract_params(seq)
                )
                candidates.append(candidate)

        # Sort by frequency
        candidates.sort(key=lambda x: x.frequency, reverse=True)

        logger.info(
            f"Pattern analysis complete: {len(candidates)} candidates found "
            f"(min frequency: {self.min_frequency})"
        )
        return candidates

    def _generate_name(self, steps: tuple) -> str:
        """Generate a descriptive name for a sequence."""
        if not steps:
            return "UnknownSequence"

        # Take first and last action words
        first_words = []
        last_words = []

        for i, step in enumerate(steps):
            words = step.split()
            if i == 0 and words:
                first_words.append(words[0])
            if i == len(steps) - 1 and words:
                last_words.append(words[-1])

        action = "And".join(first_words[:2]) if first_words else "Sequence"
        result = "And".join(last_words[:2]) if last_words else ""

        if action and result:
            return f"{action}_{result}"
        return action or f"Helper_{len(steps)}Steps"

    def _extract_params(self, steps: tuple) -> List[str]:
        """Extract suggested parameters from a sequence."""
        params = set()

        # Look for common variable patterns
        param_patterns = [
            r'\$([A-Za-z0-9_]+)',  # Signal references
            r'@sysvar::([A-Za-z0-9_:]+)',  # Sysvar references
            r'(?:value|val|threshold|timeout)[:\s]+([^\s,]+)',  # Value parameters
        ]

        for step in steps:
            for pattern in param_patterns:
                import re
                matches = re.findall(pattern, step, re.IGNORECASE)
                for match in matches:
                    if len(match) > 2 and len(match) < 30:
                        params.add(match)

        return sorted(list(params))

    def analyze_sequencing_patterns(
        self,
        test_cases: List[Any]
    ) -> Dict[str, Any]:
        """
        Comprehensive analysis of sequencing patterns.

        Returns:
            Dict with analysis results
        """
        candidates = self.scan_test_plan(test_cases)

        return {
            "total_candidates": len(candidates),
            "high_confidence": [c for c in candidates if c.confidence >= 0.7],
            "medium_confidence": [c for c in candidates if 0.4 <= c.confidence < 0.7],
            "low_confidence": [c for c in candidates if c.confidence < 0.4],
            "by_frequency": {
                c.pattern_name: c.frequency for c in candidates
            },
            "all_candidates": candidates
        }

    def suggest_helper_signatures(
        self,
        candidates: List[SequenceCandidate]
    ) -> List[Dict[str, str]]:
        """
        Generate CAPL function signature suggestions from candidates.

        Returns:
            List of suggested function signatures
        """
        suggestions = []

        for candidate in candidates:
            params = candidate.suggested_params[:3]  # Limit to 3 params

            param_str = ", ".join(
                f"int {p}" if not p.startswith("Env") else f"float {p}"
                for p in params
            ) if params else "void"

            signature = f"void {candidate.pattern_name}({param_str});"

            suggestions.append({
                "name": candidate.pattern_name,
                "signature": signature,
                "frequency": candidate.frequency,
                "confidence": candidate.confidence,
                "affected_tcs": len(candidate.affected_test_cases)
            })

        return suggestions
