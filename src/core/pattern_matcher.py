"""Pattern matcher for CAPL Pipeline V2.2.

Deterministic, config-driven phrase library for matching
test steps and generating CAPL code patterns.
"""

from pathlib import Path
from typing import Dict, List, Optional, Pattern, Match
import re
import logging

logger = logging.getLogger(__name__)


class PatternMatcher:
    """
    Deterministic pattern matcher using pre-defined phrase libraries.

    Matches test step text against known patterns and returns
    appropriate CAPL code generation actions.
    """

    # Built-in patterns (configurable via YAML)
    DEFAULT_PATTERNS: Dict[str, str] = {
        # Signal access patterns
        r'\$([A-Za-z0-9_]+)': 'signal_reference',
        r'@sysvar::([A-Za-z0-9_:]+)': 'sysvar_reference',
        r'Env([A-Za-z0-9_]+)': 'env_var_reference',

        # Action patterns
        r'(?:send|transmit|write)\s+(\w+)': 'send_signal',
        r'(?:receive|read|get)\s+(\w+)': 'receive_signal',
        r'(?:wait|delay|pause)\s+(\d+)': 'wait_delay',
        r'(?:check|verify|assert)\s+(\w+)': 'verify_signal',
        r'(?:set|put|write)\s+(\w+)\s+(?:to|=|:)\s*(.+)': 'set_signal',
        r'(?:trigger|fire)\s+(\w+)': 'trigger_event',

        # Condition patterns
        r'(?:if|when|while|ifthen)\s+(.+)': 'conditional',
        r'(?:repeat|loop|for)\s+(\d+)': 'repeat_loop',
        r'(?:until|while)\s+(.+)': 'loop_condition',

        # Test step patterns
        r'testStep\s*\(\s*["\']?([^"\',)]+)["\']?\s*,\s*["\']?([^"\',)]+)["\']?\s*\)': 'test_step_call',
        r'testCase\s*\(\s*["\']?([^"\',)]+)["\']?\s*\)': 'test_case_call',
        r'testFunction\s*\(\s*["\']?([^"\',)]+)["\']?\s*\)': 'test_function_call',

        # Expectation patterns
        r'(?:expect|should(?:_be)?|shall)\s+(.+)': 'expectation',
        r'(?:check|verify)\s+(?:that\s+)?(.+)': 'verification',
        r'(?:until|till)\s+(.+)': 'wait_until',

        # Value patterns
        r'(?:0x[0-9A-Fa-f]+|\d+)': 'numeric_value',
        r'(?:true|false|on|off|enable|disable)': 'boolean_value',
    }

    def __init__(
        self,
        pattern_file: Optional[Path] = None,
        additional_patterns: Optional[Dict[str, str]] = None
    ) -> None:
        self.patterns: Dict[str, Pattern] = {}
        self.pattern_actions: Dict[str, str] = {}

        # Load default patterns
        for pattern_str, action in self.DEFAULT_PATTERNS.items():
            self._add_pattern(pattern_str, action)

        # Load from file if provided
        if pattern_file and pattern_file.exists():
            self._load_patterns_from_file(pattern_file)

        # Add additional patterns
        if additional_patterns:
            for pattern_str, action in additional_patterns.items():
                self._add_pattern(pattern_str, action)

    def _add_pattern(self, pattern_str: str, action: str) -> None:
        """Add a pattern to the matcher."""
        try:
            compiled = re.compile(pattern_str, re.MULTILINE | re.IGNORECASE)
            self.patterns[action] = compiled
            self.pattern_actions[pattern_str] = action
        except re.error as e:
            logger.warning(f"Invalid pattern '{pattern_str}': {e}")

    def _load_patterns_from_file(self, pattern_file: Path) -> None:
        """Load patterns from YAML file."""
        import yaml

        try:
            with open(pattern_file, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)

            if data and 'patterns' in data:
                for pattern_config in data['patterns']:
                    pattern_str = pattern_config.get('pattern')
                    action = pattern_config.get('action')
                    if pattern_str and action:
                        self._add_pattern(pattern_str, action)

            logger.info(f"Loaded patterns from {pattern_file}")
        except Exception as e:
            logger.warning(f"Failed to load patterns from {pattern_file}: {e}")

    def match(self, text: str) -> List[Dict[str, any]]:
        """
        Match text against all patterns.

        Args:
            text: Text to match

        Returns:
            List of match results with action, match text, and groups
        """
        results = []

        for action, pattern in self.patterns.items():
            for match in pattern.finditer(text):
                results.append({
                    'action': action,
                    'match': match.group(0),
                    'start': match.start(),
                    'end': match.end(),
                    'groups': match.groups(),
                    'group_dict': match.groupdict() if hasattr(match, 'groupdict') else {}
                })

        # Sort by position in text
        results.sort(key=lambda x: x['start'])
        return results

    def match_first(self, text: str) -> Optional[Dict[str, any]]:
        """Return first match only."""
        matches = self.match(text)
        return matches[0] if matches else None

    def extract_signals(self, text: str) -> List[str]:
        """Extract all signal references from text."""
        signals = []

        signal_pattern = self.patterns.get('signal_reference')
        if signal_pattern:
            for match in signal_pattern.finditer(text):
                signals.append(match.group(1))

        return list(set(signals))

    def extract_values(self, text: str) -> List[str]:
        """Extract all values from text."""
        values = []

        numeric_pattern = self.patterns.get('numeric_value')
        if numeric_pattern:
            for match in numeric_pattern.finditer(text):
                values.append(match.group(0))

        bool_pattern = self.patterns.get('boolean_value')
        if bool_pattern:
            for match in bool_pattern.finditer(text):
                values.append(match.group(0))

        return list(set(values))

    def classify_step(self, text: str) -> str:
        """
        Classify a test step into a primary action category.

        Returns:
            Action category string
        """
        matches = self.match(text)
        if not matches:
            return 'unknown'

        # Priority order for classification
        priority_actions = [
            'test_step_call',
            'send_signal',
            'receive_signal',
            'set_signal',
            'verify_signal',
            'trigger_event',
            'test_case_call',
            'test_function_call',
            'expectation',
            'verification',
            'wait_delay',
            'wait_until',
            'conditional',
            'repeat_loop',
        ]

        for action in priority_actions:
            if any(m['action'] == action for m in matches):
                return action

        return matches[0]['action']
