"""LLM client behavior with a fake transport and a simulated clock: no sleeping, no network."""

from pathlib import Path

import pytest
from pydantic import BaseModel

from ats.llm.cache import ResponseCache
from ats.llm.fake import FakeLLMClient
from ats.llm.gemini import _retry_after_s  # pyright: ignore[reportPrivateUsage]
from ats.llm.managed import ManagedLLMClient
from ats.llm.ratelimit import RateLimiter
from ats.llm.types import LLMOutputInvalid, LLMRequest, RateLimitError, RawCompletion

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


def test_the_retry_delay_is_read_from_the_provider_error() -> None:
    details = {"error": {"code": 429, "details": [{"retryDelay": "34s"}]}}
    assert _retry_after_s(details) == 34.0
    assert _retry_after_s({"error": {"code": 429}}) is None
    assert _retry_after_s(None) is None
