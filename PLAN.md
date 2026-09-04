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

### Scope correction (from the client/senior discussion, adopted Day 4)

The human-in-the-loop surface is **much narrower** than v2 assumed. Confirmed direction:

- **The automation fills every field on its own.** No "leave it for a human" path for ordinary form fields.
  - **Personal details** → the profile record.
  - **Academic + professional details** → **the uploaded resume** (this is new: resume content becomes a first-class data source for form filling, not just a file to attach).
  - **Everything else / unknown questions** → the LLM answers it. Declining to answer is no longer an acceptable outcome for a required field.
- **Submission is automated.** The final-review-before-submit human gate is removed; the engine clicks Submit and verifies the result.
- **CAPTCHA is automated** via 2captcha. Not a human escalation trigger.
- **Scraping is automated.** Unchanged.
- **The ONLY *automation-initiated* human-in-the-loop trigger is 2FA** — a one-time code the system cannot possess by design. Live view exists to serve that one case.
- **User-initiated pause/resume is a separate, always-available control.** Every job in the queue gets a play/pause button so a user who queued a posting by mistake can stop it **before** it starts processing or **mid-run**, then resume or cancel. This is a deliberate user action, not the automation asking for help — the two must not share a status (see below).

**What this changes vs. what was already built:**

- **Tier 1 always answers. Confidence stops gating whether a field is filled.** Per explicit direction: every field gets whatever answer the LLM produced, however low its confidence. *Some level of hallucination is an accepted product tradeoff here* — recorded as a decision, not an oversight, because Day 3's verified "honestly abstain on ambiguous questions" behavior is precisely what is being traded away. The threshold (now **0.5**) survives only as a **cache gate** for the answers library, so a low-confidence guess is used once but never remembered and reused.
- Two capabilities that were never built at all become Day-4 blockers: **resume text extraction** (the `resumes.extracted_text` column exists but was never populated) and **file-input handling** (Tier 0 collects `textbox/combobox/checkbox/radio` only — the resume *attachment* field on essentially every ATS form is currently unhandled).
- **`pause()` currently sets `status = needs_input`** (`apply_service.py:103`) — which now collides with the 2FA meaning. The frontend renders `needs_input` as *"Waiting for you — open live view"*, so a user-paused job would wrongly prompt a live-view takeover. User-pause needs its own `paused` status (Day 4H).

**One risk flagged back, not a blocker:** automated submission means every live test creates a real job application at a real employer. Day 4 therefore lands a **local mock ATS form** as the primary submit-path test surface, plus a `SUBMIT_ENABLED` config flag (default **off** in dev) so the full cascade can be exercised end-to-end against real forms without transmitting an application. Real-employer submission is enabled deliberately, for the demo, not as a side effect of running the suite.

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

