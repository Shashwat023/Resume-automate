"""
Shared fixtures. Repository/service tests get a real async session against
an in-memory SQLite DB (fast, no mocking of SQLAlchemy needed, and it
actually exercises the queries). API-level tests get an httpx AsyncClient
wired to the FastAPI app with get_db overridden to the same in-memory DB —
the app's lifespan is deliberately NOT run for these tests, so nothing
attempts to launch a real Chrome session or touch the real app.db file.
"""

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.db import Base, get_db
from app.core.config import get_settings


@pytest.fixture(autouse=True)
def hermetic_openrouter(monkeypatch):
    """Keep tests independent of developer credentials and live API state."""
    settings = get_settings()
    monkeypatch.setattr(settings, "openrouter_api_key", "test-key")
    monkeypatch.setattr(settings, "twocaptcha_api_key", None)
    monkeypatch.setattr(settings, "captcha_proxy_url", None)
    monkeypatch.setattr(settings, "submit_enabled", False)

    async def no_preflight(*_args, **_kwargs):
        return None

    from app.services.engine import llm_client
    from app.services.scraper import bulk_sync_service, sync_service

    monkeypatch.setattr(llm_client, "preflight_check", no_preflight)
    monkeypatch.setattr(bulk_sync_service, "preflight_check", no_preflight)
    monkeypatch.setattr(sync_service, "preflight_check", no_preflight, raising=False)

    real_post = httpx.AsyncClient.post

    async def guarded_post(self, url, *args, **kwargs):
        if isinstance(getattr(self, "_transport", None), httpx.MockTransport):
            return await real_post(self, url, *args, **kwargs)
        if "openrouter.ai" in str(url).lower():
            raise AssertionError(f"test attempted a live OpenRouter request: {url}")
        return await real_post(self, url, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "post", guarded_post)


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
