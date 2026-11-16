"""Ingest job: PDF file to clean text, language and script in the `document` row.

Imported by the worker only; the API never loads PyMuPDF or the language models.
"""

import logging
from uuid import UUID

from psycopg_pool import ConnectionPool

from ats.db.task_queue import Job
from ats.pipeline.extract import PdfRejected, extract_text
from ats.pipeline.language import detect_language, detect_script
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


def _mark_failed(pool: ConnectionPool, document_id: UUID) -> None:
    with pool.connection() as conn:
        conn.execute(
            "UPDATE document SET status = 'failed', status_message = %s "
            "WHERE id = %s AND status = 'uploaded'",
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
