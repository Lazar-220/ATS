"""Tracing through Langfuse, off by default and never a reason for a job to fail (§6.3, phase 1.6).

Everything that talks to Langfuse sits behind `Tracer`. With `LANGFUSE_ENABLED` false (the
default) `get_tracer()` returns a tracer that does nothing, and the `langfuse` package is not
even imported. With it true, every call into the SDK is guarded: a Langfuse that is down,
misconfigured or slow shows up as a log line, never as an exception in the caller.

What goes into a trace is whatever the caller passes. The rule for callers (§2.4, §4.4): only
text the LLM itself was given (masked text), counts, durations and ids. Never the raw CV text,
the candidate's name, email, phone or address, or a file name; `tests/test_observability.py`
runs the pipeline over a CV with known contact data and checks every exported span for it.
"""

import logging
from collections.abc import Generator
from contextlib import AbstractContextManager, contextmanager
from typing import Any, Protocol

from ats.settings import Settings, get_settings

log = logging.getLogger(__name__)


class Observation(Protocol):
    """What a caller may do with an open span or generation."""

    @property
    def trace_id(self) -> str | None: ...

    def update(self, **fields: Any) -> None: ...


class Tracer(Protocol):
    enabled: bool

    def trace(
        self, name: str, *, input: Any = None, metadata: dict[str, Any] | None = None
    ) -> AbstractContextManager[Observation]:
        """The root of a new trace (one assessment, one CV ingest)."""
        ...

    def span(
        self, name: str, *, input: Any = None, metadata: dict[str, Any] | None = None
    ) -> AbstractContextManager[Observation]:
        """A step. A child of the current span, or a root when there is none."""
        ...

    def generation(
        self,
        name: str,
        *,
        model: str,
        input: Any,
        model_parameters: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AbstractContextManager[Observation]:
        """One LLM call."""
        ...

    def flush(self) -> None: ...


class _NoObservation:
    trace_id: str | None = None

    def update(self, **fields: Any) -> None:
        return None


_NO_OBSERVATION = _NoObservation()


class NoopTracer:
    enabled = False

    @contextmanager
    def trace(
        self, name: str, *, input: Any = None, metadata: dict[str, Any] | None = None
    ) -> Generator[Observation]:
        yield _NO_OBSERVATION

    @contextmanager
    def span(
        self, name: str, *, input: Any = None, metadata: dict[str, Any] | None = None
    ) -> Generator[Observation]:
        yield _NO_OBSERVATION

    @contextmanager
    def generation(
        self,
        name: str,
        *,
        model: str,
        input: Any,
        model_parameters: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Generator[Observation]:
        yield _NO_OBSERVATION

    def flush(self) -> None:
        return None


class _GuardedObservation:
    def __init__(self, inner: Any) -> None:
        self._inner = inner

    @property
    def trace_id(self) -> str | None:
        try:
            value = self._inner.trace_id
        except Exception:
            return None
        return value if isinstance(value, str) else None

    def update(self, **fields: Any) -> None:
        try:
            self._inner.update(**fields)
        except Exception:
            log.warning("langfuse: could not update an observation", exc_info=True)


@contextmanager
def _guarded(open_observation: Any) -> Generator[Observation]:
    """Open an SDK observation; whatever the SDK does wrong stays in the log.

    An exception raised by the body is the caller's and passes through untouched.
    """
    try:
        manager = open_observation()
        observation = manager.__enter__()
    except Exception:
        log.warning("langfuse: could not open an observation", exc_info=True)
        yield _NO_OBSERVATION
        return
    guarded = _GuardedObservation(observation)
    try:
        yield guarded
    except BaseException as exc:
        # The exception is not handed to the SDK: it would record the message and the stack
        # trace on the span, and either can carry request text. The class name is enough.
        guarded.update(level="ERROR", status_message=type(exc).__name__)
        raise
    finally:
        try:
            manager.__exit__(None, None, None)
        except Exception:
            log.warning("langfuse: could not close an observation", exc_info=True)


class LangfuseTracer:
    enabled = True

    def __init__(self, client: Any) -> None:
        self._client = client

    @property
    def client(self) -> Any:
        """The SDK client, for the eval's dataset calls (`ats.eval.langfuse_export`)."""
        return self._client

    def trace(
        self, name: str, *, input: Any = None, metadata: dict[str, Any] | None = None
    ) -> AbstractContextManager[Observation]:
        # A new trace is simply a span with no parent: the SDK starts one when no span is current.
        return self.span(name, input=input, metadata=metadata)

    def span(
        self, name: str, *, input: Any = None, metadata: dict[str, Any] | None = None
    ) -> AbstractContextManager[Observation]:
        return _guarded(
            lambda: self._client.start_as_current_observation(
                name=name, as_type="span", input=input, metadata=metadata
            )
        )

    def generation(
        self,
        name: str,
        *,
        model: str,
        input: Any,
        model_parameters: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AbstractContextManager[Observation]:
        return _guarded(
            lambda: self._client.start_as_current_observation(
                name=name,
                as_type="generation",
                model=model,
                input=input,
                model_parameters=model_parameters,
                metadata=metadata,
            )
        )

    def flush(self) -> None:
        try:
            self._client.flush()
        except Exception:
            log.warning("langfuse: flush failed", exc_info=True)


def create_tracer(settings: Settings) -> Tracer:
    if not settings.langfuse_enabled:
        return NoopTracer()
    secret = settings.langfuse_secret_key.get_secret_value() if settings.langfuse_secret_key else ""
    if not settings.langfuse_public_key or not secret:
        log.warning("LANGFUSE_ENABLED is true but the Langfuse keys are not set: tracing is off")
        return NoopTracer()
    try:
        from langfuse import Langfuse

        client = Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=secret,
            base_url=settings.langfuse_host,
        )
    except Exception:
        log.warning("langfuse: the client could not be created, tracing is off", exc_info=True)
        return NoopTracer()
    return LangfuseTracer(client)


_tracer: Tracer | None = None


def get_tracer() -> Tracer:
    """One tracer per process, built from the settings on first use."""
    global _tracer
    if _tracer is None:
        _tracer = create_tracer(get_settings())
    return _tracer


def set_tracer(tracer: Tracer | None) -> None:
    """Install `tracer` for this process (tests); None makes the next `get_tracer` rebuild it."""
    global _tracer
    _tracer = tracer
