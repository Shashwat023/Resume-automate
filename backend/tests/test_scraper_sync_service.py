import httpx
import pytest

from app.models.db_models import Job
from app.services.scraper import sync_service


def test_detect_greenhouse_job_boards_subdomain():
    assert (
        sync_service._detect_greenhouse("https://job-boards.greenhouse.io/anthropic")
        == "anthropic"
    )


def test_detect_greenhouse_legacy_subdomain():
    assert (
        sync_service._detect_greenhouse("https://boards.greenhouse.io/openai")
        == "openai"
    )


def test_detect_greenhouse_non_match_returns_none():
    assert sync_service._detect_greenhouse("https://example.com/careers") is None


def test_detect_lever():
    assert sync_service._detect_lever("https://jobs.lever.co/acme") == "acme"


def test_detect_lever_non_match_returns_none():
    assert sync_service._detect_lever("https://example.com/careers") is None


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://www.4liberty.com/", "4liberty.com"),
        ("https://acciona.com/careers", "acciona.com"),
        ("https://www.acsprostaffing.com", "acsprostaffing.com"),
    ],
)
def test_company_name_from_url_strips_www(url, expected):
    assert sync_service._company_name_from_url(url) == expected


async def test_sync_greenhouse_inserts_new_jobs(async_session, monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "jobs": [
                    {
                        "title": "Account Executive",
                        "absolute_url": "https://job-boards.greenhouse.io/anthropic/jobs/1",
                        "location": {"name": "San Francisco, CA"},
                    }
                ]
            }

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url):
            return FakeResponse()

    monkeypatch.setattr(httpx, "AsyncClient", lambda timeout=15: FakeClient())

    inserted, updated = await sync_service._sync_greenhouse("anthropic", async_session)

    assert inserted == 1
    assert updated == 0


async def test_sync_greenhouse_updates_existing_job(async_session, monkeypatch):
    async_session.add(
        Job(
            title="Old Title",
            company_name="anthropic",
            apply_url="https://job-boards.greenhouse.io/anthropic/jobs/1",
        )
    )
    await async_session.commit()

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "jobs": [
                    {
                        "title": "New Title",
                        "absolute_url": "https://job-boards.greenhouse.io/anthropic/jobs/1",
                        "location": {"name": "Remote"},
                    }
                ]
            }

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url):
            return FakeResponse()

    monkeypatch.setattr(httpx, "AsyncClient", lambda timeout=15: FakeClient())

    inserted, updated = await sync_service._sync_greenhouse("anthropic", async_session)

    assert inserted == 0
    assert updated == 1


async def test_sync_company_routes_to_greenhouse(async_session, monkeypatch):
    async def fake_sync_greenhouse(token, db):
        assert token == "anthropic"
        return 5, 2

    monkeypatch.setattr(sync_service, "_sync_greenhouse", fake_sync_greenhouse)

    result = await sync_service.sync_company(
        "https://job-boards.greenhouse.io/anthropic", async_session
    )

    assert result == {
        "success": True,
        "jobs_inserted": 5,
        "jobs_updated": 2,
        "failed": 0,
    }


async def test_sync_company_routes_to_lever(async_session, monkeypatch):
    async def fake_sync_lever(token, db):
        assert token == "acme"
        return 3, 1

    monkeypatch.setattr(sync_service, "_sync_lever", fake_sync_lever)

    result = await sync_service.sync_company(
        "https://jobs.lever.co/acme", async_session
    )

    assert result == {
        "success": True,
        "jobs_inserted": 3,
        "jobs_updated": 1,
        "failed": 0,
    }


async def test_sync_company_falls_back_to_extract_for_unknown_ats(
    async_session, monkeypatch
):
    async def fake_extract(url, db):
        assert url == "https://example.com/careers"
        return 2, 0

    monkeypatch.setattr(sync_service, "_sync_via_extract", fake_extract)

    result = await sync_service.sync_company(
        "https://example.com/careers", async_session
    )

    assert result == {
        "success": True,
        "jobs_inserted": 2,
        "jobs_updated": 0,
        "failed": 0,
    }


async def test_sync_company_reports_failure_when_extract_raises(
    async_session, monkeypatch
):
    async def fake_extract(url, db):
        raise RuntimeError("Chrome failed to launch")

    monkeypatch.setattr(sync_service, "_sync_via_extract", fake_extract)

    result = await sync_service.sync_company(
        "https://example.com/careers", async_session
    )

    assert result == {
        "success": False,
        "jobs_inserted": 0,
        "jobs_updated": 0,
        "failed": 1,
    }
