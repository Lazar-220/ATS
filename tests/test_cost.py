"""Price per call and per assessment (phase 1.6)."""

import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import BaseModel
from tracing import MemoryTracing

from ats.llm.cache import ResponseCache
from ats.llm.fake import FakeLLMClient
from ats.llm.gemini import GeminiTransport
from ats.llm.managed import ManagedLLMClient
from ats.llm.pricing import RATES, cost_usd, rate_on, usage_cost, usage_cost_parts
from ats.llm.ratelimit import RateLimiter
from ats.llm.traced import TracedLLMClient
from ats.llm.types import LLMRequest, LLMUsage, RawCompletion

REQUEST = LLMRequest(system="rules", user="data", thinking_level="low", prompt_version="test_v1")
INTRO = date(2026, 11, 20)
MODEL = "gemini-3.6-flash"


class Answer(BaseModel):
    value: int


def _usage(input_tokens: int, output_tokens: int, cached: int = 0, hit: bool = False) -> LLMUsage:
    return LLMUsage(input_tokens, output_tokens, 0.5, hit, model=MODEL, cached_input_tokens=cached)


def test_cached_input_is_a_tenth_of_the_input_price_and_the_rest_is_full_price() -> None:
    rate = rate_on(MODEL, INTRO)
    assert rate is not None
    assert rate.cached_input_per_m == pytest.approx(0.075)
    # 600k uncached at 0.75, 400k cached at 0.075, 1M output at 3.75 per million.
    assert cost_usd(rate, 1_000_000, 1_000_000, 400_000) == pytest.approx(0.45 + 0.03 + 3.75)


def test_thinking_tokens_count_as_output_in_the_adapter_and_so_in_the_price(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    metadata = SimpleNamespace(
        prompt_token_count=1000,
        candidates_token_count=200,
        thoughts_token_count=800,
        cached_content_token_count=300,
    )
    response = SimpleNamespace(text='{"value": 1}', usage_metadata=metadata)
    transport = GeminiTransport("not-a-real-key")
    monkeypatch.setattr(
        transport,
        "_client",
        SimpleNamespace(models=SimpleNamespace(generate_content=lambda **_: response)),
    )
    completion = transport.complete("m", REQUEST, Answer)
    assert (completion.input_tokens, completion.output_tokens) == (1000, 1000)
    assert completion.cached_input_tokens == 300


def test_every_known_price_has_its_source_date_or_says_it_has_none() -> None:
    assert RATES["gemini-3.6-flash"][0].checked == date(2026, 11, 17)
    assert RATES["gemini-3.8-flash"][0].checked is None  # the plan gives no date
    assert RATES["gemini-3.5-flash-lite"][0].checked == date(2026, 11, 25)


def test_flash_lite_price_matches_the_published_rates() -> None:
    rate = rate_on("gemini-3.5-flash-lite", date(2027, 6, 1))
    assert rate is not None
    assert (rate.input_per_m, rate.output_per_m) == (0.30, 2.50)
    assert rate.cached_input_per_m == pytest.approx(0.03)
    usage = _usage(1_000_000, 1_000_000, cached=500_000)
    assert usage_cost("gemini-3.5-flash-lite", usage, date(2026, 11, 25)) == pytest.approx(
        0.15 + 0.015 + 2.50
    )


def test_the_price_follows_the_date_and_an_unknown_model_has_none() -> None:
    usage = _usage(1_000_000, 1_000_000)
    assert usage_cost(MODEL, usage, date(2026, 12, 31)) == pytest.approx(0.75 + 3.75)
    assert usage_cost(MODEL, usage, date(2027, 1, 1)) == pytest.approx(1.50 + 7.50)
    assert usage_cost("some-other-model", usage, INTRO) is None


def test_a_cache_hit_costs_nothing() -> None:
    assert usage_cost(MODEL, _usage(0, 0, hit=True), INTRO) == 0.0


def test_the_parts_add_up_to_the_total() -> None:
    parts = usage_cost_parts(MODEL, _usage(2000, 500, cached=1000), INTRO)
    assert parts is not None
    assert parts["input"] + parts["output"] == pytest.approx(parts["total"])
    assert parts["output"] == pytest.approx(500 * 3.75 / 1e6)


def test_cached_tokens_of_both_calls_of_an_invalid_output_retry_are_added(tmp_path: Path) -> None:
    class Script:
        def __init__(self) -> None:
            self.steps = [
                RawCompletion("not json", 100, 5, cached_input_tokens=40),
                RawCompletion('{"value": 1}', 100, 20, cached_input_tokens=60),
            ]

        def complete(self, model: str, request: LLMRequest, schema: type[BaseModel]):  # noqa: ANN202
            return self.steps.pop(0)

    client = ManagedLLMClient(
        Script(),
        model="m",
        limiter=RateLimiter(100),
        cache=ResponseCache(tmp_path),
    )
    usage = client.generate(REQUEST, Answer).usage
    assert (usage.input_tokens, usage.output_tokens, usage.cached_input_tokens) == (200, 25, 100)


def test_the_generation_carries_tokens_cost_and_latency() -> None:
    tracing = MemoryTracing()
    inner = FakeLLMClient(
        Answer(value=1),
        responder=None,
        usage=lambda request, output: _usage(2000, 500, cached=1000),
    )
    TracedLLMClient(inner, tracing.tracer, model=MODEL, provider="fake").generate(REQUEST, Answer)
    attributes = dict(tracing.by_name("test_v1").attributes or {})
    expected = usage_cost_parts(MODEL, _usage(2000, 500, cached=1000), date.today())
    assert expected is not None
    cost = json.loads(str(attributes["langfuse.observation.cost_details"]))
    assert cost == pytest.approx(expected)
    assert json.loads(str(attributes["langfuse.observation.usage_details"])) == {
        "input": 2000,
        "output": 500,
        "total": 2500,
    }
    assert attributes["langfuse.observation.metadata.latency_s"] == "0.5"
    assert attributes["langfuse.observation.metadata.cached_input_tokens"] == "1000"


def test_a_model_without_a_price_gets_no_cost_field() -> None:
    tracing = MemoryTracing()
    inner = FakeLLMClient(Answer(value=1))
    TracedLLMClient(inner, tracing.tracer, model="unpriced", provider="fake").generate(
        REQUEST, Answer
    )
    attributes = dict(tracing.by_name("test_v1").attributes or {})
    assert "langfuse.observation.cost_details" not in attributes
