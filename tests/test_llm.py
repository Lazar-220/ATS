"""LLM client behavior with a fake transport and a simulated clock: no sleeping, no network."""

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from google.genai import errors
from pydantic import BaseModel

from ats.llm.cache import ResponseCache
from ats.llm.fake import FakeLLMClient
from ats.llm.gemini import (  # pyright: ignore[reportPrivateUsage]
    GeminiTransport,
    _is_daily_quota,  # pyright: ignore[reportPrivateUsage]
    _retry_after_s,  # pyright: ignore[reportPrivateUsage]
)
from ats.llm.managed import ManagedLLMClient
from ats.llm.ratelimit import RateLimiter
from ats.llm.types import (
    LLMOutputInvalid,
    LLMRequest,
    RateLimitError,
    RawCompletion,
    TransientServerError,
)

REQUEST = LLMRequest(system="rules", user="data", thinking_level="low", prompt_version="test_v1")


class Answer(BaseModel):
    value: int


class SimulatedTime:
    """A clock that only moves when something sleeps."""

    def __init__(self) -> None:
        self.now = 1000.0
        self.slept: list[float] = []

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


class ScriptedTransport:
    """Plays back a list of outcomes: a RawCompletion is returned, an exception is raised."""

    def __init__(self, *script: RawCompletion | Exception) -> None:
        self._script = list(script)
        self.calls = 0

    def complete(self, model: str, request: LLMRequest, schema: type[BaseModel]) -> RawCompletion:
        self.calls += 1
        step = self._script.pop(0)
        if isinstance(step, Exception):
            raise step
        return step


def good(value: int = 1) -> RawCompletion:
    return RawCompletion(text=f'{{"value": {value}}}', input_tokens=100, output_tokens=20)


def make_client(
    transport: ScriptedTransport, tmp_path: Path, time: SimulatedTime, *, rpm: int = 5
) -> ManagedLLMClient:
    return ManagedLLMClient(
        transport,
        model="test-model",
        limiter=RateLimiter(rpm, clock=time.clock, sleep=time.sleep),
        cache=ResponseCache(tmp_path),
        clock=time.clock,
        sleep=time.sleep,
        jitter=lambda: 0.5,  # fixed, so the backoff is predictable: base * 2**n * 1.5
    )


def test_the_sixth_call_at_five_per_minute_waits_for_the_window(tmp_path: Path) -> None:
    time = SimulatedTime()
    transport = ScriptedTransport(*[good(i) for i in range(6)])
    client = make_client(transport, tmp_path, time, rpm=5)

    for i in range(5):
        # Different user text each time, so the cache cannot answer.
        client.generate(LLMRequest("rules", f"data {i}", "low", "test_v1"), Answer)
    assert time.slept == []  # five requests fit in the window

    start = time.now
    client.generate(LLMRequest("rules", "data 5", "low", "test_v1"), Answer)
    assert time.slept == [60.0]
    assert time.now == start + 60.0
    assert transport.calls == 6


def test_the_limiter_frees_a_slot_as_the_window_slides() -> None:
    time = SimulatedTime()
    limiter = RateLimiter(2, clock=time.clock, sleep=time.sleep)
    limiter.acquire()
    time.now += 30
    limiter.acquire()
    limiter.acquire()  # the first call leaves the window 30 s from now
    assert time.slept == [30.0]


def test_a_429_is_retried_with_backoff_and_then_succeeds(tmp_path: Path) -> None:
    time = SimulatedTime()
    transport = ScriptedTransport(RateLimitError("429"), RateLimitError("429"), good(7))
    client = make_client(transport, tmp_path, time)

    result = client.generate(REQUEST, Answer)

    assert result.output == Answer(value=7)
    assert transport.calls == 3
    assert time.slept == [2.0, 4.0]


def test_a_429_with_a_retry_hint_waits_as_long_as_the_provider_asks(tmp_path: Path) -> None:
    time = SimulatedTime()
    transport = ScriptedTransport(RateLimitError("429", retry_after_s=34.0), good())
    client = make_client(transport, tmp_path, time)

    client.generate(REQUEST, Answer)

    assert time.slept == [34.0]


def test_a_429_that_never_clears_is_raised_after_the_retries(tmp_path: Path) -> None:
    time = SimulatedTime()
    transport = ScriptedTransport(*[RateLimitError("429") for _ in range(5)])
    client = make_client(transport, tmp_path, time)

    with pytest.raises(RateLimitError):
        client.generate(REQUEST, Answer)
    assert transport.calls == 5  # the first try and four retries


