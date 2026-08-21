# Universal Job Application Auto-Filler — Build Plan (v2, backend-only against approved frontend)

> Status: approved, implementation starting. 5-day build window.

## Context

Revision of the original plan. The client has approved a frontend, at `github.com/soumita94/Career-Ops-V3` (cloned into the repo). It ships with a `backend/` folder that we are **not** using — we build a new backend from scratch that satisfies the frontend's existing API contract exactly, and add the automation engine behind it.

**Why this changes the plan, not just the stack:** the approved frontend was built against a simple polling REST API and has no live-view or takeover UI. But the core requirement — pause on login/2FA/CAPTCHA, let a human intervene, resume the same session — needs somewhere for that human interaction to happen. This plan keeps the approved frontend as the base and adds the minimum surface required for that to work, confirmed with you: additive-only frontend changes, no auth for now, and a WebSocket layered on top of (not replacing) the existing polling.

The universality problem and its solution (cascading resolver: a11y tree → batched LLM → Stagehand `observe`/`act` → human, always returning element references not coordinates) is unchanged from the original plan — see "Automation engine" below, carried over.

### Hard constraints (unchanged)
- Open-source, self-hosted. No Skyvern, Browser Use, Anchor Browser, Browserbase cloud.
- Only two paid externals: OpenRouter (LLM) and 2captcha.
- Universal across 400+ providers, no per-provider API integrations for form-filling.
- 5 days, complete project.

### New scope this revision adds
- **Match the existing frontend's REST contract exactly** (endpoints, field names, types, status vocabulary) — it is not ours to redesign.
- **Job discovery/scraping**, triggered by the frontend's existing `AdminPage` → `POST /api/admin/sync`. This wasn't in v1 of the plan; the frontend already assumes it exists.
- **Additive frontend changes**: a live-view component, real pause/resume/cancel wiring, a log stream — into UI shells (`QueueControls.tsx`, `CurrentJobCard.tsx`, `LogViewer.tsx`) that already exist but are currently no-ops.
- **No auth.** Continue the frontend's current MVP model: `profile_id` (from `localStorage`) is the de facto session key, sent by the client, trusted by the server. Revisit later if asked.

---

## Repo restructure (Day 1, first task)

```
resume-automate/
├── Career-Ops-V3/            # delete after extracting what's needed
│   ├── frontend/    → move to resume-automate/frontend/
│   ├── backend/     → reference only, then discard (do not copy code)
│   └── portals.yml  → move to resume-automate/backend/config/portals.yml
```

`portals.yml` is a gift: it already documents the exact 3-tier discovery strategy this plan needs for job scraping (Playwright → company careers page, Greenhouse API where available, WebSearch `site:` fallback) plus a seed list of tracked companies with `careers_url`. Reuse it directly as the scraper's config and seed data.

---

## The API contract to satisfy exactly

Base: frontend calls `${VITE_API_BASE_URL}/api/...` (default `http://localhost:8000`), via a single Axios instance (`frontend/src/api/axios.ts`) that unwraps `response.data` and expects FastAPI-style `{detail}`/`{message}` errors. No changes needed there — just point `VITE_API_BASE_URL` at the new backend.

### Existing endpoints (must match byte-for-byte)

| Frontend call | Endpoint | Notes |
|---|---|---|
| `jobs.ts` | `GET /api/jobs/search?keyword&company_name&location&location_type&ats&industry&posted_within_hours&page&limit&sort` | → `{ jobs: Job[], total, page, limit }`. `Job.id` must serialize as **string** even though it's an int PK. |
| `profile.ts` | `POST/GET/PUT/DELETE /api/profile[/{id}]` | Flat `BackendProfile` — see exact field list below. **Include `gender`, `current_company`, `twitter_url`** — the old backend's Pydantic schema was missing these; the frontend sends them and we must accept/return them since the frontend is the authoritative contract now. |
| `resume.ts` | `POST /api/resume/upload` (multipart: `profile_id`, `file`) → `{success, resume_url}`; `GET /api/resume/{profile_id}`; `DELETE /api/resume/{profile_id}` | |
| `apply.ts` / `queue.ts` | `POST /api/apply/start {profile_id, job_id}` → `{application_id, status}`; `GET /api/apply/status/{id}`; `GET /api/apply/history/{profile_id}`; `GET /api/apply/details/{id}` | Polled every 4s by `useApplyStatusQuery` / `useQueueStatusQuery`. `queue.ts` derives the whole queue UI state client-side from `history` — there is no separate `/api/queue/*` endpoint, don't build one. |
| `AdminPage.tsx` | `POST /api/admin/sync {company_url}` → `{success, jobs_inserted, jobs_updated, failed}` | Drives the job-scraper (new scope, see below). |

