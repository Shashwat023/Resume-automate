"""
Job discovery/scraper. Cascading, same philosophy as the form-filling engine:
  1. Known ATS JSON APIs (Greenhouse, Lever) - free, structured, fast
  2. Stagehand extract() against the branded careers page - Day 3
  3. WebSearch site: fallback - deferred, see FLAGGED.md

Tiers 1 and 2 are both implemented. Tier 3 (broad WebSearch discovery when
a careers page can't be resolved directly) is the first thing cut under
time pressure per PLAN.md's cut list.
"""

import re
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from stagehand import Stagehand

from app.core.config import get_settings
from app.models.db_models import Job
from app.services.browser.chrome_launcher import close_session, get_or_launch
from app.services.engine.llm_client import openrouter_llm
from app.services.engine.timeouts import LLM_CALL_TIMEOUT_SECONDS, with_timeout

GREENHOUSE_BOARD_RE = re.compile(
    r"(?:job-boards\.greenhouse\.io|boards\.greenhouse\.io)/([\w-]+)"
)
LEVER_RE = re.compile(r"jobs\.lever\.co/([\w-]+)")

# A dedicated Chrome profile for scraping — not tied to any user's
# logged-in session (scraping browses public career pages, never a user's
# authenticated application flow, and must not share cookies with one).
_SCRAPER_PROFILE_KEY = "scraper"


class ScrapedJob(BaseModel):
    title: str
    location: str | None = None
    apply_url: str


class ScrapedJobs(BaseModel):
    jobs: list[ScrapedJob]


async def sync_company(company_url: str, db: AsyncSession) -> dict:
    inserted = 0
    updated = 0
    failed = 0

    board_token = _detect_greenhouse(company_url)
    if board_token:
        try:
            inserted, updated = await _sync_greenhouse(board_token, db)
        except Exception:
            failed += 1
        return {
            "success": failed == 0,
            "jobs_inserted": inserted,
            "jobs_updated": updated,
            "failed": failed,
        }

    lever_token = _detect_lever(company_url)
    if lever_token:
        try:
            inserted, updated = await _sync_lever(lever_token, db)
        except Exception:
            failed += 1
        return {
            "success": failed == 0,
            "jobs_inserted": inserted,
            "jobs_updated": updated,
            "failed": failed,
        }

    try:
        inserted, updated = await _sync_via_extract(company_url, db)
        return {
            "success": True,
            "jobs_inserted": inserted,
            "jobs_updated": updated,
            "failed": 0,
        }
    except Exception:
        return {"success": False, "jobs_inserted": 0, "jobs_updated": 0, "failed": 1}


def _detect_greenhouse(url: str) -> str | None:
    m = GREENHOUSE_BOARD_RE.search(url)
    return m.group(1) if m else None


def _detect_lever(url: str) -> str | None:
    m = LEVER_RE.search(url)
    return m.group(1) if m else None


def _company_name_from_url(url: str) -> str:
    netloc = urlparse(url).netloc or url
    return netloc.removeprefix("www.")


async def _sync_greenhouse(board_token: str, db: AsyncSession) -> tuple[int, int]:
    url = f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true"
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.json()

    inserted = 0
    updated = 0
    for item in data.get("jobs", []):
        apply_url = item.get("absolute_url")
        if not apply_url:
            continue
        existing = (
            await db.execute(select(Job).where(Job.apply_url == apply_url))
        ).scalar_one_or_none()
        location = (item.get("location") or {}).get("name", "")
        if existing:
            existing.title = item.get("title", existing.title)
            existing.location = location
            updated += 1
        else:
            db.add(
                Job(
                    title=item.get("title", "Untitled"),
                    company_name=board_token,
                    location=location,
                    apply_url=apply_url,
                    ats="greenhouse",
                )
            )
            inserted += 1
    await db.commit()
    return inserted, updated


