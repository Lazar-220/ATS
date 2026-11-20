"""Judge and re-judge jobs: one assessment per candidate-position pair (§2.4 steps 6 to 8).

Both job types run `assess`. An assessment that is `done` at the position's current
`rubric_version` is reused with no LLM call, which is what makes submitting the same CV and
posting twice free. A re-judge after an HR edit is the same function: the version moved on, so
the assessment is stale and is judged again, in place (one row per pair, its verdicts replaced).

Imported by the worker only. The API never calls the LLM.
"""

import logging
import time
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from ats.db.task_queue import Job
from ats.llm.factory import get_llm_client
from ats.llm.pricing import usage_cost
from ats.llm.types import LLMClient
from ats.observability import Observation, Tracer, get_tracer
from ats.pipeline.context import ContextRequirement, build_context
from ats.pipeline.judge import PROMPT_VERSION, THINKING_LEVEL, judge
from ats.pipeline.masking import Span
from ats.pipeline.quotes import check_quote
from ats.pipeline.score import ScoredRequirement, compute_score
from ats.services.assessments import JUDGE_JOB
from ats.services.hr_answers import REJUDGE_JOB
from ats.settings import Settings, get_settings
from ats.worker.registry import register

log = logging.getLogger(__name__)


class RubricChanged(Exception):
    """HR edited the requirements while the judge was running; the answer is for an old list."""


def _load(pool: ConnectionPool, candidate_id: UUID, position_id: UUID) -> dict[str, Any] | None:
    """Everything the judge needs, read in one short transaction. None: nothing to do."""
    with pool.connection() as conn:
        position = conn.execute(
            "SELECT rubric_version FROM job_position WHERE id = %s", (position_id,)
        ).fetchone()
        if position is None:
            raise LookupError(f"position {position_id} does not exist")
        version: int = position[0]
        done = conn.execute(
            "SELECT 1 FROM assessment WHERE candidate_id = %s AND position_id = %s "
            "AND rubric_version = %s AND status = 'done'",
            (candidate_id, position_id, version),
        ).fetchone()
        if done is not None:
            return None
        requirements = conn.execute(
            "SELECT id, parent_id, text, kind, weight, min_months FROM requirement "
            "WHERE position_id = %s AND rubric_version = %s ORDER BY ord, id",
            (position_id, version),
        ).fetchall()
        if not requirements:
            raise LookupError(f"position {position_id} has no requirements at version {version}")
        document = conn.execute(
            "SELECT masked_text, mask_spans, parsed_json FROM document "
            "WHERE candidate_id = %s AND status = 'parsed'",
            (candidate_id,),
        ).fetchone()
        if document is None or document[0] is None or document[2] is None:
            raise LookupError(f"candidate {candidate_id} has no parsed CV")
    return {
        "version": version,
        "requirements": requirements,
        "masked_text": document[0],
        "spans": [Span.model_validate(span) for span in cast(list[Any], document[1] or [])],
        "parsed_json": document[2],
    }


def assess(
    pool: ConnectionPool,
    client: LLMClient,
    candidate_id: UUID,
    position_id: UUID,
    attempt: int = 1,
) -> bool:
    """Judge one pair and store the result. False when a current assessment already existed."""
    settings = get_settings()
    loaded = _load(pool, candidate_id, position_id)
    if loaded is None:
        log.info(
            "candidate %s, position %s: already assessed, no LLM call", candidate_id, position_id
        )
        return False
    tracer = get_tracer()
    with tracer.trace(
        "assessment",
        metadata={
            "candidate_id": str(candidate_id),
            "position_id": str(position_id),
            "rubric_version": loaded["version"],
            "attempt": attempt,
        },
    ) as root:
        _record_ingest_steps(tracer, loaded["parsed_json"])
        _judge_and_store(pool, client, settings, loaded, candidate_id, position_id, attempt, root)
    return True