`BackendProfile` fields (`frontend/src/api/profile.ts:3-38`): `id, full_name, email, phone, date_of_birth?, gender?, current_title?, current_company?, years_of_experience?, linkedin_url?, github_url?, portfolio_url?, twitter_url?, country?, state?, city?, address?, postal_code?, citizenship?, visa_status?, sponsorship_required?, highest_degree?, university?, graduation_year?, preferred_job_title?, preferred_location?, expected_salary?, current_salary?, notice_period?, willing_to_relocate?, skills?, summary?, created_at?, updated_at?`.

Status vocabulary the frontend already maps (`frontend/src/api/queue.ts:15-36`) — **emit exactly these strings**, anything else silently falls into "waiting": `queued`, `pending`, `checking_url`, `rescraped_retry_queued` → waiting; `link_expired_rescraping`, `running` → running; `completed`, `success` → completed; `failed`, `error`, `link_expired_rescraped_still_unavailable` → failed; `cancelled` → cancelled.

### New additions (backend + small additive frontend edits)

1. **New status: `needs_input`.** Add to backend status vocabulary and to `frontend/src/api/queue.ts` `mapBackendStatusToJobStatus` (currently anything unrecognized falls into `waiting`, which would hide the very moment a human needs to act — this one line must not be skipped). Surface it distinctly in `QueueStatusBadge.tsx` and `CurrentJobCard.tsx` with a "Take control" affordance.

2. **Real pause/resume/cancel endpoints**, wired into the already-present but no-op buttons in `frontend/src/features/queue/components/QueueControls.tsx` (currently just toasts "not yet supported"):
   - `POST /api/apply/{application_id}/pause`
   - `POST /api/apply/{application_id}/resume`
   - `POST /api/apply/{application_id}/cancel`

3. **Live-view WebSocket**: `WS /ws/apply/{application_id}/live-view` — JPEG screencast frames out, click/type events in. New small React component (canvas + input capture), shown in a drawer/modal opened from `CurrentJobCard.tsx` when status is `needs_input`.

4. **Log stream**: `WS /ws/apply/{application_id}/logs` — replaces the hardcoded `logs: []` in `queue.ts:112`. Wire into the already-built `LogViewer.tsx`, which just needs a real data source.

No other frontend screens change. Search, Profile, Resume upload, Dashboard, Admin stay as delivered.

---

## Automation engine (carried over from v1, unchanged in principle)

The universality problem is unaffected by the frontend swap. Same cascading resolver, same reasoning: coordinates can't be verified or cached, element references can.

- **Tier 0** — CDP accessibility tree + semantic dictionary, $0, ~70-80% of fields.
- **Tier 1** — batched OpenRouter call (one per page, not per field) for leftover fields, text/a11y not vision.
- **Tier 2** — Stagehand `observe()` → `act()` for custom widgets (the exact fix for the old coordinate-clicking bug).
- **Tier 3** — human, via the new live-view WebSocket: login, 2FA, failed CAPTCHA, low-confidence field, final review before submit.

**Provider fingerprint cache** and **answers library**, unchanged — this is what makes 400+ providers affordable: first contact with a form/question pays LLM cost, every repeat is ~free.

**Chrome session model**, unchanged: launch Chrome yourself (headed, persistent `--user-data-dir`), Stagehand attaches via `cdp_url` (never launches its own), live-view proxy attaches as a second independent CDP client on the same Chrome. Pause = stop issuing commands; the browser and cookies never go away.

