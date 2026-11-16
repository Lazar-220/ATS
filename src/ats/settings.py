from functools import lru_cache

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


@lru_cache
def get_settings() -> Settings:
    return Settings()