def _record_ingest_steps(tracer: Tracer, parsed_json: dict[str, Any]) -> None:
    """Show the steps that ran at ingest inside this assessment's trace.

    Extraction, masking and parsing happen once per CV, before any position is known, so their
    real spans are in the ingest trace. These stand-ins carry the measured duration and the
    link, so one trace still lists every step (the call's generation is in the ingest trace).
    """
    ingest = cast(dict[str, Any], parsed_json.get("ingest") or {})
    steps = cast(dict[str, float | None], ingest.get("steps_s") or {})
    for name, seconds in steps.items():
        with tracer.span(
            name,
            metadata={
                "recorded_at_ingest": True,
                "duration_s": None if seconds is None else round(seconds, 4),
                "ingest_trace_id": ingest.get("trace_id"),
            },
        ):
            pass


def _judge_and_store(
    pool: ConnectionPool,
    client: LLMClient,
    settings: Settings,
    loaded: dict[str, Any],
    candidate_id: UUID,
    position_id: UUID,
    attempt: int,
    root: Observation,
) -> None:
    tracer = get_tracer()
    version: int = loaded["version"]
    rows = loaded["requirements"]
    # The model sees labels 1..n; the labels map back to row ids here and nowhere else.
    label_of = {row[0]: index for index, row in enumerate(rows, start=1)}
    pack = build_context(
        loaded["masked_text"],
        loaded["parsed_json"],
        [
            ContextRequirement(
                label=label_of[row[0]],
                text=row[2],
                kind=row[3],
                weight=int(row[4]),
                min_months=row[5],
                parent_label=label_of.get(row[1]),
            )
            for row in rows
        ],
    )

    # The slow call runs outside any transaction (the CV text is already read).
    with tracer.span("judge", input={"requirements": len(rows)}) as span:
        judged = judge(client, pack, attempt=attempt)
        span.update(
            output={
                "calls": judged.calls,
                "cache_hit": judged.usage.cache_hit,
                "latency_s": round(judged.usage.latency_s, 3),
            }
        )

    with tracer.span("quote_check") as span:
        started = time.perf_counter()
        checks = {
            label: check_quote(
                verdict.verdict,
                verdict.quote,
                loaded["masked_text"],
                loaded["spans"],
                settings.quote_fuzzy_threshold,
            )
            for label, verdict in judged.verdicts.items()
        }
        quote_check_s = time.perf_counter() - started
        span.update(
            output={
                "duration_s": round(quote_check_s, 4),
                "checked": len(checks),
                "flagged": sum(1 for check in checks.values() if check.flags),
            }
        )
    with tracer.span("score") as span:
        started = time.perf_counter()
        score = compute_score(
            [
                ScoredRequirement(label_of[row[0]], label_of.get(row[1]), row[3], float(row[4]))
                for row in rows
            ],
            {label: verdict.verdict for label, verdict in judged.verdicts.items()},
        )
        score_s = time.perf_counter() - started
        span.update(
            output={
                "duration_s": round(score_s, 4),
                "score": score.score,
                "mandatory_failed": score.mandatory_failed,
            }
        )
    cost = usage_cost(settings.llm_model, judged.usage, datetime.now(UTC).date())
    ingest = cast(dict[str, Any], loaded["parsed_json"].get("ingest") or {})
    parse = cast(dict[str, Any], ingest.get("parse") or {})
    trace = {
        "prompt_version": PROMPT_VERSION,
        "thinking_level": THINKING_LEVEL,
        "model": settings.llm_model,
        "rubric_version": version,
        "as_of": pack.as_of,
        "judge_calls": judged.calls,
        "cache_hit": judged.usage.cache_hit,
        "cached_input_tokens": judged.usage.cached_input_tokens,
        # `cost_usd` on the row is this judge call; the CV's parse call is paid once per CV, so
        # it is shown beside it and not added to each pair (cost per CV is the sum).
        "cv_parse_cost_usd": parse.get("cost_usd"),
        "latency_s": round(judged.usage.latency_s, 3),
        "quote_fuzzy_threshold": settings.quote_fuzzy_threshold,
        # Code-only steps timed here; extraction, masking and parsing are in the CV's own row.
        "steps_s": {
            "judge": round(judged.usage.latency_s, 4),
            "quote_check": round(quote_check_s, 4),
            "score": round(score_s, 4),
        },
    }
    if root.trace_id is not None:
        trace["trace_id"] = root.trace_id

    with pool.connection() as conn:
        # A share lock: an edit (which takes the row for update) waits for this write or
        # is seen by the check below, so a stale result is never stored as current.
        current = conn.execute(
            "SELECT rubric_version FROM job_position WHERE id = %s FOR SHARE", (position_id,)
        ).fetchone()
        if current is None or current[0] != version:
            raise RubricChanged(f"position {position_id} moved past version {version}")
        assessment = conn.execute(
            "INSERT INTO assessment (position_id, candidate_id, rubric_version, status, score, "
            "mandatory_failed, cost_usd, input_tokens, output_tokens, trace) "
            "VALUES (%s, %s, %s, 'done', %s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (candidate_id, position_id) DO UPDATE SET "
            "rubric_version = EXCLUDED.rubric_version, status = 'done', score = EXCLUDED.score, "
            "mandatory_failed = EXCLUDED.mandatory_failed, cost_usd = EXCLUDED.cost_usd, "
            "input_tokens = EXCLUDED.input_tokens, output_tokens = EXCLUDED.output_tokens, "
            "trace = EXCLUDED.trace, updated_at = now() RETURNING id",
            (
                position_id,
                candidate_id,
                version,
                score.score,
                score.mandatory_failed,
                cost,
                judged.usage.input_tokens,
                judged.usage.output_tokens,
                Jsonb(trace),
            ),
        ).fetchone()
        assert assessment is not None
        # A re-judge replaces the verdicts of the old rubric version.
        conn.execute("DELETE FROM verdict WHERE assessment_id = %s", (assessment[0],))
        for row in rows:
            label = label_of[row[0]]
            verdict = judged.verdicts[label]
            check = checks[label]
            flags = [{"code": code, "detail": check.detail or ""} for code in check.flags]
            conn.execute(
                "INSERT INTO verdict (assessment_id, requirement_id, verdict, quote, char_start, "
                "char_end, rationale, flags) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    assessment[0],
                    row[0],
                    verdict.verdict,
                    verdict.quote if verdict.verdict != "not_met" else None,
                    check.char_start,
                    check.char_end,
                    verdict.rationale,
                    Jsonb(flags),
                ),
            )
    log.info(
        "assessment of candidate %s for position %s: score %s, %s judge call(s), "
        "in=%s out=%s tokens, cache_hit=%s",
        candidate_id,
        position_id,
        score.score,
        judged.calls,
        judged.usage.input_tokens,
        judged.usage.output_tokens,
        judged.usage.cache_hit,
    )


