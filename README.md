# Career-Ops Automation — Universal Job Application Auto-Filler

An end-to-end system that takes a resume + profile, finds job postings, and fills out (and can submit) real ATS application forms automatically — without a per-provider integration for every ATS. The approach is a **cascading resolver**: try the cheapest, most deterministic method first, and only fall back to something more expensive when it can't do the job.

```
Tier 0 — deterministic, $0        a11y-tree + semantic dictionary match (names, emails, resume file, ...)
Tier 1 — one batched LLM call      decides a value for everything Tier 0 couldn't, using the profile + resume
Tier 2 — Stagehand observe()/act() resolves and clicks custom widgets (styled dropdowns, checkboxes) the value
                                    alone couldn't execute
Tier 3 — human (2FA only)          the one thing the system can never possess by design
```

The frontend (`Career-Ops-V3`, client-approved) is used as-is; this repo is the from-scratch backend built to match its API contract exactly, plus the automation engine behind it.

---

## What it does

1. **Profile + resume** — a candidate profile and an uploaded resume (PDF/DOCX/text). The resume is parsed twice: once for raw text (used to fill "describe your experience"-style fields) and once into structured facts (employment history, education, skills) via one LLM call, cached so it's paid for **once per resume**, not once per application.
2. **Job discovery** — `POST /api/admin/sync` scrapes a company's postings: known-ATS JSON APIs first (Greenhouse, Lever — free, instant), falling back to a Stagehand `extract()` pass against the company's own careers page for anything else.
3. **Automated application** — queue a job, and the engine launches a real (headed) Chrome, navigates to the posting, and runs the Tier 0→1→2 cascade to fill every field: personal details from the profile, academic/professional details from the resume, everything else answered by the LLM.
4. **CAPTCHA solving** — via 2captcha, automatically, no human step.
5. **Submission + verification** — clicks the real Submit control and reads the result page to tell a confirmation from a validation error (one bounded retry on the latter). Gated behind `SUBMIT_ENABLED` (default `False`) so nothing gets sent to a real employer by accident.
6. **2FA — the one human-in-the-loop step.** If a one-time code is required, the run pauses (`needs_input`), the frontend surfaces a **live view** into the actual running browser (screencast + click/keyboard passthrough) so you can type the code, then the automation resumes on the *same* browser session — no restart, no re-filling.
7. **Pause / resume / cancel** any queued or in-flight application from the Queue page.

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
│       │   ├── engine/          the Tier 0→1→2→3 cascade, submit, 2FA detection, resume parsing
│       │   ├── browser/         Chrome launcher, live-view CDP proxy
│       │   ├── captcha/         2captcha detection + solving
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
| LLM | OpenRouter (model-agnostic; Claude Haiku for Tier 1, Claude Sonnet for Tier 2 by default) |
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

204 tests, all fakes/mocks for LLM and browser calls — no network or Chrome needed to run the suite.

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

### Submission safety

**`SUBMIT_ENABLED` defaults to `False` on purpose.** With it off, every live run against a real ATS form fills the entire form and stops right before the Submit click — nothing gets sent anywhere. Flip it to `True` only when you deliberately want a real submission (a demo, or a supervised one-off test). Never enable it for routine testing against real employer forms.

---

## Design decisions worth knowing before you read the code

- **Tier 1 never abstains.** Early on it would decline to guess at genuinely ambiguous questions. Per later product direction, it now always answers — a wrong guess is preferred over a blank required field on a fully-automated submission pipeline. This is an accepted, deliberate tradeoff, not an oversight — see PLAN.md Day 4 for the reasoning and the containment measures (low-confidence answers are used once but never cached, and every answer's confidence is logged for after-the-fact auditing).
- **`needs_input` means 2FA — and only 2FA** (plus a flagged deviation: a CAPTCHA that fails twice also escalates here, since the browser's already open). Everything else — form-fill, CAPTCHA, submission — is fully automated. This is a scope correction from an earlier, broader "human-in-the-loop" design; see PLAN.md's "Scope correction" section for the full before/after.
- **Two independent CDP clients share one Chrome instance**: the automation engine's own Stagehand session, and a second, completely separate raw-CDP connection that powers the live-view screencast/input-forwarding. This is what lets a human take over mid-run without disturbing the automation's own session state.

---

## Current status & known gaps

This is an actively-developed project, not a finished product. Two documents track the honest state of things:

- **[PLAN.md](PLAN.md)** — the full day-by-day build log: what's built, what's been verified against real live forms vs. unit-tested only, and every real bug found (and how) along the way.
- **[FLAGGED.md](FLAGGED.md)** — open items that need a product/scope decision, plus a few things implemented but **not yet confirmed working live** (most notably: file-upload attachment has a live discrepancy under investigation, and CAPTCHA/2FA/submission are unit-tested but have never been exercised against a real challenge end-to-end).
- **[DEMO.md](DEMO.md)** — a ~10-minute walkthrough script for showing the system in action, and what not to demo live (real submission, a live CAPTCHA/2FA solve).

If you're picking this project up, read those two before assuming any given feature is production-ready — the code and tests describe intent; PLAN.md and FLAGGED.md describe what's actually been proven.
