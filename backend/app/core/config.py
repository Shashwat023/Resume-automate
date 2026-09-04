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
    openrouter_model_tier2: str = "deepseek/deepseek-v3.2"
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

    resume_storage_dir: Path = BACKEND_DIR / "storage" / "resumes"

    portals_config_path: Path = BACKEND_DIR / "config" / "portals.yml"


@lru_cache
def get_settings() -> Settings:
    return Settings()
