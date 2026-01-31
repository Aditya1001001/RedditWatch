"""Anthropic Claude LLM provider."""

import os
import time
from typing import Optional

import httpx

from app.config import Config
from app.llm.base import BaseLLMProvider, LLMProviderError, LLMResponse


class ClaudeProvider(BaseLLMProvider):
    """
    Anthropic Claude API provider.

    Requires ANTHROPIC_API_KEY environment variable.
    """

    API_URL = "https://api.anthropic.com/v1/messages"
    API_VERSION = "2023-06-01"

    def __init__(self, config: Config):
        self.api_key = os.getenv("ANTHROPIC_API_KEY", "")
        self.model = config.llm.claude.model
        self.max_tokens = config.llm.claude.max_tokens

    @property
    def name(self) -> str:
        return "claude"

    @property
    def model_name(self) -> str:
        return self.model

    async def is_available(self) -> bool:
        """Check if API key is configured."""
        return bool(self.api_key and self.api_key.startswith("sk-ant-"))

    async def generate(
        self,
        prompt: str,
        system: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 2048,
    ) -> LLMResponse:
        """Generate a response using Claude API."""
        if not await self.is_available():
            raise LLMProviderError("Claude API key not configured")

        start_time = time.time()

        # Build request payload
        payload = {
            "model": self.model,
            "max_tokens": min(max_tokens, self.max_tokens),
            "temperature": temperature,
            "messages": [{"role": "user", "content": prompt}],
        }

        if system:
            payload["system"] = system

        headers = {
            "Content-Type": "application/json",
            "X-API-Key": self.api_key,
            "anthropic-version": self.API_VERSION,
        }

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    self.API_URL,
                    json=payload,
                    headers=headers,
                )

                if response.status_code != 200:
                    error_data = response.json() if response.content else {}
                    error_msg = error_data.get("error", {}).get("message", response.text)
                    raise LLMProviderError(f"Claude API error ({response.status_code}): {error_msg}")

                data = response.json()
                latency_ms = int((time.time() - start_time) * 1000)

                # Extract content from response
                content = ""
                for block in data.get("content", []):
                    if block.get("type") == "text":
                        content += block.get("text", "")

                # Calculate tokens used
                usage = data.get("usage", {})
                tokens_used = usage.get("input_tokens", 0) + usage.get("output_tokens", 0)

                return LLMResponse(
                    content=content,
                    model=self.model,
                    provider=self.name,
                    tokens_used=tokens_used,
                    latency_ms=latency_ms,
                )

        except httpx.TimeoutException:
            raise LLMProviderError("Claude API request timed out")
        except httpx.RequestError as e:
            raise LLMProviderError(f"Claude API request failed: {e}")
