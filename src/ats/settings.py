from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://ats:ats@localhost:5432/ats"
    db_pool_max_size: int = 5
    # A job in `running` longer than this is assumed to belong to a dead worker.
    queue_visibility_timeout_s: float = 300
    worker_poll_interval_s: float = 1.0
    # Below this average of non-space characters per page a PDF is treated as a scan (§4.2).
    min_chars_per_page: int = 100
    upload_dir: Path = Path("data/uploads")
    max_upload_mb: int = 10
    # §6.1 names gemini-3.8-flash, which returned persistent 503s (docs/PROGRESS.md, 2026-11-17).
    llm_model: str = "gemini-3.6-flash"
    # "fake" answers with canned demo data and calls no model: for trying the interface only.
    llm_provider: Literal["gemini", "fake"] = "gemini"
    llm_api_key: SecretStr | None = None
    # The free tier allows 5 requests per minute (§6.1); raise it on the paid tier.
    llm_rpm: int = 5
    llm_cache_dir: Path = Path("data/llm_cache")
    # A judge quote passes the check at this rapidfuzz score or above (§3.2, §6.3); calibrate on
    # the golden set.
    quote_fuzzy_threshold: int = 90
    # Eval runs only (`ats.eval`): switch to OpenRouter after a Gemini daily quota. The API and
    # the worker never read these.
    llm_fallback: Literal["", "openrouter"] = ""
    openrouter_api_key: SecretStr | None = None
    openrouter_model: str = "google/gemma-4-31b-it:free"
    # Tracing is off unless this is true; the app, the worker and the eval run the same without
    # Langfuse (§6.3). The keys are the project's API keys from the Langfuse UI.
    langfuse_enabled: bool = False
    langfuse_host: str = "http://localhost:3000"
    langfuse_public_key: str = ""
    langfuse_secret_key: SecretStr | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