def _mark_failed(pool: ConnectionPool, candidate_id: UUID, position_id: UUID, error: str) -> None:
    """The queue gave up: say so on the assessment, where HR looks."""
    with pool.connection() as conn:
        version = conn.execute(
            "SELECT rubric_version FROM job_position WHERE id = %s", (position_id,)
        ).fetchone()
        if version is None:
            return
        conn.execute(
            "INSERT INTO assessment (position_id, candidate_id, rubric_version, status, trace) "
            "VALUES (%s, %s, %s, 'failed', %s) "
            "ON CONFLICT (candidate_id, position_id) DO UPDATE SET status = 'failed', "
            "trace = jsonb_build_object('error', %s::text), updated_at = now()",
            (position_id, candidate_id, version[0], Jsonb({"error": error}), error),
        )


def _run(job: Job, pool: ConnectionPool, candidate_id: UUID, position_id: UUID) -> None:
    try:
        assess(pool, get_llm_client(), candidate_id, position_id, job.attempts)
    except Exception as exc:
        if job.attempts >= job.max_attempts:
            _mark_failed(pool, candidate_id, position_id, f"{type(exc).__name__}: {exc}")
        raise


@register(JUDGE_JOB)
def judge_job(job: Job, pool: ConnectionPool) -> None:
    _run(job, pool, UUID(job.payload["candidate_id"]), UUID(job.payload["position_id"]))


@register(REJUDGE_JOB)
def rejudge_job(job: Job, pool: ConnectionPool) -> None:
    with pool.connection() as conn:
        row = conn.execute(
            "SELECT candidate_id, position_id FROM assessment WHERE id = %s",
            (UUID(job.payload["assessment_id"]),),
        ).fetchone()
    if row is None:
        log.warning("assessment %s no longer exists", job.payload["assessment_id"])
        return
    _run(job, pool, row[0], row[1])
