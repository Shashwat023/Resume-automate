"""
Shared fixtures. Repository/service tests get a real async session against
an in-memory SQLite DB (fast, no mocking of SQLAlchemy needed, and it
actually exercises the queries). API-level tests get an httpx AsyncClient
wired to the FastAPI app with get_db overridden to the same in-memory DB —
the app's lifespan is deliberately NOT run for these tests, so nothing
attempts to launch a real Chrome session or touch the real app.db file.
"""

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.db import Base, get_db


@pytest_asyncio.fixture
async def async_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        from app.models import db_models  # noqa: F401  ensure models are registered

        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest_asyncio.fixture
async def client(async_session: AsyncSession):
    from app.main import app

    async def override_get_db():
        yield async_session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
