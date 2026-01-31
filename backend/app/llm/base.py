"""Base LLM provider interface."""

import json
import re
from abc import ABC, abstractmethod
from typing import Any, Optional

from pydantic import BaseModel


class LLMResponse(BaseModel):
    """Response from an LLM provider."""

    content: str
    model: str
    provider: str
    tokens_used: Optional[int] = None
    latency_ms: Optional[int] = None


class LLMProviderError(Exception):
    """Error from an LLM provider."""

    pass


class BaseLLMProvider(ABC):
    """Abstract base class for LLM providers."""

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        system: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 2048,
    ) -> LLMResponse:
        """
        Generate a response from the LLM.

        Args:
            prompt: The user prompt
            system: Optional system prompt
            temperature: Sampling temperature (0-1)
            max_tokens: Maximum tokens to generate

        Returns:
            LLMResponse with the generated content
        """
        pass

    @abstractmethod
    async def is_available(self) -> bool:
        """
        Check if the provider is available and configured.

        Returns:
            True if the provider can be used
        """
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name for logging and UI."""
        pass

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Model name being used."""
        pass

    async def generate_json(
        self,
        prompt: str,
        system: Optional[str] = None,
        temperature: float = 0.1,
    ) -> Any:
        """
        Generate and parse a JSON response.

        Args:
            prompt: The user prompt (should request JSON output)
            system: Optional system prompt
            temperature: Lower temperature for more consistent JSON

        Returns:
            Parsed JSON object

        Raises:
            LLMProviderError: If JSON parsing fails
        """
        # Add JSON instruction to system prompt
        json_system = (system or "") + "\nYou must respond with valid JSON only. No other text."

        response = await self.generate(
            prompt=prompt,
            system=json_system.strip(),
            temperature=temperature,
        )

        # Try to extract JSON from the response
        content = response.content.strip()

        # Handle markdown code blocks
        if "```json" in content:
            match = re.search(r"```json\s*([\s\S]*?)\s*```", content)
            if match:
                content = match.group(1)
        elif "```" in content:
            match = re.search(r"```\s*([\s\S]*?)\s*```", content)
            if match:
                content = match.group(1)

        try:
            return json.loads(content)
        except json.JSONDecodeError as e:
            raise LLMProviderError(
                f"Failed to parse JSON response: {e}\nResponse was: {response.content[:500]}"
            )
