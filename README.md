# Career-Ops Automation — Universal Job Application Auto-Filler

An end-to-end system that takes a resume + profile, finds job postings, and fills out (and can submit) real ATS application forms automatically — without a per-provider integration for every ATS. The approach is a **cascading resolver**: try the cheapest, most deterministic method first, and only fall back to something more expensive when it can't do the job.

```
Tier 0 — deterministic, $0        a11y-tree + semantic dictionary match (names, emails, resume file, ...)
Tier 1 — one batched LLM call      decides a value for everything Tier 0 couldn't, using the profile + resume
Tier 2 — Stagehand observe()/act() resolves and clicks custom widgets (styled dropdowns, checkboxes) the value
                                    alone couldn't execute
Tier 3 — human                     2FA codes (the one thing the system can never possess by design), plus any
                                    single field the tiers above genuinely couldn't resolve — the run pauses and
                                    hands that field to a human rather than failing the whole application
```

The frontend (`Career-Ops-V3`, client-approved) is used as-is; this repo is the from-scratch backend built to match its API contract exactly, plus the automation engine behind it.

---

## What it does

1. **Profile + resume** — a candidate profile and an uploaded resume (PDF/DOCX/text). The resume is parsed twice: once for raw text (used to fill "describe your experience"-style fields) and once into structured facts (employment history, education, skills) via one LLM call, cached so it's paid for **once per resume**, not once per application.
2. **Job discovery** — `POST /api/admin/sync` scrapes a company's postings: known-ATS JSON APIs first (Greenhouse, Lever — free, instant), falling back to a Stagehand `extract()` pass against the company's own careers page for anything else.
3. **Automated application** — queue a job, and the engine launches a real (headed) Chrome, navigates to the posting, and runs the Tier 0→1→2 cascade to fill every field: personal details from the profile, academic/professional details from the resume, everything else answered by the LLM.
4. **CAPTCHA solving** — via 2captcha, automatically, no human step.
5. **Submission + verification** — clicks the real Submit control and reads the result page to tell a confirmation from a validation error (one bounded retry on the latter). Gated behind `SUBMIT_ENABLED` (default `False`) so nothing gets sent to a real employer by accident.
6. **Human-in-the-loop, for the things automation genuinely can't do.** If a one-time code is required, the run pauses (`needs_input`), the frontend surfaces a **live view** into the actual running browser (screencast + click/keyboard passthrough) so you can type the code, then the automation resumes on the *same* browser session — no restart, no re-filling. The 2FA wait also polls the page every few seconds and **auto-resumes on its own** if the challenge clears (e.g. you answered the code elsewhere), with a hard 10-minute ceiling so an unanswered challenge fails cleanly instead of stranding the queue forever. The same pause/live-view mechanism is the catch-all fallback for **any** field the cascade can't resolve — see "Design decisions" below.
7. **Pause / resume / cancel** any queued or in-flight application from the Queue page, or directly from the live-view panel while it's waiting on you.

---

## Architecture

```
resume-automate/
├── frontend/                  React 19 + Vite + TS (client-approved, additive changes only)
│   └── src/features/queue/    LiveView.tsx, LogViewer.tsx, QueueControls.tsx — the human-in-the-loop UI
├── backend/
│   ├── config/portals.yml     seed list of tracked companies + their scrape strategy
│   └── app/
│       ├── api/                thin controllers (profile, resume, jobs, apply, admin, ws)
│       ├── domain/              pure business rules: status vocabulary, state transitions,
│       │                        semantic dictionary, answer-key hashing
│       ├── repositories/        all SQLAlchemy queries, one per aggregate
│       ├── services/
│       │   ├── engine/          the Tier 0→1→2→3 cascade, submit, 2FA detection, resume parsing,
│       │   │                    shared textbox/autocomplete fill (field_fill.py), and the
│       │   │                    one place every browser await gets a timeout (timeouts.py)
│       │   ├── browser/         Chrome launcher, live-view CDP proxy
│       │   ├── captcha/         2captcha detection + solving, shared proxy config (proxy.py)
│       │   ├── resume/          text extraction (pypdf/python-docx) + local file storage
│       │   └── scraper/         known-ATS APIs + Stagehand extract() fallback
│       ├── ports.py              QueuePort / ResumeStoragePort — the DI seams
│       └── worker/               in-process async queue runner (pause/resume/cancel signals)
├── PLAN.md                    the day-by-day build log — what's done, what's verified live vs.
│                               unit-tested only, and every real bug found along the way
└── FLAGGED.md                 open items and honest gaps that need a product/scope decision
```

