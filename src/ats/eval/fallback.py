"""Opt-in fallback for eval runs: Gemini first, OpenRouter after a daily quota.

Lives in the eval package on purpose: the API and the worker build their client with
`ats.llm.factory.create_llm_client`, which has no fallback, so a production process cannot switch
models silently. Results of a run that used the fallback are not baselines.
"""

import logging
from pathlib import Path

from pydantic import BaseModel

from ats.llm.cache import ResponseCache
from ats.llm.factory import create_llm_client
from ats.llm.managed import ManagedLLMClient
from ats.llm.openrouter import RPM, OpenRouterTransport
from ats.llm.ratelimit import RateLimiter
from ats.llm.types import LLMClient, LLMRequest, LLMResult, RateLimitError
from ats.settings import Settings

log = logging.getLogger(__name__)

DEV_SMOKE_LABEL = "dev-smoke, non-baseline"


class FallbackLLMClient:
    """Uses `primary` until it raises a daily-quota `RateLimitError`, then `fallback` for the rest
    of the run. A daily quota on the fallback is not caught: the run stops and reports.
    """

    def __init__(self, primary: LLMClient, fallback: LLMClient) -> None:
        self._primary = primary
        self._fallback = fallback
        self.switched = False

    def generate[T: BaseModel](self, request: LLMRequest, schema: type[T]) -> LLMResult[T]:
        if not self.switched:
            try:
                return self._primary.generate(request, schema)
            except RateLimitError as exc:
                if not exc.daily:
                    raise
                self.switched = True
                log.warning("primary model's daily quota is spent; switching to the fallback")
        return self._fallback.generate(request, schema)


def create_eval_llm_client(settings: Settings, fallback: str) -> LLMClient:
    """The primary client, wrapped with the OpenRouter fallback when `fallback` is "openrouter"."""
    primary = create_llm_client(settings)
    if not fallback:
        return primary
    key = settings.openrouter_api_key.get_secret_value() if settings.openrouter_api_key else ""
    if not key:
        raise RuntimeError("the OpenRouter fallback needs OPENROUTER_API_KEY; put it in .env")
    state_dir = Path(settings.llm_cache_dir)
    secondary = ManagedLLMClient(
        OpenRouterTransport(key, state_dir=state_dir),
        model=settings.openrouter_model,
        limiter=RateLimiter(RPM),
        cache=ResponseCache(state_dir),
    )
    return FallbackLLMClient(primary, secondary)
