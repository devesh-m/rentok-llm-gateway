import os
import secrets
from typing import AsyncGenerator
from sqlalchemy import event, select
from sqlalchemy.pool import NullPool
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncSession,
    async_sessionmaker,
)
from app.config import settings
from app.models.key import Base, VirtualKey


def get_normalized_database_url(url: str) -> str:
    """Normalize DATABASE_URL for async SQLAlchemy drivers."""
    # In Linux cloud containers, use /tmp for SQLite if default relative path is specified
    if os.name != "nt" and url in ("sqlite:///./gateway.db", "sqlite+aiosqlite:///./gateway.db"):
        return "sqlite+aiosqlite:////tmp/gateway.db"

    if url.startswith("sqlite:///") and not url.startswith("sqlite+aiosqlite:///"):
        return url.replace("sqlite:///", "sqlite+aiosqlite:///")
    elif url.startswith("sqlite://") and not url.startswith("sqlite+aiosqlite://"):
        return url.replace("sqlite://", "sqlite+aiosqlite://")
    elif url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgresql://") and not url.startswith("postgresql+asyncpg://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


db_url = get_normalized_database_url(settings.DATABASE_URL)
is_sqlite = db_url.startswith("sqlite")

connect_args = {"check_same_thread": False, "timeout": 10} if is_sqlite else {}
engine_kwargs = {"poolclass": NullPool} if is_sqlite else {}

engine = create_async_engine(
    db_url,
    echo=False,
    connect_args=connect_args,
    **engine_kwargs,
)

# Enable WAL (Write-Ahead Logging) mode for SQLite to maximize concurrent read/write performance
if is_sqlite:
    @event.listens_for(engine.sync_engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency that yields a database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db() -> None:
    """Initialize database tables and seed test virtual keys if not already present."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Seed default virtual keys for instant testing
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(VirtualKey))
        existing = result.scalars().first()
        if not existing:
            # Active test key with $1.00 budget
            test_key = VirtualKey(
                key_value="gw-live-test",
                name="Default Active Test Key",
                max_budget=1.00,
                current_spend=0.00,
                is_active=True,
            )
            # Exhausted test key with $0.00 budget for testing 429 budget rejection
            exhausted_key = VirtualKey(
                key_value="gw-live-exhausted",
                name="Exhausted Budget Test Key",
                max_budget=0.00,
                current_spend=0.0001,
                is_active=True,
            )
            session.add_all([test_key, exhausted_key])
            await session.commit()
            print("Database initialized and default virtual keys seeded: ['gw-live-test', 'gw-live-exhausted']")

