from typing import Optional
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.config import settings
from app.db import get_db
from app.models.key import VirtualKey, UsageLog, ResponseCache
from app.models.schemas import (
    KeyUsageSummaryResponse,
    UsageLogItem,
    CacheStatsResponse,
)

router = APIRouter(prefix="/v1/admin", tags=["Usage & Analytics"])


@router.get("/usage", response_model=KeyUsageSummaryResponse)
async def get_key_usage(
    key: str = Query(..., description="Virtual API Key (e.g. gw-live-test)"),
    db: AsyncSession = Depends(get_db),
):
    """
    Answers the core question: 'How much has key X spent?'
    Returns key metadata, current spend, remaining budget, and itemized request logs.
    """
    clean_key = key.strip()
    if clean_key.lower().startswith("bearer "):
        clean_key = clean_key[7:].strip()

    # Query key info
    key_query = select(VirtualKey).where(VirtualKey.key_value == clean_key)
    res_key = await db.execute(key_query)
    key_obj = res_key.scalars().first()

    if not key_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": f"Virtual key '{clean_key}' not found."},
        )

    # Query usage logs for this key
    logs_query = (
        select(UsageLog)
        .where(UsageLog.key_value == clean_key)
        .order_by(UsageLog.timestamp.desc())
        .limit(50)
    )
    res_logs = await db.execute(logs_query)
    logs = res_logs.scalars().all()

    # Aggregate stats
    agg_query = select(
        func.count(UsageLog.id),
        func.coalesce(func.sum(UsageLog.total_tokens), 0),
    ).where(UsageLog.key_value == clean_key)
    res_agg = await db.execute(agg_query)
    total_requests, total_tokens = res_agg.first()

    log_items = [
        UsageLogItem(
            id=l.id,
            provider_used=l.provider_used,
            model=l.model,
            prompt_tokens=l.prompt_tokens,
            completion_tokens=l.completion_tokens,
            total_tokens=l.total_tokens,
            cost=l.cost,
            cost_saved=l.cost_saved,
            latency_ms=round(l.latency_ms, 2),
            is_cache_hit=l.is_cache_hit,
            timestamp=l.timestamp,
        )
        for l in logs
    ]

    return KeyUsageSummaryResponse(
        key_value=key_obj.key_value,
        name=key_obj.name,
        max_budget_usd=key_obj.max_budget,
        current_spend_usd=key_obj.current_spend,
        remaining_budget_usd=key_obj.remaining_budget(),
        is_exhausted=key_obj.is_exhausted(),
        total_requests=total_requests or 0,
        total_tokens=total_tokens or 0,
        recent_logs=log_items,
    )


@router.get("/cache/stats", response_model=CacheStatsResponse)
async def get_cache_stats(db: AsyncSession = Depends(get_db)):
    """Retrieve cache hit rate metrics and cumulative USD cost saved."""
    count_query = select(func.count(ResponseCache.prompt_hash))
    hits_query = select(func.coalesce(func.sum(ResponseCache.hit_count), 0))
    savings_query = select(func.coalesce(func.sum(ResponseCache.cost_saved), 0.0))

    total_entries = (await db.execute(count_query)).scalar() or 0
    total_hits = (await db.execute(hits_query)).scalar() or 0
    total_saved = (await db.execute(savings_query)).scalar() or 0.0

    return CacheStatsResponse(
        cache_enabled=settings.CACHE_ENABLED,
        total_cached_entries=total_entries,
        total_cache_hits=total_hits,
        total_cost_saved_usd=round(total_saved, 6),
    )

