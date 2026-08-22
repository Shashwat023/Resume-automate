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
    # tier1: high-volume, structured JSON field mapping, cost-sensitive.
    # tier2: harder reasoning about custom widgets, called far less often.
    # Both verified present on OpenRouter's /api/v1/models (419 models) as
    # of Day 3. openai/gpt-4o-mini also verified valid, kept as a cheap
    # fallback reference in comments in case these need reverting.
    openrouter_model_tier1: str = "anthropic/claude-haiku-4.5"
    openrouter_model_tier2: str = "anthropic/claude-sonnet-4.5"
    tier1_confidence_threshold: float = 0.6

    twocaptcha_api_key: str | None = None

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

    resume_storage_dir: Path = BACKEND_DIR / "storage" / "resumes"

    portals_config_path: Path = BACKEND_DIR / "config" / "portals.yml"


@lru_cache
def get_settings() -> Settings:
    return Settings()
