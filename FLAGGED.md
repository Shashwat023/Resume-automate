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

`settings.tier1_confidence_threshold` is `0.5` (Day 4, per direction). As of Day 4 it **only gates the answers-library cache**, not whether a field gets filled — Tier 1 now fills every field regardless of confidence (accepted tradeoff, see PLAN.md Day 4 Part C). Not empirically tuned against a broad sample of real forms yet.

Cost is logged per application (`RunEvent` with token counts), but there's no aggregate dashboard or budget alerting yet — worth having before this runs unattended at any real volume.

## 8. File-upload attach (Tier 0) is implemented and unit-tested, but NOT confirmed working live — real discrepancy found, unresolved

`fill_deterministic()` calls `Locator.set_input_files()` (Stagehand) against the real `<input type=file>` for the "Resume/CV" field on Anthropic's live Greenhouse form. The call returns **no error**. But live verification (raw JS `evaluate()` against the actual DOM, not just our own log) shows:

- Before the call: 2 `<input type=file>` elements exist on the page (Resume/CV, Cover Letter), both `files.length === 0`.
- Immediately after the call (same script run, no delay): querying the *exact same xpath* Stagehand itself just used, via native `document.evaluate()`, returns **not found**. The same xpath resolves fine via `document.evaluate()` *before* the call, so the xpath format itself isn't the issue.
- After a short wait, the file-input count on the page drops from 2 to 1, and the Resume/CV section's node IDs change entirely on re-snapshot — but it re-renders back into the same **unattached "Attach" state**, not a "file selected" state. No filename, no "remove" affordance, no visible error either.

Working theory, not confirmed: Greenhouse's upload widget's own change handler (likely `react-dropzone` or similar) doesn't recognize the CDP-injected file selection as a trusted enough event and silently resets, or Stagehand-python's RPC-based `set_input_files` handler behaves differently from Playwright's native implementation for this specific widget shape. Root cause not isolated — would need either manual `change`/`input` event dispatch experiments, or trying Tier 2's `observe()`/`act()` path (a real synthetic click that opens the OS file picker) as the more reliable alternative, mirroring the two-step fix Day 3 needed for custom comboboxes.

**Do not treat file attachment as working until this is resolved and re-verified with the same "check the real DOM, not the log" discipline.** Code and tests describe the intended behavior; the live form does not yet confirm it happens.

## 9. CAPTCHA, 2FA, and submission are implemented and unit-tested but NOT live-verified end to end

Day 4 Parts D/E/F were built and verified only at the unit-test level (fake 2captcha client, hand-written accessibility-tree fragments). None of the following has been exercised against a real browser session:

- **CAPTCHA solving.** A real solve costs 2captcha balance and can take up to 10 minutes; Anthropic's live form uses an *invisible* reCAPTCHA Enterprise widget (confirmed present via Day-4 recon), which may only render once a real submit is attempted — not safe to trigger without also risking a real submission. Detection's iframe-URL regex is grounded in that real, captured iframe source; solving and token injection are not.
- **2FA detection.** No form encountered anywhere in this project's live testing (Day 1 through Day 4) has actually presented a 2FA/OTP challenge, so `twofa_detect.py`'s label-pattern regex has never matched a real one. It's a reasonable pattern set, not a confirmed one.
- **Automated submission.** `submit_enabled` defaults to `False` specifically so this stays true — no real ATS form has been submitted through this pipeline. The bounded validation-error repair pass (rerun the fill cascade once, retry submit once) has likewise never run against a real validation error.
- **The planned local mock ATS form** (PLAN.md Part F) — the one thing that would let the submit path be tested deterministically and repeatably instead of "unit-tested logic + never exercised live" — was not built this pass. It's the single highest-value next step before trusting F at all.

None of this should be treated as working until it's actually been run once, deliberately and supervised, against something real (the mock form first, then one real ATS form with `submit_enabled=True`).
