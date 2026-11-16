from functools import lru_cache

from ats.llm.cache import ResponseCache
from ats.llm.gemini import GeminiTransport
from ats.llm.managed import ManagedLLMClient
from ats.llm.ratelimit import RateLimiter
from ats.llm.types import LLMClient
from ats.settings import Settings, get_settings


def create_llm_client(settings: Settings) -> LLMClient:
    # Compose passes an unset variable as an empty string, so empty counts as missing.
    api_key = settings.llm_api_key.get_secret_value() if settings.llm_api_key else ""
    if not api_key:
        raise RuntimeError("LLM_API_KEY is not set; put it in .env")
    return ManagedLLMClient(
        GeminiTransport(api_key),
        model=settings.llm_model,
        limiter=RateLimiter(settings.llm_rpm),
        cache=ResponseCache(settings.llm_cache_dir),
    )


@lru_cache
def get_llm_client() -> LLMClient:
    """One client per process, so one rate limiter: the quota is shared by every caller.

    Tests replace this function (or its call site) with a `FakeLLMClient`.
    """
    return create_llm_client(get_settings())
