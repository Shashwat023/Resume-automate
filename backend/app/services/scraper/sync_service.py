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
from urllib.parse import urljoin, urlparse

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

# Real bug, live-caught against https://careers.cargill.com/en (a genuine
# category-3 multi-track portal — Professional/Production/University Jobs,
# each a plain `<a href="/professional-jobs">` link, confirmed by fetching
# the raw HTML directly): the FIRST attempt at this fix — giving `url`
# fields a `"format": "uri"` JSON Schema hint so Stagehand's own real-href
# resolution kicks in (see the git history on this comment / FLAGGED.md #37
# for that full writeup) — was itself live-tested against this exact URL
# and CRASHED the extract() call outright:
#
#   stagehand.rpc_client.RPCError: [
#     {"code": "invalid_format", "format": "url",
#      "path": ["structuredContent", "sections", 0, "url"], ...},
#     ... (one per section)
#   ]
#
# Root cause, confirmed by reading the extension's own re-validation path
# (_extension/service-worker.js), not guessed: Stagehand's node-id
# substitution genuinely finds and injects the REAL href back into the
# field — but then re-validates that FINAL value against the field's
# original `.url()` check, which requires a fully-qualified ABSOLUTE URL.
# Cargill's own hrefs are RELATIVE (`/professional-jobs`, confirmed via the
# raw HTML fetch), so the real, correctly-resolved href fails Stagehand's
# OWN strictness and the whole extract() call raises rather than degrading
# that one field to empty. This is a genuine incompatibility in the
# upstream mechanism with relative hrefs — extremely common in real sites —
# not something fixable from a JSON Schema hint on our side.
#
# `ScrapedJob.apply_url` and `ListingSection.url` are therefore back to
# plain `str`: no format hint, no attempt to make Stagehand resolve a real
# href for us. The model gets whatever visible text it can (sometimes a
# real absolute URL, often nothing) with zero server-side validation risk.
# For `ListingSection` this is fine BY DESIGN — `_usable_sections` already
# keeps a label-only entry when `url` comes back empty, and
# `_navigate_to_section` already falls back to observe()+act() (find and
# click the button by its label) for exactly that case. That fallback,
# not extract()'s href resolution, is now the PRIMARY way category 3 reaches
# a relative-href section, not a backstop for an edge case.

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
    apply_url: str = ""


class ScrapedJobs(BaseModel):
    jobs: list[ScrapedJob]


class ListingSection(BaseModel):
    """One entry point to a separate list of openings on the same site."""

    label: str = ""
    url: str = ""


class PageAssessment(BaseModel):
    """
    What ONE look at a careers page tells us. Deliberately answers both
    questions at once — "are the jobs here?" and "if not, where are they?"
    — because asking them separately is what made the old cascade cost up
    to 9 LLM calls (see _assess_page).
    """

    jobs: list[ScrapedJob] = []
    sections: list[ListingSection] = []


def _result(inserted: int, updated: int, failed: int) -> dict:
    return {
        "success": failed == 0,
        "jobs_inserted": inserted,
        "jobs_updated": updated,
        "failed": failed,
    }


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
        return _result(inserted, updated, failed)

    lever_token = _detect_lever(company_url)
    if lever_token:
        try:
            inserted, updated = await _sync_lever(lever_token, db)
        except Exception:
            failed += 1
        return _result(inserted, updated, failed)

    try:
        inserted, updated = await _sync_via_extract(company_url, db)
        return _result(inserted, updated, 0)
    except Exception:
        return _result(0, 0, 1)


def _detect_greenhouse(url: str) -> str | None:
    m = GREENHOUSE_BOARD_RE.search(url)
    return m.group(1) if m else None


def _detect_lever(url: str) -> str | None:
    m = LEVER_RE.search(url)
    return m.group(1) if m else None


async def _find_job_by_apply_url(db: AsyncSession, apply_url: str) -> Job | None:
    """The one place a Job is looked up by its unique apply_url — shared by
    all three sync paths (Greenhouse, Lever, extract), which previously each
    carried their own identical copy of this query."""
    return (
        await db.execute(select(Job).where(Job.apply_url == apply_url))
    ).scalar_one_or_none()


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
        existing = await _find_job_by_apply_url(db, apply_url)
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
        existing = await _find_job_by_apply_url(db, apply_url)
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
    "'Load more'/'Show more jobs'/'Search Jobs' button. If every job posting on this page "
    "is already shown and there is no such control, find nothing."
)