def test_the_second_identical_call_comes_from_the_cache_without_a_request(
    tmp_path: Path,
) -> None:
    time = SimulatedTime()
    transport = ScriptedTransport(good(3))
    client = make_client(transport, tmp_path, time)

    first = client.generate(REQUEST, Answer)
    second = client.generate(REQUEST, Answer)

    assert transport.calls == 1
    assert (first.usage.cache_hit, first.usage.input_tokens, first.usage.output_tokens) == (
        False,
        100,
        20,
    )
    assert second.output == first.output
    # A cache hit is free, so it reports no tokens.
    assert (second.usage.cache_hit, second.usage.input_tokens, second.usage.output_tokens) == (
        True,
        0,
        0,
    )


def test_a_changed_parameter_is_a_cache_miss(tmp_path: Path) -> None:
    time = SimulatedTime()
    transport = ScriptedTransport(good(1), good(2), good(3))
    client = make_client(transport, tmp_path, time)

    client.generate(REQUEST, Answer)
    client.generate(LLMRequest("rules", "data", "high", "test_v1"), Answer)  # other level
    client.generate(LLMRequest("other rules", "data", "low", "test_v2"), Answer)  # other prompt

    assert transport.calls == 3


def test_invalid_output_gets_one_retry_and_both_calls_are_counted(tmp_path: Path) -> None:
    time = SimulatedTime()
    bad = RawCompletion(text="not json", input_tokens=100, output_tokens=5)
    transport = ScriptedTransport(bad, good(9))
    client = make_client(transport, tmp_path, time)

    result = client.generate(REQUEST, Answer)

    assert result.output == Answer(value=9)
    assert (result.usage.input_tokens, result.usage.output_tokens) == (200, 25)


def test_two_invalid_outputs_fail_and_nothing_is_cached(tmp_path: Path) -> None:
    time = SimulatedTime()
    bad = RawCompletion(text='{"value": "x"}', input_tokens=100, output_tokens=5)
    transport = ScriptedTransport(bad, bad, good(1))
    client = make_client(transport, tmp_path, time)

    with pytest.raises(LLMOutputInvalid):
        client.generate(REQUEST, Answer)
    assert transport.calls == 2

    # The failure left no cache entry: the next call reaches the transport again.
    assert client.generate(REQUEST, Answer).usage.cache_hit is False


def test_the_fake_client_returns_outputs_in_order_and_records_requests() -> None:
    fake = FakeLLMClient(Answer(value=1), Answer(value=2))

    assert fake.generate(REQUEST, Answer).output.value == 1
    assert fake.generate(REQUEST, Answer).output.value == 2
    assert fake.calls == [REQUEST, REQUEST]
    with pytest.raises(AssertionError):
        fake.generate(REQUEST, Answer)


def _quota_body(*quota_ids: str) -> dict[str, Any]:
    """The shape of a 429 as the Gemini API sends it: RetryInfo plus a QuotaFailure."""
    return {
        "error": {
            "code": 429,
            "status": "RESOURCE_EXHAUSTED",
            "details": [
                {
                    "@type": "type.googleapis.com/google.rpc.QuotaFailure",
                    "violations": [
                        {"quotaMetric": "generate_content_free_tier_requests", "quotaId": q}
                        for q in quota_ids
                    ],
                },
                {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "34s"},
            ],
        }
    }


DAILY_ID = "GenerateRequestsPerDayPerProjectPerModel-FreeTier"
MINUTE_ID = "GenerateRequestsPerMinutePerProjectPerModel-FreeTier"


@pytest.mark.parametrize(
    ("body", "daily"),
    [
        (_quota_body(DAILY_ID), True),
        (_quota_body(MINUTE_ID, DAILY_ID), True),  # any violation will do
        (_quota_body(MINUTE_ID), False),
        (_quota_body("SomethingNew-FreeTier"), False),  # unknown id: not daily
        ({"error": {"code": 429, "message": "quota PerDay exhausted"}}, False),  # no text match
        ({"error": {"details": "garbage"}}, False),
        ({"error": {"details": [{"@type": "google.rpc.QuotaFailure", "violations": None}]}}, False),
        ({"error": {"details": [None]}}, False),
        (None, False),
    ],
)
def test_only_a_per_day_quota_id_in_a_quota_failure_marks_a_429_daily(
    body: Any, daily: bool
) -> None:
    assert _is_daily_quota(body) is daily


def test_a_429_with_a_daily_quota_is_one_attempt_and_is_not_retried(tmp_path: Path) -> None:
    time = SimulatedTime()
    transport = ScriptedTransport(RateLimitError("429", retry_after_s=34.0, daily=True), good())
    client = make_client(transport, tmp_path, time)

    with pytest.raises(RateLimitError) as raised:
        client.generate(REQUEST, Answer)

    assert raised.value.daily
    assert transport.calls == 1
    assert time.slept == []


def test_a_per_minute_429_and_a_429_with_malformed_details_keep_their_retries(
    tmp_path: Path,
) -> None:
    time = SimulatedTime()
    transport = ScriptedTransport(
        RateLimitError("429", daily=_is_daily_quota(_quota_body(MINUTE_ID))),
        RateLimitError("429", daily=_is_daily_quota({"error": {"details": "garbage"}})),
        good(3),
    )
    client = make_client(transport, tmp_path, time)

    assert client.generate(REQUEST, Answer).output == Answer(value=3)
    assert transport.calls == 3


