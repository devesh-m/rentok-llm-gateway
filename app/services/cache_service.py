import hashlib
import json
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.config import settings
from app.models.key import ResponseCache, utc_now
from app.models.schemas import ChatCompletionRequest, ChatCompletionResponse


def generate_prompt_hash(request: ChatCompletionRequest) -> str:
    """Generate a deterministic SHA-256 hash for a normalized chat completion request."""
    normalized_messages = [
        {"role": m.role.strip().lower(), "content": m.content.strip()}
        for m in request.messages
    ]
    payload = {
        "model": (request.model or settings.PRIMARY_MODEL).strip().lower(),
        "messages": normalized_messages,
        "temperature": request.temperature,
    }
    encoded = json.dumps(payload, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class CacheService:
    """Manages exact-match semantic caching, TTL expiration, and cost savings accounting."""

    async def get(
        self, session: AsyncSession, prompt_hash: str
    ) -> Optional[Tuple[ChatCompletionResponse, float]]:
        """
        Check if a cached response exists and is still valid.
        Returns: (cached_response, cost_saved) or None
        """
        if not settings.CACHE_ENABLED:
            return None

        query = select(ResponseCache).where(
            ResponseCache.prompt_hash == prompt_hash,
            ResponseCache.expires_at > utc_now(),
        )
        result = await session.execute(query)
        cache_entry = result.scalars().first()

        if not cache_entry:
            return None

        # Cache Hit! Update metrics
        cost_saved = cache_entry.estimated_cost
        cache_entry.hit_count += 1
        cache_entry.cost_saved += cost_saved
        await session.commit()

        # Reconstruct ChatCompletionResponse from stored JSON
        response_dict = json.loads(cache_entry.response_json)
        response_obj = ChatCompletionResponse(**response_dict)
        return response_obj, cost_saved

    async def set(
        self,
        session: AsyncSession,
        prompt_hash: str,
        model: str,
        response: ChatCompletionResponse,
        cost: float,
    ) -> None:
        """Store a successful LLM response into the cache with TTL."""
        if not settings.CACHE_ENABLED:
            return

        expires_at = utc_now() + timedelta(seconds=settings.CACHE_TTL_SECONDS)
        
        # Strip gateway-specific dynamic latency before caching response payload
        cleaned_response = response.model_dump()
        if "gateway_metadata" in cleaned_response and cleaned_response["gateway_metadata"]:
            cleaned_response["gateway_metadata"]["cached"] = True

        cache_entry = ResponseCache(
            prompt_hash=prompt_hash,
            model=model,
            response_json=json.dumps(cleaned_response),
            prompt_tokens=response.usage.prompt_tokens,
            completion_tokens=response.usage.completion_tokens,
            estimated_cost=cost,
            hit_count=0,
            cost_saved=0.0,
            expires_at=expires_at,
        )
        session.add(cache_entry)
        await session.commit()


cache_service = CacheService()

