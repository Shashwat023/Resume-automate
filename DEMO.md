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

## 6. Human-in-the-loop — 2FA and stuck fields (talk through; only stage it if you have a real challenge handy)

- If a form challenges with a one-time code, or the cascade hits a field it genuinely can't resolve, the application pauses (`needs_input`) and a **"Take Control"** button appears — both on the Current Job card and on that job's own row in the queue table.
- Clicking it opens a live view — an actual screencast of the running browser with click/keyboard passthrough — so you type the code (or fill the stuck field) directly in the real page.
- The panel itself has **Resume** and **Cancel** buttons: continue on the *same* browser session, same cookies, no restart — or abandon that application outright.
- *Talking point:* this started as 2FA-only and deliberately grew into the universal fallback. Rather than chase every new widget shape as it's discovered, anything the automation can't resolve gets handed to a human for that one field — the agent never fails and stops on its own while a human fix is still possible.
- *Talking point:* the 2FA wait also polls the page and **auto-resumes on its own** if the challenge clears (say you answered the code on your phone), with a 10-minute ceiling so an unanswered one fails cleanly instead of stranding the queue.

This has been exercised for real — a live email-OTP challenge on a Figma application — so it's a genuine mechanism, not a mockup. Staging it live still depends on hitting a challenge on demand, which you can't count on.

---

## What NOT to demo live

- **Real submission.** `SUBMIT_ENABLED=True` sends a real application to a real employer — never flip it on during a demo unless that's explicitly the point and someone has signed off on it.
- **A live CAPTCHA/2FA solve** — costs real 2captcha balance / needs a real account with 2FA enabled; describe the mechanism (above) instead of staging it under time pressure.

## If something looks off mid-demo

Known, already-documented gaps are in [FLAGGED.md](FLAGGED.md) — worth skimming before a live demo so nothing there surprises you. Two specifically worth knowing before someone asks:

- **A typeahead/autocomplete field** (Greenhouse's "Location (City)") resolves unreliably. If it happens mid-demo, that's the human-escalation fallback doing its job — the run pauses and asks you to fill that one field rather than failing. Frame it that way rather than as a surprise.
- **Risk-based reCAPTCHA Enterprise** can reject a validly-solved token on session risk score alone, independent of anything the code does. Don't promise CAPTCHA "always works" — it works, and a hardened site can still refuse the result.

Real submissions cost ~$0.10–0.15 in LLM credits per completed form fill, if anyone asks about running economics.