**Day-1 spike: PASSED. Python confirmed, no Node sidecar built.** The installed package turned out to be Stagehand v4 (`await Stagehand.create(browser=..., model=...)`, a redesign from the v2/v3 API referenced in the original research). Four facts confirmed empirically against a real Greenhouse form: (1) `local_browser.launch(port=..., user_data_dir=..., keep_alive=True)` needs zero Browserbase key and never calls `api.stagehand.browserbase.com`; (2) `Stagehand.create(model=<callback>)` accepts a fully custom async LLM callback — no base-URL constraints, OpenRouter is just an HTTP call inside it; (3) a second, independent CDP client attaches to the same Chrome concurrently with Stagehand's own session; (4) Chrome survives `Stagehand.close()` when launched with `keep_alive=True` — the literal mechanism pause/resume depends on.

**The one real finding:** Stagehand v4's local mode bootstraps a companion browser extension via CDP `Extensions.loadUnpacked`, which **consumer Chrome Stable does not support** (confirmed at the raw protocol level, independent of Stagehand). A **Chrome for Testing** build does. Fix: `python -m playwright install chromium` (downloads a CfT build), point the Chrome launcher's `chrome_executable_path` at that binary instead of `Program Files\Google\Chrome`. One-line config, not an architectural risk.

## Job discovery/scraper (new scope, same cascading philosophy)

Triggered by `POST /api/admin/sync {company_url}`. Reuse `portals.yml`'s already-specified 3 levels:

1. **Known ATS APIs first** (free, structured, fast): Greenhouse (`boards-api.greenhouse.io/v1/boards/{token}/jobs`), Lever (`api.lever.co/v0/postings/{token}`), Ashby public API — detect from `company_url`/`careers_url` pattern.
2. **Stagehand `extract()`** against the company's branded careers page for anything not on a known ATS — same tier-2 machinery as form-filling, reused for structured extraction instead of form actions.
3. **WebSearch `site:` fallback** for broad discovery when the careers page can't be resolved directly (per `portals.yml`'s documented strategy).

Insert/update into `jobs` table, return `{success, jobs_inserted, jobs_updated, failed}` matching `AdminPage.tsx` exactly. Seed `tracked_companies` from `portals.yml` for the demo.

---

## Tech stack

| Layer | Choice | Why |
|---|---|---|
| Frontend | **Reuse as-is**: React 19 + Vite + TS, Zustand, TanStack Query, Axios, Tailwind v4, RHF+Zod | Client-approved, don't rebuild |
| Backend | FastAPI + Pydantic v2 + Uvicorn | Matches frontend's error-shape assumptions |
| DB | PostgreSQL (SQLite acceptable if time-pressed) + SQLAlchemy 2.0 + Alembic | |
| Realtime | Native `websockets`/FastAPI `WebSocket`, additive only | Confirmed: layer on top of polling, don't replace it |
| Queue | asyncio worker + DB row locking | Browser automation is serial and stateful; Celery/Redis unnecessary here |
| Browser | Chrome, headed, launched by our code | Full flag control, session persistence, sidesteps Stagehand CDP-ownership bug |
| Automation | Stagehand v4 (Python), attached via `local_browser.launch()` against a **Chrome for Testing** build | `observe()` returns elements not coordinates; CfT needed for `Extensions.loadUnpacked` |
| LLM | OpenRouter | Per constraints |
| CAPTCHA | 2captcha | Per constraints |
| Job scraping | Known-ATS JSON APIs → Stagehand `extract()` → WebSearch fallback | Reuses `portals.yml`'s documented strategy |

---

## Data model

- `profiles` — matches `BackendProfile` exactly, all fields above including the ones the old backend's schema was missing (`gender`, `current_company`, `twitter_url`)
- `resumes` — profile_id FK, file, extracted text, `resume_url`
- `jobs` — id (int PK, string on the wire), title, company_name, location, location_type, industry, posted_date, job_type, salary, description, requirements[], apply_url, company_url, ats
- `applications` — profile_id, job_id, application_id (string, external-facing), status (incl. `needs_input`), pause_reason, started_at, finished_at, error
- `run_events` — append-only audit log per application, also the source for the log-stream WS
- `field_cache` — (provider, form_signature) → resolved selector map
- `answers_library` — question_hash → user-approved answer
- `tracked_companies` — seeded from `portals.yml`, careers_url, last_synced_at

---

## Repo layout (final)

