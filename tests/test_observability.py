import json
import logging
from typing import Any

import pytest
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
from pydantic import BaseModel
from tracing import MemoryTracing

from ats.llm.fake import FakeLLMClient
from ats.llm.traced import TracedLLMClient
from ats.llm.types import LLMRequest
from ats.observability import LangfuseTracer, NoopTracer, create_tracer
from ats.settings import Settings


class Answer(BaseModel):
    text: str


REQUEST = LLMRequest(
    system="rules", user="<cv>masked text</cv>", thinking_level="low", prompt_version="judge_v1"
)


def _settings(**values: Any) -> Settings:
    return Settings(_env_file=None, **values)  # type: ignore[call-arg]


def test_tracing_is_off_by_default_and_the_sdk_is_not_touched() -> None:
    tracer = create_tracer(_settings())
    assert isinstance(tracer, NoopTracer) and not tracer.enabled
    with tracer.generation("x", model="m", input="i") as generation:
        generation.update(output="o")
        assert generation.trace_id is None


def test_enabled_without_keys_stays_off_and_says_so(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING):
        tracer = create_tracer(_settings(langfuse_enabled=True))
    assert isinstance(tracer, NoopTracer)
    assert "keys are not set" in caplog.text


def test_a_call_becomes_a_generation_with_prompt_output_tokens_and_cache_flag() -> None:
    tracing = MemoryTracing()
    client = TracedLLMClient(
        FakeLLMClient(Answer(text="ok")), tracing.tracer, model="m1", provider="fake"
    )
    result = client.generate(REQUEST, Answer)
    assert result.output.text == "ok"
    span = tracing.by_name("judge_v1")
    attributes = dict(span.attributes or {})
    assert attributes["langfuse.observation.type"] == "generation"
    assert attributes["langfuse.observation.model.name"] == "m1"
    messages = json.loads(str(attributes["langfuse.observation.input"]))
    assert messages == [
        {"role": "system", "content": "rules"},
        {"role": "user", "content": "<cv>masked text</cv>"},
    ]
    assert json.loads(str(attributes["langfuse.observation.output"])) == {"text": "ok"}
    usage = json.loads(str(attributes["langfuse.observation.usage_details"]))
    assert usage == {"input": 0, "output": 0, "total": 0}
    assert attributes["langfuse.observation.metadata.prompt_version"] == '"judge_v1"'
    assert attributes["langfuse.observation.metadata.cache_hit"] == "false"
    assert attributes["langfuse.observation.metadata.provider"] == '"fake"'
    assert json.loads(str(attributes["langfuse.observation.model.parameters"])) == {
        "thinking_level": "low"
    }


def test_a_failing_call_is_marked_with_the_error_class_only_and_still_raises() -> None:
    tracing = MemoryTracing()

    class Boom(Exception):
        pass

    def responder(request: LLMRequest, schema: type[BaseModel]) -> BaseModel:
        raise Boom("secret detail from the request")

    client = TracedLLMClient(
        FakeLLMClient(responder=responder), tracing.tracer, model="m", provider="fake"
    )
    with pytest.raises(Boom):
        client.generate(REQUEST, Answer)
    attributes = dict(tracing.by_name("judge_v1").attributes or {})
    assert attributes["langfuse.observation.level"] == "ERROR"
    assert attributes["langfuse.observation.status_message"] == "Boom"
    assert "secret detail" not in tracing.everything_sent()


class _BrokenManager:
    """An SDK observation whose every step raises."""

    def __enter__(self) -> "_BrokenManager":
        raise RuntimeError("langfuse is down")

    def __exit__(self, *exc: object) -> None:
        raise RuntimeError("never reached")


class _BrokenOnUpdate:
    trace_id = "t"

    def update(self, **fields: Any) -> None:
        raise RuntimeError("update failed")


class _BrokenOnExit:
    def __enter__(self) -> _BrokenOnUpdate:
        return _BrokenOnUpdate()

    def __exit__(self, *exc: object) -> None:
        raise RuntimeError("end failed")


class _StubClient:
    def __init__(self, manager: Any) -> None:
        self._manager = manager

    def start_as_current_observation(self, **kwargs: Any) -> Any:
        return self._manager

    def flush(self) -> None:
        raise RuntimeError("flush failed")


@pytest.mark.parametrize("manager", [_BrokenManager(), _BrokenOnExit()])
def test_a_tracing_failure_never_fails_the_call(manager: Any) -> None:
    tracer = LangfuseTracer(_StubClient(manager))
    client = TracedLLMClient(FakeLLMClient(Answer(text="ok")), tracer, model="m", provider="p")
    assert client.generate(REQUEST, Answer).output.text == "ok"
    with tracer.span("step") as step:
        step.update(output="x")
    tracer.flush()  # raises inside the stub, not here


def test_an_exception_in_the_body_passes_through_a_guarded_span() -> None:
    tracer = LangfuseTracer(_StubClient(_BrokenOnExit()))
    with pytest.raises(ValueError, match="mine"), tracer.span("step"):
        raise ValueError("mine")


class _RaisingExporter(SpanExporter):
    def export(self, spans: Any) -> SpanExportResult:
        raise ConnectionError("langfuse unreachable")

    def shutdown(self) -> None:
        return None


def test_an_exporter_that_cannot_reach_langfuse_does_not_fail_the_caller() -> None:
    import uuid

    from langfuse import Langfuse

    client = Langfuse(
        public_key=f"pk-test-{uuid.uuid4().hex}",
        secret_key="sk-test",
        base_url="http://127.0.0.1:9",
        span_exporter=_RaisingExporter(),
    )
    tracer = LangfuseTracer(client)
    traced = TracedLLMClient(FakeLLMClient(Answer(text="ok")), tracer, model="m", provider="p")
    assert traced.generate(REQUEST, Answer).output.text == "ok"
    tracer.flush()


def test_nesting_follows_the_with_blocks() -> None:
    tracing = MemoryTracing()
    with tracing.tracer.trace("assessment"), tracing.tracer.span("judge"):
        pass
    spans: list[ReadableSpan] = tracing.spans()
    root = next(span for span in spans if span.name == "assessment")
    child = next(span for span in spans if span.name == "judge")
    assert child.parent is not None and root.context is not None
    assert child.parent.span_id == root.context.span_id
    assert child.context is not None and child.context.trace_id == root.context.trace_id


def test_the_factory_wraps_the_client_only_when_tracing_is_on() -> None:
    from ats.llm.factory import create_llm_client
    from ats.observability import set_tracer

    settings = _settings(llm_provider="fake")
    try:
        set_tracer(NoopTracer())
        assert not isinstance(create_llm_client(settings), TracedLLMClient)
        tracing = MemoryTracing()
        set_tracer(tracing.tracer)
        client = create_llm_client(settings)
        assert isinstance(client, TracedLLMClient)
    finally:
        set_tracer(None)
