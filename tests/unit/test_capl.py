"""Unit tests for CAPL generation modules."""

import pytest
from pathlib import Path
from src.capl.template_engine import TemplateEngine, JinjaEnvironment
from src.capl.helper_manager import HelperValidator, HelperManager
from src.capl.generator import CaplGenerator


class TestJinjaEnvironment:
    """Tests for JinjaEnvironment."""

    def test_compile_template(self):
        """Test template compilation."""
        env = JinjaEnvironment()
        template = env.compile_template('Hello {{ name }}')
        assert template is not None

    def test_render(self):
        """Test template rendering."""
        env = JinjaEnvironment()
        result = env.render('Hello {{ name }}', {'name': 'World'})
        assert result == 'Hello World'


class TestTemplateEngine:
    """Tests for TemplateEngine."""

    def test_render_test_case(self):
        """Test test case template rendering."""
        engine = TemplateEngine()

        context = {
            'test_case_id': 'TC_001',
            'description': 'Test door lock',
            'test_function_name': 'Test_TC_001',
            'test_steps': [
                {
                    'step_id': 'TC_001.1',
                    'action': 'Set door lock',
                    'env_var': 'EnvDoorLock_FL',
                    'signal': 'DoorLock_FL',
                    'action_type': 'set'
                }
            ],
            'variables': [
                {'type': 'int', 'name': 'g_DoorLock_FL', 'initial': '0'}
            ],
            'helper_include': 'helpers.h'
        }

        result = engine.render('test_case', context)
        assert 'TC_001' in result
        assert 'Test_TC_001' in result


class TestHelperValidator:
    """Tests for HelperValidator."""

    def test_parse_signature(self):
        """Test signature parsing."""
        validator = HelperValidator()

        return_type, name, params = validator.parse_signature(
            'void VerifySignal(int signalId, float threshold)'
        )

        assert return_type == 'void'
        assert name == 'VerifySignal'
        assert len(params) == 2
        assert params[0] == ('int', 'signalId')
        assert params[1] == ('float', 'threshold')

    def test_validate_signature_valid(self):
        """Test validation of valid signatures."""
        validator = HelperValidator()

        is_valid, error = validator.validate_signature(
            'void TestFunction(int value);'
        )
        assert is_valid
        assert error is None

    def test_validate_signature_invalid_return_type(self):
        """Test validation of invalid return type."""
        validator = HelperValidator()

        is_valid, error = validator.validate_signature(
            'invalid_type TestFunction();'
        )
        assert not is_valid
        assert error is not None
        # Error message should indicate the signature is invalid
        assert 'Invalid' in error


class TestCaplGenerator:
    """Tests for CaplGenerator."""

    def test_generate_from_test_case(self):
        """Test CAPL generation from test case."""
        generator = CaplGenerator()

        test_case = {
            'test_case_id': 'TC_001',
            'description': 'Test door lock functionality',
            'steps': [
                {
                    'step_id': 'TC_001.1',
                    'action': 'Set door lock to locked',
                    'description': 'Set door lock to locked state',
                    'signal_refs': ['DoorLock_FL']
                }
            ],
            'signals': ['DoorLock_FL']
        }

        result = generator.generate_from_test_case(test_case)
        assert 'TC_001' in result
        assert 'Test_TC_001' in result or 'Test_' in result