# ONE call that decides which of the three page shapes we're on AND, if the
# jobs are right here, returns them — replacing a blind try-category-1,
# then-category-2, then-category-3 cascade that cost extract()+observe()+
# act() per attempt (up to 9 LLM calls, per user direction to collapse it).
#
# Asking for the section URLs rather than using observe() is the load-
# bearing detail: observe() hands back an Action that only act() can
# execute (2 LLM calls per hop), whereas a URL is navigable with
# page.goto() for free. That is what makes category 3 — visiting EVERY
# parallel track, not just the first — affordable at all.
#
# The two questions are deliberately answered in one response. Splitting
# them is exactly what made the old cascade expensive, and a page can only
# be classified by looking at both answers together anyway.
_ASSESS_INSTRUCTION = (
    "Assess this careers page and answer BOTH of the following at once.\n"
    "(1) `jobs`: every open job posting whose title is actually visible on "
    "this page right now — exact title, its location if shown, and the full "
    "URL to apply to or view that posting. If this page does not itself list "
    "any postings, return an empty list.\n"
    "(2) `sections`: every distinct link or button that leads to a SEPARATE "
    "list of open positions on this site. Some career portals split their "
    "openings across several parallel tracks, each with its own 'Search "
    "Jobs'/'View Openings' button — for example 'Professional Careers', "
    "'Production & Operations', 'Students & Graduates'. Return EVERY such "
    "entry point you can see, not just the first one, each with its visible "
    "label and its full destination URL. Do not include links to individual "
    "job postings, to unrelated pages (about us, benefits, diversity, "
    "locations, news), or to external job boards. If this page already lists "
    "the postings itself, return an empty list."
)


async def _assess_page(sh, page) -> PageAssessment:
    """
    The single planning call. One bounded retry on a malformed response
    before giving up — live-caught against careers.cargill.com/en:
    Stagehand's own structured-output validation rejected a real response
    outright (`RPCError: invalid_type`, array items that weren't objects —
    plain LLM structured-output flakiness on this call, unrelated to
    anything this module controls), with zero chance to recover since the
    original code let the very first failure propagate straight up. Same
    "one retry, no repair prompt needed" shape Tier 1 already uses for
    this exact class of problem (tier1_map.py's `_chat_with_repair`) — a
    fresh attempt at the identical instruction is enough, since the model
    never even saw its own output rejected to react to.

    Still lets a SECOND failure propagate: a failure here means we learned
    nothing about the page at all, which is the same "the scrape failed"
    outcome the plain extract() call had before (sync_company turns it
    into failed=1).
    """
    last_error: Exception | None = None
    for _attempt in range(2):
        try:
            result = await with_timeout(
                sh.extract(_ASSESS_INSTRUCTION, PageAssessment, page=page),
                LLM_CALL_TIMEOUT_SECONDS,
                what="extract() (page assessment)",
            )
            return result.data
        except Exception as exc:  # noqa: BLE001
            last_error = exc
    raise last_error


# Real bug, live-caught against https://careers.cargill.com/en: with no
# real href visible in the accessibility tree, the model didn't leave `url`
# empty — it echoed the tree's OWN internal node-id bracket notation
# instead (e.g. `[0-583]`, or unbracketed `0-4830`), apparently pattern-
# matching the `[id] role: label` shape it can literally see printed
# around the link, since asked for "the full destination URL" and having
# nothing better to offer. `urljoin("https://careers.cargill.com/en",
# "[0-583]")` happily produces something with a valid scheme+netloc
# (`https://careers.cargill.com/[0-583]`), so the OLD code accepted it as
# a real relative href and took the free goto() path — which silently
# landed back on the SAME page every time (this site's own SPA router
# redirects an unrecognized path home, with no exception raised anywhere)
# — producing three rounds of the SAME landing-page "jobs" written to the
# DB with a garbage `apply_url`, not real coverage of the three actual
# tracks. Detected and rejected here so this degrades to the click
# fallback instead, exactly like a genuinely empty url would.
_INTERNAL_REFERENCE_RE = re.compile(r"^\[?\d+-\d+\]?$")


def _looks_like_internal_reference(value: str) -> bool:
    return bool(_INTERNAL_REFERENCE_RE.match(value.strip()))


