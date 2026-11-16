from functools import lru_cache
from pathlib import Path

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
    llm_api_key: SecretStr | None = None
    # The free tier allows 5 requests per minute (§6.1); raise it on the paid tier.
    llm_rpm: int = 5
    llm_cache_dir: Path = Path("data/llm_cache")


@lru_cache
def get_settings() -> Settings:
    return Settings()
