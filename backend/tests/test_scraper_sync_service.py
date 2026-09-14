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


class _FakeAssessResult:
    """
    First extract() call of every run is now the page assessment (see
    sync_service._assess_page) — it answers "are the jobs here?" and
    "if not, where are they?" in one response.
    """

    def __init__(self, jobs=(), sections=()):
        self.data = sync_service.PageAssessment(
            jobs=list(jobs),
            sections=[
                sync_service.ListingSection(label=label, url=url)
                for label, url in sections
            ],
        )


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


async def test_extract_via_extract_closes_the_scraper_chrome_session(
    async_session, monkeypatch
):
    """
    Live-caught (FLAGGED.md): sh.close() alone leaves the "scraper" Chrome
    profile's browser claimed, so a second sync_company() call reuses it
    via get_or_launch() and immediately fails with "Stagehand has already
    been initialized". _sync_via_extract must also call close_session() so
    the next call gets a genuinely fresh browser.
    """
    fake = _FakeStagehandInstance(
        extract_results=[_FakeAssessResult()],
        observe_results=[_FakeObserveResult([])],
    )
    _install_fake_stagehand(monkeypatch, fake)

    closed_profile_keys: list[str] = []

    async def _fake_close_session(profile_key):
        closed_profile_keys.append(profile_key)

    monkeypatch.setattr(sync_service, "close_session", _fake_close_session)

    await sync_service._sync_via_extract("https://example.com/careers", async_session)

    assert closed_profile_keys == [sync_service._SCRAPER_PROFILE_KEY]


# ---- _assess_page: one bounded retry on a malformed response ----


async def test_assess_page_retries_once_on_a_malformed_response(monkeypatch):
    """
    Live-caught against careers.cargill.com/en: Stagehand's own structured-
    output validation rejected a real response outright (plain LLM
    flakiness on this one call, unrelated to anything in this module) —
    with the original code, that single failure ended the whole sync with
    zero chance to recover. One retry at the identical instruction is
    enough, mirroring Tier 1's own `_chat_with_repair` for this exact class
    of problem.
    """

    class _FlakyThenFineStagehand:
        def __init__(self):
            self.extract_calls = 0

        async def extract(self, instruction, schema, *, page):
            self.extract_calls += 1
            if self.extract_calls == 1:
                raise RuntimeError("RPCError: invalid_type")
            return _FakeAssessResult(
                jobs=[
                    sync_service.ScrapedJob(
                        title="Engineer", apply_url="https://x.com/1"
                    )
                ]
            )

    sh = _FlakyThenFineStagehand()
    assessment = await sync_service._assess_page(sh, page=object())

    assert sh.extract_calls == 2
    assert len(assessment.jobs) == 1


async def test_assess_page_raises_after_two_consecutive_failures():
    class _AlwaysFlakyStagehand:
        def __init__(self):
            self.extract_calls = 0

        async def extract(self, instruction, schema, *, page):
            self.extract_calls += 1
            raise RuntimeError("RPCError: invalid_type")

    sh = _AlwaysFlakyStagehand()
    with pytest.raises(RuntimeError, match="invalid_type"):
        await sync_service._assess_page(sh, page=object())

    assert sh.extract_calls == 2  # one retry, then give up — not a loop