Backend and frontend are both organized as layered/clean architecture — see PLAN.md's "Clean architecture restructure" section for the reasoning.

**Why a cascade, not per-ATS integrations:** coordinates can't be verified or cached and break the moment a page reflows; element *references* (what Stagehand's `observe()` returns) can be. That distinction — not per-provider API integrations — is what makes 400+ ATS providers tractable within the project's constraints.

---

## Tech stack

| Layer | Choice |
|---|---|
| Frontend | React 19, Vite, TypeScript, Zustand, TanStack Query, Axios, Tailwind v4, React Hook Form + Zod |
| Backend | FastAPI, Pydantic v2, SQLAlchemy 2.0 (async), SQLite |
| Browser automation | Stagehand v4 (Python) over a self-launched, headed Chrome-for-Testing instance |
| LLM | OpenRouter (model-agnostic; `meta-llama/llama-3.3-70b-instruct` for Tier 1, `z-ai/glm-4.6` for Tier 2 by default — both swappable via `.env`) |
| CAPTCHA | 2captcha |

No Skyvern, Browser Use, Anchor Browser, or Browserbase cloud — self-hosted, open-source browser automation only. The only two paid externals are OpenRouter and 2captcha, and the app stays runnable (in a degraded, Tier-0-only mode) without either key configured.

---

## Setup

### Prerequisites

- Python 3.12+
- Node 18+
- A **Chrome for Testing** build (not consumer Chrome Stable — Stagehand's local-browser mode depends on a CDP method consumer Chrome doesn't support):
  ```bash
  python -m playwright install chromium
  ```

### Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows; use `source .venv/bin/activate` on macOS/Linux
pip install -r requirements.txt

cp .env.example .env          # then fill in OPENROUTER_API_KEY / TWOCAPTCHA_API_KEY
python -m app.scripts.seed_portals   # seeds config/portals.yml's tracked companies

uvicorn app.main:app --host 0.0.0.0 --port 8000
```

> **Don't use `--reload` on Windows.** Reload mode forces uvicorn onto `SelectorEventLoop`, which can't spawn child processes on Windows — and launching Chrome is exactly that. It fails instantly with an unhelpful, near-empty error. Restart manually after code changes instead.

### Frontend

```bash
cd frontend
npm install
cp .env.example .env          # VITE_API_BASE_URL should point at the backend above
npm run dev
```

### Running tests

```bash
cd backend
pytest -q
```

321 tests, all fakes/mocks for LLM and browser calls — no network or Chrome needed to run the suite.

---

## Configuration reference

All backend settings live in `app/core/config.py`, overridable via `backend/.env`:

| Variable | Default | Purpose |
|---|---|---|
| `OPENROUTER_API_KEY` | *(unset)* | Powers Tier 1 + Tier 2. Unset → those tiers degrade gracefully, Tier 0 still works. |
| `TWOCAPTCHA_API_KEY` | *(unset)* | CAPTCHA solving. Unset → a detected CAPTCHA is logged and left unsolved. |
| `SUBMIT_ENABLED` | `False` | **Dev safety gate.** With this off, the full cascade runs and stops one click short of Submit. |
| `TIER1_CONFIDENCE_THRESHOLD` | `0.5` | Gates only the **answers-library cache** (Tier 1 always fills every field regardless of confidence — see "Design decisions" below). |
| `CAPTCHA_FAILURE_ESCALATES` | `True` | If 2captcha fails twice, escalate to a human via live view instead of failing the application outright. |
| `CAPTCHA_PROXY_URL` | *(unset)* | Routes **both** the browser and the 2captcha solve call through the same proxy, so the IP that solves a challenge matches the IP that submits the token. Required for risk-based (Enterprise) reCAPTCHA to accept a solved token at all — see below. Unset → no proxy, no behavior change. |
| `CAPTCHA_SOLVE_TIMEOUT_SECONDS` | `180` | Hard bound on a 2captcha solve. The SDK's own defaults (600s, twice over) would otherwise block a run for ~20 minutes looking identical to a hang. |
| `CAPTCHA_POLLING_INTERVAL_SECONDS` | `5` | How often the 2captcha SDK polls for a result. |
| `USE_REAL_CHROME` | `False` | Opt-in: launch consumer Chrome instead of the Chrome-for-Testing build. **Known not to work** — Stagehand's companion extension can't complete its handshake on a Stable-channel build (FLAGGED.md). Left in place as documented dead-end, not a supported path. |
| `REAL_CHROME_EXECUTABLE_PATH` | *(auto-detect)* | Only used when `USE_REAL_CHROME=True`. |

**On `CAPTCHA_PROXY_URL`:** a solved 2captcha token is bound by Google to the IP that solved it. Without a shared proxy, 2captcha solves from its own datacenter IP while the browser submits from yours — and risk-based reCAPTCHA Enterprise rejects the mismatch regardless of token validity. This was the confirmed cause of a real "Please complete the reCAPTCHA" rejection on a genuinely-solved token. Format: `scheme://user:pass@host:port`.

