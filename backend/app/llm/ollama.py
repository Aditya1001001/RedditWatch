"""Ollama LLM provider for local inference."""

import time
from typing import Optional

import httpx

from app.config import Config
from app.llm.base import BaseLLMProvider, LLMProviderError, LLMResponse


class OllamaProvider(BaseLLMProvider):
    """
    Ollama provider for local LLM inference.

    Ollama must be running locally (default: http://localhost:11434).
    Install: https://ollama.ai
    """

    def __init__(self, config: Config):
        self.base_url = config.llm.ollama.base_url.rstrip("/")
        self.model = config.llm.ollama.model
        self.timeout = config.llm.ollama.timeout

    @property
    def name(self) -> str:
        return "ollama"

    @property
    def model_name(self) -> str:
        return self.model

    async def is_available(self) -> bool:
        """Check if Ollama is running and the model is available."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                # Check if Ollama is running
                response = await client.get(f"{self.base_url}/api/tags")
                if response.status_code != 200:
                    return False

                # Check if our model is available
                data = response.json()
                models = [m["name"] for m in data.get("models", [])]

                # Model names can be "llama3.1:8b" or "llama3.1:8b-instruct-q4_0"
                # Check if any model starts with our model name
                model_base = self.model.split(":")[0]
                return any(m.startswith(model_base) or m == self.model for m in models)

        except (httpx.RequestError, httpx.TimeoutException):
            return False

    async def generate(
        self,
        prompt: str,
        system: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 2048,
    ) -> LLMResponse:
        """Generate a response using Ollama."""
        start_time = time.time()

        # Build the request payload
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }

        if system:
            payload["system"] = system

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/api/generate",
                    json=payload,
                )

                if response.status_code != 200:
                    raise LLMProviderError(
                        f"Ollama returned status {response.status_code}: {response.text}"
                    )

                data = response.json()
                latency_ms = int((time.time() - start_time) * 1000)

                return LLMResponse(
                    content=data.get("response", ""),
                    model=self.model,
                    provider=self.name,
                    tokens_used=data.get("eval_count"),
                    latency_ms=latency_ms,
                )

        except httpx.TimeoutException:
            raise LLMProviderError(
                f"Ollama request timed out after {self.timeout}s. "
                "Try increasing timeout or using a smaller model."
            )
        except httpx.RequestError as e:
            raise LLMProviderError(f"Ollama request failed: {e}")

    async def list_models(self) -> list[str]:
        """List available models in Ollama."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.base_url}/api/tags")
                if response.status_code == 200:
                    data = response.json()
                    return [m["name"] for m in data.get("models", [])]
        except (httpx.RequestError, httpx.TimeoutException):
            pass
        return []

    async def pull_model(self, model_name: str) -> bool:
        """Pull a model from Ollama registry."""
        try:
            async with httpx.AsyncClient(timeout=600.0) as client:  # Long timeout for download
                response = await client.post(
                    f"{self.base_url}/api/pull",
                    json={"name": model_name, "stream": False},
                )
                return response.status_code == 200
        except (httpx.RequestError, httpx.TimeoutException):
            return False