async def _sync_lever(company_token: str, db: AsyncSession) -> tuple[int, int]:
    url = f"https://api.lever.co/v0/postings/{company_token}?mode=json"
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.json()

    inserted = 0
    updated = 0
    for item in data:
        apply_url = item.get("hostedUrl") or item.get("applyUrl")
        if not apply_url:
            continue
        existing = (
            await db.execute(select(Job).where(Job.apply_url == apply_url))
        ).scalar_one_or_none()
        location = (item.get("categories") or {}).get("location", "")
        if existing:
            existing.title = item.get("text", existing.title)
            existing.location = location
            updated += 1
        else:
            db.add(
                Job(
                    title=item.get("text", "Untitled"),
                    company_name=company_token,
                    location=location,
                    apply_url=apply_url,
                    ats="lever",
                )
            )
            inserted += 1
    await db.commit()
    return inserted, updated


_EXTRACT_INSTRUCTION = (
    "List every open job posting visible on this page. For each one, give its "
    "exact title, its location if shown, and the full URL to apply or view the "
    "posting."
)

# A single extract() call only ever sees what's currently rendered — a real
# job board or careers page routinely spreads its full listing across
# several pages (numbered pagination, a "Next" button, or a "Load more"
# button that appends more without navigating). Per user direction: follow
# that pagination rather than silently stopping at page one. Phrased
# generically (not "click Next") since the actual control varies by site —
# observe() decides whether one exists at all.
_PAGINATION_INSTRUCTION = (
    "Find the control that shows more job listings beyond what's currently "
    "visible — a 'Next page' button, a numbered link to the next page, or a "
    "'Load more'/'Show more jobs' button. If every job posting on this page "
    "is already shown and there is no such control, find nothing."
)

# Some careers pages are landing/marketing pages, not listings — e.g. a page
# with only a "Search Jobs" button or search bar and no postings rendered
# at all. If the very first extract() finds nothing, try one drill-down hop
# to the actual listings page before giving up. Deliberately narrow: this
# follows a single "go to the job listings" link, not every link on the
# page — a page with several separate tracks (e.g. Professional/Production/
# University career sites) isn't handled by this and still needs a direct
# URL to the specific listings page (see FLAGGED.md).
_JOBS_LINK_INSTRUCTION = (
    "Find a link or button that leads to a page listing open job positions "
    "or a job search page — e.g. 'Search Jobs', 'View Openings', 'Current "
    "Openings', 'Browse Jobs'. If this page already lists job postings "
    "directly, find nothing."
)


async def _try_drilldown_to_listings(sh, page) -> bool:
    """
    One best-effort hop from a landing page to its actual job listings.
    Returns True if a link was found and clicked (caller should re-extract).
    """
    try:
        obs = await with_timeout(
            sh.observe(_JOBS_LINK_INSTRUCTION, page=page),
            LLM_CALL_TIMEOUT_SECONDS,
            what="observe() (drilldown)",
        )
    except Exception:  # noqa: BLE001
        return False

    if not obs.data:
        return False

    try:
        await with_timeout(
            sh.act(obs.data[0], page=page),
            LLM_CALL_TIMEOUT_SECONDS,
            what="act() (drilldown)",
        )
    except Exception:  # noqa: BLE001
        return False

    try:
        await with_timeout(page.wait_for_load_state("load"), what="wait_for_load_state")
    except Exception:  # noqa: BLE001
        pass  # an in-page SPA route change may never fire a "load" event
    await page.wait_for_timeout(1500)
    return True


