"""OpenAI-compatible HTTP client for LLM requests."""
import json
from typing import Optional
from pathlib import Path

import requests
import yaml


class LLMHttpClient:
    """HTTP client for OpenAI-compatible LLM APIs."""

    def __init__(self, config_path: Optional[Path] = None):
        config_path = config_path or Path("llm_config.yaml")
        if not config_path.exists():
            raise FileNotFoundError(f"LLM config not found: {config_path}")
        with open(config_path) as f:
            self.config = yaml.safe_load(f)

    def chat_completion(
        self,
        messages: list[dict],
        max_tokens: int = 1024,
        temperature: float = 0.7,
        json_mode: bool = False,
    ) -> dict:
        """Send a chat completion request."""
        import os
        api_key = os.environ.get(self.config["api_key_env"])
        if not api_key:
            raise RuntimeError(f"API key env var {self.config['api_key_env']} not set")

        payload = {
            "model": self.config["model"],
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if json_mode and self.config.get("supports_json_mode"):
            payload["response_format"] = {"type": "json_object"}

        response = requests.post(
            f"{self.config['base_url']}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=60,
        )
        response.raise_for_status()
        return response.json()