def test_the_gemini_adapter_flags_a_daily_429_from_the_sdk_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def failing(**_kwargs: object) -> None:
        raise errors.ClientError(429, _quota_body(DAILY_ID))

    transport = GeminiTransport("not-a-real-key")
    monkeypatch.setattr(
        transport, "_client", SimpleNamespace(models=SimpleNamespace(generate_content=failing))
    )

    with pytest.raises(RateLimitError) as raised:
        transport.complete("m", REQUEST, Answer)
    assert raised.value.daily and raised.value.retry_after_s == 34.0


def test_the_retry_delay_is_read_from_the_provider_error() -> None:
    details = {"error": {"code": 429, "details": [{"retryDelay": "34s"}]}}
    assert _retry_after_s(details) == 34.0
    assert _retry_after_s({"error": {"code": 429}}) is None
    assert _retry_after_s(None) is None


def test_a_503_is_retried_twice_with_jittered_exponential_backoff(tmp_path: Path) -> None:
    time = SimulatedTime()
    transport = ScriptedTransport(
        TransientServerError("overloaded", 503), TransientServerError("overloaded", 503), good(4)
    )
    client = make_client(transport, tmp_path, time)

    result = client.generate(REQUEST, Answer)

    assert result.output == Answer(value=4)
    assert transport.calls == 3
    assert time.slept == [3.0, 6.0]  # 2 * 1 * 1.5, then 2 * 2 * 1.5


def test_a_server_error_that_persists_is_raised_after_two_retries(tmp_path: Path) -> None:
    time = SimulatedTime()
    transport = ScriptedTransport(*[TransientServerError("down", 500) for _ in range(4)])
    client = make_client(transport, tmp_path, time)

    with pytest.raises(TransientServerError):
        client.generate(REQUEST, Answer)
    assert transport.calls == 3  # the first try and two retries, not more


def test_the_jitter_spreads_the_delay_between_one_and_two_times_the_base(tmp_path: Path) -> None:
    for jitter, expected in ((0.0, 2.0), (0.999, 3.998)):
        time = SimulatedTime()
        client = ManagedLLMClient(
            ScriptedTransport(TransientServerError("x", 504), good()),
            model="m",
            limiter=RateLimiter(5, clock=time.clock, sleep=time.sleep),
            cache=ResponseCache(tmp_path / str(jitter)),
            clock=time.clock,
            sleep=time.sleep,
            jitter=lambda jitter=jitter: jitter,
        )
        client.generate(REQUEST, Answer)
        assert time.slept == [pytest.approx(expected)]


def test_server_error_retries_go_through_the_rate_limiter(tmp_path: Path) -> None:
    """Five requests per minute: a 503 retry is a request and must wait like any other."""
    time = SimulatedTime()
    transport = ScriptedTransport(*[TransientServerError("busy", 503) for _ in range(2)], good())
    client = make_client(transport, tmp_path, time, rpm=2)

    client.generate(REQUEST, Answer)

    # try 1 at t=0, retry 1 after 3 s (slot 2), retry 2 needs a free slot: waits for the first
    # request to leave the window at t=60, which is longer than its own 6 s backoff.
    assert transport.calls == 3
    assert time.now - 1000.0 >= 60.0


def test_429_and_server_error_retries_have_separate_budgets(tmp_path: Path) -> None:
    time = SimulatedTime()
    transport = ScriptedTransport(
        RateLimitError("429"),
        TransientServerError("503", 503),
        RateLimitError("429"),
        TransientServerError("503", 503),
        good(),
    )
    client = make_client(transport, tmp_path, time, rpm=10)

    assert client.generate(REQUEST, Answer).output == Answer(value=1)
    assert transport.calls == 5


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        (429, RateLimitError),
        (500, TransientServerError),
        (503, TransientServerError),
        (504, TransientServerError),
        (400, errors.ClientError),  # a bad request is not retried
        (502, errors.ServerError),  # only 500, 503 and 504 are
    ],
)
def test_the_gemini_adapter_maps_the_sdk_errors_by_status_code(
    code: int, expected: type[Exception], monkeypatch: pytest.MonkeyPatch
) -> None:
    sdk_error: Any = (errors.ClientError if code < 500 else errors.ServerError)(
        code, {"error": {"code": code, "message": "x", "status": "X"}}
    )

    def failing(**_kwargs: object) -> None:
        raise sdk_error

    transport = GeminiTransport("not-a-real-key")
    monkeypatch.setattr(
        transport, "_client", SimpleNamespace(models=SimpleNamespace(generate_content=failing))
    )

    with pytest.raises(expected):
        transport.complete("m", REQUEST, Answer)
