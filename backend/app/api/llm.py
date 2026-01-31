"""LLM provider API endpoints."""

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.config import get_config
from app.llm import LLMProviderError, get_llm_provider
from app.llm.factory import check_all_providers

router = APIRouter()


class LLMStatusResponse(BaseModel):
    """Response for LLM status endpoint."""

    providers: dict
    active_provider: Optional[str] = None
    active_model: Optional[str] = None


class LLMTestRequest(BaseModel):
    """Request for LLM test endpoint."""

    prompt: str = "Say 'Hello, RedditWatch is working!' in exactly those words."


class LLMTestResponse(BaseModel):
    """Response for LLM test endpoint."""

    success: bool
    provider: str
    model: str
    response: str
    tokens_used: Optional[int] = None
    latency_ms: Optional[int] = None


@router.get("/status", response_model=LLMStatusResponse)
async def get_llm_status():
    """
    Get status of all LLM providers.

    Returns availability status for each configured provider.
    """
    config = get_config()
    providers = await check_all_providers(config)

    # Find active provider
    active_provider = None
    active_model = None

    try:
        provider = await get_llm_provider(config)
        active_provider = provider.name
        active_model = provider.model_name
    except LLMProviderError:
        pass

    return LLMStatusResponse(
        providers=providers,
        active_provider=active_provider,
        active_model=active_model,
    )


@router.post("/test", response_model=LLMTestResponse)
async def test_llm(request: LLMTestRequest):
    """
    Test the LLM provider with a simple prompt.

    This verifies that the LLM is working correctly.
    """
    try:
        provider = await get_llm_provider()
        response = await provider.generate(
            prompt=request.prompt,
            temperature=0.1,
            max_tokens=100,
        )

        return LLMTestResponse(
            success=True,
            provider=provider.name,
            model=provider.model_name,
            response=response.content,
            tokens_used=response.tokens_used,
            latency_ms=response.latency_ms,
        )

    except LLMProviderError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.post("/test-json")
async def test_llm_json():
    """
    Test the LLM's JSON generation capability.

    This is important for the analysis features which rely on structured output.
    """
    try:
        provider = await get_llm_provider()
        result = await provider.generate_json(
            prompt='Generate a JSON object with fields: "name" (string), "score" (number 1-100), "tags" (array of 3 strings). Make it about a fictional startup idea.',
        )

        return {
            "success": True,
            "provider": provider.name,
            "model": provider.model_name,
            "parsed_json": result,
        }

    except LLMProviderError as e:
        raise HTTPException(status_code=503, detail=str(e))
