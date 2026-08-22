"""
Loads config/portals.yml's tracked_companies list into the database.

Deliberately a CLI script, not an API endpoint: the frontend's contract is
fixed and would never call one, and seeding on server startup would make
boot slow and surprising. Idempotent — upserts keyed on careers_url, safe
to re-run.

Usage: python -m app.scripts.seed_portals
"""

import asyncio
import re

import yaml

from app.core.config import get_settings
from app.core.db import async_session_factory, init_db
from app.repositories.tracked_company_repository import TrackedCompanyRepository

settings = get_settings()

# Some portals.yml entries are bare ATS host URLs with no company token at
# all (e.g. "https://boards.greenhouse.io/", "https://jobs.lever.co/") —
# a data-hygiene issue in the source file, not something a scraper could
# ever resolve regardless of tier. Skipped with a warning, not counted as
# a failure. Flagged in FLAGGED.md for a source-data cleanup pass.
_BARE_ATS_HOST = re.compile(
    r"^https?://(?:www\.)?"
    r"(boards\.greenhouse\.io|job-boards\.greenhouse\.io|"
    r"jobs\.lever\.co|jobs\.eu\.lever\.co|jobs\.ashbyhq\.com|"
    r"[\w.]*myworkdayjobs\.com|[\w.]*myworkdaysite\.com)"
    r"/?$",
    re.IGNORECASE,
)


def load_tracked_companies() -> list[dict]:
    with open(settings.portals_config_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("tracked_companies") or []


def is_bare_ats_host(careers_url: str) -> bool:
    return bool(_BARE_ATS_HOST.match(careers_url.strip()))


async def seed() -> dict:
    await init_db()
    companies = load_tracked_companies()

    inserted = 0
    updated = 0
    skipped = 0

    async with async_session_factory() as db:
        repo = TrackedCompanyRepository(db)
        for entry in companies:
            name = entry.get("name")
            careers_url = entry.get("careers_url")
            if not name or not careers_url:
                skipped += 1
                continue
            if is_bare_ats_host(careers_url):
                print(
                    f"  skipping (bare ATS host, no company token): {name} -> {careers_url}"
                )
                skipped += 1
                continue

            _, was_inserted = await repo.upsert(
                name, careers_url, enabled=entry.get("enabled", True)
            )
            if was_inserted:
                inserted += 1
            else:
                updated += 1

    return {
        "total_in_file": len(companies),
        "inserted": inserted,
        "updated": updated,
        "skipped": skipped,
    }


async def main() -> None:
    result = await seed()
    print(
        f"\nSeeded tracked_companies from {settings.portals_config_path}:\n"
        f"  {result['total_in_file']} entries in file\n"
        f"  {result['inserted']} inserted, {result['updated']} updated, {result['skipped']} skipped"
    )


if __name__ == "__main__":
    asyncio.run(main())