```
resume-automate/
├── frontend/                 # moved from Career-Ops-V3/frontend, minimal additive edits only
│   └── src/features/queue/components/  # LiveView.tsx (new), QueueControls.tsx (wire real calls),
│                                        # LogViewer.tsx (wire WS), CurrentJobCard.tsx (needs_input UI)
├── backend/
│   ├── config/portals.yml    # moved from Career-Ops-V3 root
│   └── app/
│       ├── api/               # jobs, profile, resume, apply, admin, ws/
│       ├── core/               # config, db
│       ├── models/             # SQLAlchemy + Pydantic, matching BackendProfile/Job exactly
│       ├── services/
│       │   ├── resume/         # parse + structure
│       │   ├── browser/        # Chrome launcher, CDP pool, live-view proxy
│       │   ├── engine/         # tier0/1/2/3 cascade
│       │   ├── scraper/        # known-ATS APIs, Stagehand extract, WebSearch fallback
│       │   ├── captcha/
│       │   └── providers/      # fingerprinting + selector cache
│       └── worker/             # queue runner
```
(No `automation-node/` — the Day-1 spike passed on Python; the TS sidecar was never needed.)

---

## Day-by-day

### Day 1 — Restructure + foundation + the risky bit

- [x] Repo restructure: move `frontend/`, move `portals.yml`, discard `Career-Ops-V3/backend`.
- [x] Stagehand spike (Python + OpenRouter-ready callback). **Passed** — Python confirmed, requires a Chrome for Testing build (see "The one decision to settle first" above).
- [x] FastAPI scaffold, DB (SQLite for now, see note below), CORS for the frontend origin. All 5 existing endpoint groups implemented and smoke-tested against real HTTP requests (profile, jobs/search, apply/start+status+history, admin/sync).
- [x] Chrome launcher (headed, Chrome-for-Testing build, per-profile `--user-data-dir`, `keep_alive=True`) — `app/services/browser/chrome_launcher.py`.
- [x] Live-view WebSocket end-to-end (backend: `app/services/browser/live_view.py` + `app/api/ws.py`) — screencast frame delivery and input forwarding confirmed against a real launched Chrome. **Frontend `LiveView.tsx` canvas component not yet built** (backend proven, frontend wiring is Day 4 per the additive-frontend-changes scope).

Bonus, ahead of schedule: the admin/sync job scraper (`app/services/scraper/sync_service.py`, originally Day 3) is implemented for Greenhouse + Lever and was smoke-tested live — pulled 441 real jobs from Anthropic's Greenhouse board through the exact `/api/jobs/search` contract shape.

Note: using SQLite (`sqlite+aiosqlite`) via SQLAlchemy 2.0 `create_all()`, no Alembic yet — acceptable per the plan's own "SQLite acceptable if time-pressed" allowance, given how much of Day 1's budget went into the Stagehand/Chrome-for-Testing investigation. Alembic can be layered in later without schema changes if needed.

### Day 2 — Data endpoints matching the contract

