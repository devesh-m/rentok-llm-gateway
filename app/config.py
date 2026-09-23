import os
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Server & Environment
    PORT: int = 8000
    ENV: str = "development"
    APP_NAME: str = "RentOk Minimal LLM Gateway"
    VERSION: str = "1.0.0"

    # Database: SQLite WAL by default, PostgreSQL if provided
    DATABASE_URL: str = "sqlite:///./gateway.db"

    # Admin Master Secret (Used for managing keys and administrative queries)
    ADMIN_SECRET_KEY: str = "dev-admin-secret-change-in-production"

    # Primary Provider (Groq)
    GROQ_API_KEY: Optional[str] = None
    GROQ_BASE_URL: str = "https://api.groq.com/openai/v1"
    PRIMARY_MODEL: str = "openai/gpt-oss-20b"

    # Secondary / Fallback Provider (OpenRouter Free Auto-Router)
    OPENROUTER_API_KEY: Optional[str] = None
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    FALLBACK_MODEL: str = "openrouter/free"

    # Resilience & Timeouts
    REQUEST_TIMEOUT_SECONDS: float = 15.0
    ENABLE_MOCK_FALLBACK: bool = True

    # Caching (Stretch Goal)
    CACHE_ENABLED: bool = True
    CACHE_TTL_SECONDS: int = 3600

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()