async def _sync_via_extract(company_url: str, db: AsyncSession) -> tuple[int, int]:
    """
    Tier 2 fallback for any careers page that isn't a known ATS. Uses a
    dedicated "scraper" Chrome profile (see _SCRAPER_PROFILE_KEY) so this
    never shares cookies/session state with a user's logged-in application
    flow — scraping only ever browses public pages.

    Paginates: extract the current page, look for a "more" control, click
    it and repeat. Bounded three ways so this can never turn into an
    unbounded LLM-spend loop — see each check below and
    settings.scraper_max_pages's own docstring.

    If the very first page is a landing page with no postings, tries one
    drill-down hop to a "Search Jobs"-style link before giving up — see
    _try_drilldown_to_listings.
    """
    settings = get_settings()
    session = await get_or_launch(_SCRAPER_PROFILE_KEY)
    sh = await Stagehand.create(browser=session.browser, model=openrouter_llm)
    company_name = _company_name_from_url(company_url)
    seen_apply_urls: set[str] = set()
    inserted = 0
    updated = 0
    try:
        page = (
            await sh.browser.context.active_page()
            or await sh.browser.context.new_page()
        )
        await page.goto(company_url)
        await with_timeout(page.wait_for_load_state("load"), what="wait_for_load_state")
        await page.wait_for_timeout(1500)

        drilldown_attempted = False
        page_number = 1
        while page_number <= settings.scraper_max_pages:
            result = await with_timeout(
                sh.extract(_EXTRACT_INSTRUCTION, ScrapedJobs, page=page),
                LLM_CALL_TIMEOUT_SECONDS,
                what="extract()",
            )

            new_this_page = [
                item for item in result.data.jobs if item.apply_url not in seen_apply_urls
            ]
            for item in result.data.jobs:
                if item.apply_url:
                    seen_apply_urls.add(item.apply_url)

            page_inserted, page_updated = await _upsert_scraped_jobs(
                new_this_page, company_name, db
            )
            inserted += page_inserted
            updated += page_updated

            # Stop condition 1: this page added nothing new — either we've
            # reached the real end (a "Next" control that loops back, or a
            # duplicate render) or we're stuck; either way, continuing
            # would just keep spending on no signal. Exception: page one of
            # a landing page — try one drill-down hop first.
            if not new_this_page:
                if page_number == 1 and not drilldown_attempted:
                    drilldown_attempted = True
                    if await _try_drilldown_to_listings(sh, page):
                        continue  # re-extract from the listings page, same page_number
                break

            # Stop condition 2 (checked implicitly by the while-loop bound):
            # settings.scraper_max_pages caps worst-case spend even if a
            # page keeps legitimately yielding new jobs forever.
            if page_number == settings.scraper_max_pages:
                break

            try:
                obs = await with_timeout(
                    sh.observe(_PAGINATION_INSTRUCTION, page=page),
                    LLM_CALL_TIMEOUT_SECONDS,
                    what="observe() (pagination)",
                )
            except Exception:  # noqa: BLE001
                break  # best-effort — treat a failed pagination check as "no more pages"

            # Stop condition 3: no pagination/load-more control found —
            # this genuinely is the last page.
            if not obs.data:
                break

            try:
                await with_timeout(
                    sh.act(obs.data[0], page=page),
                    LLM_CALL_TIMEOUT_SECONDS,
                    what="act() (pagination)",
                )
            except Exception:  # noqa: BLE001
                break  # couldn't advance — stop rather than retry indefinitely
            await page.wait_for_timeout(1500)  # let the next page/appended jobs render
            page_number += 1
    finally:
        # sh.close() only detaches the Stagehand wrapper — it does NOT close
        # the underlying Chrome browser (see chrome_launcher.py's own
        # comment on this). Without also closing the session, the "scraper"
        # profile's browser stays alive and already-claimed, so the next
        # sync_company() call reuses it via get_or_launch() and immediately
        # fails with "Stagehand has already been initialized" — the same
        # one-way-extension-state-machine bug documented for the
        # application-filling flow (FLAGGED.md #26-29), live-caught here too
        # when two syncs ran back-to-back. Must close both, in this order,
        # same as runner.py's fix.
        await sh.close()
        await close_session(_SCRAPER_PROFILE_KEY)

    return inserted, updated


async def _upsert_scraped_jobs(
    items: list[ScrapedJob], company_name: str, db: AsyncSession
) -> tuple[int, int]:
    inserted = 0
    updated = 0
    for item in items:
        if not item.apply_url:
            continue
        existing = (
            await db.execute(select(Job).where(Job.apply_url == item.apply_url))
        ).scalar_one_or_none()
        if existing:
            existing.title = item.title or existing.title
            existing.location = item.location or existing.location
            updated += 1
        else:
            db.add(
                Job(
                    title=item.title or "Untitled",
                    company_name=company_name,
                    location=item.location or "",
                    apply_url=item.apply_url,
                    ats=None,
                )
            )
            inserted += 1
    await db.commit()
    return inserted, updated