### Submission safety

**`SUBMIT_ENABLED` defaults to `False` on purpose.** With it off, every live run against a real ATS form fills the entire form and stops right before the Submit click — nothing gets sent anywhere. Flip it to `True` only when you deliberately want a real submission (a demo, or a supervised one-off test). Never enable it for routine testing against real employer forms.

---

## Design decisions worth knowing before you read the code

- **Tier 1 never abstains.** Early on it would decline to guess at genuinely ambiguous questions. Per later product direction, it now always answers — a wrong guess is preferred over a blank required field on a fully-automated submission pipeline. This is an accepted, deliberate tradeoff, not an oversight — see PLAN.md Day 4 for the reasoning and the containment measures (low-confidence answers are used once but never cached, and every answer's confidence is logged for after-the-fact auditing).
- **`needs_input` is the universal "automation is stuck, a human can unstick it" state.** It started as 2FA-only, then grew — deliberately, each time in response to a real live failure:
  - `2fa_required` — a one-time code. The original and still the primary case.
  - CAPTCHA that failed twice (`CAPTCHA_FAILURE_ESCALATES`) — the browser's already open, so escalating beats failing outright.
  - `manual_fields_required` — **any** field the whole cascade genuinely couldn't resolve. Rather than chase every new widget shape as it's discovered (a typeahead city picker was the one that forced this), any unresolvable field the ATS is actually blocking submission on now pauses and hands that one field to a human. The guiding rule, per product direction: *the agent never fails and stops on its own while a human fix is still possible.* Only after a genuinely human-assisted final submit attempt still fails does a run end as `failed`.
- **One Chrome process per application, not per profile.** Cookies/login continuity comes from reusing the same `--user-data-dir` on a fresh launch — *not* from keeping one browser alive across applications. That distinction is forced by Stagehand's own extension: its runtime state machine is `created → initialized → closed`, one-way, with no reset, so a second `Stagehand.create()` against the same Chrome process can never succeed. Every application therefore closes its session (while still holding the per-profile lock, so the next one can't race it) and the next gets a fresh process. This took four attempts to get right — the full trail is in FLAGGED.md #26–#29.
- **Two independent CDP clients share one Chrome instance**: the automation engine's own Stagehand session, and a second, completely separate raw-CDP connection that powers the live-view screencast/input-forwarding. This is what lets a human take over mid-run without disturbing the automation's own session state.

---

## Current status & known gaps

This is an actively-developed project, not a finished product. Two documents track the honest state of things:

- **[PLAN.md](PLAN.md)** — the full day-by-day build log: what's built, what's been verified against real live forms vs. unit-tested only, and every real bug found (and how) along the way.
- **[FLAGGED.md](FLAGGED.md)** — open items that need a product/scope decision, plus everything implemented but not yet confirmed live. Now 31 entries; the later ones (#23 onward) are the live-testing era against real Greenhouse forms at two different companies, and are the most useful read for anyone picking this up.

- **[DEMO.md](DEMO.md)** — a ~10-minute walkthrough script for showing the system in action, and what not to demo live (real submission, a live CAPTCHA/2FA solve).

**What has now been exercised against real forms** (updating the earlier "never tested live" caveats): CAPTCHA solving via 2captcha (works, repeatedly), the full Tier 0→1→2 cascade filling ~20 fields, submission with validation-error detection and repair, a real email-OTP 2FA challenge on a live Figma application, and the `manual_fields_required` escalation firing correctly on a field the cascade couldn't resolve.

**What's still genuinely open:**
- **Risk-based reCAPTCHA Enterprise** can reject a validly-solved token purely on session risk score. `CAPTCHA_PROXY_URL` addresses the largest known cause (IP mismatch) but needs a real proxy to verify, and no amount of this is a guarantee — it's an adversarial system by design. See FLAGGED.md.
- **A typeahead/autocomplete combobox** (Greenhouse's "Location (City)") still resolves unreliably. It's the specific failure that motivated the general human-escalation fallback, which now catches it rather than failing the run.
- **`USE_REAL_CHROME`** is a documented dead end, not a working option.

If you're picking this project up, read PLAN.md and FLAGGED.md before assuming any given feature is production-ready — the code and tests describe intent; those two describe what's actually been proven. Where they disagree with this README, they're the more recent record.