# Real bug, live-caught against careers.cargill.com/en (fourth pass — same
# root cause as the section-link problem above, on a DIFFERENT field):
# with the section-navigation bug fixed and the crawl genuinely reaching
# all three real tracks, every single job posting harvested from them
# STILL had a garbage `apply_url` — not the bracketed node-id shape this
# time, but a bare requisition-number-looking string (`"13147"`,
# `"13151"`, ...), presumably a Job ID visible as plain text near the
# posting. `_looks_like_internal_reference`'s narrow `\d+-\d+` pattern
# never matches a bare number with no dash, so every one of these 73 rows
# sailed straight past it and into the database as a real-looking-but-
# useless "apply_url" — confirmed directly: 0 of 73 inserted rows started
# with `http`.
#
# An apply_url is fundamentally different from a section link: it's
# stored and used STANDALONE (e.g. `<a href={job.apply_url}>`), with no
# "current page" to resolve a relative path against — so, unlike a
# section, there is no legitimate relative form for it to take. Requiring
# a genuine absolute http(s) URL is therefore not an approximation of
# "looks real enough," it is the actual, complete correctness bar. Any
# job whose extract()-provided apply_url fails this is treated as
# unusable and dropped — same as the pre-existing "no apply_url at all"
# case — rather than writing a link that LOOKS legitimate but goes
# nowhere.
def _looks_like_real_apply_url(value: str) -> bool:
    parsed = urlparse(value.strip())
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def _usable_sections(
    sections: list[ListingSection], current_url: str, limit: int
) -> list[ListingSection]:
    """
    Turns whatever the model returned into a bounded list of distinct
    section entries. Everything here is defensive against a plausible-but-
    wrong answer, since a mis-identified "section" costs a real page load
    plus an extract() call:

    - relative hrefs are resolved against the page we're actually on
    - non-http(s) (mailto:, javascript:, tel:) is dropped
    - a value that's actually the tree's own internal node-id notation,
      not a real href, is dropped (see _looks_like_internal_reference)
    - the current page is dropped (a "Careers" link pointing back at itself
      would otherwise re-extract the same page and waste a call)
    - duplicates are dropped ignoring the fragment and trailing slash, so
      /jobs, /jobs/ and /jobs#top count once
    - the whole thing is capped at `limit`

    A section with NO resolvable url but a real label is kept, not dropped
    — live-caught on a genuinely JS-routed portal (a button with a click
    handler and no href at all, the case this URL-based design can't see):
    the caller falls back to observe()/act() for exactly these, at the cost
    of two extra LLM calls instead of the free goto() the URL case gets.
    Deduped on normalized label text instead of a URL, since there isn't one.
    """

    def normalize(url: str) -> str:
        return url.split("#")[0].rstrip("/")

    here = normalize(current_url)
    seen_urls: set[str] = set()
    seen_labels: set[str] = set()
    usable: list[ListingSection] = []

    for section in sections:
        raw = (section.url or "").strip()
        label = (section.label or "").strip()

        if raw and _looks_like_internal_reference(raw):
            raw = ""

        if not raw:
            if not label or label.lower() in seen_labels:
                continue
            seen_labels.add(label.lower())
            usable.append(ListingSection(label=label, url=""))
            if len(usable) >= limit:
                break
            continue

        absolute = urljoin(current_url, raw)
        parsed = urlparse(absolute)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            continue
        key = normalize(absolute)
        if key == here or key in seen_urls:
            continue
        seen_urls.add(key)
        usable.append(ListingSection(label=label, url=absolute))
        if len(usable) >= limit:
            break

    return usable


_SECTION_CLICK_INSTRUCTION_TEMPLATE = (
    "Find and click the '{label}' link or button that leads to its own "
    "separate list of open positions on this site."
)


async def _navigate_to_section(sh, page, section: "ListingSection") -> bool:
    """
    Reach one section's listing page: goto() when a real URL resolved
    (free), otherwise fall back to observe()+act() by the section's own
    label (2 LLM calls) for a genuinely JS-routed entry point with no
    discoverable href. Returns whether navigation succeeded.
    """
    if section.url:
        try:
            await page.goto(section.url)
            await with_timeout(
                page.wait_for_load_state("load"), what="wait_for_load_state"
            )
        except Exception:  # noqa: BLE001
            return False
        await page.wait_for_timeout(1500)
        return True

    try:
        obs = await with_timeout(
            sh.observe(
                _SECTION_CLICK_INSTRUCTION_TEMPLATE.format(label=section.label),
                page=page,
            ),
            LLM_CALL_TIMEOUT_SECONDS,
            what="observe() (section click)",
        )
    except Exception:  # noqa: BLE001
        return False
    if not obs.data:
        return False

    try:
        await with_timeout(
            sh.act(obs.data[0], page=page),
            LLM_CALL_TIMEOUT_SECONDS,
            what="act() (section click)",
        )
    except Exception:  # noqa: BLE001
        return False

    try:
        await with_timeout(page.wait_for_load_state("load"), what="wait_for_load_state")
    except Exception:  # noqa: BLE001
        pass  # an in-page SPA route change may never fire a "load" event
    await page.wait_for_timeout(1500)
    return True


