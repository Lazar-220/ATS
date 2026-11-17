"""The `LLMClient` that every real call goes through: cache, rate limit, 429 retry, validation."""

import logging
import random
import time
from collections.abc import Callable

from pydantic import BaseModel, ValidationError

from ats.llm.cache import ResponseCache, cache_key
from ats.llm.ratelimit import RateLimiter
from ats.llm.types import (
    LLMOutputInvalid,
    LLMRequest,
    LLMResult,
    LLMUsage,
    RateLimitError,
    RawCompletion,
    TransientServerError,
    Transport,
)

log = logging.getLogger(__name__)

MAX_BACKOFF_S = 60.0


class ManagedLLMClient:
    def __init__(
        self,
        transport: Transport,
        *,
        model: str,
        limiter: RateLimiter,
        cache: ResponseCache,
        max_429_retries: int = 4,
        max_server_retries: int = 2,
        backoff_base_s: float = 2.0,
        jitter: Callable[[], float] = random.random,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._transport = transport
        self._model = model
        self._limiter = limiter
        self._cache = cache
        self._max_429_retries = max_429_retries
        self._max_server_retries = max_server_retries
        self._jitter = jitter
        self._backoff_base_s = backoff_base_s
        self._clock = clock
        self._sleep = sleep

    def generate[T: BaseModel](self, request: LLMRequest, schema: type[T]) -> LLMResult[T]:
        started = self._clock()
        key = cache_key(self._model, request, schema)

        cached = self._cache.get(key)
        if cached is not None:
            output = _parse(cached.text, schema)
            if output is not None:
                return self._result(request, output, 0, 0, started, cache_hit=True)
            # An entry that no longer fits the schema is a miss; the new answer overwrites it.

        input_tokens = output_tokens = 0
        # §4.5: invalid output gets one retry call, then the caller fails. Both calls are billed.
        for _attempt in range(2):
            completion = self._complete(request, schema)
            input_tokens += completion.input_tokens
            output_tokens += completion.output_tokens
            output = _parse(completion.text, schema)
            if output is not None:
                self._cache.put(key, completion)  # only validated answers are cached
                return self._result(
                    request, output, input_tokens, output_tokens, started, cache_hit=False
                )
            log.warning(
                "model output did not match %s (%s)", schema.__name__, request.prompt_version
            )
        raise LLMOutputInvalid(f"the model's output did not match {schema.__name__} after a retry")

    def _complete(self, request: LLMRequest, schema: type[BaseModel]) -> RawCompletion:
        rate_limited = server_failed = 0
        while True:
            self._limiter.acquire()  # a retry is a request too and counts against the quota
            try:
                return self._transport.complete(self._model, request, schema)
            except RateLimitError as exc:
                # A spent daily quota does not come back within any retry delay.
                if exc.daily or rate_limited >= self._max_429_retries:
                    raise
                delay = exc.retry_after_s
                if delay is None:
                    delay = min(self._backoff_base_s * 2**rate_limited, MAX_BACKOFF_S)
                rate_limited += 1
                log.warning("429 from the provider, retry %s in %.1f s", rate_limited, delay)
            except TransientServerError as exc:
                if server_failed >= self._max_server_retries:
                    raise
                # Jitter keeps workers that failed together from retrying together.
                delay = min(
                    self._backoff_base_s * 2**server_failed * (1 + self._jitter()), MAX_BACKOFF_S
                )
                server_failed += 1
                log.warning(
                    "%s from the provider, retry %s in %.1f s",
                    exc.status_code,
                    server_failed,
                    delay,
                )
            self._sleep(delay)

    def _result[T: BaseModel](
        self,
        request: LLMRequest,
        output: T,
        input_tokens: int,
        output_tokens: int,
        started: float,
        *,
        cache_hit: bool,
    ) -> LLMResult[T]:
        usage = LLMUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_s=self._clock() - started,
            cache_hit=cache_hit,
            model=self._model,
        )
        log.info(
            "llm call model=%s prompt=%s thinking=%s in=%s out=%s latency=%.2fs cache_hit=%s",
            self._model,
            request.prompt_version,
            request.thinking_level,
            usage.input_tokens,
            usage.output_tokens,
            usage.latency_s,
            usage.cache_hit,
        )
        return LLMResult(output=output, usage=usage)


def _parse[T: BaseModel](text: str, schema: type[T]) -> T | None:
    try:
        return schema.model_validate_json(text)
    except ValidationError:
        return None
