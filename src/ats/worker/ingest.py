"""Ingest job: PDF file to clean text, language and script, and for a CV on to masked text,
parsed items and tenure, all in the `document` row.

One job, resumed by document state: `uploaded` is extracted, an `extracted` CV is masked and
parsed, anything later is skipped. A redelivered job therefore never repeats a finished step,
and the LLM call is cached on top of that.

Imported by the worker only; the API never loads PyMuPDF or the language models.
"""

import logging
from datetime import date
from uuid import UUID

from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from ats.db.task_queue import Job
from ats.llm.factory import get_llm_client
from ats.pipeline.extract import PdfRejected, extract_text
from ats.pipeline.facts import build_facts
from ats.pipeline.language import detect_language, detect_script
from ats.pipeline.masking import mask_text
from ats.pipeline.parsing import parse_cv
from ats.services.rankings import INGEST_JOB
from ats.services.requirements import enqueue_setup
from ats.settings import get_settings
from ats.worker.registry import register

log = logging.getLogger(__name__)

FAILED_MESSAGE = "Processing failed unexpectedly. Upload the file again to retry."


def _ingest(pool: ConnectionPool, document_id: UUID) -> None:
    settings = get_settings()
    with pool.connection() as conn:
        row = conn.execute(
            "SELECT kind, sha256, storage_path, status FROM document WHERE id = %s",
            (document_id,),
        ).fetchone()
    if row is None:
        raise LookupError(f"document {document_id} does not exist")
    kind, sha256, storage_path, status = row
    # A redelivered job (its worker died after committing) must not redo or undo the work.
    if status == "extracted" and kind == "cv":
        _parse(pool, document_id)
        return
    if status != "uploaded":
        log.info("document %s is already %s, nothing to ingest", document_id, status)
        return

    pdf = (settings.upload_dir / storage_path).read_bytes()
    try:
        extracted = extract_text(pdf, min_chars_per_page=settings.min_chars_per_page)
    except PdfRejected as exc:
        # A rejection is an outcome, not an error: the job completes and the document says why.
        with pool.connection() as conn:
            conn.execute(
                "UPDATE document SET status = 'rejected', status_message = %s WHERE id = %s",
                (str(exc), document_id),
            )
        log.info("document %s rejected: %s", document_id, exc)
        return

    # `raw_text` keeps the original script; normalization is applied only where text is compared.
    lang = detect_language(extracted.text)
    script = detect_script(extracted.text)
    with pool.connection() as conn:
        conn.execute(
            "UPDATE document SET status = 'extracted', status_message = NULL, raw_text = %s, "
            "lang = %s, script = %s WHERE id = %s",
            (extracted.text, lang, script, document_id),
        )
        if kind == "posting":
            position = conn.execute(
                "UPDATE job_position SET posting_text = %s WHERE source_sha256 = %s RETURNING id",
                (extracted.text, sha256),
            ).fetchone()
            if position is not None:
                # In this transaction, so the text and the job exist together. A posting is
                # ingested once per sha256, which is why an existing position never gets here
                # again; the dedup key is the second guard against a re-run.
                enqueue_setup(conn, position[0])
    log.info(
        "document %s extracted: %s pages, lang=%s, script=%s",
        document_id,
        extracted.page_count,
        lang,
        script,
    )
    if kind == "cv":
        _parse(pool, document_id)


def _parse(pool: ConnectionPool, document_id: UUID) -> None:
    """Mask, parse, locate and measure one extracted CV; store the result in one transaction."""
    with pool.connection() as conn:
        row = conn.execute("SELECT raw_text FROM document WHERE id = %s", (document_id,)).fetchone()
    assert row is not None and row[0] is not None
    masked = mask_text(row[0])

    # The slow call runs outside any transaction, and sees only masked text (§2.4).
    result = parse_cv(get_llm_client(), masked.masked_text)
    # Production passes today's date; only the eval passes a fixed one.
    facts = build_facts(result.output, masked.masked_text, masked.spans, date.today())

    with pool.connection() as conn:
        locked = conn.execute(
            "SELECT status FROM document WHERE id = %s FOR UPDATE", (document_id,)
        ).fetchone()
        if locked is None or locked[0] != "extracted":
            return  # a concurrent run of the same job finished first
        candidate_id = None
        if result.output.is_cv:
            # The only place the original name, email, phone and address are kept (§2.4).
            candidate = conn.execute(
                "INSERT INTO candidate (full_name, email, phone, address) "
                "VALUES (%s, %s, %s, %s) RETURNING id",
                (
                    masked.contact.full_name,
                    masked.contact.email,
                    masked.contact.phone,
                    masked.contact.address,
                ),
            ).fetchone()
            assert candidate is not None
            candidate_id = candidate[0]
            conn.execute(
                "UPDATE request_candidate SET candidate_id = %s WHERE document_id = %s",
                (candidate_id, document_id),
            )
        conn.execute(
            "UPDATE document SET status = 'parsed', candidate_id = %s, masked_text = %s, "
            "mask_spans = %s, parsed_json = %s, flags = %s WHERE id = %s",
            (
                candidate_id,
                masked.masked_text,
                Jsonb([span.model_dump() for span in masked.spans]),
                Jsonb(facts.parsed_json),
                Jsonb(facts.flags),
                document_id,
            ),
        )
    log.info(
        "document %s parsed: is_cv=%s flags=%s (in=%s out=%s tokens, cache_hit=%s)",
        document_id,
        result.output.is_cv,
        [flag["code"] for flag in facts.flags],
        result.usage.input_tokens,
        result.usage.output_tokens,
        result.usage.cache_hit,
    )


def _mark_failed(pool: ConnectionPool, document_id: UUID) -> None:
    with pool.connection() as conn:
        conn.execute(
            "UPDATE document SET status = 'failed', status_message = %s "
            "WHERE id = %s AND status IN ('uploaded', 'extracted')",
            (FAILED_MESSAGE, document_id),
        )


@register(INGEST_JOB)
def ingest(job: Job, pool: ConnectionPool) -> None:
    document_id = UUID(job.payload["document_id"])
    try:
        _ingest(pool, document_id)
    except Exception:
        if job.attempts >= job.max_attempts:
            # The queue gives up after this attempt; say so on the document, where HR looks.
            _mark_failed(pool, document_id)
        raise
