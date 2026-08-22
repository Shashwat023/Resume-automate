# Flagged for discussion with senior

Items surfaced during Day 3 (Intelligence + Scraper) implementation that need a product/scope decision, not an engineering one. Not blockers for the current build — noted so they don't get lost.

---

## 1. Bulk-scraping all 409 tracked companies

`config/portals.yml` has two separate lists that look similar but aren't: `tracked_companies` (409 entries — actual companies to scrape) and `search_queries` (45 entries — saved job-board search strings, e.g. "Ashby — AI PM"). 409 + 45 = 454, which is where an earlier, incorrect "454 companies" estimate came from — corrected here.

More importantly: **every single one of the 409 tracked companies has `scan_method: websearch`** — verified by parsing the file directly, not sampling. None of their `careers_url` values resolve to a Greenhouse or Lever URL (the only entries that looked ATS-hosted, e.g. `https://boards.greenhouse.io/`, turned out to be bare host URLs with no company token — junk data, see #2 below, correctly skipped by the seeder). So there is currently **no free/fast tier** for any of the 409 real companies — every one of them would need a real browser session + an LLM `extract()` call to discover job postings.

That makes bulk-scraping genuinely expensive: hours of browser time (headed Chrome, page loads, waits) plus real LLM spend across up to 399 pages (409 minus the 10 skipped junk entries), run one at a time (the automation is single-session by design — see PLAN.md's Chrome session model).

**What exists today:** `python -m app.scripts.seed_portals` loads all 399 valid entries into the `tracked_companies` table (metadata only, free, instant — verified live: 399 inserted, 10 skipped, re-running is a no-op). Actually *scraping* a company only happens when `/api/admin/sync` is called for that one URL — so scraping stays entirely manual/opt-in, one company at a time, via the existing Admin page. Nothing scrapes automatically on a schedule or in bulk.

**Needs a decision:** if/when bulk coverage across all 399 is wanted, that's a real scheduling + cost-budget question (batch size, rate limiting, retry policy, a dollar ceiling) — not something to default into without sign-off. Given zero of them have a free API path, this is a bigger cost commitment than initially scoped.

---

## 2. Junk entries in `portals.yml`

Some `careers_url` entries are bare ATS host URLs with no company token at all — e.g. `https://boards.greenhouse.io/`, `https://jobs.lever.co/`. These can never resolve to an actual job board; they're a data-hygiene issue in the source file. `seed_portals.py` detects and skips these (logged, not counted as a failure), but the underlying file could use a cleanup pass.

---

## 3. No authentication

`profile_id` from browser localStorage is the de-facto session key across the whole API — any client can pass any `profile_id` and read/act on that profile's data. Explicitly accepted for this build phase per an earlier decision (see PLAN.md), carried forward here since it's still true.

---

## 4. No database migrations (Alembic)

Schema changes go through SQLAlchemy's `create_all()`, which only creates missing tables — it does **not** alter an existing table's columns. Day 3 added two columns to `AnswerLibrary` (`source`, `confidence`); picking those up required deleting the local dev `app.db` (gitignored, disposable) and letting it recreate. Fine for solo/dev use; will need real migrations before this has any persistent production data worth preserving across a deploy.

---

## 5. Two pre-existing bugs, found but not fixed (carried over from the clean-architecture restructure pass)

- **`frontend/src/pages/AdminPage.tsx`**'s scrape-results table has a malformed JSX `<a>` tag — the `href`/`target`/`rel`/`className` attributes render as literal visible text instead of being attributes on the tag, and the resulting link has no `href` at all. It's syntactically valid JSX (that's why the build never caught it), just semantically wrong. Left as-is because fixing it changes visible page output, and the restructure's mandate was zero visual change.
- **`app/domain/semantic_dictionary.py`**'s `\baddress\b` pattern matches a relocation *judgment* question ("What is the address from which you plan on working? ... type 'relocating'") as if it were a literal home-address field. Currently harmless — it only fires when `profile.address` happens to be set, and even then just fills a literal address into a field that's really asking a yes/no relocation question. Caught while writing `tests/test_domain_semantic_dictionary.py`; not fixed since it's shipped Tier-0 matching behavior and not in scope for either the restructure or Day 3.

---

## 6. Frontend `npm run build` is broken independent of app code

The `build` script is `tsc -b && vite build`. On this machine, `npm`'s configured `script-shell` is Windows PowerShell 5.1, which doesn't support `&&` as a statement separator — the script fails immediately with a parser error, before either `tsc` or `vite` even runs. Worked around throughout by running `npx tsc -b` and `npx vite build` separately. Also, `npx tsc -b` on its own surfaces 2 genuinely pre-existing type errors (`src/api/resume.ts`, `src/app/router.tsx`) unrelated to any of this work.

---

## 7. Tier 1 (LLM) confidence and cost, in practice

`settings.tier1_confidence_threshold` defaults to `0.6` — chosen as a starting point, not empirically tuned against real forms yet. Worth revisiting once there's a broader sample of live runs across more than one ATS/company.

Cost is logged per application (`RunEvent` with token counts), but there's no aggregate dashboard or budget alerting yet — worth having before this runs unattended at any real volume.