1. **New status: `needs_input`.** Add to backend status vocabulary and to `frontend/src/api/queue.ts` `mapBackendStatusToJobStatus` (currently anything unrecognized falls into `waiting`, which would hide the very moment a human needs to act — this one line must not be skipped). Surface it distinctly in `QueueStatusBadge.tsx` and `CurrentJobCard.tsx` with a "Take control" affordance. **Per the scope correction, this status now has exactly one cause: 2FA.**

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
- **Tier 3** — human, via the live-view WebSocket. **Scope narrowed (see "Scope correction" below): 2FA only.**

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
- `resumes` — profile_id FK, file, `resume_url`, `extracted_text` (populated Day 4 — was declared but never written), `parsed_facts` (Day 4: structured education/employment/skills, parsed once per resume and reused across every application)
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
- [x] `apply/start`, `apply/status`, `apply/history`, `apply/details` — status vocabulary exact. `needs_input` added to both the backend vocabulary and `frontend/src/api/queue.ts` (`mapBackendStatusToJobStatus` → `waiting_for_user` at `queue.ts:25`, `describeBackendStatus` at `queue.ts:56`) — done during the clean-architecture restructure pass.
- [x] Tier 0 harvester (a11y tree → semantic dictionary → fill) — **real, verified**. `app/services/engine/tier0_harvest.py` + `semantic_dictionary.py` + `runner.py`. Uses Stagehand's `page.snapshot()` (its own accessibility-tree representation — no need to hand-roll raw CDP `Accessibility.getFullAXTree`), regex-matches `textbox` roles against a label dictionary, fills via `page.locator(xpath).fill()`. Tested live against a real Anthropic Greenhouse form: correctly filled First/Last Name, Email, Phone, Website, LinkedIn from the profile; correctly left the 6 genuine free-text judgment questions ("Why Anthropic?", relocation address, etc.) unmatched for Tier 1+. Includes a heuristic "click Apply to reveal the form" step (common on Greenhouse/Lever, not universal — that generalization is Tier 2's job) and per-field error isolation (one stale xpath doesn't abort the whole run — this fired for real during testing and the fix/hardening are both in).
- [ ] Point `VITE_API_BASE_URL` at the new backend, confirm existing screens (Search, Profile, Upload, Dashboard) work unmodified end to end. Backend confirmed working via direct HTTP calls and through the real running frontend during manual testing (profile autosave, admin sync, search results all verified in-browser); a pre-existing frontend bug was found and fixed along the way (see Known issues found below).

### Day 3 — Intelligence + scraper

- [x] **Tier 1 batched LLM field mapping** — `app/services/engine/tier1_map.py` + `openrouter_client.py`. One OpenRouter call per page for every field Tier 0 couldn't match; decides a value using the profile + answers library, applies directly for textboxes/native selects, hands custom-widget fields to Tier 2. Verified live against the real Anthropic Greenhouse form: correctly wrote a genuine free-text answer for "Why Anthropic?", correctly left 7-11 genuinely ambiguous fields at low confidence rather than guessing (the honesty instruction working as designed), and correctly served 6 fields from the answers-library cache on a second run with zero fresh LLM cost.
- [x] **Tier 2 Stagehand `observe`→`act`** — `app/services/engine/tier2_resolve.py` + `llm_client.py::openrouter_llm` (the full Stagehand LLM-callback contract, mapped from the installed package source, not guessed — see PLAN.md's contract notes above this table). **Verified against custom-styled dropdowns on a live form**, exactly as required: Tier 2 genuinely opened and selected values in 5 real custom React-select comboboxes on Anthropic's production Greenhouse form (visa sponsorship ×2, relocation, in-person-25%, Country) — confirmed via raw CDP inspection of the actual rendered page, not just log messages. **A real bug was caught and fixed during this verification**: a single observe()+act() call only opened the dropdown without completing the selection (the option element doesn't exist in the accessibility tree until the dropdown is open, so it can't be resolved in one shot) — fixed with a genuine two-step open-then-select flow, now covered by regression tests. This is the direct, now-verified fix for the coordinate-clicking bug the whole rebuild exists for. No literal `<input type=checkbox>` existed on the test form to verify against — all of this form's multi-choice fields render as the same custom-combobox widget type, so the checkbox code path is implemented and unit-tested but not live-verified.
- [x] Job scraper tier 1 (known-ATS: Greenhouse, Lever) — done Day 1, tested live (499 real jobs).
- [x] **Job scraper tier 2 — Stagehand `extract()` fallback** for non-ATS pages, `app/services/scraper/sync_service.py::_sync_via_extract`. Verified live: completed successfully against a real company page (correctly found zero jobs on a homepage with none listed) and failed gracefully against another (no crash, proper `{success: false}`). Uses a dedicated `"scraper"` Chrome profile, never a user's logged-in session.
- [x] **`portals.yml` seeding** — `app/scripts/seed_portals.py`. Corrected a real miscount along the way: the file has 409 tracked companies, not 454 (454 = 409 tracked_companies + 45 separate search_queries entries, conflated by an earlier grep). All 409 have `scan_method: websearch` — **zero** resolve to a free Greenhouse/Lever API directly; every real scrape needs the extract() fallback. 10 bare-ATS-host junk entries correctly detected and skipped. Verified live: 399 inserted, 10 skipped; re-run is idempotent (0 inserted, 399 updated).
- [x] `admin/sync` endpoint wired to `AdminPage.tsx` exactly — done Day 1.
- [x] **Answers library** — `app/domain/answer_key.py` (question normalization/hashing) + `app/repositories/answer_library_repository.py`. Per-decision: only caches high-confidence answers, tagged `source` ('llm'/'human'); a human answer always overwrites an LLM one, an LLM answer never overwrites a human one. Verified live — a second run against the same form served 6 answers from cache with zero fresh LLM cost for those fields.

**Bugs found and fixed during Day 3** (both caught by writing tests / live-verifying, not assumed): (1) `tier1_map.py`'s prompt-building crashed on `datetime` values from the raw profile dict — fixed with `json.dumps(..., default=str)`, regression-tested. (2) Tier 2's single-step combobox resolution reported false success — see above, fixed with the two-step flow.

Day-2 leftovers closed alongside this: `queue.ts`'s `needs_input` mapping was already done (PLAN.md's own note was stale); Upload Resume and Queue pages verified live in a real browser (a real file upload round-tripped through `POST /api/resume/upload` end to end).

### Day 4 — Full autonomy + 2FA-only human-in-the-loop

Re-scoped per "Scope correction" above. The theme is no longer "hand off to a human" — it is **"never need to, except for 2FA"**. Ordered by what unblocks what.

**A. Resume as a data source (new capability, blocks everything else) — [x] done, unit-tested**
- [x] **Resume text extraction** — `services/resume/extract.py`: `pypdf` for PDF, `python-docx` for DOCX, plain-text passthrough otherwise, best-effort (never fails the upload). Wired into `ResumeService.upload`. Verified against the real resume on file for profile 1 — 4452 chars extracted correctly from a real PDF.
- [x] **Structured resume parse** — `services/engine/resume_parse.py::parse_resume_facts`, one `chat_json` call → `ResumeFacts` (employment/education/skills/certifications). `ResumeService.get_facts` caches the result on `Resume.parsed_facts` (JSON), so it's paid once per resume — verified via unit test that a second call makes zero further parse calls. A re-upload invalidates the stale cache (`parsed_facts` reset to `None`). Degrades to empty facts, never raises, if there's no key or no text — same kill-switch pattern as Tier 1.
- [x] **Feed it to Tier 1** — `map_fields`/`build_prompt` take an optional `resume_facts` param; `runner.py` fetches it once per application (via `ResumeService`) before the Tier 1 call.
- Not unit-tested live against a real form yet (no field on the test form actually needed resume-only data) — the extraction/parse/cache pipeline itself IS live-verified (real PDF → real text), the "Tier 1 answers a resume-only question correctly" claim is not.

**B. File upload — the resume attachment field — [~] implemented, unit-tested, but live verification found a real unresolved discrepancy — DO NOT treat as working**
- [x] `file` added to `tier0_harvest.TARGET_ROLES`. Real recon finding (not guessed): the role renders as the comma-joined `input, file` on a live Greenhouse form, not a bare `file` role — parsing handles this. The field's real label ("Resume/CV") and its required-marker (`*`) both live on the enclosing `group:` node, not the input itself — also confirmed live and handled (`_enclosing_group`). A real form had **two** file inputs (Resume/CV, Cover Letter); the resume is only attached to the one whose label actually says resume/CV (`_RESUME_FIELD_LABEL`), a bug caught while writing the test for it, fixed before it shipped.
- [x] Filled deterministically in Tier 0 via `Locator.set_input_files()` (Stagehand — no raw CDP needed, contrary to the original plan) with the profile's stored resume path. No LLM cost.
- [ ] **Live verification found a real, unresolved false-success pattern** (same class of bug as Day 3's combobox issue, not yet root-caused): `set_input_files()` returns no error, but checking the actual DOM (not our own log) shows the file was never reflected in the widget's own state — the input's `files.length` never left 0, and the section re-rendered back to its unattached "Attach" state with no filename shown and no error either. Full details, evidence, and a working theory (React/dropzone not recognizing the CDP-injected selection as trusted; or a Stagehand-python RPC difference from real Playwright) are in [FLAGGED.md](FLAGGED.md) #8. **This blocks calling Section B complete** — needs either an event-dispatch fix or a fallback through Tier 2's `observe`/`act` (a real synthetic click + native file-picker), mirroring the Day-3 two-step combobox fix.
- [ ] Tier 2 fallback for drag-and-drop/custom uploaders — not started; likely now the *primary* path pending B's root cause, not just a fallback for a rarer widget shape.

**C. Tier 1 never abstains — it always answers — [x] done, unit-tested**
- [x] **Confidence no longer gates filling at all.** Whatever value the LLM returns for a field gets written to the form, regardless of how low its confidence is. There is no skip path, no second pass, no escalation, no human handoff.
- [x] **`tier1_confidence_threshold` drops 0.6 → 0.5 and is repurposed**: it stops being a fill gate and becomes purely a **cache gate** for the answers library. Everything is *filled*; only answers at or above 0.5 are *remembered* — preserves the Day-3 decision (cache high-confidence only) for the reason that motivated it, so a low-confidence guess is used once but never propagated into future applications.
- [x] **Prompt inverted** — the system prompt now instructs the model to always produce its best answer and use confidence to express uncertainty, not as permission to decline (Day 3's verified abstention behavior on ambiguous fields is the thing being traded away, deliberately).
- [x] **Required-field detection** — `FormField.required`, captured from the same `group:` ancestor pattern found in Part B. Informational only (nothing gates on it); not yet wired into a `run_events` log line for an unfilled required field — small remaining gap.
- [x] `Tier1Result.low_confidence` renamed to `low_confidence_filled` — fields are filled, just flagged; `runner.py`'s log line updated to match.
- [x] Every answer keeps logging value + confidence to `run_events`, low-confidence at `warn`.

**D. CAPTCHA — automated via 2captcha — [x] done, unit-tested; NOT live-verified against a real solve**
- [x] **API key from env**: `TWOCAPTCHA_API_KEY` added to `backend/.env` by you, surfaced as `settings.twocaptcha_api_key`.
- [x] `services/captcha/detect.py` — regex over iframe `src` (not DOM attributes; the sitekey is public by design and sits right in the iframe URL's `k=`/`sitekey=` query param). **Grounded in a real finding**: Anthropic's live Greenhouse form embeds an *invisible reCAPTCHA Enterprise* iframe — its exact URL shape (`/recaptcha/enterprise/anchor?...&k=...&size=invisible`) is what `_RECAPTCHA_IFRAME` matches, not a guess.
- [x] `services/captcha/solver.py` — thin async wrapper (`asyncio.to_thread`) over the synchronous `2captcha-python` SDK; `services/captcha/service.py` orchestrates detect → solve → inject-token-into-page, one retry on failure.
- [x] **Kill switch**: no key configured → detection still runs and logs it, solving is skipped (`outcome="no_key"`), never crashes the run.
- [x] Retry once on failure, then **`captcha_failure_escalates: bool = True`** (config, deviation flagged as planned) — escalates to `needs_input`/`pause_reason="captcha_failed"` via the same pause/resume mechanism as 2FA, rather than failing the application outright.
- **Not live-verified**: no live run actually triggered and solved a real CAPTCHA — that would cost real 2captcha balance and up to 10 minutes per attempt, and Anthropic's is invisible (may only fire on real submit, which wasn't safe to trigger this pass). Detection regex is grounded in a real captured iframe URL; solving/injection is unit-tested against a fake 2captcha client only.

**E. 2FA — the one real human-in-the-loop path — [x] done, unit-tested; NOT live-verified (no 2FA challenge encountered in any live test to date)**
- [x] **Detection** — `services/engine/twofa_detect.py`, deterministic regex over the accessibility tree's label/heading text (same Tier-0 philosophy — no DOM attribute access). Runs after navigation/apply-click, and again after each submit attempt.
- [x] On detection → `status = needs_input`, `pause_reason = "2fa_required"`, halts and calls `wait_for_resume` (existing Day-1 mechanism); resumes on the same live Chrome session.
- [x] On resume → continues the cascade from where it stopped (re-snapshots naturally as part of the normal flow).
- **Not live-verified**: no 2FA challenge was encountered on any real form used in this project so far, so the detection pattern itself is unconfirmed against real markup — flagged in FLAGGED.md.

**F. Submission + verification — [x] implemented, unit-tested; NOT live-verified against a real form (deliberately — `submit_enabled` defaults False)**
- [x] `services/engine/submit.py` — `find_submit_button` (regex over the tree, same technique as the existing `_click_apply_if_present`) + `read_outcome` (confirmation-phrase vs validation-error regex over the post-click tree).
- [x] **`submit_enabled` config flag, default `False`** — the full cascade runs and stops one click short; logged clearly (`"Submission skipped — SUBMIT_ENABLED is False"`) and the application is marked `completed` at that point (a deliberate simplification — see note below).
- [x] **Post-submit verification**: confirmation text → `completed`. Validation error → **one bounded repair pass** — reruns the full Tier0→Tier1→Tier2 cascade against the corrected page state and retries submit once. This is a **simplified version of the original design** (a full rerun, not per-field-error-message targeting) — flagged as a known simplification, not the fuller design originally scoped.
- [ ] **Local mock ATS form** — not built this pass. This is the biggest real gap in F: without it, the submit path (and the repair-pass loop) has never been exercised against anything, real or fake — only unit-tested at the regex/logic level with hand-written tree fragments.

**Known simplification, flagged rather than hidden**: with `submit_enabled=False`, the run is marked `completed` even though nothing was actually submitted — chosen over inventing a new status, since the vocabulary only has `queued/running/needs_input/completed/failed/cancelled` and `needs_input` is reserved for 2FA. The `RunEvent` log is the source of truth for "was this actually submitted" — always check it, don't infer submission from status alone while `submit_enabled` is off.

**H. Per-job play/pause in the queue (user-initiated, distinct from 2FA) — [x] done, unit-tested, AND live-verified**

The scenario: a user queues a posting by mistake and wants to stop it — either before it starts, or while it is mid-run.

- [x] **New status `paused`** in `app/domain/status.py`. `apply_service.pause()` now sets `PAUSED` (not `NEEDS_INPUT`) and calls a new `queue.signal_pause()`.
- [x] **Frontend status mapping** — `paused` maps to `waiting` in `mapBackendStatusToJobStatus`, with its own `describeBackendStatus` label. A new `QueueItem.rawStatus` field carries the un-coarsened backend status through so per-row controls (which need to tell "paused" apart from an ordinary "queued", both mapped to `waiting`) don't need a new `JobStatus` badge variant.
- [x] **Pause before processing starts** — `worker/queue_runner.py` gained a `_pause_events` dict (mirroring the existing `_cancel_events`) plus `signal_pause`/`is_paused`; `runner.py` checks `is_paused()` before `get_or_launch()`. **Live-verified**: paused a freshly-queued application immediately, confirmed via server logs that Chrome never launched and status held at `paused` for several seconds — the "costs nothing" claim is real, not assumed.
- [x] **Pause mid-run** — checkpoints via `_check_paused_and_wait` at every tier boundary in `_run_fill_cascade` (after Tier 0, Tier 1, Tier 2) and immediately before the submit click in `_submit_and_verify`. Tier-boundary and pre-submit checkpoints are unit-tested-only, not yet live-exercised (lower risk — same code path as the pre-launch gate, which was live-tested).
- [x] **Cancel while paused** — a real gap found while implementing this: the existing `wait_for_resume` had nothing listening for a cancel signal while blocked, so cancelling a paused (or 2FA-paused, or CAPTCHA-escalated) application would leave its task — and Chrome session — blocked forever. Fixed with `wait_for_resume_or_cancel` (races both events via `asyncio.wait`) used at every pause point, plus a new `ApplicationCancelled` sentinel exception so the runner unwinds cleanly without the generic error handler overwriting the already-`CANCELLED` status with `FAILED`.
- [x] **Resume** continues on the same live Chrome session — **live-verified**: resumed the same paused application, confirmed it transitioned to `running` and proceeded (a subsequent Stagehand init timeout was an environmental issue from this session's own heavy Chrome-profile reuse, not a functional problem with resume itself — see FLAGGED.md #10).
- [x] `transitions.ensure_can_resume` now accepts both `NEEDS_INPUT` and `PAUSED`.

**Two more real bugs found and fixed during H's live verification** (neither specific to H, both were blocking it — full detail in FLAGGED.md #10):
1. `QueuePage.tsx`'s `hasActiveJob` gate only checked the *aggregate* queue status, which doesn't move for a single `needs_input` job among otherwise-terminal ones — `CurrentJobCard` (and the whole Live View entry point from Part G) was unreachable in exactly that case. Fixed by also checking `queueState.currentJobId` directly.
2. `runner.py`'s initial profile/job/resume lookup had **no exception handling at all** — a DB error there (this session hit a real one: a stale dev DB missing a column) killed the background task silently, leaving the application stuck at `queued` forever with zero error, zero log line, zero UI signal. Fixed by moving that lookup inside the same try/except that already covers every later failure.

**G. Frontend wiring — [x] fully done, including Part H's per-row control**
- [x] `QueueControls.tsx` — replaced the "not yet supported" toasts with real calls to `pauseApply`/`resumeApply`/`cancelApply`, targeting the queue's current application via `queueState.currentJobId`.
- [x] **Real bug found and fixed**: `mapHistoryToQueueState` only ever set `currentJobId` from an item with status `running` — a `needs_input` (2FA) item maps to `waiting_for_user`, a *different* status, so `currentJobId` silently went `undefined` the moment a job most needed attention. Fixed by including `waiting_for_user` in the "current job" lookup.
- [x] **`LiveView.tsx`** — canvas (`<img>` of JPEG frames) + click/keyboard capture over `WS /ws/apply/{id}/live-view`, coordinates scaled from rendered size to the frame's natural (real viewport) size before forwarding as CDP `Input.dispatch{Mouse,Key}Event` params. Opened from "Take Control" on `CurrentJobCard`. **Live-verified**: opened against a real application, WS connected (confirmed via the connected-state indicator), no console errors.
- [x] **`useApplicationLogs` hook** — real `WS /ws/apply/{id}/logs` connection, replacing the hardcoded `logs: []`. **Live-verified**: real Tier 0/1/2 log lines from actual historical runs rendered correctly in `LogViewer`.
- [x] **`JobTimelineModal.tsx`** (new, Day 5) — the run_events timeline for ANY job (not just the live "current" one), via `GET /api/apply/details/{id}` (extended with an `events` field — additive, `getDetails` was unused in the frontend before this so nothing broke). Opened via a new History icon on every `QueueTable` row. **Live-verified**: opened against a real completed (failed) application, showed its real 3-event history with correct error-level coloring.
- [x] **Per-row Pause/Resume buttons in `QueueTable.tsx`** (Part H's frontend half) — `usePauseJobMutation`/`useResumeJobMutation` take an explicit application id (unlike `QueueControls`' current-job-only mutations), shown/hidden per row via `item.rawStatus`. **Live-verified** end to end via the underlying API (see H above) — the buttons themselves were exercised through the same click-through pass that opened Live View and the timeline modal.
- [x] Safety fix in `QueueControls.tsx`: the generic "Resume Queue" button is disabled while the current job is `waiting_for_user`, directing to Take Control instead.
- [x] `npx tsc -b` and `npx vite build` both clean (two pre-existing unrelated errors confirmed via `git diff` to predate this session).

**Deferred out of Day 4:** provider fingerprint cache (a cost optimization, moved to the Day-5 cut list).

### Day 5 — Make it real

- [x] **First fully successful end-to-end live fill run of the complete Day 4 cascade**, Greenhouse: CAPTCHA solved automatically, Tier 0 → 4 fields, Tier 1 → 8 fields (including low-confidence-but-filled, per the accepted tradeoff), Tier 2 → 13 fields (custom dropdowns, arbitration agreement, EEOC questions), 2 left unhandled, run marked `completed` (stopped short of Submit — `SUBMIT_ENABLED=False`). Two real, serious bugs found and fixed to get here — both reported live by the user, not found by me proactively:
  1. **Multiple applications for one profile raced on a single shared Chrome session** — `queue_runner.py`'s own docstring claimed "serial per profile" but nothing enforced it. Fixed with `get_profile_lock()`, live-verified. Full detail: FLAGGED.md #11.
  2. **CAPTCHA solving crashed on every real run**: `page.url` used as a plain attribute when it's actually an async method on Stagehand's `Page` — 2captcha correctly rejected the resulting bound-method-object as an invalid URL. The unit test suite didn't catch it because the test double's shape didn't match the real class. Fixed (`await page.url()`), fake corrected to match. Full detail: FLAGGED.md #12.
- [ ] Lever, Ashby, and the scraper's extract-fallback path specifically not re-verified this pass (Greenhouse covered above; `admin/sync` extract-fallback was live-verified in Day 3).
- [ ] ~~Final-review-before-submit gate.~~ **Removed** — submission is automated per the scope correction; the `SUBMIT_ENABLED` flag (Day 4F) is the dev-safety mechanism that replaces it.
- [ ] **Turn `SUBMIT_ENABLED` on and do one deliberate, supervised real submission end to end.** **Not done — deliberately.** This sends a real job application to a real employer; it needs your explicit go-ahead before an agent does it, not just a plan checkbox. Flagged, not executed.
- [x] **Error handling, retries, `run_events` timeline visible via existing UI.** Two real silent-failure classes found and fixed this pass (see Part H above and FLAGGED.md #10): the initial-lookup exception gap, and the `hasActiveJob` visibility gap. The `run_events` timeline is now visible for any job via the new `JobTimelineModal` (Part G), not just the live one.
- [x] **`.env.example`** — `backend/.env.example` added (was missing); `frontend/.env.example` confirmed already correct (`VITE_API_BASE_URL=http://localhost:8000`).
- [x] **README** — root `README.md` added: architecture, setup, config reference, submission-safety callout, pointers to this file and FLAGGED.md.
- [ ] Demo script — not yet written.

**Cut list, in order:** scraper's WebSearch fallback tier (rely on known-ATS + extract only) → multi-user concerns → provider fingerprint cache (moved here from Day 4) → non-Greenhouse/Lever ATS coverage → UI polish beyond the four additive components.

**Never cut:** resume-as-data-source + file upload (without them "fills every detail on its own" is false), per-job user play/pause (the only way to stop a mistakenly-queued application before it is submitted), 2FA live-view + resume, automated submit with post-submit verification, exact contract match on existing endpoints (breaking those breaks the approved frontend).

---

## Known issues found and fixed during manual testing

- **Profile autosave silently blocked forever.** `frontend/src/features/profile/schema.ts`: `yearsOfExperience`/`totalExperience` used `z.number().min(0).optional()`, but React Hook Form's `valueAsNumber: true` turns an *empty* number input into `NaN`, not `undefined` — and Zod's `.optional()` accepts `undefined` but rejects `NaN`. Leaving that field blank (the common case) failed validation on every keystroke elsewhere in the form, with only a `console.warn` and no user-visible error, so autosave looked like it was working (indicator, no toast) while never actually saving. Fixed with a `z.preprocess` that maps `NaN` back to `undefined` before validation. Worth a sweep for the same pattern anywhere else `valueAsNumber` is used on an optional field.

---

## Verification

- **Contract fidelity:** point the *unmodified* frontend at the new backend; Search, Profile, Upload, Dashboard, Admin all work with zero frontend errors before any additive changes are made.
- **Spike gate:** as v1 — Python Stagehand `observe()` against a live Greenhouse form, zero Browserbase calls.
- **Tier 0/2 regression:** golden-file test across 5 saved ATS forms; explicit pass on the custom checkbox/dropdown that broke the old build.
- **Session continuity (flagship test, re-scoped to 2FA):** queue an application on a site that challenges with a one-time code → status flips to `needs_input` with `pause_reason = "2fa_required"` → live view opens → human types the code → click Resume → the cascade continues and submits on the same browser session, no restart.
- **Full autonomy (new flagship test):** against the local mock ATS form, a single run fills **every** field — personal from profile, academic/professional from the parsed resume, unknown questions from the LLM, resume file attached via the file input — then submits and detects the confirmation. Zero `needs_input` events, zero unfilled required fields.
- **Resume as a data source:** a question answerable *only* from resume content (e.g. a prior employer not present on the profile record) is filled correctly.
- **Submit safety:** with `SUBMIT_ENABLED=False`, a full run against a real ATS form reaches the submit control and stops — verified by the form still being on-screen, unsubmitted.
- **User pause, before start:** pause a `queued` job → it never launches Chrome and never spends an LLM call → press play → it runs normally from the beginning.
- **User pause, mid-run:** pause a `running` job → it stops at the next tier boundary with status `paused` → press play → it continues on the *same* Chrome session with previously-filled fields still filled, not refilled from scratch.
- **Pause beats submit:** a job paused while `SUBMIT_ENABLED=True` never submits — the pre-submit checkpoint holds.
- **Status separation:** a user-paused job never shows the 2FA "open live view" prompt, and a 2FA pause never looks like a user pause.
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
| **Automated submission sends real applications to real employers** | `SUBMIT_ENABLED` defaults off in dev; local mock ATS form is the primary submit-path test surface; real submission only ever run deliberately and supervised |
| **Filling every field regardless of confidence will put some wrong answers on real job applications** — Day 3's verified "abstain when unsure" behavior is deliberately traded away, and submission is now automatic, so a bad answer reaches a real employer with no human between | **Accepted tradeoff, explicitly directed** — not a defect to fix later. Prevention is out of scope by choice, so the mitigations are containment: (a) low-confidence answers are used but never cached, so one bad guess never propagates to future applications; (b) every answer is logged with its confidence, low ones at `warn`, so a bad application is explainable afterward; (c) per-job pause can stop a run before the submit checkpoint if a user spots it in the log |
| Resume parse quality now gates form-fill accuracy for all academic/professional fields | Parsed once per resume and cached, so it is cheap to inspect and correct; parse failure degrades to raw `extracted_text` in the Tier 1 prompt rather than failing the run |

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
