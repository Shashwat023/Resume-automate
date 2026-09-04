# Demo script

A ~10-minute walkthrough of the working system. Assumes a fresh checkout — see [README.md](README.md) for setup.

**Before you start:** `SUBMIT_ENABLED` should stay `False` for this demo (the default) — every step below fills a real form and stops one click short of Submit. Nothing gets sent to a real employer.

---

## 1. Start everything

```bash
# Terminal 1
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8000   # no --reload — see README

# Terminal 2
cd frontend
npm run dev
```

Open `http://localhost:5173`.

## 2. Profile + resume (2 min)

- **Profile** page → fill in a few fields, let it autosave.
- **Upload Resume** page → upload a real PDF/DOCX resume.
  - *Talking point:* the resume is now parsed twice — once for raw text, once into structured facts (employment/education/skills) via one cached LLM call — this is what lets the engine answer "which university" or "years at your last job" from the actual resume instead of just the profile's summary fields.

## 3. Discover jobs (1 min)

- **Admin** page → sync a company, e.g. `https://boards.greenhouse.io/anthropic`.
  - *Talking point:* known-ATS boards (Greenhouse/Lever) resolve instantly via their public JSON API; anything else falls back to a Stagehand `extract()` pass against the company's own careers page — no per-provider integration needed either way.
- **Search Jobs** page → confirm the synced postings show up.

## 4. Queue and watch it fill (3-4 min, the main event)

- From Search, queue one job.
- **Queue** page:
  - `LogViewer` streams real Tier 0 → Tier 1 → Tier 2 log lines live over WebSocket as the browser (a real, visible Chrome window) fills the form.
  - *Talking point:* Tier 0 fills what it can match deterministically for free (name, email, resume attachment); Tier 1 makes one batched LLM call for everything else, using the profile *and* the resume facts; Tier 2 resolves custom widgets (styled dropdowns, checkboxes) via Stagehand `observe()`/`act()` — element references, not screen coordinates, which is why it survives page reflows.
  - With `SUBMIT_ENABLED=False`, the run stops right before the Submit click — the form is fully filled and visibly sitting there, unsubmitted.

## 5. Pause / resume / cancel (2 min)

- Queue a second job. Immediately click the row's **Pause** button.
  - *Talking point:* this costs nothing — the pause is checked *before* Chrome even launches, so a mistakenly-queued job never spends a browser session or an LLM call if you catch it fast enough.
- Click **Resume** — it continues normally.
- Click the **History** icon on any row (including an old one from a previous run) to show the full `run_events` timeline for that specific application — this works for completed/failed jobs too, not just the live one.

## 6. 2FA — the one human-in-the-loop step (talk through, don't fake it)

Not staged live in this demo (no test account with 2FA readily available) — describe the mechanism instead:

- If a form challenges with a one-time code, the application pauses (`needs_input`), and a **"Take Control"** button appears on the Queue page.
- Clicking it opens a live view — an actual screencast of the running browser with click/keyboard passthrough — so you type the code directly into the real page.
- Closing it and pressing Resume continues the *same* browser session, same cookies, no restart.
- *Talking point:* this is the only thing the system can't do for you by design — everything else (CAPTCHA via 2captcha, form-fill, submission) is fully automated.

---

## What NOT to demo live

- **Real submission.** `SUBMIT_ENABLED=True` sends a real application to a real employer — never flip it on during a demo unless that's explicitly the point and someone has signed off on it.
- **A live CAPTCHA/2FA solve** — costs real 2captcha balance / needs a real account with 2FA enabled; describe the mechanism (above) instead of staging it under time pressure.

## If something looks off mid-demo

Known, already-documented gaps are in [FLAGGED.md](FLAGGED.md) — worth skimming before a live demo so nothing there surprises you. The file-upload attach step in particular has a known live discrepancy (FLAGGED.md #8) — don't promise it works if asked directly.
