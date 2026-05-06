"""Configuration loader for CAPL Pipeline V2.2.

Loads and validates configuration from .env and YAML files.
"""

from pathlib import Path
from typing import Dict, Any, Optional
import os
import yaml
import logging
from dotenv import load_dotenv

logger = logging.getLogger(__name__)


class ConfigLoader:
    """
    Load and validate configuration from environment and YAML files.

    Handles:
    - .env file loading
    - api_config.yaml parsing
    - Environment variable overrides
    - Validation of required fields
    """

    def __init__(self, config_dir: Optional[Path] = None) -> None:
        self.config_dir = config_dir or Path.cwd()
        self.env_loaded = False
        self._config: Dict[str, Any] = {}
        self._api_config: Dict[str, Any] = {}

    def load(self) -> Dict[str, Any]:
        """Load all configuration sources."""
        # Load .env file
        self._load_env()

        # Load api_config.yaml
        self._load_api_config()

        # Build combined config
        self._config = {
            "logging": self._load_logging_config(),
            "llm": self._load_llm_config(),
            "sto": self._load_sto_config(),
            "canoe": self._load_canoe_config(),
            "performance": self._load_performance_config(),
            "compliance": self._load_compliance_config(),
            "features": self._load_feature_flags(),
        }

        return self._config

    def _load_env(self) -> None:
        """Load environment variables from .env file."""
        env_path = self.config_dir / ".env"
        if env_path.exists():
            load_dotenv(env_path)
            self.env_loaded = True
            logger.info(f"Loaded environment from {env_path}")

    def _load_api_config(self) -> Dict[str, Any]:
        """Load api_config.yaml."""
        api_config_path = self.config_dir / "api_config.yaml"
        if api_config_path.exists():
            with open(api_config_path, 'r', encoding='utf-8') as f:
                self._api_config = yaml.safe_load(f) or {}
            logger.info(f"Loaded API config from {api_config_path}")
        return self._api_config

    def _load_logging_config(self) -> Dict[str, Any]:
        """Load logging configuration."""
        return {
            "level": os.getenv("LOG_LEVEL", "INFO"),
            "verbose": os.getenv("LOG_VERBOSE", "false").lower() == "true",
            "file": os.getenv("LOG_FILE", "logs/pipeline.log"),
        }

    def _load_llm_config(self) -> Dict[str, Any]:
        """Load LLM configuration."""
        api_llm = self._api_config.get("llm", {})

        return {
            "primary_provider": os.getenv("LLM_PRIMARY_PROVIDER", api_llm.get("preferred", {}).get("provider", "azure")),
            "primary_model": os.getenv("LLM_PRIMARY_MODEL", api_llm.get("preferred", {}).get("model", "o3-mini")),
            "secondary_provider": os.getenv("LLM_SECONDARY_PROVIDER", "azure"),
            "secondary_model": os.getenv("LLM_SECONDARY_MODEL", "gpt-5-mini"),
            "tertiary_provider": os.getenv("LLM_TERTIARY_PROVIDER", "bedrock"),
            "tertiary_model": os.getenv("LLM_TERTIARY_MODEL", "claude-haiku-4-5"),
            "lightweight_model": os.getenv("LLM_LIGHTWEIGHT_MODEL", "gpt-5-nano"),
            "timeout": int(os.getenv("LLM_TIMEOUT", "30")),
            "max_retries": int(os.getenv("LLM_MAX_RETRIES", "2")),
            "cache_enabled": os.getenv("LLM_CACHE_ENABLED", "true").lower() == "true",
            "cache_ttl": int(os.getenv("LLM_CACHE_TTL", "3600")),
            "fallback_chain": api_llm.get("fallback_chain", []),
            "task_overrides": api_llm.get("task_overrides", {}),
            "circuit_breaker": self._api_config.get("circuit_breaker", {}),
            "token_budget": self._api_config.get("token_budget", {}),
        }

    def _load_sto_config(self) -> Dict[str, Any]:
        """Load STO processing configuration."""
        return {
            "enrich_auto": os.getenv("STO_ENRICH_AUTO", "true").lower() == "true",
            "drop_threshold": float(os.getenv("STO_DROP_THRESHOLD", "0.20")),
            "spec_format": os.getenv("STO_SPEC_FORMAT", "docx"),
        }

    def _load_canoe_config(self) -> Dict[str, Any]:
        """Load CANoe integration configuration."""
        return {
            "path": os.getenv("CANOE_PATH", ""),
            "version": os.getenv("CANOE_VERSION", ""),
            "cli_timeout": int(os.getenv("CANOE_CLI_TIMEOUT", "60")),
        }

    def _load_performance_config(self) -> Dict[str, Any]:
        """Load performance configuration."""
        return {
            "max_parallel_tasks": int(os.getenv("MAX_PARALLEL_TASKS", "4")),
            "max_memory_mb": int(os.getenv("MAX_MEMORY_MB", "2048")),
            "cache_signal_resolution": os.getenv("CACHE_SIGNAL_RESOLUTION", "true").lower() == "true",
        }

    def _load_compliance_config(self) -> Dict[str, Any]:
        """Load compliance configuration."""
        return {
            "mode": os.getenv("COMPLIANCE_MODE", "false").lower() == "true",
            "retention_days": int(os.getenv("AUDIT_RETENTION_DAYS", "90")),
            "traceability_format": os.getenv("TRACEABILITY_FORMAT", "jsonld"),
        }

    def _load_feature_flags(self) -> Dict[str, Any]:
        """Load feature flags."""
        return {
            "enable_helper_suggestions": os.getenv("ENABLE_HELPER_SUGGESTIONS", "true").lower() == "true",
            "enable_template_browser": os.getenv("ENABLE_TEMPLATE_BROWSER", "true").lower() == "true",
            "enable_incremental_generation": os.getenv("ENABLE_INCREMENTAL_GENERATION", "true").lower() == "true",
            "enable_dry_run": os.getenv("ENABLE_DRY_RUN", "false").lower() == "true",
        }

    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value by key path (e.g., 'llm.primary_model')."""
        keys = key.split(".")
        value = self._config
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
        return value if value is not None else default

    def get_api_config(self) -> Dict[str, Any]:
        """Get raw API configuration."""
        return self._api_config

    def validate(self) -> tuple[bool, list[str]]:
        """Validate configuration completeness."""
        errors = []

        # Check required LLM settings
        if not self.get("llm.primary_provider"):
            errors.append("LLM_PRIMARY_PROVIDER not configured")

        if not self.get("llm.primary_model"):
            errors.append("LLM_PRIMARY_MODEL not configured")

        # Check compliance mode requirements
        if self.get("compliance.mode"):
            if not self.get("llm.cache_enabled"):
                errors.append("Cache should be enabled in compliance mode")

        return len(errors) == 0, errors
