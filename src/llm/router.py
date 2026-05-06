"""Multi-provider LLM router for CAPL Pipeline V2.2.

Routes LLM requests across Azure, AWS Bedrock, and Google Vertex AI
with circuit breaker pattern for fault tolerance.
"""

from pathlib import Path
from typing import Dict, List, Optional, Any, Callable
import asyncio
import logging
import os
import time
import yaml
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class ProviderStatus(Enum):
    """Provider circuit breaker status."""
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing recovery


@dataclass
class ProviderConfig:
    """Configuration for an LLM provider."""
    provider: str
    model: str
    role: str
    max_context_tokens: int
    api_key: Optional[str] = None
    endpoint: Optional[str] = None
    api_version: Optional[str] = None


@dataclass
class CircuitState:
    """Circuit breaker state for a provider."""
    status: ProviderStatus = ProviderStatus.CLOSED
    failure_count: int = 0
    last_failure_time: float = 0.0


class LLMRouter:
    """
    Multi-provider LLM router with circuit breaker pattern.

    Supports:
    - Azure OpenAI (primary)
    - AWS Bedrock (cross-provider fallback)
    - Google Vertex AI (cross-provider fallback)
    - Local Ollama (offline/compliance fallback)
    """

    def __init__(
        self,
        api_config_path: Optional[Path] = None,
        cache_dir: Optional[Path] = None
    ) -> None:
        self.api_config_path = api_config_path or Path("api_config.yaml")
        self.cache_dir = cache_dir or Path("logs/llm_cache")
        self._config: Dict[str, Any] = {}
        self._circuit_states: Dict[str, CircuitState] = {}
        self._init_config()

    def _init_config(self) -> None:
        """Load configuration from api_config.yaml."""
        if self.api_config_path.exists():
            with open(self.api_config_path, 'r', encoding='utf-8') as f:
                self._config = yaml.safe_load(f) or {}

        # Initialize circuit states for each provider
        for provider in ['azure', 'bedrock', 'vertexai']:
            self._circuit_states[provider] = CircuitState()

        # Configure cache
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._cache_enabled = os.getenv("LLM_CACHE_ENABLED", "true").lower() == "true"
        self._cache_ttl = int(os.getenv("LLM_CACHE_TTL", "3600"))

    async def chat(
        self,
        prompt: str,
        task: str = "general",
        response_schema: Optional[str] = None,
        max_tokens: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Send chat request with multi-provider fallback.

        Args:
            prompt: System prompt or user message
            task: Task type for routing (gap_resolution, helper_drafting, validation)
            response_schema: Optional schema name for structured output
            max_tokens: Optional token limit

        Returns:
            Dict with response content and metadata
        """
        # Get task-specific config
        task_config = self._config.get("llm", {}).get("task_overrides", {}).get(task, {})
        preferred = task_config or self._config.get("llm", {}).get("preferred", {})

        # Build provider chain
        providers = self._build_provider_chain(preferred)

        # Try each provider until success
        last_error = None
        for provider_config in providers:
            provider_name = provider_config.provider

            # Check circuit breaker
            if self._is_circuit_open(provider_name):
                logger.debug(f"Circuit open for {provider_name}, skipping")
                continue

            try:
                result = await self._call_provider(provider_config, prompt, max_tokens)
                self._record_success(provider_name)
                return result

            except Exception as e:
                logger.warning(f"Provider {provider_name} failed: {e}")
                self._record_failure(provider_name)
                last_error = e
                continue

        # All providers failed
        raise RuntimeError(f"All LLM providers failed. Last error: {last_error}")

    def _build_provider_chain(self, preferred: Dict[str, Any]) -> List[ProviderConfig]:
        """Build ordered list of providers to try."""
        providers = []

        # Preferred provider first
        preferred_config = ProviderConfig(
            provider=preferred.get("provider", "azure"),
            model=preferred.get("model", "o3-mini"),
            role="primary",
            max_context_tokens=preferred.get("max_context_tokens", 200000),
        )
        providers.append(preferred_config)

        # Add fallback chain
        for fallback in self._config.get("llm", {}).get("fallback_chain", []):
            providers.append(ProviderConfig(
                provider=fallback.get("provider", "azure"),
                model=fallback.get("model", "gpt-5-mini"),
                role=fallback.get("role", "fallback"),
                max_context_tokens=fallback.get("max_context_tokens", 128000),
            ))

        return providers

    async def _call_provider(
        self,
        config: ProviderConfig,
        prompt: str,
        max_tokens: Optional[int]
    ) -> Dict[str, Any]:
        """Call an LLM provider."""
        if config.provider == "azure":
            return await self._call_azure(config, prompt, max_tokens)
        elif config.provider == "bedrock":
            return await self._call_bedrock(config, prompt, max_tokens)
        elif config.provider == "vertexai":
            return await self._call_vertexai(config, prompt, max_tokens)
        elif config.provider == "ollama":
            return await self._call_ollama(config, prompt, max_tokens)
        else:
            raise ValueError(f"Unknown provider: {config.provider}")

    async def _call_azure(
        self,
        config: ProviderConfig,
        prompt: str,
        max_tokens: Optional[int]
    ) -> Dict[str, Any]:
        """Call Azure OpenAI."""
        # Check for API key
        api_key = os.getenv("AZURE_OPENAI_API_KEY")
        endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")

        if not api_key or not endpoint:
            raise RuntimeError("Azure OpenAI credentials not configured")

        # For now, return a placeholder - actual implementation would use openai package
        logger.info(f"Calling Azure OpenAI: {config.model}")
        return {
            "content": f"[Azure response placeholder - model: {config.model}]",
            "model": config.model,
            "provider": "azure",
            "usage": {"total_tokens": len(prompt) // 4}
        }

    async def _call_bedrock(
        self,
        config: ProviderConfig,
        prompt: str,
        max_tokens: Optional[int]
    ) -> Dict[str, Any]:
        """Call AWS Bedrock."""
        # Check for credentials
        access_key = os.getenv("AWS_ACCESS_KEY_ID")
        secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")

        if not access_key or not secret_key:
            raise RuntimeError("AWS Bedrock credentials not configured")

        logger.info(f"Calling AWS Bedrock: {config.model}")
        return {
            "content": f"[Bedrock response placeholder - model: {config.model}]",
            "model": config.model,
            "provider": "bedrock",
            "usage": {"total_tokens": len(prompt) // 4}
        }

    async def _call_vertexai(
        self,
        config: ProviderConfig,
        prompt: str,
        max_tokens: Optional[int]
    ) -> Dict[str, Any]:
        """Call Google Vertex AI."""
        project = os.getenv("GOOGLE_CLOUD_PROJECT")
        if not project:
            raise RuntimeError("Google Cloud project not configured")

        logger.info(f"Calling Vertex AI: {config.model}")
        return {
            "content": f"[Vertex AI response placeholder - model: {config.model}]",
            "model": config.model,
            "provider": "vertexai",
            "usage": {"total_tokens": len(prompt) // 4}
        }

    async def _call_ollama(
        self,
        config: ProviderConfig,
        prompt: str,
        max_tokens: Optional[int]
    ) -> Dict[str, Any]:
        """Call local Ollama instance."""
        import httpx

        base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{base_url}/api/generate",
                    json={
                        "model": config.model or "qwen2.5-coder",
                        "prompt": prompt,
                        "stream": False
                    }
                )
                response.raise_for_status()
                data = response.json()

                return {
                    "content": data.get("response", ""),
                    "model": config.model,
                    "provider": "ollama",
                    "usage": {"total_tokens": data.get("eval_count", 0)}
                }
        except Exception as e:
            raise RuntimeError(f"Ollama call failed: {e}")

    def _is_circuit_open(self, provider: str) -> bool:
        """Check if circuit breaker is open for provider."""
        state = self._circuit_states.get(provider)
        if not state:
            return False

        if state.status == ProviderStatus.CLOSED:
            return False

        if state.status == ProviderStatus.OPEN:
            # Check recovery timeout
            cb_config = self._config.get("circuit_breaker", {})
            recovery_timeout = cb_config.get("recovery_timeout", 30)

            if time.time() - state.last_failure_time > recovery_timeout:
                state.status = ProviderStatus.HALF_OPEN
                return False
            return True

        return False

    def _record_success(self, provider: str) -> None:
        """Record successful call, reset circuit."""
        if provider in self._circuit_states:
            self._circuit_states[provider] = CircuitState()

    def _record_failure(self, provider: str) -> None:
        """Record failed call, potentially open circuit."""
        state = self._circuit_states.get(provider)
        if not state:
            state = CircuitState()
            self._circuit_states[provider] = state

        state.failure_count += 1
        state.last_failure_time = time.time()

        cb_config = self._config.get("circuit_breaker", {})
        threshold = cb_config.get("failure_threshold", 3)

        if state.failure_count >= threshold:
            state.status = ProviderStatus.OPEN
            logger.warning(f"Circuit opened for {provider} after {state.failure_count} failures")

    def get_provider_status(self) -> Dict[str, str]:
        """Get status of all providers."""
        return {
            provider: state.status.value
            for provider, state in self._circuit_states.items()
        }
