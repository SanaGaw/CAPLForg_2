"""CAPL structural fingerprinter for CAPL Pipeline V2.2.

Structural comparison for CAPL files using regex-based fingerprinting.
Does NOT use Python's ast module (which only parses Python code).
"""

from pathlib import Path
from typing import List, Dict, Tuple, Optional
import re
import hashlib
import logging

logger = logging.getLogger(__name__)


class CaplStructuralFingerprinter:
    """
    Structural comparison for CAPL files using regex-based fingerprinting.
    Does NOT use Python's ast module (which only parses Python code).
    """

    # CAPL-specific patterns for structural extraction
    PATTERNS = {
        'function': re.compile(
            r'(?:^|(?<=\s))(?:void|int|long|double|float|char|byte|word|dword|qword|int64)\s+'
            r'([A-Za-z0-9_]+)\s*\([^)]*\)\s*\{?',
            re.MULTILINE
        ),
        'variable': re.compile(
            r'^(?:var|message|timer|msTimer)\s+([A-Za-z0-9_]+)\s*[:=]',
            re.MULTILINE
        ),
        'on_handler': re.compile(
            r'^on\s+(key|message|timer|msTimer|envVar|sysvar|start|stop|preStart|errorFrame)\s+'
            r'([A-Za-z0-9_:.\[\]]+|0x[0-9A-Fa-f]+|\*)\s*\{?',
            re.MULTILINE
        ),
        'testStep_call': re.compile(
            r'testStep\(\s*["\']([^"\']+)["\']\s*,\s*["\']([^"\']+)["\']\s*\)',
            re.MULTILINE
        ),
        'signal_ref': re.compile(
            r'[@\$]([A-Za-z0-9_:.\[\]]+)',
            re.MULTILINE
        ),
        'include': re.compile(
            r'#include\s+["\']([^"\']+)["\']',
            re.MULTILINE
        ),
    }

    def __init__(self, ignore_whitespace: bool = True, ignore_comments: bool = True) -> None:
        self.ignore_whitespace = ignore_whitespace
        self.ignore_comments = ignore_comments

    def _preprocess(self, content: str) -> str:
        """Normalize CAPL content for fingerprinting."""
        if self.ignore_comments:
            content = re.sub(r'//.*$', '', content, flags=re.MULTILINE)
            content = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)
        if self.ignore_whitespace:
            content = re.sub(r'\s+', ' ', content)
        return content.strip()

    def extract_fingerprint(self, filepath: Path) -> Dict[str, List[str]]:
        """
        Extract structural elements from a .can file.
        Returns: {
            'functions': ['ECUWakeUp', 'VerifySignal', ...],
            'variables': ['g_DoorLockStatus', ...],
            'on_handlers': [('message', '0x100'), ('envVar', 'EnvDoorLock'), ...],
            'testSteps': [('TC_001', 'Check Door Lock'), ...],
            'signal_refs': ['@sysvar::Lighting::LF_DRL_Cmd', '$BCM_DoorLock'],
            'includes': ['helpers.cin', 'constants.cin']
        }
        """
        content = filepath.read_text(encoding='utf-8')
        content = self._preprocess(content)

        fingerprint: Dict[str, List] = {}
        for key, pattern in self.PATTERNS.items():
            matches = pattern.findall(content)
            if key == 'on_handler':
                fingerprint[key] = [
                    tuple(m) if isinstance(m, tuple) else (m, '') for m in matches
                ]
            elif key == 'testStep_call':
                fingerprint[key] = [tuple(m) for m in matches]
            else:
                fingerprint[key] = list(set(matches))  # Deduplicate
        return fingerprint

    def compare(
        self, file_a: Path, file_b: Path, tolerance: float = 0.95
    ) -> Tuple[bool, Dict]:
        """
        Compare two CAPL files structurally.
        Returns: (pass: bool, diff_report: dict)
        tolerance: minimum similarity ratio (0.0-1.0) for pass
        """
        fp_a = self.extract_fingerprint(file_a)
        fp_b = self.extract_fingerprint(file_b)

        # Compute similarity per category
        similarities = {}
        for key in fp_a.keys() | fp_b.keys():
            set_a = set(fp_a.get(key, []))
            set_b = set(fp_b.get(key, []))
            if not set_a and not set_b:
                similarities[key] = 1.0
            else:
                intersection = len(set_a & set_b)
                union = len(set_a | set_b)
                similarities[key] = intersection / union if union > 0 else 0.0

        # Weighted average (testSteps and signal_refs are most critical)
        weights = {
            'testStep_call': 0.4,
            'signal_ref': 0.3,
            'function': 0.15,
            'variable': 0.1,
            'on_handler': 0.05,
        }
        overall = sum(
            similarities.get(k, 0.0) * weights.get(k, 0.1) for k in weights
        ) / sum(weights.values())

        diff_report = {
            'overall_similarity': round(overall, 3),
            'per_category': {k: round(v, 3) for k, v in similarities.items()},
            'missing_in_b': {
                k: list(set(fp_a.get(k, [])) - set(fp_b.get(k, []))) for k in fp_a
            },
            'extra_in_b': {
                k: list(set(fp_b.get(k, [])) - set(fp_a.get(k, []))) for k in fp_b
            },
        }
        return overall >= tolerance, diff_report

    def generate_golden_diff(
        self, golden_dir: Path, generated_dir: Path
    ) -> str:
        """Batch compare all .can files. Returns markdown report."""
        report_lines = ["# CAPL Structural Comparison Report\n"]
        for golden_file in golden_dir.glob("*.can"):
            generated_file = generated_dir / golden_file.name
            if not generated_file.exists():
                report_lines.append(f"MISSING {golden_file.name}: not found in generated output\n")
                continue
            passed, diff = self.compare(golden_file, generated_file)
            status = "PASS" if passed else "FAIL"
            report_lines.append(
                f"{status} {golden_file.name} (similarity: {diff['overall_similarity']:.3f})\n"
            )
            if not passed:
                for cat in ['testStep_call', 'signal_ref']:
                    if diff['missing_in_b'].get(cat) or diff['extra_in_b'].get(cat):
                        report_lines.append(
                            f"  - {cat}: missing={diff['missing_in_b'][cat]}, "
                            f"extra={diff['extra_in_b'][cat]}\n"
                        )
        return "\n".join(report_lines)

    def compute_file_hash(self, filepath: Path) -> str:
        """Compute SHA-256 hash of file content (after preprocessing)."""
        content = filepath.read_text(encoding='utf-8')
        content = self._preprocess(content)
        return hashlib.sha256(content.encode()).hexdigest()
