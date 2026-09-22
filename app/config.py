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
    PRIMARY_MODEL: str = "llama-3.3-70b-versatile"
    PRIMARY_MODEL: str = "openai/gpt-oss-20b"

    # Secondary / Fallback Provider (Gemini OpenAI-compatible endpoint)
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_BASE_URL: str = "https://generativelanguage.googleapis.com/v1beta/openai"
    FALLBACK_MODEL: str = "gemini-1.5-flash"

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

