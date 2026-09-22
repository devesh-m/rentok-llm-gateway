import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.main import app
from app.db import get_db, init_db
from app.models.key import Base, VirtualKey

# Use in-memory SQLite for fast, isolated test execution
TEST_DB_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(
    TEST_DB_URL,
    connect_args={"check_same_thread": False},
)

TestAsyncSessionLocal = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def override_get_db():
    async with TestAsyncSessionLocal() as session:
        yield session


app.dependency_overrides[get_db] = override_get_db


@pytest_asyncio.fixture(autouse=True)
async def prepare_database():
    """Create fresh tables and seed test keys before each test."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    async with TestAsyncSessionLocal() as session:
        # Seed test keys
        active_key = VirtualKey(
            key_value="gw-live-test",
            name="Default Active Test Key",
            max_budget=1.00,
            current_spend=0.00,
            is_active=True,
        )
        exhausted_key = VirtualKey(
            key_value="gw-live-exhausted",
            name="Exhausted Budget Key",
            max_budget=0.00,
            current_spend=0.0001,
            is_active=True,
        )
        session.add_all([active_key, exhausted_key])
        await session.commit()

    yield

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

