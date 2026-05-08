"""CAPL generator for CAPL Pipeline V2.2.

Main CAPL emission logic for generating test cases from parsed test plans.
"""

from pathlib import Path
from typing import Dict, List, Optional, Any
import logging

from .template_engine import TemplateEngine
from .helper_manager import HelperManager
from ..core.signal_registry import SignalRegistry
from ..core.pattern_matcher import PatternMatcher

logger = logging.getLogger(__name__)


class CaplGenerator:
    """
    Main CAPL code generator.

    Transforms test cases (from Excel parser) into CAPL test functions
    using templates, helpers, and signal registry information.
    """

    def __init__(
        self,
        signal_registry: Optional[SignalRegistry] = None,
        template_engine: Optional[TemplateEngine] = None,
        helper_manager: Optional[HelperManager] = None
    ) -> None:
        self.registry = signal_registry or SignalRegistry()
        self.template_engine = template_engine or TemplateEngine()
        self.helper_manager = helper_manager or HelperManager()
        self.pattern_matcher = PatternMatcher()

    def generate_from_test_case(self, test_case: Dict[str, Any]) -> str:
        """
        Generate CAPL code from a test case dictionary.

        Args:
            test_case: Dict containing test_case_id, steps, signals, etc.

        Returns:
            Generated CAPL code string
        """
        test_case_id = test_case.get('test_case_id', test_case.get('test_id', 'Unknown'))
        description = test_case.get('description', '')
        steps = test_case.get('steps', [])
        signals = test_case.get('signals', [])

        # Build context for template
        context = self._build_context(test_case_id, description, steps, signals)

        # Render template
        return self.template_engine.render('test_case', context)

    def _build_context(
        self,
        test_case_id: str,
        description: str,
        steps: List[Dict[str, Any]],
        signals: List[str]
    ) -> Dict[str, Any]:
        """Build template rendering context from test case data."""
        # Process steps
        test_steps = []
        variables = []

        for i, step in enumerate(steps):
            step_id = step.get('step_id', f"{test_case_id}.{i+1}")
            action = step.get('action', step.get('description', ''))
            expected = step.get('expected_result', '')
            step_signals = step.get('signal_refs', [])

            # Classify action type
            action_type = self.pattern_matcher.classify_step(action)

            # Resolve signals for this step
            env_var = None
            resolved_signal = None

            for sig in step_signals:
                signal_info = self.registry.lookup(sig)
                if signal_info:
                    env_var = signal_info.env_var_name
                    resolved_signal = signal_info.name
                    break

            test_steps.append({
                'step_id': step_id,
                'action': action,
                'description': step.get('description', action),
                'action_type': action_type,
                'env_var': env_var,
                'signal': resolved_signal,
                'expected_value': expected,
            })

            # Add variables as needed
            if resolved_signal and resolved_signal not in [v['name'] for v in variables]:
                variables.append({
                    'type': 'int',
                    'name': f'g_{resolved_signal}',
                    'initial': '0'
                })

        # Generate function name
        test_function_name = f'Test_{test_case_id.replace("-", "_").replace(".", "_")}'

        return {
            'test_case_id': test_case_id,
            'description': description,
            'test_function_name': test_function_name,
            'test_steps': test_steps,
            'variables': variables,
            'includes': self.helper_manager.get_all_signatures()[:5],  # Limit includes
            'helper_include': 'helpers.h',  # Default helper include
        }

    def generate_batch(
        self,
        test_cases: List[Dict[str, Any]],
        output_dir: Path
    ) -> Dict[str, Any]:
        """
        Generate CAPL files for multiple test cases.

        Args:
            test_cases: List of test case dictionaries
            output_dir: Directory for output files

        Returns:
            Dict with generation results
        """
        output_dir.mkdir(parents=True, exist_ok=True)

        results = {
            'total': len(test_cases),
            'successful': 0,
            'failed': 0,
            'files': []
        }

        for test_case in test_cases:
            try:
                content = self.generate_from_test_case(test_case)
                test_id = test_case.get('test_case_id', test_case.get('test_id', 'Unknown'))
                output_path = output_dir / f"{test_id}.can"

                output_path.write_text(content, encoding='utf-8')
                results['files'].append(str(output_path))
                results['successful'] += 1

            except Exception as e:
                logger.error(f"Error generating {test_case.get('test_id')}: {e}")
                results['failed'] += 1

        return results

    def generate_signal_verify(self, signal_name: str, expected_value: Any) -> str:
        """
        Generate a signal verification snippet.

        Args:
            signal_name: Name of signal to verify
            expected_value: Expected value

        Returns:
            CAPL code snippet
        """
        signal = self.registry.lookup(signal_name)

        context = {
            'signal_name': signal_name,
            'expected_value': expected_value,
            'env_var': signal.env_var_name if signal else None
        }

        return self.template_engine.render('signal_verify', context)

    def generate_ecu_wakeup(self, ecu_list: List[Dict[str, str]]) -> str:
        """
        Generate ECU wake-up sequence.

        Args:
            ecu_list: List of dicts with 'name', 'signal', 'env_var' keys

        Returns:
            CAPL code for ECU wake-up
        """
        context = {
            'ecus': ecu_list
        }

        return self.template_engine.render('ecus_wakeup', context)