async def _harvest_listing(
    sh,
    page,
    db: AsyncSession,
    company_name: str,
    seen_apply_urls: set[str],
    max_pages: int,
    first_page_jobs: list[ScrapedJob] | None = None,
) -> tuple[int, int]:
    """
    Extract every posting from ONE listing page, following its pagination.

    `first_page_jobs` is the small but important optimization that keeps
    category 1 at its original single-call cost: the assessment call has
    already extracted this page's postings, so re-extracting them here
    would be a wasted LLM call. Sections reached by goto() pass None and
    extract normally.

    `seen_apply_urls` is shared by the caller across every section, so a
    posting listed under two parallel tracks is counted and upserted once.
    """
    inserted = 0
    updated = 0
    pending = first_page_jobs
    page_number = 1

    while page_number <= max_pages:
        if pending is not None:
            jobs = pending
            pending = None
        else:
            try:
                result = await with_timeout(
                    sh.extract(_EXTRACT_INSTRUCTION, ScrapedJobs, page=page),
                    LLM_CALL_TIMEOUT_SECONDS,
                    what="extract()",
                )
            except Exception:  # noqa: BLE001
                # One unreadable section must not discard the sections
                # already harvested — the caller keeps going.
                break
            jobs = result.data.jobs

        # Same defense as _usable_sections, and the same live-caught cause:
        # with no real href visible in the tree, the model invents SOME
        # plausible-looking-but-fake token instead of leaving apply_url
        # empty — the internal node-id shape (`[0-583]`) on one pass, a
        # bare requisition-number-looking string (`"13147"`) on another
        # (see _looks_like_real_apply_url's own docstring for the second,
        # separately live-caught case). Sanitized to "" HERE, before it
        # reaches the dedup set below — otherwise every differently-valued
        # garbage token for the SAME posting (re-extracted on a re-render)
        # looks like a distinct new job and both the in-memory dedup and
        # _upsert_scraped_jobs' DB-level lookup miss it, inserting the
        # same posting repeatedly with an unusable, non-navigable
        # apply_url (live-caught: 3 duplicate rows for one Cargill
        # landing-page posting, then separately 73/73 rows with a
        # real-looking-but-dead apply_url). An empty apply_url is already
        # the existing, correctly-handled "unusable, skip" case.
        for job in jobs:
            if job.apply_url and not _looks_like_real_apply_url(job.apply_url):
                job.apply_url = ""

        new_this_page = [j for j in jobs if j.apply_url not in seen_apply_urls]
        for job in jobs:
            if job.apply_url:
                seen_apply_urls.add(job.apply_url)

        page_inserted, page_updated = await _upsert_scraped_jobs(
            new_this_page, company_name, db
        )
        inserted += page_inserted
        updated += page_updated

        # Stop condition 1: this page added nothing new — either we've
        # reached the real end (a "Next" control that loops back, or a
        # duplicate render) or we're stuck; either way, continuing would
        # just keep spending on no signal.
        if not new_this_page:
            break

        # Stop condition 2 (checked implicitly by the while-loop bound):
        # max_pages caps worst-case spend even if a page keeps legitimately
        # yielding new jobs forever.
        if page_number == max_pages:
            break

        try:
            obs = await with_timeout(
                sh.observe(_PAGINATION_INSTRUCTION, page=page),
                LLM_CALL_TIMEOUT_SECONDS,
                what="observe() (pagination)",
            )
        except Exception:  # noqa: BLE001
            break  # best-effort — treat a failed pagination check as "no more pages"

        # Stop condition 3: no pagination/load-more control found — this
        # genuinely is the last page.
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

    return inserted, updated


