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

## 2. Junk entries in `portals.yml`  — still open (data hygiene, unchanged)

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

## 6. Frontend `npm run build` — FIXED

Was `tsc -b && vite build`; PowerShell 5.1's `script-shell` doesn't support `&&` as a statement separator, so the script failed before either half ran. Fixed with npm's own `pre`-script hook instead of a shell operator — `"prebuild": "tsc -b"` + `"build": "vite build"` — which npm runs in sequence regardless of the OS shell, and stops on the first failure exactly like `&&` did. Also fixed the two pre-existing type errors this uncovered: `resume.ts`'s `onUploadProgress` callback was typed against the raw DOM `ProgressEvent` instead of axios's own `AxiosProgressEvent` (now imported and used in both `api/resume.ts` and `resume.queries.ts`), and `router.tsx` imported `SettingsPage` but never registered its route — added the missing `ROUTES.SETTINGS` route entry (the page and route constant already existed; only the router entry was missing, so `/settings` 404'd in addition to the unused-import warning). `npm run build` now succeeds end-to-end with zero errors.

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

## 10. Day 4 Part H (per-job pause) — done and live-verified; two more real bugs found along the way

Backend (`paused` status, pre-launch gate, mid-run tier-boundary checkpoints, pre-submit checkpoint, cancel-while-paused via `wait_for_resume_or_cancel`) and frontend (per-row Pause/Resume/History buttons in `QueueTable.tsx`, `paused` status mapping) are both built, unit-tested (217 backend tests), and — unlike most of Day 4 — **actually live-verified**: queued a real application against a real profile, paused it immediately, confirmed via server logs that Chrome never launched and status held at `paused` for several seconds, resumed it, confirmed it transitioned to `running` and proceeded.

Two real, independent bugs were found and fixed during that live pass — neither was specific to H, both were blocking it:

1. **`QueuePage.tsx`'s `hasActiveJob` gate only checked the aggregate queue status** (`running`/`paused`), which does not move when a single job is stuck at `needs_input` (2FA) while others are terminal — the exact scenario that most needs the Take-Control UI. `CurrentJobCard` (and therefore the Live View entry point built in Day 4 Part G) was completely unreachable in that case. Fixed by also checking `queueState.currentJobId` directly, which already correctly includes `waiting_for_user`.
2. **The initial profile/job/resume lookup in `runner.py`'s `run_application` had no exception handling at all.** A DB error there (this session hit exactly one: a stale dev `app.db` missing the `parsed_facts` column — see #4, no Alembic) killed the background task silently — no `FAILED` status, no error message, no logged event, the application just sits at `queued` forever with zero explanation anywhere in the UI or logs. Fixed by moving that lookup inside the same try/except that already handles every later failure. Confirmed live: after the fix, a genuine failure (a Stagehand init timeout, likely from many stale Chrome profiles accumulated during this session's own extensive testing) was caught and logged with a clear message instead of hanging.

**Not yet exercised live**: cancel while genuinely paused mid-run (unit-tested via `wait_for_resume_or_cancel`, not run against a live browser session), and pause at the mid-run tier-boundary checkpoints specifically (only pause-before-launch and the full lifecycle were live-tested — the tier-boundary and pre-submit checkpoints share the same `_check_paused_and_wait` code path, so this is lower risk, but it's still an honest gap).

## 11. Real bug reported and fixed: multiple applications for one profile raced on a single shared Chrome session

Reported live: queuing several applications against the same profile in quick succession produced `[stagehand] ERROR CDP response failed ... Frame with the given frameId is not found` and every job failed near-instantly or after a timeout — "not a single form is getting filled."

**Root cause**: `chrome_launcher.get_or_launch(profile_key)` deliberately returns ONE shared Chrome session per profile (so cookies/login persist across a profile's applications — see PLAN.md's "Chrome session model"). But `worker/queue_runner.py`'s own docstring *claimed* "browser automation is stateful and serial per profile" without that ever actually being enforced — `enqueue_application()` spawns a task for every queued application immediately, with nothing stopping two applications for the same profile from running concurrently, both driving the same browser, racing over the same pages/frames.

**Fix**: `queue_runner.get_profile_lock(profile_key)` — an `asyncio.Lock` per profile, held by `runner.py` for the entire Chrome-touching portion of a run (including while paused/2FA/CAPTCHA-blocked, since a paused application still "owns" that page's current state). A second application for the same profile now genuinely waits its turn instead of racing. Unit-tested (serialization order asserted directly) and **live-verified**: queued two applications for the same profile back-to-back, confirmed via server logs that only one Stagehand session initialized at a time.

## 12. Real bug reported and fixed: CAPTCHA solving crashed with `ApiException: ERROR_PAGEURL` on every real run

Reported live, in the same session as #11 — once concurrency stopped masking it, this was the very next thing blocking every run: `services/captcha/service.py::resolve_captcha` called `solve(challenge, page.url)`, but **`Page.url` is an async method on Stagehand's `Page`** (`async def url(self) -> str`), not a plain property. `page.url` alone evaluated to the bound method object, not a string, which 2captcha's API correctly rejected as an invalid page URL. This escaped the unit test suite because `test_captcha_service.py`'s `FakePage` had `.url` as a plain string attribute — the fake didn't match the real class's actual shape, so the test suite validated the wrong contract.

**Fix**: `await page.url()`. `FakePage` in the test suite was also corrected to model `url()` as an async method, so this class of mismatch is caught in future. **Live-verified**: requeued a real application, confirmed the log now reads `CAPTCHA solved (recaptcha)`, and watched the run proceed through the full Tier 0→1→2 cascade to completion (4 Tier 0 fields, 8 Tier 1 fields, 13 Tier 2 fields resolved, 2 left unhandled) — the first fully successful end-to-end live run of the complete Day 4 cascade.

## 13. Real bugs found running actual end-to-end submissions (Day 5, real personal data): submit button unreachable, and a deeper Tier 2 false-success

Found live, testing with `SUBMIT_ENABLED=True` and the user's real profile/resume against a real Anthropic Greenhouse form — two more genuine bugs, both now fixed:

1. **`_SUBMIT_BUTTON` (submit.py) and `_APPLY_BUTTON` (runner.py) both used `^`/`$` anchors without `re.MULTILINE`.** Without that flag, `^`/`$` only anchor to the whole tree STRING's start/end, not each line — so neither regex could ever match a button in the middle of a real, multi-line accessibility tree, only the degenerate case where it happened to be the first/last line. This blocked EVERY real submission attempt with "submit button not found." The Apply-button half of this bug was silently masked the entire project, because every URL actually tested shows the form directly with no landing-page click needed — its always-broken return value never mattered until now. Every existing unit test for both regexes used single-line tree fixtures, which trivially satisfy `^`/`$` regardless of the bug — added real multi-line fixtures (captured from the live form) to catch this class of regression going forward.

2. **Tier 2 reported "resolved" for a field whose own description said it wasn't.** `act()`'s `success=True` only means the click executed, not that the widget's value changed. Real log line: `Agreement to Arbitrate` logged as resolved, while its own `action_description` read *"...currently showing 'Select...' option"* — the unselected placeholder. Fixed in the previous session with a DOM read-back (`_verify_not_still_placeholder`, reading `field.xpath`'s `inner_text()`) — **that fix was itself wrong, and worse than the bug it fixed.** Live-verified next session: on this exact widget shape (a real ARIA `role="combobox"` `<input>`, used only for keyboard/search — a common pattern), the VISIBLE selected value is rendered by separate SIBLING elements outside that input's own subtree. Both `inner_text()` and `input_value()` on `field.xpath` are structurally always empty, selected or not — confirmed with a direct before/after live check (`''` both times, `act()` genuinely succeeding in between). Result: a 100% false-negative rate — every single Tier 2 field across an entire real run got flagged as "still shows a placeholder" and rejected, even though selection had genuinely worked, which is what actually caused every real submission attempt to fail with "This field is required." Refixed by going back to the ORIGINAL reliable signal: check the model's own `action_description` text for a **quoted** placeholder phrase (e.g. `'Select...'`) rather than querying a DOM element whose relationship to the visible value varies by site. Quoted-only matching specifically avoids false-positiving on ordinary phrases like "Select the option" that legitimately contain the word "select". Live-reconfirmed working after the refix.

3. **Exact-value dropdown matching left required fields blank when the ATS's real option wording didn't match Tier 1's guess.** Tier 1 decides a value *before* the dropdown is ever opened (the real options aren't in the tree until then), so its answer is often a reasonable paraphrase — "1-2 years" vs the ATS's actual "Less than 5 years" bucket — and the exact-wording select instruction then finds nothing. Fixed with a fallback retry: when the exact-value instruction finds no match, retry once with an instruction that explicitly permits the closest available option instead of an exact match. Accepted tradeoff, same reasoning as Tier 1's own "always answer" — an approximate selection beats a blank required field on a fully-automated submission.

4. **Added a proactive, targeted repair pass before the FIRST submit attempt**, not just reactively after a validation error — scoped to only the fields nothing handled in the first pass (re-collected fresh by label, since xpaths can drift). Deliberately narrower than a full cascade re-run: blindly re-running Tier 1+2 on already-succeeded fields would re-execute their clicks too, and a checkbox/dropdown "set" action isn't guaranteed idempotent — re-clicking an already-checked box can toggle it back off.

5. **Added an explicit scroll-to-top immediately before the final submit-button search**, per a live observation that the page had scrolled during the fill cascade. The accessibility-tree snapshot itself isn't scroll-dependent, so this is presented as a safety/hygiene measure rather than a proven root cause — the real root cause of "submit button not found" was #1 above.

**Status as of this fix**: #1 confirmed live. #2's refix is now live-confirmed working: a real run resolved **13 of 19** Tier 2 fields correctly (Country, visa sponsorship x2, relocation, AI policy, interviewed-before, cybersecurity products, AI/ML models, role preference, engineering background — real descriptions naming real selected options, not placeholder text). #3 (closest-match fallback) is live-confirmed engaging correctly. #4 (targeted pre-submit repair) confirmed running. #5 (scroll-to-top) shipped as a safety measure, not a proven root cause.

**Still no real application has completed submission** — every attempt so far has been cut short by the OpenRouter key running out of credits mid-run (two different keys now, $10 and $5, both exhausted across this testing). The remaining 6 unresolved fields in the most recent run (including the required "Agreement to Arbitrate") failed with `402 Payment Required`, not a code issue — this is now clearly a live-testing-budget problem, not a correctness problem.

