import time
from typing import Optional
from fastapi import APIRouter, Depends, Header, Response, Security, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import get_db
from app.models.schemas import ChatCompletionRequest, ChatCompletionResponse
from app.services.usage_service import usage_service
from app.services.cache_service import cache_service, generate_prompt_hash
from app.services.llm_client import llm_client

router = APIRouter(tags=["Chat Completions"])
security = HTTPBearer(auto_error=False)


@router.post(
    "/v1/chat/completions",
    response_model=ChatCompletionResponse,
    summary="OpenAI-compatible Chat Completion Proxy",
)
@router.post(
    "/chat/completions",
    response_model=ChatCompletionResponse,
    include_in_schema=False,
)
async def chat_completions(
    request: ChatCompletionRequest,
    response: Response,
    x_api_key: Optional[str] = Header(
        default="gw-live-test",
        description="Virtual API Key (e.g., gw-live-test or gw-live-exhausted)",
    ),
    bearer: Optional[HTTPAuthorizationCredentials] = Security(security),
    authorization: Optional[str] = Header(default=None, include_in_schema=False),
    db: AsyncSession = Depends(get_db),
):
    """
    Core LLM Gateway proxy endpoint:
    1. Authenticates virtual API key (via Authorization: Bearer <key> or X-API-Key: <key>) & verifies remaining budget.
    2. Checks exact-match cache for identical prior prompt.
    3. Forwards to Primary Provider (Groq) with automatic fallback to Secondary (Gemini) or Mock.
    4. Atomically logs token usage, calculates spend in USD, and increments key balance.
    """
    # Resolve key from Authorization Bearer header first, then X-API-Key header
    raw_key = None
    if bearer and bearer.credentials:
        raw_key = bearer.credentials
    elif authorization:
        raw_key = authorization
    elif x_api_key:
        raw_key = x_api_key

    if not raw_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": {
                    "message": "Missing virtual API key. Provide 'Authorization: Bearer gw-live-...' or 'X-API-Key: gw-live-...'",
                    "type": "authentication_error",
                    "code": 401,
                }
            },
        )

    # 1. Pre-Check: Authenticate Key & Enforce Budget
    key_obj = await usage_service.validate_virtual_key_and_budget(db, raw_key)

    # 2. Smart Semantic + Exact Cache Check (Stretch Goal)
    prompt_hash = generate_prompt_hash(request)
    cached_result = await cache_service.get(db, prompt_hash, request=request)

    if cached_result:
        cached_response, cost_saved = cached_result
        response.headers["X-Cache"] = "HIT"
        response.headers["X-Provider"] = "cache"
        response.headers["X-Cost-Saved-USD"] = str(cost_saved)

        # Log cache hit with $0.00 cost incurred
        await usage_service.record_usage(
            session=db,
            key_value=key_obj.key_value,
            provider_used="cache",
            model=cached_response.model,
            prompt_tokens=cached_response.usage.prompt_tokens,
            completion_tokens=cached_response.usage.completion_tokens,
            cost=0.00,
            latency_ms=1.5,
            status_code=200,
            is_cache_hit=True,
            cost_saved=cost_saved,
        )
        return cached_response

    # 3. Cache Miss: Dispatch to LLM Proxy with Fallback Resilience
    response.headers["X-Cache"] = "MISS"
    llm_response, provider_used, latency_ms, cost_usd = await llm_client.call_llm(request)

    response.headers["X-Provider"] = provider_used
    response.headers["X-Latency-Ms"] = f"{latency_ms:.2f}"
    response.headers["X-Request-Cost-USD"] = f"{cost_usd:.8f}"

    # 4. Atomic Spend Accounting & Request Logging
    await usage_service.record_usage(
        session=db,
        key_value=key_obj.key_value,
        provider_used=provider_used,
        model=llm_response.model,
        prompt_tokens=llm_response.usage.prompt_tokens,
        completion_tokens=llm_response.usage.completion_tokens,
        cost=cost_usd,
        latency_ms=latency_ms,
        status_code=200,
        is_cache_hit=False,
        cost_saved=0.0,
    )

    # 5. Populate Cache for subsequent exact & semantic requests
    await cache_service.set(
        session=db,
        prompt_hash=prompt_hash,
        model=llm_response.model,
        response=llm_response,
        cost=cost_usd,
        request=request,
    )

    return llm_response