async def test_extract_pagination_follows_next_page_until_none_found(
    async_session, monkeypatch
):
    from app.services.scraper.sync_service import ScrapedJob

    fake = _FakeStagehandInstance(
        extract_results=[
            # Category 1: the assessment finds the postings on the pasted
            # URL itself, so page 1 costs no second extract().
            _FakeAssessResult(
                jobs=[
                    ScrapedJob(
                        title="Engineer", location="Remote", apply_url="https://x.com/1"
                    )
                ]
            ),
            _FakeExtractResult(
                [
                    ScrapedJob(
                        title="Designer", location="Remote", apply_url="https://x.com/2"
                    )
                ]
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

    same_job = ScrapedJob(
        title="Engineer", location="Remote", apply_url="https://x.com/1"
    )
    fake = _FakeStagehandInstance(
        extract_results=[
            _FakeAssessResult(jobs=[same_job]),
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


# ---- _usable_sections: defending against a plausible-but-wrong answer ----


def test_usable_sections_resolves_relative_urls_against_the_current_page():
    sections = [sync_service.ListingSection(label="Search Jobs", url="/jobs/search")]

    usable = sync_service._usable_sections(
        sections, "https://careers.example.com/en/home", limit=6
    )

    assert [s.url for s in usable] == ["https://careers.example.com/jobs/search"]


def test_usable_sections_drops_non_navigable_schemes():
    sections = [
        sync_service.ListingSection(label="Email us", url="mailto:jobs@example.com"),
        sync_service.ListingSection(label="Apply", url="javascript:void(0)"),
        sync_service.ListingSection(label="Real", url="https://example.com/jobs"),
    ]

    usable = sync_service._usable_sections(sections, "https://example.com/", limit=6)

    assert [s.url for s in usable] == ["https://example.com/jobs"]


def test_usable_sections_drops_a_link_back_to_the_current_page():
    """
    A "Careers" nav link pointing at the page we're already on would
    otherwise cost a reload plus a wasted extract() of the same page.
    """
    sections = [
        sync_service.ListingSection(
            label="Careers", url="https://example.com/careers/"
        ),
        sync_service.ListingSection(label="Grads", url="https://example.com/grads"),
    ]

    usable = sync_service._usable_sections(
        sections, "https://example.com/careers", limit=6
    )

    assert [s.url for s in usable] == ["https://example.com/grads"]


def test_usable_sections_dedupes_ignoring_fragment_and_trailing_slash():
    sections = [
        sync_service.ListingSection(label="A", url="https://example.com/jobs"),
        sync_service.ListingSection(label="B", url="https://example.com/jobs/"),
        sync_service.ListingSection(label="C", url="https://example.com/jobs#top"),
    ]

    usable = sync_service._usable_sections(sections, "https://example.com/", limit=6)

    assert len(usable) == 1


def test_usable_sections_respects_the_limit():
    sections = [
        sync_service.ListingSection(label=str(n), url=f"https://example.com/{n}")
        for n in range(20)
    ]

    usable = sync_service._usable_sections(sections, "https://example.com/", limit=3)

    assert len(usable) == 3


# ---- category 2: one entry point behind a "Search Jobs" button ----


async def test_category2_single_section_is_navigated_and_harvested(
    async_session, monkeypatch
):
    from app.services.scraper.sync_service import ScrapedJob

    fake = _FakeStagehandInstance(
        extract_results=[
            # Landing page: no postings, one way in.
            _FakeAssessResult(
                sections=[("Search Jobs", "https://example.com/jobs")],
            ),
            _FakeExtractResult(
                [
                    ScrapedJob(
                        title="Engineer", location="Remote", apply_url="https://x.com/1"
                    )
                ]
            ),
        ],
        observe_results=[_FakeObserveResult([])],  # no pagination on the listing
    )
    _install_fake_stagehand(monkeypatch, fake)

    inserted, _ = await sync_service._sync_via_extract(
        "https://example.com/careers", async_session
    )

    assert inserted == 1
    # 2 LLM calls total (assess + extract), where the old observe/act
    # drill-down cascade needed 4.
    assert fake.extract_calls == 2
    assert fake.act_calls == 0  # navigation is goto(), not act()
    assert fake.browser.context._page.goto_calls == [
        "https://example.com/careers",
        "https://example.com/careers",  # reset before the section
        "https://example.com/jobs",
    ]


async def test_category2_no_sections_and_no_jobs_stops_immediately(
    async_session, monkeypatch
):
    fake = _FakeStagehandInstance(
        extract_results=[_FakeAssessResult()],  # nothing here, nowhere to go
        observe_results=[],
    )
    _install_fake_stagehand(monkeypatch, fake)

    inserted, _ = await sync_service._sync_via_extract(
        "https://example.com/careers", async_session
    )

    assert inserted == 0
    assert fake.extract_calls == 1  # the assessment and nothing more
    assert fake.observe_calls == 0
    assert fake.act_calls == 0


# ---- category 3: several parallel tracks on one portal ----


async def test_category3_visits_every_section_and_lists_all_jobs(
    async_session, monkeypatch
):
    """
    The Cargill shape: three parallel career tracks on one portal, each
    behind its own "Search Jobs" button. Previously only the first was ever
    followed (FLAGGED.md #33 deferred this explicitly) — every posting in
    the other two was silently lost.
    """
    from app.services.scraper.sync_service import ScrapedJob

    def job(n):
        return ScrapedJob(
            title=f"Job {n}", location="Remote", apply_url=f"https://x.com/{n}"
        )

    fake = _FakeStagehandInstance(
        extract_results=[
            _FakeAssessResult(
                sections=[
                    ("Professional", "https://careers.example.com/professional"),
                    ("Production", "https://careers.example.com/production"),
                    ("Students", "https://careers.example.com/students"),
                ]
            ),
            _FakeExtractResult([job(1)]),
            _FakeExtractResult([job(2)]),
            _FakeExtractResult([job(3)]),
        ],
        observe_results=[_FakeObserveResult([]) for _ in range(3)],
    )
    _install_fake_stagehand(monkeypatch, fake)

    inserted, _ = await sync_service._sync_via_extract(
        "https://careers.example.com/en", async_session
    )

    assert inserted == 3
    assert fake.extract_calls == 4  # 1 assessment + 1 per track
    assert fake.act_calls == 0
    assert fake.browser.context._page.goto_calls == [
        "https://careers.example.com/en",
        "https://careers.example.com/en",  # reset before section 1
        "https://careers.example.com/professional",
        "https://careers.example.com/en",  # reset before section 2
        "https://careers.example.com/production",
        "https://careers.example.com/en",  # reset before section 3
        "https://careers.example.com/students",
    ]

    jobs = (await async_session.execute(select(Job))).scalars().all()
    assert {j.apply_url for j in jobs} == {
        "https://x.com/1",
        "https://x.com/2",
        "https://x.com/3",
    }


async def test_category3_dedupes_a_job_listed_under_two_tracks(
    async_session, monkeypatch
):
    """
    Parallel tracks overlap in practice (a graduate engineering role listed
    under both "Professional" and "Students"). The seen-set is shared
    across sections, so the duplicate is neither re-inserted nor counted.
    """
    from app.services.scraper.sync_service import ScrapedJob

    shared = ScrapedJob(
        title="Grad Engineer", location="X", apply_url="https://x.com/1"
    )

    fake = _FakeStagehandInstance(
        extract_results=[
            _FakeAssessResult(
                sections=[
                    ("Professional", "https://example.com/a"),
                    ("Students", "https://example.com/b"),
                ]
            ),
            _FakeExtractResult([shared]),
            _FakeExtractResult([shared]),
        ],
        observe_results=[_FakeObserveResult([]) for _ in range(2)],
    )
    _install_fake_stagehand(monkeypatch, fake)

    inserted, updated = await sync_service._sync_via_extract(
        "https://example.com/careers", async_session
    )

    assert inserted == 1
    assert updated == 0  # not re-upserted as an "update" either

    jobs = (await async_session.execute(select(Job))).scalars().all()
    assert len(jobs) == 1


async def test_category3_fan_out_is_capped_by_max_sections(async_session, monkeypatch):
    """
    A page whose "sections" we mis-identify (a nav menu, a list of office
    locations) must not turn into an unbounded crawl.
    """
    from app.core.config import get_settings
    from app.services.scraper.sync_service import ScrapedJob

    monkeypatch.setattr(get_settings(), "scraper_max_sections", 2)

    def job(n):
        return ScrapedJob(
            title=f"Job {n}", location="Remote", apply_url=f"https://x.com/{n}"
        )

    fake = _FakeStagehandInstance(
        extract_results=[
            _FakeAssessResult(
                sections=[(str(n), f"https://example.com/{n}") for n in range(10)]
            ),
            *[_FakeExtractResult([job(n)]) for n in range(10)],
        ],
        observe_results=[_FakeObserveResult([]) for _ in range(10)],
    )
    _install_fake_stagehand(monkeypatch, fake)

    inserted, _ = await sync_service._sync_via_extract(
        "https://example.com/careers", async_session
    )

    assert inserted == 2
    assert fake.extract_calls == 3  # assessment + 2 sections, not 10


async def test_category3_one_dead_section_does_not_abandon_the_others(
    async_session, monkeypatch
):
    from app.services.scraper.sync_service import ScrapedJob

    fake = _FakeStagehandInstance(
        extract_results=[
            _FakeAssessResult(
                sections=[
                    ("Broken", "https://example.com/broken"),
                    ("Good", "https://example.com/good"),
                ]
            ),
            _FakeExtractResult(
                [
                    ScrapedJob(
                        title="Engineer", location="Remote", apply_url="https://x.com/1"
                    )
                ]
            ),
        ],
        observe_results=[_FakeObserveResult([])],
    )
    _install_fake_stagehand(monkeypatch, fake)

    real_goto = fake.browser.context._page.goto

    async def flaky_goto(url):
        if url.endswith("/broken"):
            raise RuntimeError("navigation failed")
        await real_goto(url)

    fake.browser.context._page.goto = flaky_goto

    inserted, _ = await sync_service._sync_via_extract(
        "https://example.com/careers", async_session
    )

    # The second section was still harvested despite the first one failing.
    assert inserted == 1


async def test_category1_also_chases_sections_when_the_page_has_jobs_too(
    async_session, monkeypatch
):
    """
    Real bug, live-caught against careers.cargill.com/en: this used to
    return immediately once ANY job was found directly on the page,
    skipping sections entirely — on the assumption that a page with jobs
    is a genuine listing page, and "other sections" on it are just filters
    over the same set. Cargill's own landing page disproved that: it shows
    a few unrelated "spotlight" postings ALONGSIDE its three real
    Professional/Production/University track buttons, and the old logic
    saw the spotlight jobs, returned, and never visited a single real
    track — 0 net jobs on a portal with hundreds. Both are now harvested:
    whatever's directly on the page AND every section.
    """
    from app.services.scraper.sync_service import ScrapedJob

    fake = _FakeStagehandInstance(
        extract_results=[
            _FakeAssessResult(
                jobs=[
                    ScrapedJob(
                        title="Spotlight Role",
                        location="Remote",
                        apply_url="https://x.com/1",
                    )
                ],
                sections=[("Professional", "https://example.com/professional")],
            ),
            _FakeExtractResult(
                [
                    ScrapedJob(
                        title="Engineer", location="Remote", apply_url="https://x.com/2"
                    )
                ]
            ),
        ],
        observe_results=[_FakeObserveResult([])],  # pagination on the section
    )
    _install_fake_stagehand(monkeypatch, fake)

    inserted, _ = await sync_service._sync_via_extract(
        "https://example.com/jobs", async_session
    )

    assert inserted == 2
    # Section visited first, THEN the landing page is explicitly reloaded
    # to harvest its own jobs — not the other way around, so a click-
    # fallback section always sees the same page state the assessment did.
    assert fake.browser.context._page.goto_calls == [
        "https://example.com/jobs",
        "https://example.com/jobs",  # reset before the section
        "https://example.com/professional",
        "https://example.com/jobs",  # reload before the on-page harvest
    ]


async def test_category1_skips_the_reload_when_there_are_no_sections_to_chase(
    async_session, monkeypatch
):
    """The common case (a genuine single-listing page, no sections at all)
    must not pay for a pointless extra goto() back to a page it never
    left."""
    from app.services.scraper.sync_service import ScrapedJob

    fake = _FakeStagehandInstance(
        extract_results=[
            _FakeAssessResult(
                jobs=[
                    ScrapedJob(
                        title="Engineer", location="Remote", apply_url="https://x.com/1"
                    )
                ],
            ),
        ],
        observe_results=[_FakeObserveResult([])],
    )
    _install_fake_stagehand(monkeypatch, fake)

    inserted, _ = await sync_service._sync_via_extract(
        "https://example.com/jobs", async_session
    )

    assert inserted == 1
    assert fake.extract_calls == 1
    assert fake.browser.context._page.goto_calls == ["https://example.com/jobs"]


async def test_extract_pagination_respects_max_page_cap(async_session, monkeypatch):
    from app.core.config import get_settings
    from app.services.scraper.sync_service import ScrapedJob

    monkeypatch.setattr(get_settings(), "scraper_max_pages", 2)

    def _unique_job(n):
        return ScrapedJob(
            title=f"Job {n}", location="Remote", apply_url=f"https://x.com/{n}"
        )

    # Every page yields a new job AND a pagination control — would loop
    # forever without the cap. First result is the page assessment (must
    # carry .sections, even if empty) — the rest are plain per-page
    # extract() results consumed by _harvest_listing's own pagination loop.
    fake = _FakeStagehandInstance(
        extract_results=[
            _FakeAssessResult(jobs=[_unique_job(1)]),
            *[_FakeExtractResult([_unique_job(i)]) for i in range(2, 10)],
        ],
        observe_results=[_FakeObserveResult([_FakeAction()]) for _ in range(10)],
    )
    _install_fake_stagehand(monkeypatch, fake)

    inserted, updated = await sync_service._sync_via_extract(
        "https://example.com/careers", async_session
    )

    assert inserted == 2
    assert fake.extract_calls == 2  # capped at scraper_max_pages, not 9


# ---- real bug, live-caught (twice) against careers.cargill.com/en ----
#
# Attempt 1: giving apply_url/url a `"format": "uri"` JSON Schema hint so
# Stagehand's own node-id -> real-href resolution would kick in. Live-tested
# and it CRASHED the whole extract() call: Stagehand's own re-validation of
# the substituted-back value requires an ABSOLUTE url, and Cargill's real
# hrefs are relative (`/professional-jobs`) — a genuine upstream
# incompatibility, not something a schema hint can route around. Reverted;
# see the long comment above ScrapedJob/ListingSection's definitions for
# the full trace. These two tests guard against that hint quietly
# reappearing — they assert its ABSENCE, the opposite of what an earlier
# version of this test file asserted.


def test_scraped_job_apply_url_has_no_uri_format_hint():
    """
    A `"format": "uri"` hint here would silently reintroduce the crash
    documented above the ScrapedJob/ListingSection class definitions —
    Stagehand's own re-validation of a resolved-but-relative href raises
    RPCError and takes down the whole extract() call. Plain `str`, no hint,
    is a deliberate choice, not an oversight.
    """
    schema = sync_service.ScrapedJobs.model_json_schema()
    apply_url_schema = schema["$defs"]["ScrapedJob"]["properties"]["apply_url"]
    assert "format" not in apply_url_schema


def test_listing_section_url_has_no_uri_format_hint():
    schema = sync_service.PageAssessment.model_json_schema()
    url_schema = schema["$defs"]["ListingSection"]["properties"]["url"]
    assert "format" not in url_schema


def test_url_fields_are_plain_strings_not_strict_url_types():
    """
    Guards against reaching for pydantic.HttpUrl/AnyUrl instead — same
    crash risk as the format:"uri" hint (both ultimately tell Stagehand's
    extension to attempt the same relative-href-hostile resolution), plus
    HttpUrl/AnyUrl would themselves reject a relative string or an
    unresolved empty one on the Python side.
    """
    job = sync_service.ScrapedJob(title="Engineer", apply_url="/relative/path")
    assert job.apply_url == "/relative/path"
    section = sync_service.ListingSection(label="Search Jobs", url="")
    assert section.url == ""


# ---- real bug, live-caught against careers.cargill.com/en (second pass):
# the model echoed the tree's own internal node-id notation as a "url" ----


@pytest.mark.parametrize(
    "value",
    ["[0-583]", "0-4830", "[0-2987]", "12-345"],
)
def test_looks_like_internal_reference_matches_node_id_shapes(value):
    """
    Live-caught: with no real href visible in the accessibility tree, the
    model didn't leave `url` empty — it echoed the tree's own `[id]`
    bracket notation instead (the exact values seen live are the
    parametrized cases here, both bracketed and not). These must be
    detected, not treated as real relative hrefs.
    """
    assert sync_service._looks_like_internal_reference(value)


@pytest.mark.parametrize(
    "value",
    ["/professional-jobs", "https://example.com/jobs", "jobs-2024", "abc-def"],
)
def test_looks_like_internal_reference_does_not_match_real_paths(value):
    assert not sync_service._looks_like_internal_reference(value)


def test_usable_sections_treats_a_node_id_url_as_no_url_not_a_real_href():
    """
    The actual live failure: `urljoin()` happily resolves a node-id string
    against the current page into something with a valid scheme+netloc
    (`https://careers.cargill.com/[0-583]`), which the OLD code accepted as
    a real relative href — taking the free goto() path to a URL that isn't
    real. This must degrade to the label-only / click-fallback case
    instead, exactly like an empty url already does.
    """
    sections = [sync_service.ListingSection(label="Search Jobs", url="[0-583]")]

    usable = sync_service._usable_sections(
        sections, "https://careers.cargill.com/en", limit=6
    )

    assert len(usable) == 1
    assert usable[0].url == ""
    assert usable[0].label == "Search Jobs"


async def test_harvest_listing_sanitizes_a_node_id_apply_url_to_unusable(
    async_session, monkeypatch
):
    """
    The other half of the same live failure: three re-extractions of the
    SAME landing page each returned the same posting with a DIFFERENT
    garbage node-id "apply_url" — since each string was unique, neither
    the in-memory dedup set nor the DB-level upsert lookup recognized them
    as the same job, so it was inserted three times with an unusable,
    non-navigable apply_url. Sanitizing to "" collapses them into the
    already-correctly-handled "no usable url, skip" case.
    """
    job = sync_service.ScrapedJob(
        title="Territory Manager", location="Taichung, Taiwan", apply_url="[0-2987]"
    )
    fake = _FakeStagehandInstance(extract_results=[], observe_results=[])

    inserted, updated = await sync_service._harvest_listing(
        fake,
        fake.browser.context._page,
        async_session,
        "cargill",
        seen_apply_urls=set(),
        max_pages=1,
        first_page_jobs=[job],
    )

    assert inserted == 0
    assert updated == 0
    assert job.apply_url == ""


@pytest.mark.parametrize("garbage", ["13147", "9902", "req-4821", "N/A"])
async def test_harvest_listing_sanitizes_a_bare_requisition_number_apply_url(
    async_session, garbage
):
    """
    Second, separately live-caught variant of the SAME root cause, on the
    real Cargill site: with the section-navigation bug fixed, every single
    job posting harvested from the real tracks still had a garbage
    apply_url — not the bracketed node-id shape this time, but a bare
    requisition-number-looking string (confirmed directly: 0 of 73 rows
    inserted in that run started with "http"). `_looks_like_internal_
    reference`'s narrow `\\d+-\\d+` pattern never matches a bare number
    with no dash, so these sailed straight past that check. The broader
    "must actually be an absolute http(s) URL" bar catches all of these.
    """
    job = sync_service.ScrapedJob(
        title="Merchant", location="Guadalajara, Mexico", apply_url=garbage
    )
    fake = _FakeStagehandInstance(extract_results=[], observe_results=[])

    inserted, _ = await sync_service._harvest_listing(
        fake,
        fake.browser.context._page,
        async_session,
        "cargill",
        seen_apply_urls=set(),
        max_pages=1,
        first_page_jobs=[job],
    )

    assert inserted == 0
    assert job.apply_url == ""


async def test_harvest_listing_keeps_a_genuine_absolute_apply_url(async_session):
    """The fix must not become so strict it rejects real links."""
    job = sync_service.ScrapedJob(
        title="Engineer", location="Remote", apply_url="https://careers.example.com/1"
    )
    fake = _FakeStagehandInstance(extract_results=[], observe_results=[])

    inserted, _ = await sync_service._harvest_listing(
        fake,
        fake.browser.context._page,
        async_session,
        "example",
        seen_apply_urls=set(),
        max_pages=1,
        first_page_jobs=[job],
    )

    assert inserted == 1
    assert job.apply_url == "https://careers.example.com/1"


@pytest.mark.parametrize(
    "value,expected",
    [
        ("https://example.com/jobs/1", True),
        ("http://example.com/jobs/1", True),
        ("13147", False),
        ("[0-583]", False),
        ("0-4830", False),
        ("/relative/path", False),
        ("", False),
        ("ftp://example.com/x", False),
    ],
)
def test_looks_like_real_apply_url(value, expected):
    assert sync_service._looks_like_real_apply_url(value) is expected


# ---- _usable_sections: a JS-routed button with no href is kept, not dropped ----


def test_usable_sections_keeps_a_label_only_entry_with_no_url():
    """
    A genuinely JS-routed portal (a button with a click handler and no
    href at all) has nothing for the model to resolve a URL from — the OLD
    behavior silently dropped this section entirely, losing that entire
    track. It's now kept so the caller can fall back to observe()/act().
    """
    sections = [sync_service.ListingSection(label="Search Jobs", url="")]

    usable = sync_service._usable_sections(sections, "https://example.com/", limit=6)

    assert len(usable) == 1
    assert usable[0].label == "Search Jobs"
    assert usable[0].url == ""


def test_usable_sections_drops_a_label_only_entry_with_no_label_either():
    sections = [sync_service.ListingSection(label="", url="")]

    usable = sync_service._usable_sections(sections, "https://example.com/", limit=6)

    assert usable == []


def test_usable_sections_dedupes_label_only_entries_by_label_text():
    sections = [
        sync_service.ListingSection(label="Search Jobs", url=""),
        sync_service.ListingSection(label="search jobs", url=""),
    ]

    usable = sync_service._usable_sections(sections, "https://example.com/", limit=6)

    assert len(usable) == 1


def test_usable_sections_counts_label_only_entries_toward_the_limit():
    sections = [
        sync_service.ListingSection(label="A", url=""),
        sync_service.ListingSection(label="B", url=""),
        sync_service.ListingSection(label="C", url="https://example.com/jobs"),
    ]

    usable = sync_service._usable_sections(sections, "https://example.com/", limit=2)

    assert len(usable) == 2


# ---- category 3, hardened: a JS-only section falls back to observe()/act() ----


async def test_category3_falls_back_to_click_when_a_section_has_no_href(
    async_session, monkeypatch
):
    """
    Per user direction after the live Cargill failure: a section the
    assessment could only describe by its visible label (no discoverable
    href) must still be reached — by finding and clicking it, the same way
    the pre-category-3 single drill-down hop always worked.
    """
    from app.services.scraper.sync_service import ScrapedJob

    fake = _FakeStagehandInstance(
        extract_results=[
            _FakeAssessResult(sections=[("Search Jobs", "")]),  # no href at all
            _FakeExtractResult(
                [
                    ScrapedJob(
                        title="Engineer", location="Remote", apply_url="https://x.com/1"
                    )
                ]
            ),
        ],
        observe_results=[
            _FakeObserveResult([_FakeAction()]),  # click the "Search Jobs" button
            _FakeObserveResult([]),  # pagination: no next page
        ],
    )
    _install_fake_stagehand(monkeypatch, fake)

    inserted, _ = await sync_service._sync_via_extract(
        "https://example.com/careers", async_session
    )

    assert inserted == 1
    assert fake.act_calls == 1  # the click, nothing else
    # A reset goto() precedes the click (every section always starts from
    # the same page the assessment saw) — the click itself is act(), not a
    # navigation, so no goto() to the section's own (nonexistent) URL.
    assert fake.browser.context._page.goto_calls == [
        "https://example.com/careers",
        "https://example.com/careers",
    ]


async def test_category3_mixes_url_and_click_sections_in_one_run(
    async_session, monkeypatch
):
    """
    The real-world shape: SOME tracks on a portal resolve to a real href
    (free goto()), others are JS-only buttons (observe()+act()) — both
    must be visited in the same run, in the order the assessment returned
    them.
    """
    from app.services.scraper.sync_service import ScrapedJob

    def job(n):
        return ScrapedJob(
            title=f"Job {n}", location="Remote", apply_url=f"https://x.com/{n}"
        )

    fake = _FakeStagehandInstance(
        extract_results=[
            _FakeAssessResult(
                sections=[
                    ("Professional", "https://example.com/professional"),
                    ("Production", ""),  # JS-only button
                ]
            ),
            _FakeExtractResult([job(1)]),
            _FakeExtractResult([job(2)]),
        ],
        observe_results=[
            _FakeObserveResult([_FakeAction()]),  # click "Production"
            _FakeObserveResult([]),  # pagination on professional's listing
            _FakeObserveResult([]),  # pagination on production's listing
        ],
    )
    _install_fake_stagehand(monkeypatch, fake)

    inserted, _ = await sync_service._sync_via_extract(
        "https://example.com/careers", async_session
    )

    assert inserted == 2
    assert fake.act_calls == 1  # only the click-fallback section needed one
    assert fake.browser.context._page.goto_calls == [
        "https://example.com/careers",
        "https://example.com/careers",  # reset before "Professional"
        "https://example.com/professional",
        "https://example.com/careers",  # reset before "Production"
    ]


async def test_category3_click_fallback_failure_does_not_abandon_other_sections(
    async_session, monkeypatch
):
    """A section whose button can't be found or clicked must not abort the
    whole run — the same "one dead entry point, keep going" contract the
    URL-based path already has."""
    from app.services.scraper.sync_service import ScrapedJob

    fake = _FakeStagehandInstance(
        extract_results=[
            _FakeAssessResult(
                sections=[
                    ("Broken Button", ""),
                    ("Good", "https://example.com/good"),
                ]
            ),
            _FakeExtractResult(
                [
                    ScrapedJob(
                        title="Engineer", location="Remote", apply_url="https://x.com/1"
                    )
                ]
            ),
        ],
        observe_results=[
            _FakeObserveResult([]),  # nothing found to click for "Broken Button"
            _FakeObserveResult([]),  # pagination on the good section
        ],
    )
    _install_fake_stagehand(monkeypatch, fake)

    inserted, _ = await sync_service._sync_via_extract(
        "https://example.com/careers", async_session
    )

    assert inserted == 1