async def _sync_via_extract(company_url: str, db: AsyncSession) -> tuple[int, int]:
    """
    Fallback for any careers page that isn't a known ATS. Uses a dedicated
    "scraper" Chrome profile (see _SCRAPER_PROFILE_KEY) so this never
    shares cookies/session state with a user's logged-in application flow —
    scraping only ever browses public pages.

    ONE assessment call (see _assess_page) decides which of three page
    shapes we're on, replacing what used to be a blind try-one-then-the-
    next cascade costing extract()+observe()+act() per attempt:

      1. the postings are on the pasted URL           -> harvest right here
      2. one "Search Jobs"-style entry point          -> goto it, harvest
      3. SEVERAL parallel tracks, each with their own
         listings (Cargill's Professional / Production
         / Students sections)                         -> goto each in turn,
                                                         harvest all of them

    The category is derived from what the assessment returned rather than
    asked for as a label: a model can confidently answer "multi_section"
    and then hand back a single section (or vice versa), and at that point
    the label and the data disagree with no way to tell which is wrong.
    Counting the sections it actually returned cannot disagree with itself.

    Spend is bounded on both axes: scraper_max_sections caps how many
    listing pages we'll visit, scraper_max_pages caps pagination within
    each one.
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

        assessment = await _assess_page(sh, page)

        # Real bug, live-caught against https://careers.cargill.com/en:
        # `assessment.jobs` and `assessment.sections` used to be treated as
        # mutually exclusive (jobs present -> harvest here and STOP, never
        # touching sections at all). Cargill's own `/en` landing page
        # disproved that assumption directly — it surfaces a handful of
        # unrelated "spotlight" postings (Taiwan, Colombia, Colorado; none
        # with a resolvable apply_url, so none were even insertable)
        # ALONGSIDE its three real Professional/Production/University
        # track buttons. The old branch saw `assessment.jobs` was non-empty,
        # returned immediately, and NEVER visited a single one of the three
        # real tracks — net result: 0 jobs on a portal with hundreds. This
        # was a foreseen, explicitly flagged risk (FLAGGED.md #35) that
        # turned out to be real on the very first genuine multi-track
        # portal tested, not a hypothetical.
        #
        # Both are now harvested unconditionally: whatever is directly on
        # the page (cheap — already extracted, zero extra calls) AND every
        # section (bounded by SCRAPER_MAX_SECTIONS regardless). Sections
        # are visited FIRST and the page is explicitly reloaded via goto()
        # before harvesting the landing page's own jobs+pagination last —
        # not the other way around — because a click-fallback section
        # (see _navigate_to_section) needs the SAME page state the
        # assessment actually saw; harvesting on-page jobs first can trigger
        # this function's own pagination and navigate the page away from
        # that state before a click-fallback section ever gets a chance.
        # The known remaining cost of doing both: a genuine single-listing
        # page whose "other sections" are really just filters over the same
        # jobs pays a few extra, capped LLM calls to re-discover postings
        # the dedupe set then discards — accepted, since the alternative
        # just proved itself capable of a total, silent failure.
        sections = _usable_sections(
            assessment.sections, company_url, settings.scraper_max_sections
        )

        # Real bug, live-caught against careers.cargill.com/en (third pass):
        # after Production Jobs' click-fallback succeeded, the browser was
        # left on THAT track's own page — and University Jobs' click-
        # fallback then failed outright (observe() found nothing), because
        # its button only ever existed on the ORIGINAL landing page, not on
        # a sibling track's page. Each section's click-fallback needs the
        # SAME page the assessment actually saw, not wherever the PREVIOUS
        # section's navigation left off. Reset unconditionally before every
        # section — including the first, where it's redundant with the
        # goto() already done above — rather than trying to skip it in the
        # "probably still fresh" case: a free, deterministic goto() is far
        # cheaper than a subtle staleness bug in the one thing this loop
        # exists to get right.
        for section in sections:
            await page.goto(company_url)
            await with_timeout(
                page.wait_for_load_state("load"), what="wait_for_load_state"
            )
            await page.wait_for_timeout(1500)

            if not await _navigate_to_section(sh, page, section):
                continue  # a dead entry point must not abandon the others

            section_inserted, section_updated = await _harvest_listing(
                sh,
                page,
                db,
                company_name,
                seen_apply_urls,
                settings.scraper_max_pages,
            )
            inserted += section_inserted
            updated += section_updated

        if assessment.jobs:
            if sections:
                # Only reload if we actually navigated away above — saves
                # one pointless goto() on the common case (a genuine
                # single-listing page with no sections at all).
                await page.goto(company_url)
                await with_timeout(
                    page.wait_for_load_state("load"), what="wait_for_load_state"
                )
                await page.wait_for_timeout(1500)

            page_inserted, page_updated = await _harvest_listing(
                sh,
                page,
                db,
                company_name,
                seen_apply_urls,
                settings.scraper_max_pages,
                first_page_jobs=assessment.jobs,
            )
            inserted += page_inserted
            updated += page_updated
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
        existing = await _find_job_by_apply_url(db, item.apply_url)
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
