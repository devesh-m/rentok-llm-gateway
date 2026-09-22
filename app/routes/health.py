from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.config import settings
from app.db import get_db

router = APIRouter(tags=["Health & Status"])


@router.get("/health", summary="Service Liveness Probe")
async def health_check(db: AsyncSession = Depends(get_db)):
    """Health check endpoint verifying database connectivity and configuration."""
    db_status = "healthy"
    try:
        await db.execute(text("SELECT 1"))
    except Exception as exc:
        db_status = f"unhealthy: {str(exc)}"

    return {
        "status": "healthy" if db_status == "healthy" else "degraded",
        "service": settings.APP_NAME,
        "version": settings.VERSION,
        "database": db_status,
        "providers": {
            "groq_configured": bool(settings.GROQ_API_KEY),
            "gemini_configured": bool(settings.GEMINI_API_KEY),
            "mock_fallback_enabled": settings.ENABLE_MOCK_FALLBACK,
        },
    }


@router.get("/", include_in_schema=False)
async def root():
    return {
        "message": f"{settings.APP_NAME} is running.",
        "documentation": "/docs",
        "health": "/health",
    }

