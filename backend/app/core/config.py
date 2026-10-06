from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = f"sqlite+aiosqlite:///{BACKEND_DIR / 'app.db'}"

    frontend_origin: str = "http://localhost:5173"

    openrouter_api_key: str | None = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    # tier1: our own direct OpenRouter call with our own simple schema
    # (openrouter_client.py) — meta-llama/llama-3.3-70b-instruct, explicit
    # user direction. ~$0.71/M tokens (same price prompt/completion).
    #
    # tier2: qwen/qwen3.6-27b, explicit user direction (kept after one
    # unilateral revert to Claude that was wrong — see below).
    # KNOWN RISK, not yet resolved: tier2 is routed through STAGEHAND's own
    # internal RPC/callback protocol (llm_client.py), which does a strict
    # validate -> dump -> re-validate round-trip on the model's structured
    # output (see test_llm_client_shape_conformance.py). One live run on
    # qwen/qwen3.6-27b produced `"structuredContent": Invalid input`
    # mid-run, cascading into "RPC client is closed" and killing the
    # application — see FLAGGED.md #13. If the crash recurs, that's the
    # next thing to actually fix (e.g. constrain/retry the structured-
    # output call specifically inside llm_client.py), not silently swap
    # the model without asking.
    openrouter_model_tier1: str = "meta-llama/llama-3.3-70b-instruct"
    # Switched from qwen/qwen3.6-27b after live testing (FLAGGED.md #16/#17):
    # Qwen's action-generation was the suspected source of repeated
    # `-32602 Invalid mouse button` CDP errors and slow (~15-80s, some
    # >120s) observe() calls — both a latency and a reliability problem for
    # this tier's job (deciding real clicks against custom widgets).
    # deepseek/deepseek-v3.2 chosen per user direction: better reasoning
    # than Qwen for this kind of agentic action-generation, at roughly
    # half Qwen's per-token cost ($0.27/$0.40 vs $0.60/$3.60 per M
    # in/out, OpenRouter pricing as of 2026-09-03). Do not swap this model
    # again without asking first — confirmed standing constraint.
    openrouter_model_tier2: str = "qwen/qwen3.5-122b-a10b"
    # Scraper-only retry policy. A company's extract-based sync is tried up
    # to `scraper_primary_attempts` times with the primary Tier-2 model,
    # stopping as soon as one run stores `scraper_fallback_min_jobs` jobs;
    # if every attempt comes back short (or crashes), it's re-run ONCE with
    # this fallback model — never more. Picked
    # from a 7-model benchmark on 2026-10-04 (gpt-5.6-luna primary: 96% of
    # jobs found at ~1/7 Gemini's cost; Gemini 3.8 Flash found 99.7% and
    # recovered the one site Luna missed). Empty string disables it.
    openrouter_model_tier2_fallback: str = "google/gemini-3.8-flash"
    # Cap on one Tier-2/Stagehand reply. Largest seen in the benchmark was
    # ~3k tokens (a 30-job page); 16k leaves room for ~200 postings.
    openrouter_tier2_max_tokens: int = 16000
    # Live-caught 2026-10-05: with hidden "thinking" on, glm-4.6 and Qwen3.5
    # spent 100+s (one Qwen reply: 6.9k tokens vs Gemini's ~1k) on a page
    # assessment, tripping the 120s extract() cap. Scraping needs no reasoning.
    openrouter_disable_reasoning: bool = True
    scraper_primary_attempts: int = 3
    scraper_fallback_min_jobs: int = 1
    # A 0-job run is only retried if it crashed or the visited pages showed
    # at least this many links to individual postings (evidence the model
    # missed them). Below it the site is treated as having no listings and
    # is not re-run — retrying an empty site only burns tokens.
    scraper_retry_min_job_links: int = 3
    # Day 4 scope correction: no longer gates whether a field gets filled
    # (Tier 1 always answers) — gates only whether an answer is cached into
    # the answers library. See tier1_map.py::map_fields.
    tier1_confidence_threshold: float = 0.5

    twocaptcha_api_key: str | None = None
    # Deviation flagged in FLAGGED.md: the Day-4 scope says CAPTCHA never
    # involves a human, but the browser is already open if 2captcha fails
    # twice — escalating to needs_input beats failing the application
    # outright. Easy to flip to False if the senior wants a hard fail instead.
    captcha_failure_escalates: bool = True

    # The single biggest latent freeze in the pipeline before this existed:
    # 2captcha's SDK defaults are recaptchaTimeout=600 and defaultTimeout=120,
    # and we call it via `asyncio.to_thread`, which is UNCANCELLABLE — so a
    # slow reCAPTCHA solve blocked the run for up to 10 minutes per attempt,
    # twice (service.py retries once) = ~20 minutes of a completely
    # unresponsive application that looks identical to a hang from the UI.
    # Bounded explicitly here instead of inheriting the SDK's defaults.
    captcha_solve_timeout_seconds: int = 180
    captcha_polling_interval_seconds: int = 5

    # Root cause of the live "Please complete the reCAPTCHA" rejection
    # despite a genuinely 2captcha-solved token: with no proxy configured,
    # 2captcha's worker solves the challenge from ITS OWN datacenter IP —
    # Google mints the token bound to that IP — then our browser submits
    # it from a completely different IP. Google's Enterprise risk
    # assessment sees a token/submission IP mismatch and rejects
    # regardless of token validity. Fix: route BOTH the browser's page
    # navigation (chrome_launcher.py) and the 2captcha solve call
    # (solver.py) through the SAME proxy, so the IPs match. Standard
    # proxy URL: "http://user:pass@host:port" (or "https://"/"socks5://").
    # None (default) = no regression, everything behaves as before.
    captcha_proxy_url: str | None = None

    # Dev-safety gate: with this False (the default), the full cascade runs
    # and stops one click short of Submit — every live test against a real
    # ATS form otherwise files a real job application at a real employer.
    # Flip to True only deliberately (demo, or the mock ATS form in tests).
    submit_enabled: bool = False

    # MUST be a "Chrome for Testing" build, not consumer Chrome Stable.
    # Consumer Chrome does not support the CDP `Extensions.loadUnpacked` method
    # that Stagehand v4's local-browser mode depends on to bootstrap its
    # companion extension (confirmed empirically, Day-1 spike). Installed via
    # `python -m playwright install chromium`, which downloads a CfT build to
    # %LOCALAPPDATA%\ms-playwright on Windows (~/.cache/ms-playwright on Linux/Mac).
    chrome_executable_path: str = str(
        Path.home()
        / "AppData"
        / "Local"
        / "ms-playwright"
        / "chromium-1234"
        / "chrome-win64"
        / "chrome.exe"
    )
    chrome_profiles_dir: Path = BACKEND_DIR / ".chrome-profiles"
    chrome_debug_port_base: int = 9222

    # Real, live-caught issue: a real submission was rejected with "Please
    # complete the reCAPTCHA" despite a genuinely 2captcha-solved token —
    # manual testing of the SAME form showed no captcha challenge at all,
    # meaning Google's risk-based (not puzzle-based) reCAPTCHA Enterprise
    # scored the automated session too low to accept ANY token. A fresh
    # "Chrome for Testing" profile with `navigator.webdriver=true` and no
    # browsing history is a large part of that signal. Opt-in fallback:
    # launch real consumer Chrome (a normal Chrome flag, `--load-extension`,
    # works on any build — unlike the CDP `Extensions.loadUnpacked` method
    # above, which consumer Chrome doesn't support) with a PERSISTENT
    # profile that accumulates real history/cookies across runs, then
    # connect Stagehand to it instead of having it launch+bootstrap a
    # throwaway "Chrome for Testing" instance. Off by default — this is a
    # real architecture change, not proven yet against the actual form.
    use_real_chrome: bool = False
    real_chrome_executable_path: str | None = None  # None -> auto-detect
    real_chrome_profiles_dir: Path = BACKEND_DIR / ".real-chrome-profiles"

    # Bound on the scraper's extract() pagination loop (sync_service.py) —
    # per user direction: a careers page/job board isn't limited to one
    # page's worth of postings, so the fallback now follows "next
    # page"/"load more" controls and re-extracts. Capped so a page whose
    # pagination control we can't recognize correctly (or a genuinely
    # infinite feed) can't turn into an unbounded LLM-spend loop — each
    # extra page costs one extract() call (~$0.005-0.015, see FLAGGED.md).
    scraper_max_pages: int = 15

    # Bound on the "category 3" fan-out (sync_service.py): a careers portal
    # that splits its openings across several parallel tracks — Cargill's
    # Professional / Production / Students sections, each behind its own
    # "Search Jobs" button — must have ALL of them visited, not just the
    # first (which is what the old single drill-down hop did). Each section
    # is a separate listing page costing at least one extract() call, plus
    # its own pagination, so the fan-out is capped: a page whose "sections"
    # we mis-identify (a nav menu, a footer, a list of office locations)
    # can't turn into an unbounded crawl. 6 covers every real multi-track
    # portal seen so far with headroom.
    scraper_max_sections: int = 6

    # Deterministic "follow the job links" exploration (sync_service.py
    # _explore_job_entry_links), used when the normal flow saved 0 jobs.
    # Live-caught on 4liberty.com: home -> Careers -> "View All Job Openings"
    # -> listings (in an iframe) is three hops, and the model-picked
    # one-hop flow stopped at /careers. Depth counts pages expanded from the
    # landing page; the page budget caps LLM extract calls (one per page).
    scraper_max_explore_depth: int = 3
    scraper_max_explore_pages: int = 8

    # How long a tracked company (config/portals.yml, seeded into
    # TrackedCompany) stays "already covered" after a sync attempt before
    # the bulk "sync all tracked companies" job (see
    # services/scraper/bulk_sync_service.py) will attempt it again — per
    # explicit user direction, matching a daily-click habit: a company
    # synced this morning isn't re-hit again today, only once ~20h have
    # passed. Applies regardless of whether that attempt succeeded or
    # failed — a company that errors every time still only costs one
    # attempt per window, not one per bulk-sync loop iteration, which
    # would otherwise burn the whole run's budget retrying the same
    # broken site forever.
    tracked_company_resync_hours: int = 20

    resume_storage_dir: Path = BACKEND_DIR / "storage" / "resumes"

    portals_config_path: Path = BACKEND_DIR / "config" / "portals.yml"


@lru_cache
def get_settings() -> Settings:
    return Settings()