**Minor edge case spotted — now FIXED**: the closest-match fallback (#3) could report `resolved` for a selection where its own description explicitly said no match was found — e.g. `"How many years of professional software engineering experience..."` resolved with description *"The '1-2 years' option was not found in the dropdown... There is no '1-2 years' option visible."* — `act()` still reported `success=True` (something was clicked), and the description didn't quote a literal placeholder string, so the original check couldn't catch it. Fixed in `tier2_resolve.py` with a second, independent check (`_NO_MATCH_PHRASES`) alongside the placeholder-quote check — matches phrases like "not found", "there is no ... visible", "could not find", "no matching option" — renamed `_check_description_for_placeholder` to `_check_description_for_failure` since it now catches both shapes. Unit-tested against the exact real description text above, plus a genuine-success description to confirm no false-positive. **Not live-reconfirmed** — no live credits spent verifying this specific fix; same caveat as the rest of this section.

**Also worth knowing**: several answers now cached in the answers library from these live runs are LLM guesses that could not be verified against the real candidate's actual circumstances (e.g. work authorization / sponsorship status, years of experience, country). If any are wrong, they will be reused automatically in future applications against the same questions until corrected.

## 14. Real bug reported and fixed: Tier 0 filled the Phone field with a mangled number

Reported live: the Phone field showed `03545037` instead of the real number. Two real, distinct bugs stacked here:

1. **Country-code duplication** (the original report): the profile stores phone WITH its country code (`+918303545027`), correct for a single combined phone field. This real form splits entry into a separate Country/dial-code dropdown PLUS a plain Phone textbox, so filling the raw value duplicated the code (`+91` selected in Country, `+91...` typed into Phone too).
2. **A second bug found fixing the first**: the initial fix used a regex (`^\+\d{1,4}[\s\-]*`) that greedily eats up to 4 digits after `+` — but calling codes are 1-3 digits and genuinely ambiguous from the digit string alone (`+1` is 1 digit, `+91` is 2, `+971` is 3). Live-confirmed: against `+918303545027` it ate `+9183` instead of `+91`, leaving the exact mangled value reported (`03545027`, off by one digit from the report — same root cause).

**Fix**: replaced the regex with `phonenumbers` (Google's libphonenumber Python port), which parses against the real ITU calling-code table instead of guessing a digit count. Only strips when a sibling Country-labeled combobox actually exists on the page (unchanged from the original design) — a form with one combined phone field still gets the full number. Unit-tested against 1-, 2-, and 3-digit calling codes specifically, since that's exactly the dimension the first, wrong fix got wrong. **Not yet live-reconfirmed** — found and fixed while a live run was stuck (see #15), not verified against the real form again yet.

## 15. Real bug found and fixed: no timeout anywhere in Tier 2 — a single bad call could hang an application forever

A live run got stuck twice at the same field with zero progress, zero error, zero log line — genuinely hung, not just slow. Backend log showed a CDP-level error immediately before the hang: `[stagehand] ERROR CDP response failed {"method":"Input.dispatchMouseEvent","error":"-32602 Invalid mouse button"}`. Whether that CDP error is what caused the subsequent hang, or just preceded it, wasn't conclusively isolated — but the deeper, definitely-real bug is that **nothing in `tier2_resolve.py` bounded how long an `observe()`/`act()` call could take at all**. A hang there had no way to resolve itself short of killing the whole process.

**Fix**: every `observe()`/`act()` call site now wrapped in `asyncio.wait_for(..., timeout=120)`. 120s chosen because real observe() calls on `qwen/qwen3.6-27b` have been seen taking up to ~78s live — well above that, not tuned to the failure. A timeout now surfaces as a normal, recoverable `ERROR:observe() failed: ...` for that one field (same as any other exception already handled there), rather than hanging the entire application and its Chrome session indefinitely. Unit-tested (a fake that never returns must produce a bounded error, not hang the test suite). **Not yet live-reconfirmed against the actual CDP "Invalid mouse button" trigger** — that specific error's root cause (possibly Qwen-specific action-generation producing a malformed click parameter) is still unresolved; the timeout makes it recoverable, not fixed at the source.

## 16. Freeze-cause code scan (requested after two live runs stalled) — four fixes applied, root CDP cause still not isolated

Requested after "still frozen for 38 mins" during Day 5 live testing. A static scan of every await between Tier 0 and Tier 2 found the completed 120s Tier 2 timeout (#15) had already turned that specific case into a clean failure rather than a hang — but several other unbounded waits in the same request path were still real latent freezes, not yet hit live but structurally identical to #15. All four are now fixed:

1. **2captcha's own SDK defaults were never overridden.** `recaptchaTimeout=600`/`defaultTimeout=120` (SDK defaults) run inside `asyncio.to_thread`, which cannot be cancelled — a slow solve blocked the whole application for up to 10 minutes per attempt, twice over (`service.py` retries once = ~20 minutes total, completely unresponsive, indistinguishable from a hang from the UI). Fixed: `solver.py` now passes `captcha_solve_timeout_seconds` (config, default 180s) explicitly for both `recaptchaTimeout` and `defaultTimeout`, plus a `pollingInterval` (default 5s), and wraps the whole call in `asyncio.wait_for(..., timeout=captcha_solve_timeout_seconds + 30)` as a backstop above the SDK's own polling bound (which only bounds the polling loop, not a single wedged HTTP request). Caveat kept honest in the code comment: `to_thread` genuinely can't be cancelled, so the orphaned worker thread may still run to completion in the background — the fix makes the *application* stop waiting and fail cleanly, not guarantee the underlying thread dies.
2. **`page.snapshot()`, `page.goto()`, `page.wait_for_load_state()`, `Stagehand.create()`, and `get_or_launch()` had no timeout anywhere**, in `runner.py`, `tier0_harvest.py`, and the scraper's `sync_service.py` — the same class of bug #15 fixed for Tier 2's `observe()`/`act()`, just never generalized past Tier 2. New shared `app/services/engine/timeouts.py` (`with_timeout`, `describe`) — `tier2_resolve.py`'s private timeout helper was replaced with this shared one rather than kept as a Tier-2-only copy, since the bug was never Tier-2-specific. `PAGE_CALL_TIMEOUT_SECONDS = 60` for these browser round-trips (vs `LLM_CALL_TIMEOUT_SECONDS = 120` for genuinely slow reasoning calls). Each wrapped call names itself in its error (`"page.snapshot exceeded 60s"`) rather than a bare, unactionable `TimeoutError()`.
3. **`detect_2fa` scanned the ENTIRE page tree, including plain body text**, not just interactive fields — a live risk (not yet hit) since a security-role job description mentioning "two-factor authentication," a privacy footer about "verification codes," or a cookie banner could match and pause an application indefinitely waiting for a human who was never actually needed, with no way to tell that apart from a real freeze. Confirmed against job 462's real page text specifically that this risk did not apply there (no trigger phrases present), but it's a live risk in general. Fixed: `twofa_detect.py` now only matches lines that are actual interactive `textbox`/`input` fields or `heading`/`dialog` roles — the only places a real challenge can present itself — never `StaticText`/paragraph/link body prose. Unit-tested that prose alone (even literally containing "two-factor authentication and one-time passcode") no longer triggers a pause, while a real challenge (an input field with an accompanying description) still does.
4. **The per-profile lock (#11) had no timeout on ACQUIRE.** It's correctly held for a run's entire Chrome-touching portion, deliberately including while paused for 2FA — but that means one genuinely stuck run silently blocks every LATER application for that same profile forever, with those later applications showing no error at all: they simply never start, which looks identical to the underlying freeze one level up. Fixed: `queue_runner.py` adds `profile_session()` (an async context manager wrapping `get_profile_lock` with `asyncio.wait_for` on the acquire only — release behavior of an already-held lock is unchanged) and `PROFILE_LOCK_TIMEOUT_SECONDS = 1800` (30 minutes, well above the longest real run observed so far). A timed-out acquire raises `ProfileBusyError`, which `runner.py`'s existing catch-all exception handler turns into a normal `FAILED` status with a clear message instead of an invisible indefinite queue stall. `runner.py` now uses `profile_session` instead of calling `get_profile_lock` directly.

**Root cause NOT isolated by this pass, deliberately left open**: the CDP error that preceded the original hang, `[stagehand] ERROR CDP response failed {"method":"Input.dispatchMouseEvent","error":"-32602 Invalid mouse button"}` (9 occurrences in one run), still has no confirmed cause. Working theory, unconfirmed: Qwen-specific action-generation producing a malformed click parameter that the CDP layer rejects, which may be what wedges the RPC connection in the first place (`observe()` then hangs on that stuck connection until the new global timeout catches it, and the eventual `RPC client is closed` cascade follows). These four fixes make every consequence of that error recoverable rather than a silent freeze; they do not prevent the CDP error from happening. Would need either a live repro with request/response-level 2captcha/Stagehand logging, or reporting it upstream to Qwen/Stagehand, to actually isolate.

**Not live-reconfirmed**: none of these four fixes has been exercised against a real browser session yet (same live-credit constraint as #13/#14). All are unit-tested in isolation (`test_captcha_solver.py`'s two new tests, `test_twofa_detect.py`'s scoping tests, `test_worker_queue_runner.py`'s `profile_session` timeout test) and the full 251-test backend suite passes.

## 17. Four more real bugs found live in the second-pass test (Day 5+, deepseek-v3.2 test run): phone fallback, blind arbitration-text guessing, and a real fix for `-32602`

Found and fixed live, testing again against the real Anthropic Greenhouse form:

1. **Phone number got a wrong, domestic-format value ("08303545027" — a leading 0) on a form where Tier 0's textbox match should have caught it but apparently didn't.** Root cause of WHY Tier 0 missed this specific field not isolated (a label-parsing quirk on that tree, or a missing xpath at harvest time) — but wherever it falls through, Tier 1 was free-forming a phone value from resume/profile text with no country-code awareness at all, since the stripping logic (`tier0_harvest.py`'s `strip_country_code`, see #14) only ever ran in Tier 0's own code path. Fixed: `strip_country_code` made a public function, and `tier1_map.py`'s `_apply()` now applies the exact same normalization — keyed off `semantic_dictionary.match_field()`, not a hardcoded label — to any phone-like field Tier 1 ends up handling, computing the same "does a sibling Country selector exist" signal `map_fields` already has visibility into. Closes the gap regardless of which tier ends up writing the field.

2. **`-32602 Invalid mouse button` confirmed to be genuinely non-deterministic** — reported live: the same question, asked on two separate application runs against the same job, failed in one run and succeeded in the other. Root cause investigated further: `act()` dispatches a click via CDP's `Input.dispatchMouseEvent` (a "trusted" synthetic input event) — Chrome's own CDP layer is rejecting the button parameter before it ever reaches the page's JS. Stagehand exposes a structurally different mechanism, `Locator.send_click_event()`, which dispatches a real DOM `MouseEvent` directly via JS against the resolved element, entirely bypassing that CDP input pipeline — exactly the "custom widgets that listen for synthetic DOM events rather than trusted clicks" fallback PLAN.md's Part C anticipated but never wired up. Fixed in `tier2_resolve.py`'s `_act_with_retry`: on a `-32602` failure, try `send_click_event()` on the resolved Action's selector BEFORE falling back to a second plain `act()` retry (switching mechanisms is more likely to succeed than repeating the identical CDP call the browser just rejected). Not yet live-reconfirmed against the specific field that failed non-deterministically, but unit-tested for both the success and the fall-through-to-plain-retry paths.

3. **New fallback: required fields outside the pipeline's actual scope now pause for a human instead of silently failing or guessing.** Reported live: "Please read the arbitration agreement below" isn't a widget-resolution problem — it's a comprehension task (read an embedded legal document, then answer), which no amount of retrying `observe()`/`act()` will ever fix, and per the Day-4 scope correction 2FA was supposed to be the ONLY human-in-the-loop point. Added `_escalate_unhandled_required_fields_if_any()` in `runner.py`, using the exact same pause/Live-View/resume pattern already proven for CAPTCHA-escalation and 2FA (`NEEDS_INPUT` status, `wait_for_resume_or_cancel`). Scoped to REQUIRED fields only (`FormField.required`, the ATS's own `*` marker) — an unresolved OPTIONAL field is still left blank exactly as before. Wired in at both repair checkpoints: the pre-submit targeted repair and the post-validation-error targeted repair (see #16's fix to that same call site). Unit-tested: pauses and correctly resumes for a required-unhandled field, does NOT pause when only optional fields are unhandled.

4. **Root-caused and fixed why the pre-submit repair pass never actually triggered, and why the post-validation retry reran the ENTIRE cascade (~10-25 min) instead of a handful of fields — cutting live run time roughly in half.** `_unhandled_labels()` counted a field as "handled" the moment `tier1.from_library` had an entry for it — but `tier1_map.py`'s `map_fields()` appends to `from_library` unconditionally the instant a cached ANSWER exists, before it's known whether that field is a direct fill or a for_tier2 custom widget needing a real click. A live run had Tier 2 explicitly log failures for 'Country' and 'Agreement to Arbitrate' (both cached answers) in the same pass, yet the completion summary still claimed "0 still unhandled" and skipped repair entirely — deferring everything to the far more expensive post-submit full-cascade rerun this same fix replaced with the targeted `_repair_unhandled_fields` path. Fixed: `from_library` dropped from the handled-set (it can never legitimately contribute a label `tier1.filled`/`tier2.resolved` doesn't already have — see the in-code docstring for the full reasoning). Unit-tested directly against the real shape (a from_library field with a tier2 failure) and the regression it must not reintroduce (a field tier2 genuinely resolved).

**Also switched Tier 2's model** from `qwen/qwen3.6-27b` to `deepseek/deepseek-v3.2` per user direction after live testing suggested Qwen's action-generation was the likely source of the CDP click errors and slow (sometimes >120s) `observe()` calls — DeepSeek-V3.2 (671B total / ~37B active MoE) reasons better for this kind of agentic action-generation at roughly half Qwen's per-token cost. Confirmed live: the same run that surfaced bugs #1-3 above ran meaningfully faster per-field with DeepSeek (`observe()` calls mostly 2-6s vs Qwen's 15-80s) before an accumulated CDP/RPC failure independently ended that specific run — see #16 for why that failure is now recoverable rather than a silent hang.

**Status**: all four fixed and unit-tested (264 backend tests passing). Not yet live-reconfirmed as a full end-to-end batch — the next live run is the first test of all of them together.

## 18. Real bug found and fixed: a second, differently-named 2captcha exception class bypassed the entire CAPTCHA-escalation fallback

Found live, same test session as #17: a real solve attempt failed with `ApiException: ERROR_CAPTCHA_UNSOLVABLE` and the WHOLE APPLICATION crashed to `FAILED` instead of escalating to a human via Live View — even though `captcha_failure_escalates` (default `True`) exists specifically to make that not happen.

**Root cause**: `2captcha-python` has two entirely separate exception class hierarchies that happen to share the name `ApiException`: `twocaptcha.exceptions.solver.ApiException` (a `SolverExceptions` subclass — what `solver.py`'s `except SolverExceptions` was written to catch) and `twocaptcha.exceptions.api.ApiException` (a bare `Exception` subclass, raised from the package's lower-level HTTP layer and left to propagate up through the solver's own methods uncaught). The real failure came from the second one. Not being a `SolverExceptions` subclass, it sailed straight past `solver.py`'s `except SolverExceptions`, meaning `solve()` never wrapped it as our own `CaptchaError` — so `service.py`'s `resolve_captcha` retry/escalation loop, which only ever catches `CaptchaError`, never even saw it. The raw exception propagated all the way to `runner.py`'s top-level handler and killed the application outright.

**Fix**: `solver.py` now also imports and catches `twocaptcha.exceptions.api.ApiException` and `NetworkException` alongside `SolverExceptions`, wrapping either family into `CaptchaError` the same way. Unit-tested against the exact real failure (`ApiException` from the `api` module, message `ERROR_CAPTCHA_UNSOLVABLE`) to confirm it's now caught and wrapped rather than left raw.

**Not yet live-reconfirmed** that the escalation path itself (pause → Live View → human solves → resume) works end-to-end for a captcha specifically — `test_captcha_service.py`'s existing `test_failure_retries_once_then_escalates_by_default` covers the `CaptchaError` → escalation boundary generically, but this exact exception class was never exercised against a live 2captcha call before now.

## 19. Two more false-success wording variants of #17's "toggle, not select" bug, found on the very next live run

Same false-success SHAPE as #17's fix (a select-step description narrating re-opening the dropdown instead of confirming a specific option was chosen), but different phrasing each time the model happened to word it differently:

- `_NO_MATCH_PHRASES` (added in #17) started FALSE-POSITIVING on the closest-match fallback's own legitimate reasoning — "...that specific option is not present in the accessibility tree. The closest matching option that is visible and available for selection is 'Less than 5 years'." — flagging a genuine success as a failure on nearly every closest-match resolution (which is common, since exact wording rarely matches — see #13). Fixed with a carve-out, `_CLOSEST_MATCH_RESOLVED`: only treat `_NO_MATCH_PHRASES` as a failure when the description does NOT also name a specific resolved option.
- A fourth "toggle, not select" wording slipped past #17's `_TOGGLE_NOT_SELECT_PHRASES`: "Click on the 'Agreement to Arbitrate' dropdown to open it and see the options." — no "toggle", no "the dropdown" after "open". Very likely the actual field behind that run's `"This field is required"` submit failure, since the run's own summary claimed 0 unhandled fields. Added `to open it` / `and see the options` to the pattern.

**This class of bug (natural-language description parsing via regex) is inherently open-ended** — different models, and even the same model on different calls, phrase a non-committal "I opened it" narrative in many ways regex can't exhaustively enumerate. Each fix closes one more observed real case, not the whole space. The real backstop against an unenumerated future wording is #17's human-escalation fallback (`_escalate_unhandled_required_fields_if_any`): if a REQUIRED field's false-success ever isn't caught by these checks, the ATS's own "This field is required" response is still the final safety net (submission fails cleanly with a clear reason rather than silently going through wrong), even though by that point it's more expensive than catching it earlier. Unit-tested for both variants; not yet live-reconfirmed.

## 20. The real fix: stop trusting our own click-success bookkeeping for repair targeting — read the ATS's validation error directly off the page

After #17-19 caught three real false-success wordings and the live run STILL failed submission with "This field is required" despite "0 still unhandled" by our own accounting, it became clear the actual problem wasn't a specific missed regex — it's that **our own Tier 2 success tracking is not a fully reliable ground truth**, and chasing one false-success wording at a time (#17, #18, #19) has diminishing returns; new phrasings can always slip through.

**Fix**: `submit.py` gains `find_invalid_field_labels(formatted_tree)`, which reads the validation error DIRECTLY off the page instead of inferring it from our own bookkeeping — confirmed live (Greenhouse) that the "This field is required" text renders as a plain text node immediately following the invalid field's own label/group in the accessibility tree. Scans every line, attributing each validation-error match to the nearest preceding field label (careful to not let the error text's OWN line, which matches the same `[id] role: text` shape, overwrite the real label sitting above it).

`_repair_unhandled_fields` (runner.py) gains an `also_target: set[str]` parameter — labels to re-target even if `_unhandled_labels` thinks they're already handled. `_submit_and_verify` now calls `find_invalid_field_labels` on the post-submit snapshot and passes the result in as `also_target`, so the ATS's own error location can force a re-target regardless of what our own click-success tracking believes. This doesn't replace the description-parsing checks from #17-19 (they still avoid wasted submit attempts by catching false successes proactively, before ever clicking submit) — it's a second, independent, strictly more reliable layer that only has to be right about WHERE the error is, not WHY the field was never actually filled correctly.

Unit-tested directly (5 new tests: attribution to the nearest preceding label, multiple simultaneous errors, the error-line-overwriting-the-real-label edge case, deduplication, and the no-error case). Not yet live-reconfirmed — the next live run is the first test of this fix.

## 21. Real root cause found for the persistent "Why Anthropic?" failure — a poisoned answers-library cache entry, not a widget bug

Every single live test in this project's history — dating back to the very first bug report ("it skipped this one qn which is marked impt - Why Anthropic?*") — failed to fill this exact field, and none of the Tier 2 fixes (#13, #17-19) ever touched it because it's a plain textbox handled entirely by Tier 1, never Tier 2.

**Root cause, finally isolated**: `answers_library` had a row for "Why Anthropic?" with an EMPTY string as the answer, `source=llm`, `confidence=0.5` (exactly at the cache-gate threshold), created 2026-09-02. The cache-write gate only ever checked `confidence >= threshold` — never whether the answer had any actual content. Once that blank answer got cached, every run since (including every repair pass) reused it: `.fill("")` on the textarea genuinely succeeds with no exception, so it was logged and tracked as a normal success, while the real ATS correctly rejected the empty required field on every single submission attempt. `find_invalid_field_labels` (#20) correctly identified this field as the one the ATS was rejecting, but the repair pass then reused the SAME poisoned cache entry and failed again.

**Fix**, three layers in `tier1_map.py`:
1. The answers-library READ path (`map_fields`) now treats a cached answer with no non-whitespace content as no cache hit at all — falls through to a fresh LLM attempt instead of trusting a blank answer forever.
2. The fresh-LLM-answer path (`_apply_answers`) now excludes empty/whitespace answers from `answered_ids`, routing them into the same one-shot omitted-field repair retry a genuinely missing `field_id` already gets, instead of treating "technically present but empty" as done.
3. `_apply()` itself gained a belt-and-suspenders guard: an empty value for a textbox is now reported as an error ("answer was empty — not filled") rather than silently calling `.fill("")` and letting it look like a success.

None of these write an empty answer to the cache anymore either — closing the loop that created the poisoned row in the first place.

**Also done**: the poisoned "Why Anthropic?" cache row (and the rest of the accumulated answers-library cache and queue/run-event history from this session's extensive testing) was wiped for a clean manual test — profile, resume, and job listings were kept intact.

Unit-tested (3 new tests: a poisoned cache entry is bypassed for a fresh LLM call, a whitespace-only LLM answer is not treated as filled, an empty answer is never written to the cache). **Not yet live-reconfirmed** — the poisoned cache row is gone and the guard is in place, but no live run has been made since this fix to confirm "Why Anthropic?" now actually gets a real answer end to end.

## 22. Two more real bugs found live: a mislabeled invalid field, a broken invisible-reCAPTCHA injection, and the Execution Timeline UI's real root cause

1. **`find_invalid_field_labels` (added in #20) mislabeled a real validation error** — attributed it to "Toggle flyout" (a dropdown's own open/close button text) instead of the actual field, because the "nearest preceding labeled line" walk tracked ANY labeled line, including non-field buttons that happened to sit closer to the error text than the real field's own group label. Fixed: only lines whose role is one of `tier0_harvest.TARGET_ROLES` (the actual fillable field types) or `group` are tracked as candidate labels now.

2. **CAPTCHA token injection never actually worked for Anthropic's real widget.** A live submission was rejected with *"Please complete the reCAPTCHA and resubmit your application"* despite 2captcha genuinely solving the challenge and the token being injected — confirming FLAGGED.md #9's flagged-but-unverified concern. Root cause: writing the solved token into the hidden `g-recaptcha-response` textarea (the only thing `_inject_token` did) is the correct technique for a classic VISIBLE reCAPTCHA v2 checkbox, where the site's own JS polls that field — but Anthropic's form uses an INVISIBLE/Enterprise widget, whose real "solved" state lives entirely inside Google's own JS, set only when its registered callback actually fires. Writing to the DOM field never touches that internal state, so the site's own submit-gate still believed nothing had happened. Fixed: `_inject_token` now ALSO walks `window.___grecaptcha_cfg.clients` (the internal registry `grecaptcha` and `grecaptcha.enterprise` both share) looking for a function property matching `/callback/i` at any nesting depth, and invokes it directly with the token — mimicking what Google's own widget does after a real solve. Kept as an ADDITION to the DOM-field write, not a replacement, since a classic widget may still only need the field. Verified functionally in isolation (Node, a mock `___grecaptcha_cfg` structure with a deeply-nested callback) that the real callback gets found and invoked with the correct token — **not yet reconfirmed against the real Anthropic form**, since this technique reverse-engineers Google's own (unofficial, lightly-versioned) internal structure and can only be fully trusted after a real submission actually goes through.

3. **The frontend's "Execution Timeline" card was stuck on "Reviewing & Submitting" for the entire rest of a real run**, from seconds after it started. Root cause: `TimelineCard.tsx`'s step-derivation treated ANY `[captcha]`-tagged log line as "now submitting" — but CAPTCHA solving happens TWICE in a real run: once immediately after landing on the form (to reveal it, long before any field is filled), and again right before the actual final submit (since invisible/Enterprise widgets often only render once a submit is genuinely attempted). The first, early solve tripped the jump to step 5 immediately, and because the step index only ever increases, every subsequent Tier 0/1/2 log line was then silently ignored — the UI showed "Reviewing & Submitting" while the backend was still filling `First Name`. Fixed: only a `[submit]`-tagged log line (which the backend only ever emits from inside the actual submit-and-verify step) advances to "Reviewing & Submitting" now; the CAPTCHA/2FA-based triggers were dropped entirely as unreliable timing signals. `deriveStepIndex` exported and unit-tested directly (5 new tests, including the exact real log sequence that triggered the bug).

**Also done this pass**: wiped the poisoned answers-library cache and all queue/run-event history (see #21) for a clean manual end-to-end test — profile, resume, and job listings were kept intact.

## 23. Three more real bugs from testing a second, non-Anthropic company (Figma) — plus Layer 2 (bot-detection) and Layer 3 (2FA) hardening

Testing against a company other than Anthropic (to isolate whether earlier failures were Anthropic-specific) surfaced three field-fill bugs, one of which turned out not to be a bug at all.

1. **Phone number gets a leading `0` — investigated, NOT a bug, not fixed.** Verified with `phonenumbers`: `+918303545027` in India's own NATIONAL format is `083035 45027` — the leading `0` is India's legitimate national trunk prefix, added by the phone widget's own re-formatting the moment a country is selected (our `strip_country_code` correctly produces the code-free `8303545027`; Tier 0 fills that first, Tier 2 selects the country afterward, and the widget reformats what's already in the box). Left as-is per product decision; revisit only if a real submission is ever actually *rejected* because of it — no such rejection has been observed.

2. **Dropdown selections landed on the wrong option** (a live run selected "Afghanistan +93" for a Country field whose intended value was "India") **or on nothing at all** (a live run left "Location (City)" blank across the whole first attempt and both repair passes). Root cause: Tier 2's `observe()` is an LLM call (DeepSeek) and is non-deterministic on dropdowns — `act()`'s own `success=True` only ever meant "a click executed," never "the right element got clicked," and nothing verified WHICH option `observe()` had actually found before clicking it. Fixed in `tier2_resolve.py`:
   - **Pre-act verification**: `Action.description` (returned by `observe()`, before any click happens) is now checked against the intended value BEFORE acting — a description naming "Afghanistan +93 option" for an intended "India" is caught and triggers one retry with an instruction explicitly excluding the wrong match by name; if the retry still names the wrong option (or nothing), the field errors out loud into the existing repair pass rather than silently landing on the wrong value. This is a genuinely different (cheaper, more reliable) mechanism than the DOM-read-back approach `#13` already found to be a 100% false-negative for this widget shape — it checks the model's own already-returned description text, not a DOM query, and costs nothing extra in the success case.
   - **Bounded render-poll** replacing the fixed 400ms wait after opening a dropdown (`_wait_for_options_to_render`, polls a generic option selector via `page.evaluate()`, capped ~3s) — reduces how often the option list simply hadn't rendered yet when `observe()` looked, which is plausibly why "Afghanistan" (commonly first in an unfiltered/not-yet-populated country list) got matched instead of "India" in the first place.

3. **A regression from this same session's own earlier fix**: `field_fill.py`'s `fill_textbox` (added to fix Figma's typeahead "Location (City)" field, see below) clicked the FIRST visible `[role="option"]`-shaped element ANYWHERE on the page after typing into any textbox — unsafe if some unrelated dropdown/listbox happened to still be open elsewhere on the page. Fixed: only clicks a suggestion whose own text plausibly contains the value just typed.

**Layer 2 (bot-detection, best-effort, not a guaranteed bypass)**: `chrome_launcher.py`'s CfT launch now passes `--disable-blink-features=AutomationControlled`, removing the `navigator.webdriver=true` signal Chrome sets under CDP control. The persistent per-profile `user_data_dir` already accumulated real cookies/history across runs before this. This is a cheap, low-maintenance supplement — the actual fix for risk-based reCAPTCHA Enterprise scoring remains Layer 1's proxy (`captcha_proxy_url`, see #22-adjacent notes), matching the browser's egress IP to the solving IP; this flag alone does not make that unnecessary.

**Layer 3 (2FA auto-detect)**: `_handle_2fa_if_present` used to pause and block on `wait_for_resume_or_cancel` with NO timeout and NO re-checking of the page — completely silent and indefinite if nobody was watching Live View, or if the challenge could have cleared on its own (e.g. a code answered outside the browser entirely). Now polls every 5s: a manual Resume still works immediately at any point, and on every poll tick with no manual action the page is re-snapshotted and re-checked — if the challenge is gone, the run auto-resumes without any human involvement. If it's still present after 10 minutes with no manual resume either, a new `TwoFactorTimeout` is raised, which the existing top-level `except Exception` in `run_application` already turns into a clean FAILED status, a logged RunEvent, and a released profile lock — the queue advances instead of being stranded. **Not live-verified** — no 2FA challenge has been encountered on any real ATS form tested so far (same caveat `twofa_detect.py`'s own docstring already carries); covered entirely by unit tests (auto-clear, manual resume, cancellation, hard-timeout).

Unit-tested throughout (11 new tests: 3 for the wrong-option pre-act verification and its retry, 2 for the render-poll, 1 for the `fill_textbox` mis-click regression guard, 2 for `wait_for_resume_or_cancel`'s new timeout return value, 5 for the 2FA poll loop's four outcomes). Dropdown fixes not yet live-reconfirmed against Figma or another company — the next live test is what actually validates them.

## 24. Reverted a same-session regression (pre-act description verification), and promoted the typeahead recovery to run before the closest-match fallback

**The revert**: `#23`'s pre-act "does observe()'s returned option actually name the intended value" check was live-tested (Figma, GLM-4.6) and found to be a net-negative regression — it broke three PREVIOUSLY-WORKING fields (Veteran Status, Disability Status, Location (City)) in a single run. Root cause: it demands the returned option literally contain the intended value's text, but EEOC-mandated fields always have Tier 1 deciding a short paraphrase ("Not a veteran") while the ATS's real option is the full compliance-mandated sentence ("I am not a protected veteran") — correct answer, different wording, which the check can't distinguish from an actually-wrong entity match (its original target, Afghanistan-vs-India). Confirmed via the run's own `run_events`: `"Tier 2 failed to resolve 'Veteran Status': observe() kept matching the wrong option (wanted 'Not a veteran', first got 'option: I am not a protected veteran', retry got nothing)"` — a correct selection, rejected. Removed entirely (`_description_names_value` and its call site in `_resolve_combobox`); the existing closest-match fallback already exists specifically to allow this class of paraphrase, and the render-poll fix from the same session is unaffected/kept.

**The reorder**: the typeahead-recovery step (`_type_then_reobserve_select`) was the LAST resort, tried only after the closest-match fallback also came up empty. For a field that's typeahead-driven every time (confirmed: Location (City) has an empty option list until something is typed, full stop), waiting through a doomed closest-match attempt first just wastes a round-trip. Now tried immediately after the exact-match attempt finds nothing, before the closest-match fallback — cheaper and more likely correct for a field whose list was never going to show anything without typing, regardless of wording.

**Also reworded** the final "nothing worked" error to name which strategies were actually tried (exact match, typing, closest-match) and explicitly flag that this may mean the widget doesn't match any pattern Tier 2 currently knows how to drive — distinguishing "no strategy left for this UI shape" from "found options but the guess was wrong," to make future diagnosis faster.

**Broader design gap this pass didn't build** (discussed, not yet implemented): a true generic catch-all for widget shapes entirely outside Tier 2's two modeled patterns (single-click, open+select) — e.g. multi-select, sliders, date pickers, rich text. Current behavior: such a field falls through the combobox path, exhausts all three strategies, and errors out — which already surfaces via the existing required-field escalation (pause + Live View) for anything the ATS requires, and is silently left blank if optional. Not changed this pass because the immediate, concretely-diagnosed problem (typeahead fields, and the regression above) took priority; explicitly flagged as future work if a genuinely unrecognized widget shape is hit live.

Unit-tested: 3 existing combobox tests updated for the new call order (typeahead before closest-match); 3 tests for the reverted pre-act mechanism removed as obsolete. 314 total passing. **Not yet live-reconfirmed** — this fix responds to a live failure but the fix itself hasn't been tested against a real form yet.

## 25. "The agent must never fail and stop on its own" — generalized human-in-the-loop escalation to ANY unresolved field, and closed the final-attempt gap

Per explicit user direction: rather than chase every individual widget shape as it's discovered (today's Location (City) typeahead, tomorrow something else), any field the automation genuinely cannot resolve should fall back to the same human-in-the-loop mechanism already used for 2FA — pause, let the user fill it manually via Live View, then continue — instead of the whole application failing outright.

**Two real gaps closed in `runner.py`:**

1. `_escalate_unhandled_required_fields_if_any` (renamed `_escalate_unhandled_fields_if_any`) only ever escalated fields flagged `required` (our own `*`-marker heuristic). Now accepts `also_target` — always includes any field the ATS's own validation error is blocking on (`find_invalid_field_labels`), regardless of our required guess, since the ATS is what actually decides whether the application goes through.

2. `_submit_and_verify`'s retry loop only ever escalated after the FIRST submit attempt's validation error — the FINAL attempt just returned FAILED outright with no human fallback at all. Extended to three attempts: attempt 0 is the original automated repair (required-only escalation, as before); attempt 1, if still unresolved, broadens escalation to **every** still-unhandled field regardless of required, as the last chance before the final attempt; attempt 2 is that human-assisted final try. Only a genuinely human-assisted attempt that still fails ends the run — not an infinite loop, one bounded extra step.

**Deliberately not built this pass**: the 2FA escalation path polls with a timeout and can auto-resume on its own (see `#23`'s Layer 3); this field-escalation path still waits indefinitely for a manual resume, with no auto-timeout. Flagged as a reasonable follow-up (mirror the bounded-wait pattern here too) rather than scope-creeping this pass, which focused specifically on "never fails silently."

No frontend changes needed — the Live View Resume button added in `#23` is not reason-specific (works for any `needs_input` status, not just 2FA), so it already covers this escalation reason (`manual_fields_required`) too.

Unit-tested: 2 new tests (`test_final_submit_attempt_is_human_assisted_before_giving_up`, `test_final_attempt_still_failing_after_human_help_truly_gives_up`) confirming the broadened escalation targets the right fields at the right attempt, and that a still-failing human-assisted final attempt truly ends the run rather than looping. 316 total passing. **Not yet live-reconfirmed.**

## 26. Real, deeper root cause of "second job never runs": Stagehand's own claimed-browser lifecycle, not the queue logic

Confirmed live, twice: any SECOND application for the same profile within a single backend process's lifetime — cancelled first application or not — instantly failed with `RuntimeError: This browser is already attached to a Stagehand instance`, before doing anything at all.

**Root cause, confirmed against the installed `stagehand` package source, not guessed:** `Stagehand.create(browser=...)` permanently marks that `StagehandBrowser` object as claimed. `Stagehand.close()` (called at the end of every application, including via `#25`'s `try/finally` fix) does **not** release that claim — `_release_browser` is called from exactly one place in the SDK, `_cleanup_failed_create`, used only when `Stagehand.create()` itself fails during initialization. A normal, successful close never un-claims the browser. `chrome_launcher.py`'s `get_or_launch()` caches and reuses the SAME `StagehandBrowser` object per profile (by design, so cookies/login persist across a profile's applications) — meaning the *second* application to ever call `get_or_launch()` for a profile, in the same process, was always going to collide with the first one's now-permanent claim. This is not a cancellation-specific bug or a queue-concurrency bug at all — it reproduced identically when two brand-new applications were queued back-to-back after a completely unrelated prior run had used that profile once.

**Fix:** `ChromeSession` now tracks `handed_out` and the discovered `extension_id`. `get_or_launch()` still hands out the freshly-launched browser as-is on a profile's first call, but on every call after that, it reconnects to the SAME already-running Chrome process (`keep_alive=True` kept it alive) via `local_browser.connect(cdp_url, extension_id=...)` — `connect()` constructs a brand-new, unclaimed `StagehandBrowser` wrapper each time, so there's never a second `Stagehand.create()` against an already-claimed object. Cookie/login continuity is preserved (same Chrome process, same profile directory); only the wrapper object is fresh each time. Applies uniformly to both the default CfT-launch path (extension id discovered once via the same `/json/list` technique already used for the real-Chrome path) and the opt-in real-Chrome path.

Unit-tested: `test_second_get_or_launch_reconnects_instead_of_reusing_claimed_browser` confirms a second `get_or_launch()` call for one profile returns a genuinely different, reconnected browser object rather than the first one, with no second Chrome process launch. 317 total passing. **Live-reconfirmation pending** — the original two-jobs-at-once test that surfaced this is being re-run now that the fix is in place.

## 27. Close the browser session on FAILED/CANCELLED runs; two real frontend control gaps found live

**Backend — "browser is already booked" recovery.** Following `#26`: a FAILED or CANCELLED run left its Chrome session cached and claimed. If that browser (or its extension, per `#26`'s "already initialized" follow-up) ended up in a bad state, every later application for that profile kept failing with no way to recover short of manually killing Chrome — confirmed live. `run_application`'s `finally` block now checks the application's final status and calls `chrome_launcher.close_session()` when it's `FAILED` or `CANCELLED`, discarding that session so the next application for the profile gets a guaranteed-clean relaunch. A run that finishes cleanly keeps its session cached, unchanged — cookie/login continuity across a profile's applications is still the point of the cache. Paired with switching `keep_alive` to `False` (`#`prior entry): `close_session()`'s `session.browser.close()` now actually terminates the underlying Chrome process instead of leaving it running forever.

**Frontend — two real control gaps, both confirmed by reading the code, not guessed:**

1. `QueueTable.tsx`'s per-row action buttons (Pause, Resume, Retry, Skip) were wrapped in `opacity-0 group-hover:opacity-100` — invisible unless the mouse was hovering exactly that row. A running job's own Pause button was there in the DOM the whole time, just never visible without hovering — read as "there's no pause/resume button" live. Now always visible.
2. There was **no** way to resume a `needs_input` job from the queue table at all — only `rawStatus === 'paused'` showed a Resume button; `needs_input` (2FA / manual-field escalation) showed nothing. The only path was `CurrentJobCard`'s "Take Control," which exists for exactly ONE job (whichever the store considers "current") — a second job also reaching `needs_input` had no control anywhere. Added a per-row "Take Control" button for `status === 'waiting_for_user'` that opens the same `LiveView` component (with its own working Resume button, added in `#23`) scoped to that specific row's application id — every job needing input can now be resumed directly from the table, not just "the current one."

Unit-tested (backend): `test_failed_run_closes_the_browser_session`, `test_completed_run_does_not_close_the_browser_session`. 319 total passing. Frontend: `npx tsc --noEmit` clean; not yet manually verified in a live browser.

## 28. #26 and #27's fix were both incomplete — the real constraint is in the Stagehand extension's own JS, and it's permanent, success or failure alike

Live-tested #26/#27's fix (reconnect via a fresh `StagehandBrowser` wrapper + close the session only on FAILED/CANCELLED): queued two jobs, the first one **completed successfully**, and the second one immediately failed with the exact same `RuntimeError`/`RPCError` family — `RPCError: Stagehand has already been initialized`. This proved both prior fixes wrong in the same way: the failure isn't about cancellation, and reconnecting to the same long-lived Chrome process doesn't help.

**Real root cause, confirmed by reading Stagehand's own bundled extension JS** (`stagehand/_extension/service-worker.js`): the extension's runtime state is a one-way machine — `created -> initialized -> closed` — enforced by a literal check (`if (status !== "created") throw new Error("Stagehand has already been initialized")`) with **no reset path anywhere in the code**. This state lives in the Chrome extension's own persistent service worker, tied to the Chrome **process**, not to any Python object. So:

- #26's "reconnect for a fresh, unclaimed `StagehandBrowser` wrapper" fixed the wrapper-level `_claimed` flag correctly, but the SAME underlying extension instance (same Chrome process) still remembers it was already initialized once — a fresh Python wrapper around the same extension state doesn't help.
- #27's "only close the session on FAILED/CANCELLED" was based on the wrong theory that a clean completion left something reusable — it doesn't; the extension is spent either way.

**The actual fix:** every application now closes its own Chrome session unconditionally at the end (`run_application`'s `finally`, regardless of outcome), and `chrome_launcher.get_or_launch()` reverted to its original simple form — reuse the cached session only while it's still open (needed so `live_view_service.py` can attach a second CDP client to a profile's browser while an application is actively paused), otherwise launch a genuinely fresh Chrome process. A fresh process means a fresh extension load, which means a fresh `"created"` state. Cookie/login continuity across a profile's applications comes from reusing the same `user_data_dir` on that fresh launch (unchanged, always worked this way) — not from keeping one Chrome process alive across different applications, which was never actually compatible with how the Stagehand extension manages its own lifecycle.

Unit-tested: `test_get_or_launch_reuses_the_cached_session_while_still_open`, `test_get_or_launch_relaunches_fresh_once_the_session_is_closed` (chrome_launcher), `test_completed_run_also_closes_the_browser_session` (renamed/corrected from the wrong assertion in #27), `test_failed_run_closes_the_browser_session` unchanged. 320 total passing. **Live-reconfirmation pending** — this is the third attempt at this specific bug; the next live two-jobs-in-a-row test is what actually proves it.

## 29. #28's fix had a race condition — closing the session after releasing the profile lock was wrong ordering

Live-tested #28's fix (close every session unconditionally) and it reproduced the SAME `RuntimeError: This browser is already attached to a Stagehand instance` on the second of two concurrently-enqueued jobs. Root cause: the close-session call lived in `run_application`'s OUTER `finally`, which only runs AFTER `async with profile_session(...)` has already exited and released the per-profile lock. A second application, already blocked waiting on that lock, could acquire it and call `get_or_launch()` **before** the first application's own session-close had actually completed — reconnecting to a browser that hadn't finished tearing down yet, reproducing the exact failure #28 was meant to prevent.

**Fix:** moved the close-session call to run from INSIDE the `async with profile_session(...)` block — specifically wrapping `Stagehand.create()` itself (not just the code after it), so the session is discarded even if `create()` fails before `sh` exists at all — guaranteeing it completes before the lock releases. The outer `finally` no longer touches session cleanup at all.

Unit-tested: `test_session_is_closed_before_the_profile_lock_releases` directly asserts the per-profile `asyncio.Lock` is still held (`.locked() is True`) at the moment `close_session()` runs, and released afterward. The two existing close-on-failure/close-on-completion tests were also corrected to mock a session actually being obtained (`get_or_launch` returning a fake session, with `Stagehand.create` as the failure/success point) rather than mocking `get_or_launch` itself to fail, matching the corrected code structure. 321 total passing.

This is the fourth attempt at this one bug (#26 → #27 → #28 → this). Each prior attempt was live-tested and found wrong in a different, specific way — logged here in full rather than quietly overwritten, since the pattern itself (confident fix, live-tested, wrong) is the more useful thing to carry forward: **this class of bug does not get fixed by reasoning about the SDK from documentation or source reading alone — every one of the first three fixes was based on a plausible, source-confirmed theory that still turned out incomplete once actually run.** Live-reconfirmation is still pending for this one too.

## 30. Cancel Run button was disabled on exactly the job most likely to need cancelling

Live-caught from a screenshot: a queue with a single job stuck at `waiting_for_user` (2FA) showed "Idle" as its aggregate status, and the "Cancel Run" button was disabled — no way to cancel the one job actively needing attention.

Root cause: `queue.ts`'s aggregate status computation only counts a job as making the queue "active" when its own status is literally `'running'` (`hasRunning = running?.status === 'running'`) — a job at `'waiting_for_user'` matches neither that nor `hasWaiting` (a different status value, meant for plain queued jobs), so `overallStatus` falls through every branch to its `'idle'` default. `QueueControls.tsx`'s Cancel button disables on `status === 'idle'`.

Fixed narrowly in `QueueControls.tsx` rather than the aggregate computation itself: widening `hasRunning` to include `waiting_for_user` was tried first and reverted — it also flips the top Pause/Resume button's ternary (`status === 'running' ? Pause : Resume`) to show "Pause" instead of the intended "Waiting for you..." for a needs_input job, a worse regression than the one being fixed. Instead, the Cancel button's `disabled` check now also allows canceling whenever `needsInput` is true (checking the actual current job directly, not the lossy aggregate) — leaves every other status-driven UI element untouched.

`npx tsc --noEmit` clean. Not yet manually re-verified in a live browser.

## 31. Cancel added directly to the Live View panel — not routed through the queue-level Cancel button at all

Per user direction: rather than keep fixing the queue-wide Cancel button's gating logic (see `#30`), give the choice right where the user is already looking — the Live View panel now has both **Resume** and **Cancel** side-by-side, using the same per-job `useCancelJobMutation`/`useResumeJobMutation` the rest of the queue UI already relies on. Whoever opens Live View to handle a 2FA/manual-field escalation can immediately decide to proceed or give up, without navigating back to the queue controls.

`npx tsc --noEmit` clean. Not yet manually re-verified in a live browser.

## 32. Scraper's extract() fallback now paginates instead of stopping at the first page

Per user/senior direction: the scraper shouldn't be limited to whatever's rendered on the first page load. `_sync_via_extract` (`sync_service.py`) is now a bounded loop — extract the current page, `observe()` for a "next page"/"load more" control, `act()` to advance, repeat — rather than a single extract() call.

Bounded three independent ways, since this is real LLM spend per page and the pagination control on an arbitrary site can't be recognized with certainty:
1. A page that yields zero genuinely-new `apply_url`s stops the loop (duplicate render or stuck state — no signal to keep going on).
2. No pagination/load-more control found by `observe()` stops the loop (the real end of the listing).
3. A hard cap, `SCRAPER_MAX_PAGES` (default 15), stops the loop regardless — worst-case spend stays predictable even against a page whose pagination this can't correctly recognize, or a genuinely very long listing.

Deduping is cumulative across pages (a `seen_apply_urls` set), not just per-page — a job that reappears on a re-rendered page (common with "Load more" buttons that sometimes duplicate the tail of the previous page) is not re-counted or re-upserted twice.

**Explicitly still not solved** (asked about directly, answered honestly): a bare ATS platform root (e.g. `job-boards.greenhouse.io/` with no company token) has no directory of companies to enumerate — this pagination loop helps once you're on an actual listing page, it doesn't invent one where none exists.

Unit-tested: 3 new tests covering each stop condition (`test_extract_pagination_follows_next_page_until_none_found`, `test_extract_pagination_stops_when_a_page_yields_no_new_jobs`, `test_extract_pagination_respects_max_page_cap`). 324 total passing. **Not yet live-tested** against a real multi-page careers site — the existing Greenhouse/Lever jobs in the DB all came from the free API path, which this doesn't touch.

**Update — live-tested against `jobs.ashbyhq.com/notion` (130 real postings, not Greenhouse/Lever):** ran cleanly end-to-end — one `extract()` call captured all 130 jobs (77 inserted, 53 already existed), `observe()` correctly found no pagination control and the loop stopped without ever calling `act()`. Confirms the refactor doesn't regress the common case. The `act()`-driven click-through path itself (stop conditions 1/2, real page advance) is still unexercised live — this site had no separate "load more" control to click — only unit-tested so far.

## 33. Landing-page careers sites (a "Search Jobs" button, no listings on the URL given) now get one drill-down hop

Live-caught via manual review, not a crash: pasting a marketing/landing URL (e.g. `careers.cargill.com/en`, `salesforce.com/company/careers/`) into sync returned `0 jobs` — correct behavior for the old code, but unhelpful, since the actual listings are one click away behind a "Search Jobs" button.

Distinguished from two related, explicitly out-of-scope cases (see user discussion):
- A bare ATS platform root with no company token — no directory exists to enumerate; still unsolved and unsolvable without a different discovery mechanism (see `#32`).
- A career site split into multiple parallel tracks by experience level (e.g. Cargill's separate Professional / Production / University listings pages) — following one such link arbitrarily would miss the others, and per user's own tradeoff analysis, blindly crawling all of them for a single-persona app would waste LLM spend scraping job levels a given user base doesn't need. **Deferred, not built.**

What's built: if the very first `extract()` call on the given URL finds zero postings, `_sync_via_extract` now tries exactly one drill-down hop — `observe()` for a single "Search Jobs"/"View Openings"/"Current Openings"-style link, `act()` to follow it, then re-`extract()` from the resulting page. If that retry is also empty, it stops for good — no repeated or recursive drilling. Costs at most 3 extra LLM calls (`observe`+`act`+`extract`), and only when page one is genuinely empty.

Unit-tested: `test_extract_drilldown_follows_search_jobs_link_when_first_page_is_empty`, `test_extract_drilldown_not_attempted_when_no_link_found`, `test_extract_drilldown_stops_if_retry_still_empty`. 327 total passing. **Not yet live-tested** against a real landing-page careers site.

## 34. End-to-end test pass on the post-cleanup tree — 7 bugs found, all deferred

Ran a full E2E pass after the dead-code/duplicate-logic cleanup commit (`0029cea`), in three layers: a live-HTTP/WebSocket journey against an isolated backend (53 assertions), a **real-browser** run of the actual automation engine (real Chrome for Testing + Stagehand + CDP) against a local mock ATS form (20 assertions), and a real-browser walkthrough of every frontend route driving the live API.

**All three layers passed** — 53/53, 20/20, and every route rendering against live data. Notably the engine run filled 8 fields from the accessibility tree, correctly attached the resume to `Resume/CV` but **not** `Cover Letter`, honoured the Tier 1 kill switch (no API key -> zero LLM spend), stopped one click short of Submit under `SUBMIT_ENABLED=False`, and released its Chrome session, per-profile lock and queue event maps cleanly. The cleanup commit caused **no regressions**: 327 backend tests, `tsc -b` clean, `vite build` clean, frontend vitest unchanged (same 3 pre-existing `QueueSummary.test.tsx` failures as before the cleanup).

Test safety: the local `.env` has `SUBMIT_ENABLED=True`, so a real run would file a genuine application at a real employer. The whole pass ran on a throwaway DB + storage dir with submit forced off, no OpenRouter key, and `127.0.0.1`/`example.invalid` targets only. `backend/app.db` was never touched.

The bugs below were found by that pass. **All of them are now fixed — see `#36`** for what each fix was and how it was verified. The original diagnoses are kept verbatim below, since the reasoning is what makes the fixes reviewable.

### 34.1 — Profile form loads empty on first visit (looks like data loss) — highest priority
`pages/ProfilePage.tsx` passes `defaultValues: (initialData as any) || {}` to `useForm`. `defaultValues` is captured on the **first render only**, which happens before `useProfileQuery()` resolves — and the `useEffect` that used to re-sync was deliberately removed (see the comment in that file) to stop the cursor jumping mid-type during autosave. Nothing replaced it, so the form is never told the data arrived.

Masked in normal use because `profileStore` is a `persist`-ed zustand store: on the second and later visits the store is already hydrated from `localStorage` at first render, so the form fills correctly. It only bites on a genuinely fresh browser, a new device, or cleared site data.

Reproduced deterministically: cleared `auto-apply-profile-state` from `localStorage` -> reloaded `/profile` -> every field blank (`firstName`/`lastName`/`email`/`phone` all `""`) while the server still held the full profile and the page header still rendered "Ada Lovelace" (the header reads the store, not the form). Reloading again -> all fields populated.

Fix direction: `reset(data)` in a `useEffect` keyed on the resolved query data (not on store identity), so it fires once when data lands rather than on every store write. Restoring the old always-on sync would bring the cursor-jumping bug back.

### 34.2 — A fresh clone cannot boot: `main.py` crashes on import
`main.py` calls `app.mount("/storage/resumes", StaticFiles(directory=settings.resume_storage_dir))` at **module import**, but the directory is created by `lifespan()`, which runs later at startup. Hit on the very first launch of the isolated instance: `RuntimeError: Directory '...' does not exist`. Anyone cloning the repo and running uvicorn before the storage dir exists hits it. Fix: `mkdir(parents=True, exist_ok=True)` immediately before the `mount` call.

### 34.3 — New users stare at a ~9s spinner on the resume page
`GET /api/resume/{profile_id}` returning 404 is the normal "no resume uploaded yet" state, but `main.tsx` configures react-query with `retry: 2`, so it is retried as though transient — three requests with backoff before the upload dropzone appears. Fix: don't retry 404s (a `retry` predicate that returns `false` for a 404).

### 34.4 — Resume card's "File Name" and "Size" are structurally always blank
`ResumeGetOut` returns only `profile_id`, `resume_url`, `uploaded_at` — no filename, no byte size — yet `ResumeCard` renders a "File Name" row (renders empty) and "Size: Unknown size". The queue's `ConfirmQueueDialog` shows the name correctly because it derives it from the URL's last path segment. Fix either way: add `file_name`/`size_bytes` to the schema, or derive from the URL in the card as the dialog already does.

### 34.5 — Queue header contradicts the panel next to it
Observed live: the header read "Queue Status: **Idle** / No active jobs" while the panel immediately to its right read "**Currently Processing** — User Input Required" for the same application. `mapHistoryToQueueState` (`api/queue.ts`) only sets `overallStatus = 'running'` when some item maps to `running`; `waiting_for_user` (i.e. `needs_input`) is excluded, so a run blocked on 2FA/manual input reports the queue as idle.

Related, same function: `completed` counts only `completed` + `failed`, so a **cancelled** job is in `total` but can never be in `completed` — progress is permanently short of 100%. Confirmed live at "2 / 3 done, 1 remaining" with the remaining job cancelled.

### 34.6 — Dead settings control: queue polling interval does nothing
`pages/SettingsPage.tsx` holds `const [pollingInterval, setPollingInterval] = useState('2000')` and renders a select labelled "Queue Polling Interval — 2 Seconds (Default)", but that value is never read by anything; `queue.queries.ts` hardcodes `refetchInterval: 4000`. So the control is inert **and** its default disagrees with the real interval.

Worth noting this is dead code the cleanup pass in `0029cea` could not catch: `pollingInterval` *is* read (by the `<select value=...>`), so neither `noUnusedLocals` nor oxlint flags it. Only running the UI reveals it.

### 34.7 — Breadcrumb is wrong on two routes; `/settings` is unreachable from the nav
`DashboardLayout` derives the breadcrumb with `navItems.find(i => i.path === location.pathname)?.name || 'Dashboard'`. `navItems` has no entry for `/settings` or for an unknown path, so both `/settings` and the 404 page display the breadcrumb "Platform / Dashboard". `/settings` also has no sidebar link at all — the route exists and renders fine, but is only reachable by typing the URL.

### 34.8 — Observation, not yet a bug: `created_at` ties make job ordering non-deterministic
`Job.created_at` is `DateTime` with `server_default=func.now()` at **second** granularity. A bulk scrape inserting many jobs within the same second gives them identical timestamps, and `JobRepository.search` orders solely by `created_at` — so ties resolve arbitrarily and `LIMIT/OFFSET` pagination over them can skip or repeat rows between pages. Surfaced while writing the E2E: three jobs seeded in one statement were returned in the *same* order for both `sort=oldest` and the default newest-first, until the seed was given explicitly distinct timestamps. Fix: add `Job.id` as a tiebreaker to both order-by branches.

### Not covered by this pass
Live-view screencast against a real Chrome session (only the 4404-rejection path was exercised); the admin scrape button (real outbound network + LLM spend); real ATS submission; and the Tier 1 / Tier 2 LLM paths — the harness ran keyless deliberately, so everything past Tier 0 in the cascade is still only unit-tested.

## 35. Category 3 (multi-track career portals) built, and the 3-category cascade collapsed from 9 LLM calls to 1 decision call

Two requests that turned out to be the same change.

### The problem with the old cascade

Scraping an unknown careers page worked by *guessing and retrying*: assume the postings are on the pasted URL and `extract()`; if that came back empty, assume it's a landing page and `observe()` + `act()` + re-`extract()`. Each attempt was its own `extract`/`observe`/`act` round trip, so probing the page shape cost up to **9 LLM calls before a single job was read** — and category 3 was never reached at all, because the single drill-down hop followed exactly one link and then stopped.

### What category 3 is

A career portal that splits its openings across **several parallel tracks on the same site**, each behind its own "Search Jobs" button — Cargill's Professional / Production / Students sections being the live example. `#33` identified this shape and **explicitly deferred it** ("following one such link arbitrarily would miss the others... Deferred, not built"). Per user direction it is now built: every track is visited in turn and all of their postings are listed.

### The fix: assess once, dispatch free

One structured `extract()` call (`_assess_page`) now answers both questions in a single response — *"are the postings on this page?"* and *"if not, where are they?"* — returning `jobs` **and** a list of `sections`, each with a label and a URL.

Asking for **URLs** rather than using `observe()` is the load-bearing detail. `observe()` returns an Action that only `act()` can execute — 2 LLM calls per hop — whereas a URL is navigable with `page.goto()` for free. That is what makes visiting N tracks affordable instead of costing 2N extra calls.

| Page shape | LLM calls before | after |
|---|---|---|
| Cat 1 — postings on the pasted URL | 1 | **1** (the assessment returns them; no second extract of the same page) |
| Cat 2 — one "Search Jobs" entry point | 4 | **2** |
| Cat 3 — N parallel tracks | never reached | **1 + N** |

Categories 2 and 3 are deliberately the *same* code path — the only difference is how many entry points came back.

### Decisions worth challenging

- **The category is derived, not asked for.** The schema has no `category` field. A model can answer `"multi_section"` and then return one section, at which point the label and the data disagree with no way to tell which is wrong. Counting the sections actually returned cannot contradict itself.
- **A page that yields postings does NOT also chase its sections.** On a real listing page, links that look like "other sections" are usually filters over the *same* jobs, and following each costs a page load plus an `extract()` to re-discover postings the dedupe set then throws away. **Known cost of this choice:** a portal that both lists jobs directly *and* hides more behind parallel tracks will miss those tracks. Flagged rather than silently assumed away.
- **`_usable_sections` assumes the answer may be wrong.** Relative hrefs are resolved against the current page; `mailto:`/`javascript:` are dropped; a link back to the page we're already on is dropped (a "Careers" nav link pointing at itself would otherwise burn a reload and an extract); duplicates are dropped ignoring fragment and trailing slash; and the whole list is capped by `SCRAPER_MAX_SECTIONS` (default 6) so a mis-identified nav menu or office-location list can't become an unbounded crawl.
- **One dead section does not abandon the others** — a failed `goto()` skips that track and continues. Conversely an assessment-call failure still propagates, because that means we learned nothing about the page at all: the same "scrape failed" outcome the plain `extract()` had before.
- **Dedupe is shared across sections**, so a graduate role listed under both "Professional" and "Students" is inserted once, not twice.

### Not changed

Pagination *within* a listing page still costs `observe()` + `act()` per page — that is a genuinely different control (often a button with no href) and was out of scope here. It remains the biggest remaining per-page cost and is the obvious next optimization if spend matters.

### Testing

12 new tests, **336 total passing**, ruff clean. Call counts are asserted exactly, not approximately — `test_category2_single_section_is_navigated_and_harvested` pins 2 extracts and **0** `act()` calls; `test_category3_visits_every_section_and_lists_all_jobs` pins 4 extracts for 3 tracks and asserts the exact `goto()` sequence. Also covered: cross-track dedupe, the `max_sections` cap, a dead section not aborting the run, and category 1 not chasing sections.

**Not yet live-tested** against a real multi-track portal (e.g. `careers.cargill.com/en`). The unit tests fix the control flow and the call counts; they cannot tell us whether the model reliably distinguishes real track entry points from nav chrome on a specific real site. That needs one live run to confirm.

## 36. Cleanup pass: every bug from `#34` fixed, plus a test suite that was silently testing nothing

Follow-up sweep over the whole system (test run + dead-code/duplication/complexity hunt). All eight items from `#34` are resolved; two further problems were found during the sweep itself.

### Found during this sweep (not in `#34`)

**`QueueSummary.test.tsx` was asserting against a component that never rendered.** `vi.mock('../../../store/queueStore', ...)` — but the test file sits one directory deeper (`__tests__/`) than the component, so three levels resolved to `features/queue/store/queueStore`, a path that does not exist. The factory was registered against a module nothing imports, the real store was used, `queueState` was `null`, the component early-returned `null`, and all three tests failed against an empty `<body><div /></body>`. The sibling `TimelineCard.test.tsx` uses four levels for `../../../../types` — the inconsistency was right there. Fixed to `../../../../store/queueStore`; **8/8 frontend tests now pass** where it was 5/8.

Worth noting what this masked: these three failures had been dismissed as "pre-existing" in `#34`'s baseline, which is exactly how a broken test stops being a signal. The component had *zero* real coverage the whole time.

**`QueueControls` would have silently lost its "Waiting for you..." affordance.** Caught while verifying the `#34.5` fix in a live browser, not by any test. Making the aggregate status correctly report a 2FA-blocked job as `running` meant `QueueControls` took its `status === 'running'` branch and rendered **Pause Queue** instead of the deliberately-disabled "Waiting for you..." button that `#30`/`#31` exist to provide. Fixed by checking `needsInput` *before* the status branch, so the aggregate can stay truthful without regressing the affordance. The now-unreachable `needsInput` ternaries inside the Resume button were removed.

### `#34` fixes

- **34.1 Profile form empty on first visit** — `reset()` once, in an effect keyed on the resolved query data and guarded by a ref, rather than restoring the always-on store sync (which is what caused the cursor-jumping the old effect was deleted for). Verified live on a fully-cleared browser: all fields populate; then typing into City and waiting out the autosave debounce leaves the value **and the caret position (12) and focus** intact, and the server received `Cambridge UK` with name/email/phone/company **not** clobbered by `formToBackend`'s `New User` / `user_<ts>@example.com` / `0000000000` fallbacks.
- **34.2 Fresh clone can't boot** — `mkdir(parents=True, exist_ok=True)` before the `StaticFiles` mount in `main.py`, since that mount runs at import time and `lifespan()` is too late.
- **34.3 ~9s spinner for new users** — `retry` is now a predicate that refuses to retry a 404. This required preserving the status code: the axios interceptor flattened errors to a bare `Error`, discarding it, so `ApiError`/`isNotFound` were added in `api/axios.ts`. Verified live: **exactly one** `GET /api/resume/1 → 404` where there were three, dropzone renders immediately.
- **34.4 Resume card blank File Name / Size** — `lib/resumeFile.ts::resumeFileName()` derives the name from the stored URL's last segment. `ConfirmQueueDialog` was already doing this inline, so this also removes a duplicated derivation; `ResumeToolbar` and `ResumeUploader` now share it too. The **Size** row was deleted outright — `ResumeGetOut` has no size field, so it could only ever render "Unknown size". `Resume.file_name` is now optional, because the API genuinely does not send it.
- **34.5 Queue header contradicted the panel beside it** — `waiting_for_user` now counts as active in the aggregate status *and* in `QueueSummary`'s subtitle; `cancelled` now counts toward "done" so progress can reach 100%. Verified live: header reads "Running / 1 job(s) running" next to "Currently Processing — User Input Required", with the correct disabled button.
- **34.6 Dead settings controls** — the polling selector is now real: `store/settingsStore.ts` (persisted, same pattern as `themeStore`) feeds `refetchInterval` in `useQueueStatusQuery`, and the option list no longer claims a "2 Seconds (Default)" that disagreed with the hardcoded 4000ms. The **Desktop Notifications** toggle was **deleted** — nothing anywhere calls the Notification API, and making it work is a feature, not a cleanup. Persistence verified live (`{"queuePollingIntervalMs":8000}`); the refetch cadence itself could not be measured, because the automated browser pane reports `visibilityState: 'hidden'` and react-query correctly suspends interval refetching when the document is hidden.
- **34.7 Wrong breadcrumb, unreachable route** — unmatched paths no longer claim to be "Dashboard"; `/settings` added to the sidebar, and `ROUTES.QUEUE` now used instead of a hardcoded `'/queue'`.
- **34.8 `created_at` ties** — `Job.id` added as a tiebreaker to both order-by branches in `JobRepository.search`. Two regression tests seed six jobs sharing one timestamp and assert that paging sees each row exactly once, and that `sort=oldest` is the exact reverse of the default.

### Result

**338 backend tests** (+2) and **8/8 frontend tests** (from 5/8) passing; ruff, `tsc -b`, oxlint and `vite build` all clean. No new dead exports were introduced — `ApiError` and `DEFAULT_QUEUE_POLLING_INTERVAL_MS` were un-exported once the scan flagged them as unused outside their own module.

## 37. Real root cause of category 3 (`#35`) never actually working: plain `str` URL fields never got Stagehand's own real-href resolution — **superseded, see `#38`**

**This entry's fix (the `format: "uri"` schema hint) was itself live-tested against the same URL and found wrong — it crashed the extract() call outright.** Left below verbatim, same convention `#26`→`#27`→`#28`→`#29` already established in this file: each wrong attempt is real information, not noise to quietly delete. `#38` is the corrected account, ending in a fix actually confirmed against the live site.

Live-caught by the user against `https://careers.cargill.com/en` — exactly the multi-track shape `#35` was built for. The log showed **one** assessment `extract()` call, then `stagehand.close()` — no section navigation, no jobs, `0 jobs_inserted`. `#35`'s own unit tests all passed and gave no warning, because they fake `sh.extract()` directly with a Python object, bypassing the exact mechanism that was actually broken.

### Root cause, confirmed by reading Stagehand's own bundled extension JS, not guessed

First ruled out the obvious guess (JS-only buttons with no href): fetched `careers.cargill.com/en`'s raw HTML directly (no browser, no LLM — plain `httpx.get`) and confirmed its three tracks are ordinary `<a class="button-like" href="/professional-jobs">Search Jobs</a>` links — trivially present, real hrefs, nothing exotic.

The actual cause lives in `stagehand/_extension/service-worker.js`. `extract()` does **not** hand the model raw HTML — it hands it an accessibility TREE (role + visible label per node, e.g. `link: Search Jobs (Professional Jobs)`), which never includes the href at all. Separately, `extract()` builds its own `combinedUrlMap` (real node-id → real href) while snapshotting. Before generation, `transformSchema` rewrites any schema field whose JSON Schema carries `"format": "uri"` (a Zod `.url()` check) into a plain node-id string, so the model only has to copy an id it can actually **see** printed in the tree — then `injectUrls` swaps that id back for the real href from `combinedUrlMap` after the model responds. A field with no such format hint gets none of this: the model is asked to produce a URL as free text from a tree that never shows one, and correctly declines rather than hallucinating — which is why `sections` came back empty instead of wrong.

`ListingSection.url` (added in `#35`) was plain `str`. So was the pre-existing `ScrapedJob.apply_url`, meaning this likely undermined every category's URL reliability, not just category 3's sections — `#32`'s "130/130 jobs" live success on `jobs.ashbyhq.com/notion` was apparently a case where enough real URL text happened to be visible in that site's own tree, not evidence the mechanism was sound in general.

### Fix: give both URL fields the same hint pydantic's `HttpUrl`/`AnyUrl` emit automatically

`pydantic.HttpUrl`/`AnyUrl` emit `{"format": "uri"}` in their JSON Schema, which is what actually triggers Stagehand's resolution — confirmed directly (`model_json_schema()` on all three: `HttpUrl`, `AnyUrl`, and plain `str`, only the first two carry `format`). But adopting `HttpUrl`/`AnyUrl` themselves was rejected: Stagehand's own `injectUrls` legitimately substitutes `""` when a node id doesn't resolve (a link that disappeared between snapshot and generation), and a strict URL type would raise inside the **SDK's own** re-validation of the model's response (`schema.model_validate(result.data)`, in `stagehand.py`) — crashing the whole `extract()` call over one unresolved field rather than just leaving it empty.

Used `Annotated[str, Field(json_schema_extra={"format": "uri"})]` instead — gets the same `format: "uri"` hint (verified via `model_json_schema()`) while staying a lenient `str` on the Python side (verified `ScrapedJob(apply_url="")` and `ListingSection(url="")` both construct without error). Applied to both `ScrapedJob.apply_url` and `ListingSection.url`.

### Also built: a click-based fallback for the case that turned out NOT to be Cargill's problem, but is real elsewhere

Per direction to make the agent able to "search for buttons and crawl for each one of them": `_usable_sections` previously **dropped** any section with no resolvable URL outright. It now keeps a section that has a real label but no URL (deduped on normalized label text, still counted toward `SCRAPER_MAX_SECTIONS`), and `_navigate_to_section` dispatches per-section: `goto()` when a URL resolved (free, unchanged), or one `observe()` + `act()` pair to find and click the button by its label when it didn't (2 LLM calls, only paid when actually needed). A portal can mix both kinds of section in the same run. A section that fails either way is skipped, not fatal — same "one dead entry point, keep going" contract the URL path already had.

### Testing

10 new tests, **348 total passing**, ruff clean. Two are schema-shape regressions that would have caught this exact bug before it ever reached a live run (`apply_url`/`ListingSection.url` must carry `format: "uri"`), one confirms the lenient-empty-string tolerance that rules out `HttpUrl`/`AnyUrl`, and the rest cover the click-fallback: kept-not-dropped, dedup, the limit, a pure-click category-3 run, a run mixing URL and click sections, and a failed click not aborting the others.

**Not yet live-reconfirmed against Cargill itself** — the schema fix is the direct, mechanically-verified cause of what the log showed, and the click fallback is unit-tested control flow, but neither has been run against the real page since this fix. That's the next live call to spend, when you're ready to spend it.

## 38. `#37`'s fix live-tested and found wrong; the real, fully live-confirmed fix — four sequential real bugs, all found by actually running against `careers.cargill.com/en`

Per direct instruction: "test the same url on urself and resolve it accordingly." Ran the real `_sync_via_extract()` against the real Cargill URL, with a real OpenRouter key, eleven times over — each failure diagnosed from a real traceback or real inserted rows, never guessed. What follows is the honest sequence, not a cleaned-up version of it.

### Attempt 1 (`#37`'s fix) — crashed outright

`ListingSection.url`/`ScrapedJob.apply_url` given a `"format": "uri"` hint so Stagehand's node-id substitution would resolve real hrefs. First live call:

```
stagehand.rpc_client.RPCError: [
  {"code": "invalid_format", "format": "url",
   "path": ["structuredContent", "sections", 0, "url"], ...},
  ... (one per section)
]
```

Traced into the extension's own re-validation path: Stagehand's substitution genuinely finds and injects the REAL href — but Cargill's hrefs are RELATIVE (`/professional-jobs`, confirmed via a raw `httpx.get` of the page — ordinary `<a href>` tags, nothing exotic), and the field's `.url()` check requires an ABSOLUTE url. The real, correctly-resolved value fails Stagehand's own strictness. A genuine upstream incompatibility with relative hrefs — common in real sites — not fixable from a JSON Schema hint on our side. **Reverted**: both fields are back to plain `str`, no format hint, full stop. Category 3's click-fallback (`_navigate_to_section`, already built in `#35`) is now the PRIMARY way a section is reached, not a backstop.

### Attempt 2 — silent false success: 9 "jobs" that were 3 duplicates of landing-page noise

With the crash gone, `_sync_via_extract` returned `inserted=9` — looked like progress. Direct DB inspection showed otherwise: the same 3 unrelated "spotlight" postings (Taiwan/Colombia/Colorado — clearly a rotating widget, not the real job boards), written **three times** with three different garbage `apply_url` values (`[0-2987]`, `0-4830`, `0-6673`). The model, lacking any real href to copy, had echoed the tree's own internal `[id]` bracket notation as if it were a URL — and `urljoin()` happily resolved that garbage into something with a valid scheme+netloc, so the OLD dispatch logic (`if assessment.jobs: harvest here and STOP — never touch sections`) took the category-1 branch and never visited a single one of the three real tracks. This was the exact risk `#35` had explicitly flagged and accepted as a known cost ("a portal that both lists jobs directly AND hides more behind parallel tracks will miss those tracks") — now confirmed real on the first genuine multi-track portal tested, not hypothetical.

**Fixed**: `assessment.jobs` and `assessment.sections` are no longer mutually exclusive — both are harvested unconditionally. Sections are visited FIRST (so a click-fallback section sees the exact page state the assessment did), then the landing page is explicitly reloaded via `goto()` before harvesting its own jobs+pagination last.

### Attempt 3 — the University track failed because the browser was on the wrong page

Re-tested: Professional Jobs' click-fallback correctly found and clicked its real button, landing on a genuine search-results URL (`.../search-jobs?...job_type=Professional`) and harvesting **33 real, distinct postings**. Production Jobs also clicked through correctly. University Jobs then failed — `observe()` found nothing to click. Root cause: after Production's navigation succeeded, the browser was left on Production's OWN page, and University's button only ever existed on the ORIGINAL landing page. Sections were being visited in a plain loop with no reset between them.

**Fixed**: every section now starts from an unconditional `page.goto(company_url)` reset, not just the last one before the final on-page-jobs harvest. A free, deterministic navigation was judged cheaper than any cleverness about which section "probably" still has a fresh page.

Also newly caught in this same pass: `_assess_page`'s single `extract()` call raised `RPCError: invalid_type` (array items that weren't objects) on a later attempt — plain LLM structured-output flakiness on this one call, unrelated to anything above. Given a single flaky response can happen to any extract() call, and Tier 1 already has a proven "one retry, no repair prompt needed" pattern for exactly this (`tier1_map.py`'s `_chat_with_repair`), `_assess_page` now gets the same: one retry at the identical instruction before letting a second failure propagate.

### Attempt 4 — all three real tracks reached; then a fourth, deeper bug: 0 of 73 jobs had a real link

With sections 1-3 all confirmed reaching genuine, distinct search-results URLs and real job titles flowing in (Professional: 18, University: 18, plus several generic nav items — "Career Areas," "Jobs by Category" — the model also flagged as "sections," a known, already-accepted, bounded cost from `#35`'s own design, not a new bug), the run finished with `inserted=40`. Direct inspection of what actually landed: **every single one of the 73 rows written across this test session had a garbage `apply_url`** — not the bracket-notation shape from Attempt 2, but a bare requisition-number-looking string (`"13147"`, `"13151"`, ...), presumably a Job ID visible as plain text near each posting. Same root cause as Attempt 2 (no real href visible in the tree, so the model invents SOME plausible-looking token), on a different field, in a shape the earlier fix's narrow `\d+-\d+` pattern never matched.

**Fixed**: a separate, stricter validator for `apply_url` specifically — `_looks_like_real_apply_url` requires a genuine absolute `http(s)://` URL, full stop. This is not an approximation for this field the way the sections check is: an `apply_url` is stored and used STANDALONE (`<a href={job.apply_url}>`), with no "current page" to resolve a relative path against, so there is no legitimate non-absolute form for it to take. Anything that fails is treated exactly like a missing apply_url already was — dropped, not written. All 73 garbage rows from this test session were deleted from `app.db`.

### What's confirmed live vs. what's still open

**Confirmed, live, against the real site**: the crawl now correctly discovers and navigates to every real track on a genuine multi-track portal (all three of Professional/Production/University reached via observe()+act(), each landing on a distinct, real, correct search-results URL), harvests real distinct job titles/locations from them, and no longer writes fabricated links into the database.

**Still open, found by this same pass, not yet solved**: Cargill's individual job POSTINGS apparently never expose a real, extractable href via Stagehand's plain-text `extract()` either — confirmed directly, 0 of 73 harvested postings had a usable apply_url. The new validation correctly refuses to write those as fake links (the right behavior — no silent corruption), but the practical result is that a sync against Cargill today still inserts **zero** usable jobs, even though the crawl mechanism itself is now proven correct. Recovering a real apply_url per posting would need a fundamentally different mechanism than what exists now — e.g. a deterministic `page.evaluate()` DOM read keyed by matching titles, bypassing the LLM's text-based extraction for this one field entirely — since an `observe()+act()` click-fallback per JOB (as opposed to per SECTION, where there are only a handful) is not viable at the scale of a page with dozens to hundreds of postings. Not attempted this pass; flagged as the next real gap, not silently assumed solved.

### Testing

15 more tests on top of `#37`'s 10 (**374 total passing**), ruff clean, including: the reverted schema now asserted absent (guards against the crash silently reappearing), the mutually-exclusive dispatch bug's fix (jobs-and-sections harvested together, exact `goto()` sequences pinned), the per-section reset (also pinned by exact `goto()` sequence), the assessment retry (one retry then give up, not a loop), and the broader `apply_url` validator (bare numbers, node-ids, and relative paths all rejected; genuine absolute URLs kept) — the last of these parametrized directly against the real garbage values seen live (`"13147"`, `"[0-583]"`, `"0-4830"`).

Also worth carrying forward, independent of this specific site: this whole sequence is a second, independent confirmation of the pattern `#29` already named — a confident, source-grounded fix, live-tested, found wrong, twice over in this pass alone (Attempts 1 and 2 each seemed complete when written). Neither unit tests written before a live run, nor careful reading of the SDK's source, substituted for actually running it.

## 39. Live test run for enqueue+apply — 97 pre-existing garbage-URL jobs found live-blocking real applications, a defensive check added, and one real application successfully filed end to end

Per direct instruction to test the real enqueue-and-apply flow, with `SUBMIT_ENABLED=True` in the live `.env` and explicit authorization for a genuine submission if the test reached that point.

### Real bug: 97 jobs already in the database had an unusable `apply_url`, crashing real runs

First attempt (a real `salesforce.com` job) failed immediately: `RPCError: -32000 Cannot navigate to invalid URL`. The job's stored `apply_url` was `"8-12876"` — exactly the node-id-echo garbage shape root-caused and fixed for the SCRAPER in `#38` — but these specific 97 rows (77 `jobs.ashbyhq.com`, 20 `salesforce.com`) had been written to `app.db` by scrapes that ran *before* that fix existed. `#38`'s fix stops the garbage from being written to NEW rows; it does nothing for rows already sitting in the database, and nothing in `runner.py` had ever validated `job.apply_url` before handing it straight to `page.goto()`.

Notable in passing: the 77 `jobs.ashbyhq.com` rows are very likely the SAME 77 `#32` reported as a live success ("130 jobs... 77 inserted") — confirming the suspicion raised in `#38` that that success was never actually verified to have real, usable links.

**Fixed two ways:**
1. `runner.py` now checks `job.apply_url.startswith(("http://", "https://"))` immediately after the profile/job lookup — before any Chrome session is launched — and fails the application with a clear, actionable message (names the bad value, suggests re-syncing) instead of a raw CDP protocol error after a wasted browser launch. Unit-tested (`test_run_fails_fast_on_a_job_with_no_real_apply_url`): confirms no browser is launched at all for a job with the exact live-caught garbage shape.
2. The 97 known-bad rows (and the two applications that had already failed against them) were deleted from `app.db` after a backup — 751 real jobs remained, all with genuine URLs.

### Real, unresolved ambiguity: a submit-time crash whose outcome couldn't be determined from logs alone

A full run against a live Anthropic posting (`job-boards.greenhouse.io/anthropic/...`) filled every field correctly through Tier 0/1/2 — including "Why Anthropic?" and "Agreement to Arbitrate," both historically the most failure-prone fields in this entire project's history (`#13`, `#19`, `#21`) — solved CAPTCHA twice, and then crashed at exactly the submit step: `RPCError: -32001 Session with given id not found`.

That specific error text is a **standard Chrome DevTools Protocol** message, not one either the Stagehand SDK or its bundled extension emits — grepped both, no hits. It's classically raised when a CDP session's target has been invalidated by a full navigation, which is exactly what a genuinely successful submit → confirmation-page redirect would trigger. Weight of evidence: the click most likely fired, and the crash happened on the post-click confirmation read-back — meaning **the run recorded `failed`, but a real application may well have actually gone through.**

This could not be resolved from the available logs (no snapshot or intermediate event was written between the CAPTCHA-solved line and the crash), and root-causing it further would need either reproducing it live again — itself risking a genuine duplicate application if the first one *did* submit — or deeper instrumentation of the exact CDP call that failed. Per direct instruction, **left alone rather than guessed at**: the application was not retried, and the user was told to verify independently (email / Greenhouse applicant portal) rather than have this assumed either way.

**Not yet fixed, flagged for later**: `_submit_and_verify` has no defense against this specific CDP-session-invalidation class of error — a `-32001`-style failure right after a click should arguably be treated as "outcome unknown, do NOT let this look like a clean retry candidate" rather than a plain `failed` indistinguishable from every other failure reason. Worth a distinct status or at minimum a message calling out the ambiguity explicitly, so the UI doesn't imply "safe to retry" when it might not be.

### Real, separate bug: a stale/expired job listing produces a misleading error instead of naming the actual problem

Redirected to Figma next (skipping Anthropic per direct instruction to avoid the ambiguity above). The first Figma job tried (`boards.greenhouse.io/figma/jobs/5364702004?gh_jid=...` — note the legacy, non-`job-boards` domain) failed in 10 seconds: `submit button not found`, having filled exactly one field (`EMAIL`). Direct `httpx.get` of that URL (no browser, no LLM) showed why: it 302-redirects to `https://www.figma.com/careers/` — Figma's generic marketing careers page, not a job posting at all. The listing had simply expired since it was scraped; the "EMAIL" field was very likely a newsletter signup on the landing page, not an application form field.

**Confirmed this is not a rare edge case**: all 157 `figma` rows in `app.db` share this same legacy `boards.greenhouse.io` URL pattern (vs. `anthropic`/`pistontechnologies`'s current `job-boards.greenhouse.io`), meaning most or all of them are equally likely stale.

**Also confirmed while investigating**: `db_models.py`'s own `Application` docstring lists a status vocabulary including `checking_url`, `rescraped_retry_queued`, `link_expired_rescraping`, `link_expired_rescraped_still_unavailable` — exactly the concept needed here (detect an expired link, automatically re-scrape, retry) — but grepping the entire `app/` tree turns up **zero references to any of these outside that one docstring**. This was planned vocabulary from an earlier design pass that was never actually built; `domain/status.py`'s real, live vocabulary has no such states. A dead listing today just fails with whatever confusing symptom its redirect target happens to produce (`submit button not found` here; something else on a different dead-link shape) rather than a clear "this job posting no longer exists."

**Not fixed this pass** — building real link-expiry detection and an automatic re-scrape/retry flow is a genuine feature, not a quick-test-session fix; flagged here so it isn't lost, and because the status vocabulary already half-exists in a docstring is exactly the kind of thing worth knowing before someone assumes it's already built.

### What actually succeeded

Third attempt, `pistontechnologies` (real `job-boards.greenhouse.io` posting, freshness confirmed via a plain `httpx.get` before enqueueing — no redirect, real form fields present): a complete, unambiguous, real success. Full log: 6 Tier 0 fields, 6 Tier 1 fields (2 from cache), 2 Tier 2 fields (one via a targeted repair pass after the first attempt left "Cover Letter" unhandled), CAPTCHA solved twice (pre-fill and pre-submit), a real submit click, and `"Submission confirmed: Thank you for applying"` read directly off the resulting page. **A real job application was filed.**

### Result

**375 backend tests** (+1), ruff clean. `app.db` backed up before the 97-row cleanup (`app.db.bak.<timestamp>`); 751 real jobs remain.