- [x] `profile`, `resume` endpoints, exact `BackendProfile` shape (resume upload implemented, not yet smoke-tested with a real file).
- [x] `jobs/search` endpoint + `jobs` table (done Day 1, tested with 441 real Greenhouse jobs).
- [x] `apply/start`, `apply/status`, `apply/history`, `apply/details` — status vocabulary exact. `needs_input` added to the **backend** vocabulary; **`frontend/src/api/queue.ts` `mapBackendStatusToJobStatus` still needs the matching one-line addition** so it doesn't fall into the `waiting` default.
- [x] Tier 0 harvester (a11y tree → semantic dictionary → fill) — **real, verified**. `app/services/engine/tier0_harvest.py` + `semantic_dictionary.py` + `runner.py`. Uses Stagehand's `page.snapshot()` (its own accessibility-tree representation — no need to hand-roll raw CDP `Accessibility.getFullAXTree`), regex-matches `textbox` roles against a label dictionary, fills via `page.locator(xpath).fill()`. Tested live against a real Anthropic Greenhouse form: correctly filled First/Last Name, Email, Phone, Website, LinkedIn from the profile; correctly left the 6 genuine free-text judgment questions ("Why Anthropic?", relocation address, etc.) unmatched for Tier 1+. Includes a heuristic "click Apply to reveal the form" step (common on Greenhouse/Lever, not universal — that generalization is Tier 2's job) and per-field error isolation (one stale xpath doesn't abort the whole run — this fired for real during testing and the fix/hardening are both in).
- [ ] Point `VITE_API_BASE_URL` at the new backend, confirm existing screens (Search, Profile, Upload, Dashboard) work unmodified end to end. Backend confirmed working via direct HTTP calls and through the real running frontend during manual testing (profile autosave, admin sync, search results all verified in-browser); a pre-existing frontend bug was found and fixed along the way (see Known issues found below).

### Day 3 — Intelligence + scraper

- [ ] Tier 1 batched LLM mapping, Tier 2 Stagehand `observe`/`act` — verify against a custom-styled checkbox and dropdown specifically.
- [x] Job scraper tier 1 (known-ATS: Greenhouse, Lever) — done Day 1 ahead of schedule, tested live (441 real jobs). Stagehand `extract()` fallback for non-ATS pages and `portals.yml` seed-loading still pending.
- [x] `admin/sync` endpoint wired to `AdminPage.tsx` exactly — done Day 1.
- [ ] Answers library.

### Day 4 — Human-in-the-loop, for real

- [ ] Pause/resume/cancel endpoints, wired into `QueueControls.tsx`.
- [ ] `needs_input` triggers: login wall, 2FA, failed CAPTCHA, low-confidence field.
- [ ] Log stream WS wired into `LogViewer.tsx`.
- [ ] 2captcha integration + escalation to human on failure.
- [ ] Provider fingerprint cache.

### Day 5 — Make it real

- [ ] End-to-end runs: Greenhouse, Lever, Ashby, one company career page requiring the scraper's extract fallback.
- [ ] Final-review-before-submit gate.
- [ ] Error handling, retries, `run_events` timeline visible via existing UI where possible.
- [ ] Demo script, README, `.env.example` (backend + confirm frontend's existing `.env.example` still points correctly).

**Cut list, in order:** scraper's WebSearch fallback tier (rely on known-ATS + extract only) → multi-user concerns → provider cache → non-Greenhouse/Lever ATS coverage → UI polish beyond the four additive components.

**Never cut:** live-view + pause/resume, final review gate, exact contract match on existing endpoints (breaking those breaks the approved frontend).

---

## Known issues found and fixed during manual testing

- **Profile autosave silently blocked forever.** `frontend/src/features/profile/schema.ts`: `yearsOfExperience`/`totalExperience` used `z.number().min(0).optional()`, but React Hook Form's `valueAsNumber: true` turns an *empty* number input into `NaN`, not `undefined` — and Zod's `.optional()` accepts `undefined` but rejects `NaN`. Leaving that field blank (the common case) failed validation on every keystroke elsewhere in the form, with only a `console.warn` and no user-visible error, so autosave looked like it was working (indicator, no toast) while never actually saving. Fixed with a `z.preprocess` that maps `NaN` back to `undefined` before validation. Worth a sweep for the same pattern anywhere else `valueAsNumber` is used on an optional field.

---

## Verification

- **Contract fidelity:** point the *unmodified* frontend at the new backend; Search, Profile, Upload, Dashboard, Admin all work with zero frontend errors before any additive changes are made.
- **Spike gate:** as v1 — Python Stagehand `observe()` against a live Greenhouse form, zero Browserbase calls.
- **Tier 0/2 regression:** golden-file test across 5 saved ATS forms; explicit pass on the custom checkbox/dropdown that broke the old build.
- **Session continuity (flagship test):** queue an application on a site requiring login → status flips to `needs_input` → live view opens → log in manually → click Resume → completes and submits on the same browser session, no restart.
- **Scraper:** `admin/sync` against a Greenhouse-hosted company returns nonzero `jobs_inserted`; against a non-ATS branded careers page falls through to Stagehand `extract()` and still returns jobs.
- **Cache:** two jobs on the same ATS → second run makes zero Tier 1 LLM calls.
- **Status vocabulary:** every status the backend emits round-trips through `mapBackendStatusToJobStatus` to something other than the `waiting` default, including `needs_input`.

---

## Risks

| Risk | Mitigation |
|---|---|
| ~~Python Stagehand needs Browserbase / can't do OpenRouter~~ | **Resolved** — spike passed, zero Browserbase key needed, custom LLM callback confirmed |
| Stagehand v4 local mode requires a Chrome-for-Testing build, not consumer Chrome | Solved: `python -m playwright install chromium`; `chrome_executable_path` points at it |
| Frontend contract drift (field names/status strings) breaks existing screens silently | Contract-fidelity test first, before any new feature work |
| Job scraper scope creep across 400+ providers | Cascading same as form-filling: known APIs → extract → WebSearch fallback (cuttable first) |
| No auth means any client can pass any `profile_id` | Explicitly accepted for this phase per your decision; flagged for later |
| 5-day scope, now with scraper as new work | Vertical slice first (Greenhouse/Lever), explicit cut list above |

---

## Clean architecture restructure (post Day-2, backend + frontend)

Both codebases were restructured into layered architecture with **zero behavioral or visual change** — verified via full manual smoke tests (backend: profile/resume/jobs/admin/apply/live-view WS; frontend: real browser click-through against the real restructured backend) plus a new backend pytest suite (63 tests, `backend/tests/`).

**Backend** — new layers: `domain/` (pure business rules: status vocabulary, application state-machine transitions, the semantic dictionary), `repositories/` (all SQLAlchemy query construction, one per aggregate), `services/*_service.py` (use-case orchestration), `ports.py` (`QueuePort`, `ResumeStoragePort` — formalizes the informal `set_run_fn` DI that already existed), `api/*.py` (now thin controllers only). `api/deps.py` is the DI hub. Route paths, request/response shapes, and status codes are byte-for-byte unchanged — confirmed against every endpoint including exact `detail` error strings.

**Frontend** — conservative, additive-only: deleted 6 verified-dead files (a duplicate hook set from a prior refactor), added `@/` path aliases (`vite.config.ts` + `tsconfig.app.json`, mirroring the alias that already existed unused in `vitest.config.ts`), fixed the one real layering inversion (`getStoredProfileId`/`setStoredProfileId` moved to `src/lib/session.ts`), gave Admin a real feature folder (`src/api/admin.ts` + `features/admin/services/admin.queries.ts`), and extracted inlined page logic into hooks (`features/profile/hooks/useAutosaveProfile.ts`, `features/search/hooks/useQueueConfirmation.ts`, `src/lib/exportJson.ts`). No JSX/CSS/store-shape/query-key changes anywhere.

**Two pre-existing findings surfaced along the way (neither touched, both out of scope for a zero-behavior-change restructure):**
- `pages/AdminPage.tsx`'s scrape-results table has a malformed JSX `<a>` tag (attributes floating as literal text instead of inside the tag) — visible garbled text and a non-functional link in the Company URL column. Syntactically valid JSX (why the build never caught it), pre-existing, moved verbatim during the Admin extraction.
- `domain/semantic_dictionary.py`'s `\baddress\b` pattern matches a relocation *judgment* question ("What is the address from which you plan on working? ... type 'relocating'") as if it were a literal home-address field. Currently harmless (falls through to unmatched whenever `profile.address` is empty) but could produce a wrong autofill if a profile has an address set. Caught while writing `tests/test_domain_semantic_dictionary.py`; not fixed since it's shipped Tier-0 matching behavior, not a restructure regression.

---

## References

- [Stagehand — connecting to an existing browser (`cdpUrl`)](https://docs.stagehand.dev/v2/configuration/browser)
- [Stagehand Python SDK docs](https://docs.stagehand.dev/v3/sdk/python)
- [Issue #1392 — `connectOverCDP` page cannot be passed to Stagehand](https://github.com/browserbase/stagehand/issues/1392)
- [Issue #1549 — custom OpenAI-compatible LLM endpoints in stagehand-python](https://github.com/browserbase/stagehand/issues/1549)
- [Issue #1250 — `storageState` / `userDataDir` broken in v3](https://github.com/browserbase/stagehand/issues/1250)
- [browserbase/stagehand-python](https://github.com/browserbase/stagehand-python)
- [Career-Ops-V3 (approved frontend, cloned reference)](https://github.com/soumita94/Career-Ops-V3)
