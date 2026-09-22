from typing import Optional
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from app.models.key import VirtualKey, UsageLog, utc_now


class UsageService:
    """Handles key authentication, pre-request budget checks, and atomic post-request usage logging."""

    async def validate_virtual_key_and_budget(
        self, session: AsyncSession, raw_key: str
    ) -> VirtualKey:
        """
        Validate that virtual key exists, is active, and is strictly under its budget cap.
        Throws HTTP 401 if key invalid, HTTP 403 if revoked, HTTP 429 if budget exceeded.
        """
        cleaned_key = raw_key.strip()
        if cleaned_key.lower().startswith("bearer "):
            cleaned_key = cleaned_key[7:].strip()

        query = select(VirtualKey).where(VirtualKey.key_value == cleaned_key)
        result = await session.execute(query)
        virtual_key = result.scalars().first()

        if not virtual_key:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "error": {
                        "message": "Invalid virtual API key provided.",
                        "type": "authentication_error",
                        "code": 401,
                    }
                },
                headers={"WWW-Authenticate": "Bearer"},
            )

        if not virtual_key.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": {
                        "message": "Virtual API key is deactivated or revoked.",
                        "type": "permission_denied",
                        "code": 403,
                    }
                },
            )

        # Per-Key Budget Enforcement Check
        if virtual_key.current_spend >= virtual_key.max_budget:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "error": {
                        "message": (
                            f"Budget limit exceeded for key '{virtual_key.name}'. "
                            f"Current spend: ${virtual_key.current_spend:.4f} USD, "
                            f"Spending cap: ${virtual_key.max_budget:.4f} USD."
                        ),
                        "type": "budget_exceeded",
                        "code": 429,
                        "current_spend_usd": virtual_key.current_spend,
                        "max_budget_usd": virtual_key.max_budget,
                    }
                },
            )

        return virtual_key

    async def record_usage(
        self,
        session: AsyncSession,
        key_value: str,
        provider_used: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        cost: float,
        latency_ms: float,
        status_code: int = 200,
        is_cache_hit: bool = False,
        cost_saved: float = 0.0,
    ) -> UsageLog:
        """
        Atomically increment key spend balance and record request usage log.
        """
        # 1. Atomic balance increment in SQL
        await session.execute(
            update(VirtualKey)
            .where(VirtualKey.key_value == key_value)
            .values(current_spend=VirtualKey.current_spend + cost)
        )

        # 2. Insert persistent usage log entry
        log_entry = UsageLog(
            key_value=key_value,
            provider_used=provider_used,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            cost=cost,
            cost_saved=cost_saved,
            latency_ms=latency_ms,
            status_code=status_code,
            is_cache_hit=is_cache_hit,
            timestamp=utc_now(),
        )
        session.add(log_entry)
        await session.commit()
        await session.refresh(log_entry)
        return log_entry


usage_service = UsageService()

