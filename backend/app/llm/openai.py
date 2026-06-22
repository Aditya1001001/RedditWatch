"""OpenAI LLM provider."""

import asyncio
import logging
import os
import time
from typing import Optional

import httpx

from app.config import Config
from app.llm.base import BaseLLMProvider, LLMProviderError, LLMResponse

logger = logging.getLogger(__name__)


class OpenAIProvider(BaseLLMProvider):
    """
    OpenAI-compatible API provider.

    Works with OpenAI, Groq, DeepSeek, and any OpenAI-compatible endpoint.
    Requires OPENAI_API_KEY environment variable.
    """

    def __init__(self, config: Config):
        self.api_key = os.getenv("OPENAI_API_KEY", "")
        self.model = config.llm.openai.model
        self.max_tokens = config.llm.openai.max_tokens
        self.base_url = config.llm.openai.base_url.rstrip("/")

    @property
    def name(self) -> str:
        return "openai"

    @property
    def model_name(self) -> str:
        return self.model

    async def is_available(self) -> bool:
        """Check if API key is configured."""
        return bool(self.api_key)

    async def generate(
        self,
        prompt: str,
        system: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 2048,
    ) -> LLMResponse:
        """Generate a response using OpenAI API."""
        if not await self.is_available():
            raise LLMProviderError("OpenAI API key not configured")

        start_time = time.time()

        # Build messages
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": min(max_tokens, self.max_tokens),
        }

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        max_retries = 5

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = None

                for attempt in range(max_retries):
                    response = await client.post(
                        f"{self.base_url}/chat/completions",
                        json=payload,
                        headers=headers,
                    )

                    if response.status_code == 429:
                        retry_after = float(
                            response.headers.get("retry-after", 2 ** attempt)
                        )
                        wait_time = min(retry_after, 60)
                        logger.warning(
                            f"Rate limited (429), retrying in {wait_time:.1f}s "
                            f"(attempt {attempt + 1}/{max_retries})"
                        )
                        await asyncio.sleep(wait_time)
                        continue

                    break  # Not a 429, proceed

                if response.status_code != 200:
                    error_data = response.json() if response.content else {}
                    error_msg = error_data.get("error", {}).get("message", response.text)
                    raise LLMProviderError(f"OpenAI API error ({response.status_code}): {error_msg}")

                data = response.json()
                latency_ms = int((time.time() - start_time) * 1000)

                # Extract content
                content = data["choices"][0]["message"]["content"]

                # Calculate tokens used
                usage = data.get("usage", {})
                tokens_used = usage.get("total_tokens", 0)

                return LLMResponse(
                    content=content,
                    model=self.model,
                    provider=self.name,
                    tokens_used=tokens_used,
                    latency_ms=latency_ms,
                )

        except httpx.TimeoutException:
            raise LLMProviderError("OpenAI API request timed out")
        except httpx.RequestError as e:
            raise LLMProviderError(f"OpenAI API request failed: {e}")
