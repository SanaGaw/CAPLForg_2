"""Unit tests for LLM modules."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from src.llm.router import LLMRouter
from src.llm.chat_resolver import ChatResolver
from src.llm.prompts import PromptManager


class TestLLMRouter:
    """Tests for LLMRouter."""

    def test_init(self, tmp_path):
        """Test router initialization."""
        config_file = tmp_path / "api_config.yaml"
        config_file.write_text('''
llm:
  preferred:
    provider: azure
    model: o3-mini
    max_context_tokens: 200000
''')

        router = LLMRouter(api_config_path=config_file)
        assert router.api_config_path == config_file

    def test_provider_chain(self, tmp_path):
        """Test provider chain building."""
        config_file = tmp_path / "api_config.yaml"
        config_file.write_text('''
llm:
  preferred:
    provider: azure
    model: o3-mini
  fallback_chain:
    - provider: ollama
      model: qwen2.5-coder
''')

        router = LLMRouter(api_config_path=config_file)
        chain = router._build_provider_chain(router._config.get("llm", {}).get("preferred", {}))

        assert len(chain) >= 1
        assert chain[0].provider == "azure"


class TestChatResolver:
    """Tests for ChatResolver."""

    def test_build_resolution_prompt(self):
        """Test resolution prompt building."""
        mock_router = MagicMock()
        mock_registry = MagicMock()
        mock_registry.get_all_signals.return_value = []

        resolver = ChatResolver(mock_router, mock_registry)

        gap = {
            'id': 'gap_test',
            'type': 'signal_alias',
            'signal_name': 'TestSignal'
        }

        prompt = resolver._build_resolution_prompt(gap, "Use CAN bus", None)
        assert 'TestSignal' in prompt
        assert 'signal_alias' in prompt

    def test_validate_resolution_skip(self):
        """Test validation of skip action."""
        mock_router = MagicMock()
        mock_registry = MagicMock()
        resolver = ChatResolver(mock_router, mock_registry)

        resolution = {'action': 'skip', 'target': 'TestSignal'}
        validation = resolver._validate_resolution({}, resolution)

        assert validation['passes']


class TestPromptManager:
    """Tests for PromptManager."""

    def test_get_prompt(self):
        """Test prompt retrieval."""
        manager = PromptManager()

        config_prompt = manager.get_prompt('config_builder')
        assert 'Configuration' in config_prompt

        chat_prompt = manager.get_prompt('chat_resolver')
        assert 'Test Engineering' in chat_prompt

    def test_build_prompt(self):
        """Test prompt building."""
        manager = PromptManager()

        context = {
            'signal_name': 'TestSignal',
            'gap_type': 'signal_alias'
        }

        prompt = manager.build_prompt('config_builder', context)
        assert 'TestSignal' in prompt

    def test_add_template(self):
        """Test custom template addition."""
        manager = PromptManager()

        manager.add_template('custom', 'Custom prompt template')
        assert manager.get_prompt('custom') == 'Custom prompt template'
