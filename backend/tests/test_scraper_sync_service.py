import httpx
import pytest
from sqlalchemy import select

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


# ---- _sync_via_extract: pagination loop ----


class _FakePage:
    def __init__(self):
        self.goto_calls: list[str] = []

    async def goto(self, url):
        self.goto_calls.append(url)

    async def wait_for_load_state(self, state):
        pass

    async def wait_for_timeout(self, ms):
        pass


class _FakeContext:
    def __init__(self, page):
        self._page = page

    async def active_page(self):
        return None

    async def new_page(self):
        return self._page


class _FakeBrowser:
    def __init__(self, page):
        self.context = _FakeContext(page)


class _FakeExtractResult:
    def __init__(self, jobs):
        self.data = sync_service.ScrapedJobs(jobs=jobs)


class _FakeObserveResult:
    def __init__(self, data):
        self.data = data


class _FakeAction:
    pass


class _FakeStagehandInstance:
    def __init__(self, extract_results, observe_results):
        self.browser = _FakeBrowser(_FakePage())
        self._extract_results = extract_results
        self._observe_results = observe_results
        self.extract_calls = 0
        self.observe_calls = 0
        self.act_calls = 0
        self.closed = False

    async def extract(self, instruction, schema, *, page):
        result = self._extract_results[self.extract_calls]
        self.extract_calls += 1
        return result

    async def observe(self, instruction, *, page):
        result = self._observe_results[self.observe_calls]
        self.observe_calls += 1
        return result

    async def act(self, action, *, page):
        self.act_calls += 1
        return None

    async def close(self):
        self.closed = True


def _install_fake_stagehand(monkeypatch, fake_instance):
    class _FakeStagehandCls:
        @staticmethod
        async def create(*, browser, model):
            return fake_instance

    monkeypatch.setattr(sync_service, "Stagehand", _FakeStagehandCls)

    class _FakeSession:
        browser = object()

    async def _fake_get_or_launch(profile_key):
        return _FakeSession()

    monkeypatch.setattr(sync_service, "get_or_launch", _fake_get_or_launch)


async def test_extract_pagination_follows_next_page_until_none_found(
    async_session, monkeypatch
):
    from app.services.scraper.sync_service import ScrapedJob

    fake = _FakeStagehandInstance(
        extract_results=[
            _FakeExtractResult(
                [ScrapedJob(title="Engineer", location="Remote", apply_url="https://x.com/1")]
            ),
            _FakeExtractResult(
                [ScrapedJob(title="Designer", location="Remote", apply_url="https://x.com/2")]
            ),
        ],
        observe_results=[
            _FakeObserveResult([_FakeAction()]),  # page 1 -> has a next page
            _FakeObserveResult([]),  # page 2 -> no more pages
        ],
    )
    _install_fake_stagehand(monkeypatch, fake)

    inserted, updated = await sync_service._sync_via_extract(
        "https://example.com/careers", async_session
    )

    assert inserted == 2
    assert updated == 0
    assert fake.extract_calls == 2
    assert fake.observe_calls == 2
    assert fake.act_calls == 1  # clicked through to page 2 exactly once
    assert fake.closed is True

    jobs = (await async_session.execute(select(Job))).scalars().all()
    assert {j.apply_url for j in jobs} == {"https://x.com/1", "https://x.com/2"}


async def test_extract_pagination_stops_when_a_page_yields_no_new_jobs(
    async_session, monkeypatch
):
    from app.services.scraper.sync_service import ScrapedJob

    same_job = ScrapedJob(title="Engineer", location="Remote", apply_url="https://x.com/1")
    fake = _FakeStagehandInstance(
        extract_results=[
            _FakeExtractResult([same_job]),
            _FakeExtractResult([same_job]),  # identical page — stuck/duplicate render
        ],
        observe_results=[_FakeObserveResult([_FakeAction()])],
    )
    _install_fake_stagehand(monkeypatch, fake)

    inserted, updated = await sync_service._sync_via_extract(
        "https://example.com/careers", async_session
    )

    assert inserted == 1
    # Stopped after page 2 found nothing new — never checked for a 3rd page.
    assert fake.extract_calls == 2
    assert fake.observe_calls == 1


async def test_extract_pagination_respects_max_page_cap(async_session, monkeypatch):
    from app.core.config import get_settings
    from app.services.scraper.sync_service import ScrapedJob

    monkeypatch.setattr(get_settings(), "scraper_max_pages", 2)

    def _unique_job(n):
        return ScrapedJob(title=f"Job {n}", location="Remote", apply_url=f"https://x.com/{n}")

    # Every page yields a new job AND a pagination control — would loop
    # forever without the cap.
    fake = _FakeStagehandInstance(
        extract_results=[_FakeExtractResult([_unique_job(i)]) for i in range(1, 10)],
        observe_results=[_FakeObserveResult([_FakeAction()]) for _ in range(10)],
    )
    _install_fake_stagehand(monkeypatch, fake)

    inserted, updated = await sync_service._sync_via_extract(
        "https://example.com/careers", async_session
    )

    assert inserted == 2
    assert fake.extract_calls == 2  # capped at scraper_max_pages, not 9
