"""One trace per assessment, and nothing personal in anything sent to tracing (phase 1.6)."""

import json
from datetime import date
from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient
from pdfs import make_pdf
from psycopg.rows import DictRow
from psycopg_pool import ConnectionPool
from tracing import MemoryTracing

from ats.llm.factory import create_llm_client
from ats.llm.pricing import rate_on
from ats.observability import LangfuseTracer, set_tracer
from ats.settings import Settings, get_settings
from ats.worker import ingest, judge, position_setup
from integration.test_ingest import upload, wait_until_settled

pytestmark = pytest.mark.integration

POSTING = make_pdf(
    "Senior Python developer, Belgrade\nRequirements\nExperience with Python and PostgreSQL\n"
    "Experience leading a team of engineers\n" + "Zahtevi za poziciju razvojnog inzenjera. " * 4
)
CV = make_pdf(
    "Marko Petrovic\nmarko.petrovic@example.com\n+381 64 123 4567\n"
    "Address: Knez Mihailova 5, Belgrade\n"
    "Backend work\nSenior Python developer at Acme Bank, 2019-2023\n"
    "Built PostgreSQL services and led a team of engineers\n" * 2
)
# Name, email, phone and address of the candidate, in the forms a leak could take.
PERSONAL = [
    "Marko",
    "Petrovic",
    "marko.petrovic",
    "example.com",
    "381 64",
    "123 4567",
    "Knez Mihailova",
]
STEPS = {"extraction", "masking", "parsing", "judge", "quote_check", "score"}


def _use_fake_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    client = create_llm_client(Settings(llm_provider="fake"))
    for module in (position_setup, ingest, judge):
        monkeypatch.setattr(module, "get_llm_client", lambda: client)


def test_one_trace_per_assessment_with_every_step_and_nothing_personal(
    client: TestClient,
    worker: ConnectionPool,
    conn: psycopg.Connection[DictRow],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tracing = MemoryTracing()
    set_tracer(tracing.tracer)
    try:
        _use_fake_provider(monkeypatch)
        accepted = upload(client, POSTING, [CV])
        wait_until_settled(conn)
        spans = tracing.spans()
        sent = tracing.everything_sent()
    finally:
        set_tracer(None)

    assert client.get(f"/rankings/{accepted['request_id']}").json()["status"] == "done"
    row = conn.execute("SELECT id, trace, cost_usd FROM assessment").fetchone()
    assert row is not None
    trace_id = row["trace"]["trace_id"]

    in_trace = [span for span in spans if f"{span.context.trace_id:032x}" == trace_id]  # type: ignore[union-attr]
    assert {span.name for span in in_trace} >= STEPS | {"assessment"}
    roots = [span for span in in_trace if span.parent is None]
    assert [span.name for span in roots] == ["assessment"]
    # The judge call is a generation inside the trace, under the judge span.
    generation = next(
        span
        for span in in_trace
        if span.attributes and span.attributes.get("langfuse.observation.type") == "generation"
    )
    judge_span = next(span for span in in_trace if span.name == "judge")
    assert generation.parent is not None and judge_span.context is not None
    assert generation.parent.span_id == judge_span.context.span_id

    # The CV's own ingest has a trace of its own; the assessment's stand-in spans link to it.
    ingest_id = conn.execute("SELECT parsed_json FROM document WHERE kind = 'cv'").fetchone()
    assert ingest_id is not None
    ingest_trace = ingest_id["parsed_json"]["ingest"]["trace_id"]
    assert ingest_trace != trace_id
    assert {s.name for s in spans if f"{s.context.trace_id:032x}" == ingest_trace} >= {  # type: ignore[union-attr]
        "document_ingest",
        "extraction",
        "masking",
        "parsing",
    }

    # The CV body is in the prompts (masked), so the search below can find a leak.
    assert "Acme Bank" in sent
    for secret in PERSONAL:
        assert secret not in sent, f"{secret!r} reached the tracing exporter"
    assert row["trace"]["steps_s"].keys() >= {"judge", "quote_check", "score"}
    # Cost is stored on the assessment (the judge call) and the CV's parse cost sits beside it.
    # The demo client reports invented token counts, so the numbers are not real prices.
    if rate_on(get_settings().llm_model, date.today()) is not None:
        assert row["cost_usd"] is not None and row["cost_usd"] > 0
        assert row["trace"]["cv_parse_cost_usd"] > 0


class _DownClient:
    """A Langfuse SDK client for which everything fails."""

    def start_as_current_observation(self, **kwargs: Any) -> Any:
        raise ConnectionError("langfuse is down")

    def flush(self) -> None:
        raise ConnectionError("langfuse is down")


def test_a_broken_tracer_never_fails_a_job(
    client: TestClient,
    worker: ConnectionPool,
    conn: psycopg.Connection[DictRow],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_tracer(LangfuseTracer(_DownClient()))
    try:
        _use_fake_provider(monkeypatch)
        accepted = upload(client, POSTING, [CV])
        wait_until_settled(conn)
    finally:
        set_tracer(None)
    assert client.get(f"/rankings/{accepted['request_id']}").json()["status"] == "done"
    row = conn.execute("SELECT status, trace FROM assessment").fetchone()
    assert row is not None and row["status"] == "done"
    assert "trace_id" not in row["trace"]  # no tracing, so no id, and the job still finished
    assert json.dumps(row["trace"])  # still plain JSON
