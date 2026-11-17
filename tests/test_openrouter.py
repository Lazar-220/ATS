"""The OpenRouter fallback, against recorded-shape responses. Nothing here touches the network."""

import json
from datetime import date
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import BaseModel, SecretStr

from ats.eval.fallback import DEV_SMOKE_LABEL, FallbackLLMClient, create_eval_llm_client
from ats.eval.golden import DEFAULT_ROOT, GoldSet, load_golden
from ats.eval.harness import format_report, plan_run, run_eval
from ats.eval.stages import load_contacts
from ats.eval.stub import StubJudge
from ats.llm.cache import ResponseCache, cache_key
from ats.llm.factory import create_llm_client
from ats.llm.managed import ManagedLLMClient
from ats.llm.openrouter import DAILY_CAP, OpenRouterTransport
from ats.llm.ratelimit import RateLimiter
from ats.llm.types import (
    LLMOutputInvalid,
    LLMRequest,
    LLMResult,
    LLMUsage,
    RateLimitError,
)
from ats.pipeline.parsing import ParsedCV
from ats.settings import Settings

REQUEST = LLMRequest(
    system="rules", user="<cv>data</cv>", thinking_level="minimal", prompt_version="t"
)
MODEL = "google/gemma-4-31b-it:free"
TODAY = date(2026, 11, 17)


class Answer(BaseModel):
    value: int


def key_body(used: int, limit: int = 50) -> dict[str, Any]:
    """The shape of GET /api/v1/key, as documented."""
    return {
        "data": {
            "is_free_tier": True,
            "free_model_daily_requests": {
                "used": used,
                "limit": limit,
                "remaining": limit - used,
            },
        }
    }


def completion(text: str) -> dict[str, Any]:
    return {
        "model": MODEL,
        "choices": [{"message": {"role": "assistant", "content": text}}],
        "usage": {"prompt_tokens": 120, "completion_tokens": 9},
    }


RATE_LIMITED = {
    "error": {
        "code": 429,
        "message": "Rate limit exceeded",
        "metadata": {"error_type": "rate_limit_exceeded"},
    }
}


