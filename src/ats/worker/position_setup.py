"""Position setup job: the posting text becomes the position's requirement rows (§2.4).

Imported by the worker only. The API never calls the LLM.
"""

import logging
from uuid import UUID

from psycopg_pool import ConnectionPool

from ats.db.task_queue import Job
from ats.llm.factory import get_llm_client
from ats.pipeline.requirements import extract_requirements
from ats.services.assessments import enqueue_judgements
from ats.services.requirements import POSITION_SETUP_JOB, insert_requirements
from ats.worker.registry import register

log = logging.getLogger(__name__)


@register(POSITION_SETUP_JOB)
def position_setup(job: Job, pool: ConnectionPool) -> None:
    position_id = UUID(job.payload["position_id"])
    with pool.connection() as conn:
        row = conn.execute(
            "SELECT posting_text, (SELECT count(*) FROM requirement WHERE position_id = %s) "
            "FROM job_position WHERE id = %s",
            (position_id, position_id),
        ).fetchone()
    if row is None:
        raise LookupError(f"position {position_id} does not exist")
    posting_text, existing = row
    # A redelivered job (its worker died after committing) must not pay for the call again.
    if existing:
        log.info("position %s already has requirements, nothing to do", position_id)
        return
    if not posting_text:
        raise LookupError(f"position {position_id} has no posting text yet")

    # The slow call runs outside any transaction, so no row stays locked while it waits.
    result = extract_requirements(get_llm_client(), posting_text)

    with pool.connection() as conn:
        # The lock serializes two runs of the same job: the second sees the first one's rows.
        locked = conn.execute(
            "SELECT rubric_version FROM job_position WHERE id = %s FOR UPDATE", (position_id,)
        ).fetchone()
        assert locked is not None
        already = conn.execute(
            "SELECT count(*) FROM requirement WHERE position_id = %s", (position_id,)
        ).fetchone()
        if already is not None and already[0] > 0:
            return
        insert_requirements(conn, position_id, locked[0], result.output)
        # CVs that were parsed before the requirements existed have been waiting for this.
        enqueue_judgements(conn, position_id)
    log.info(
        "position %s: %s requirements extracted (in=%s out=%s tokens, cache_hit=%s)",
        position_id,
        len(result.output.requirements),
        result.usage.input_tokens,
        result.usage.output_tokens,
        result.usage.cache_hit,
    )
