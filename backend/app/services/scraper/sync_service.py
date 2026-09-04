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

from app.models.db_models import Job
from app.services.browser.chrome_launcher import get_or_launch
from app.services.engine.llm_client import openrouter_llm
from app.services.engine.timeouts import with_timeout

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


async def _sync_via_extract(company_url: str, db: AsyncSession) -> tuple[int, int]:
    """
    Tier 2 fallback for any careers page that isn't a known ATS. Uses a
    dedicated "scraper" Chrome profile (see _SCRAPER_PROFILE_KEY) so this
    never shares cookies/session state with a user's logged-in application
    flow — scraping only ever browses public pages.
    """
    session = await get_or_launch(_SCRAPER_PROFILE_KEY)
    sh = await Stagehand.create(browser=session.browser, model=openrouter_llm)
    try:
        page = (
            await sh.browser.context.active_page()
            or await sh.browser.context.new_page()
        )
        await page.goto(company_url)
        await with_timeout(
            page.wait_for_load_state("load"), what="wait_for_load_state"
        )
        await page.wait_for_timeout(1500)

        result = await sh.extract(
            "List every open job posting visible on this page. For each one, give its "
            "exact title, its location if shown, and the full URL to apply or view the "
            "posting.",
            ScrapedJobs,
            page=page,
        )
    finally:
        await sh.close()

    company_name = _company_name_from_url(company_url)
    inserted = 0
    updated = 0
    for item in result.data.jobs:
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