class Server:
    """A scripted OpenRouter: answers /key from `used` and /chat/completions from a queue."""

    def __init__(self, *replies: httpx.Response, used: int | None = 0) -> None:
        self.replies = list(replies)
        self.used = used
        self.posts: list[dict[str, Any]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/key"):
            if self.used is None:
                return httpx.Response(500)
            return httpx.Response(200, json=key_body(self.used))
        self.posts.append(json.loads(request.content))
        return self.replies.pop(0)


def transport(server: Server, tmp_path: Path) -> OpenRouterTransport:
    http = httpx.Client(
        base_url="https://openrouter.test/api/v1", transport=httpx.MockTransport(server)
    )
    return OpenRouterTransport("sk-test", state_dir=tmp_path, http=http, today=lambda: TODAY)


def client(server: Server, tmp_path: Path) -> ManagedLLMClient:
    return ManagedLLMClient(
        transport(server, tmp_path),
        model=MODEL,
        limiter=RateLimiter(1000),
        cache=ResponseCache(tmp_path / "cache"),
        sleep=lambda _s: None,
    )


def ok(text: str = '{"value": 4}') -> httpx.Response:
    return httpx.Response(200, json=completion(text))


def test_a_request_is_json_mode_with_the_schema_in_the_system_text(tmp_path: Path) -> None:
    server = Server(ok())
    result = client(server, tmp_path).generate(REQUEST, Answer)

    body = server.posts[0]
    assert body["model"] == MODEL
    assert body["response_format"] == {"type": "json_object"}
    assert body["messages"][0]["role"] == "system" and "rules" in body["messages"][0]["content"]
    assert '"value"' in body["messages"][0]["content"]  # the schema
    assert body["messages"][1] == {"role": "user", "content": "<cv>data</cv>"}
    assert result.output == Answer(value=4)
    assert (result.usage.input_tokens, result.usage.output_tokens) == (120, 9)
    assert result.usage.model == MODEL


def test_invalid_output_gets_one_retry_and_then_fails(tmp_path: Path) -> None:
    server = Server(ok("not json"), ok('{"value": "x"}'))
    with pytest.raises(LLMOutputInvalid):
        client(server, tmp_path).generate(REQUEST, Answer)
    assert len(server.posts) == 2

    recovered = Server(ok("not json"), ok())
    assert client(recovered, tmp_path / "b").generate(REQUEST, Answer).output.value == 4


def test_the_cache_key_names_the_model() -> None:
    assert cache_key("gemini-3.6-flash", REQUEST, Answer) != cache_key(MODEL, REQUEST, Answer)


def test_a_429_when_the_key_says_the_daily_requests_are_spent_is_daily(tmp_path: Path) -> None:
    server = Server(httpx.Response(429, json=RATE_LIMITED), used=0)
    original = server.__call__

    def after_the_call(request: httpx.Request) -> httpx.Response:
        response = original(request)
        if request.url.path.endswith("/chat/completions"):
            server.used = DAILY_CAP  # the counter the key reports now says: spent
        return response

    http = httpx.Client(
        base_url="https://openrouter.test/api/v1", transport=httpx.MockTransport(after_the_call)
    )
    t = OpenRouterTransport("k", state_dir=tmp_path, http=http, today=lambda: TODAY)
    with pytest.raises(RateLimitError) as raised:
        t.complete(MODEL, REQUEST, Answer)
    assert raised.value.daily


def test_a_429_with_requests_left_is_retried_like_a_per_minute_limit(tmp_path: Path) -> None:
    server = Server(httpx.Response(429, json=RATE_LIMITED), ok(), used=3)
    result = client(server, tmp_path).generate(REQUEST, Answer)
    assert result.output.value == 4
    assert len(server.posts) == 2


def test_a_429_inside_a_200_body_is_read_as_a_429(tmp_path: Path) -> None:
    server = Server(httpx.Response(200, json=RATE_LIMITED), ok(), used=3)
    assert client(server, tmp_path).generate(REQUEST, Answer).output.value == 4


def test_the_hard_cap_of_50_applies_even_if_the_account_allows_more(tmp_path: Path) -> None:
    server = Server(ok())
    server.used = 50  # /key reports used 50 of a limit of 1000
    http = httpx.Client(
        base_url="https://openrouter.test/api/v1",
        transport=httpx.MockTransport(
            lambda r: (
                httpx.Response(200, json=key_body(50, limit=1000))
                if r.url.path.endswith("/key")
                else ok()
            )
        ),
    )
    t = OpenRouterTransport("k", state_dir=tmp_path, http=http, today=lambda: TODAY)
    with pytest.raises(RateLimitError) as raised:
        t.complete(MODEL, REQUEST, Answer)
    assert raised.value.daily


def test_without_the_key_endpoint_a_local_counter_caps_calls_across_runs(tmp_path: Path) -> None:
    first = Server(*[ok() for _ in range(DAILY_CAP)], used=None)
    t1 = transport(first, tmp_path)
    for _ in range(DAILY_CAP):
        t1.complete(MODEL, REQUEST, Answer)

    # A new process on the same day: the count was written to disk.
    second = Server(ok(), used=None)
    with pytest.raises(RateLimitError) as raised:
        transport(second, tmp_path).complete(MODEL, REQUEST, Answer)
    assert raised.value.daily
    assert second.posts == []


def test_the_local_counter_starts_over_on_a_new_day(tmp_path: Path) -> None:
    t = transport(Server(ok(), used=None), tmp_path)
    t.complete(MODEL, REQUEST, Answer)
    assert t.remaining_today() == DAILY_CAP - 1
    tomorrow = OpenRouterTransport(
        "k",
        state_dir=tmp_path,
        http=transport(Server(used=None), tmp_path)._http,
        today=lambda: date(2026, 11, 18),
    )
    assert tomorrow.remaining_today() == DAILY_CAP


# --- the fallback client ---------------------------------------------------------------------


class Scripted:
    def __init__(self, model: str, *steps: Exception | int) -> None:
        self.model = model
        self.steps = list(steps)
        self.calls = 0

    def generate[T: BaseModel](self, request: LLMRequest, schema: type[T]) -> LLMResult[T]:
        self.calls += 1
        step = self.steps.pop(0)
        if isinstance(step, Exception):
            raise step
        usage = LLMUsage(1, 1, 0.0, False, model=self.model)
        return LLMResult(output=schema.model_validate({"value": step}), usage=usage)


def test_a_daily_quota_on_the_primary_switches_to_the_fallback_for_the_rest_of_the_run() -> None:
    primary = Scripted("gemini", 1, RateLimitError("daily", daily=True))
    fallback = Scripted("gemma", 2, 3, 4)
    both = FallbackLLMClient(primary, fallback)

    results = [both.generate(REQUEST, Answer) for _ in range(4)]

    assert [r.usage.model for r in results] == ["gemini", "gemma", "gemma", "gemma"]
    assert primary.calls == 2  # never asked again after the daily quota


def test_a_per_minute_429_on_the_primary_does_not_switch() -> None:
    both = FallbackLLMClient(Scripted("gemini", RateLimitError("minute")), Scripted("gemma"))
    with pytest.raises(RateLimitError):
        both.generate(REQUEST, Answer)
    assert not both.switched


def test_a_daily_quota_on_the_fallback_too_stops_the_run() -> None:
    both = FallbackLLMClient(
        Scripted("gemini", RateLimitError("d", daily=True)),
        Scripted("gemma", RateLimitError("d2", daily=True)),
    )
    with pytest.raises(RateLimitError) as raised:
        both.generate(REQUEST, Answer)
    assert raised.value.daily and "d2" in str(raised.value)


# --- opt-in, and unreachable from the API and the worker -------------------------------------


def settings(**extra: Any) -> Settings:
    return Settings(_env_file=None, llm_api_key=SecretStr("g"), **extra)  # pyright: ignore[reportCallIssue]


def test_the_production_client_never_has_a_fallback_even_when_one_is_configured() -> None:
    configured = settings(llm_fallback="openrouter", openrouter_api_key=SecretStr("o"))
    assert isinstance(create_llm_client(configured), ManagedLLMClient)


def test_api_and_worker_code_never_mention_the_fallback() -> None:
    src = Path(__file__).resolve().parents[1] / "src" / "ats"
    files = [*(src / "api").rglob("*.py"), *(src / "worker").rglob("*.py")]
    files += [*(src / "services").rglob("*.py"), src / "llm" / "factory.py"]
    for path in files:
        text = path.read_text(encoding="utf-8").lower()
        assert "openrouter" not in text and "ats.eval" not in text, path


def test_the_eval_client_is_the_plain_client_unless_the_fallback_is_asked_for() -> None:
    assert isinstance(create_eval_llm_client(settings(), ""), ManagedLLMClient)
    asked = settings(openrouter_api_key=SecretStr("o"))
    assert isinstance(create_eval_llm_client(asked, "openrouter"), FallbackLLMClient)


def test_asking_for_the_fallback_without_a_key_is_an_error() -> None:
    with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"):
        create_eval_llm_client(settings(), "openrouter")


# --- labelling -------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def golden() -> GoldSet:
    return load_golden()


class AnsweredBy:
    """A client whose answers come from a named model."""

    def __init__(self, models: list[str]) -> None:
        self.models = models
        self.n = 0

    def generate[T: BaseModel](self, request: LLMRequest, schema: type[T]) -> LLMResult[T]:
        model = self.models[min(self.n, len(self.models) - 1)]
        self.n += 1
        empty = ParsedCV(
            is_cv=True,
            suspected_injection=False,
            experience=[],
            education=[],
            skills=[],
            certificates=[],
            languages=[],
            projects=[],
        )
        return LLMResult(
            output=schema.model_validate(empty.model_dump()),
            usage=LLMUsage(1, 1, 0.0, False, model),
        )


def _run(golden: GoldSet, models: list[str]) -> str:
    result = run_eval(
        golden,
        variant="A",
        split="dev",
        limit=None,
        stages=["parsing"],
        judge=StubJudge(golden),
        client=AnsweredBy(models),
        model="gemini-3.6-flash",
        min_chars_per_page=100,
        contacts=load_contacts(DEFAULT_ROOT),
        fallback_model=MODEL,
    )
    assert result.parsing is not None
    return (
        format_report(result)
        + "\n"
        + (result.label or "")
        + "|"
        + ",".join(sorted({r.model for r in result.parsing.records}))
    )


def test_a_run_that_used_the_fallback_is_labelled_dev_smoke_with_both_model_names(
    golden: GoldSet,
) -> None:
    text = _run(golden, ["gemini-3.6-flash"] * 5 + [MODEL])
    assert f"LABEL: {DEV_SMOKE_LABEL}" in text
    assert "Primary gemini-3.6-flash, fallback google/gemma-4-31b-it:free" in text
    assert text.endswith(f"{DEV_SMOKE_LABEL}|gemini-3.6-flash,{MODEL}")


def test_a_run_that_stayed_on_the_primary_has_no_label(golden: GoldSet) -> None:
    text = _run(golden, ["gemini-3.6-flash"])
    assert "LABEL:" not in text


def test_the_dry_run_with_the_fallback_says_so(golden: GoldSet, tmp_path: Path) -> None:
    plan = plan_run(
        golden,
        ["parsing"],
        model="gemini-3.6-flash",
        cache=ResponseCache(tmp_path),
        min_chars_per_page=100,
        fallback_model=MODEL,
    )
    text = plan.describe()
    assert "Fallback enabled (opt-in)" in text and MODEL in text and DEV_SMOKE_LABEL in text
    assert (
        "Fallback"
        not in plan_run(
            golden, ["parsing"], model="m", cache=ResponseCache(tmp_path), min_chars_per_page=100
        ).describe()
    )
