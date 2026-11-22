"""Creating a ranking request: files, position, documents, request rows and ingest jobs.

Everything that touches the database runs in the caller's transaction, so a request either
exists with all its jobs or not at all.
"""

import hashlib
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from uuid import UUID, uuid4

import psycopg

from ats.db import task_queue
from ats.pipeline.facts import NOT_A_CV
from ats.services.assessments import enqueue_judgements
from ats.services.requirements import enqueue_missing_setup, retry_failed_setup

INGEST_JOB = "ingest"
# Shown on the request for a document triage judged not to be a CV: it has no candidate and no
# assessment, so without a message HR cannot tell why it is missing from the ranking.
NOT_A_CV_MESSAGE = "The system judged this document not to be a CV, so it was not ranked."

type DocumentKind = Literal["cv", "posting"]


@dataclass(frozen=True)
class StoredFile:
    """A file as the database knows it: what registering a document needs."""

    filename: str
    sha256: str


@dataclass(frozen=True)
class PdfUpload(StoredFile):
    content: bytes


@dataclass(frozen=True)
class CreatedRanking:
    request_id: UUID
    position_id: UUID


class DocumentKindConflict(Exception):
    """The same bytes were already stored as the other kind of document."""

    def __init__(self, filename: str, existing_kind: str) -> None:
        super().__init__(f"{filename!r} was already uploaded as a {existing_kind}")
        self.filename = filename
        self.existing_kind = existing_kind


def make_upload(filename: str, content: bytes) -> PdfUpload:
    return PdfUpload(filename=filename, sha256=hashlib.sha256(content).hexdigest(), content=content)


def storage_name(sha256: str) -> str:
    # Relative to UPLOAD_DIR: the API and the worker may mount it at different paths.
    return f"{sha256}.pdf"


def store_file(upload_dir: Path, upload: PdfUpload) -> None:
    """Write the PDF under its hash. Content-addressed, so storing twice is a no-op."""
    target = upload_dir / storage_name(upload.sha256)
    if target.exists():
        return
    upload_dir.mkdir(parents=True, exist_ok=True)
    # Temp file plus rename: a reader never sees a half-written PDF.
    fd, temp_name = tempfile.mkstemp(dir=upload_dir, suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(upload.content)
        os.replace(temp_name, target)
    except BaseException:
        Path(temp_name).unlink(missing_ok=True)
        raise


def _enqueue_ingest(conn: psycopg.Connection[Any], document_id: UUID, *, rerun: bool) -> None:
    # The queue's dedup key is unique for all time, so a deliberate re-run needs a fresh one.
    key = f"{INGEST_JOB}:{document_id}" + (f":{uuid4().hex}" if rerun else "")
    task_queue.enqueue(conn, INGEST_JOB, {"document_id": str(document_id)}, dedup_key=key)


def register_document(
    conn: psycopg.Connection[Any], kind: DocumentKind, upload: StoredFile
) -> UUID:
    """Find or create the document for these bytes; enqueue ingest only when it is needed.

    A new document is ingested once. A `failed` one, and one stalled before its last step, is
    ingested again on re-upload. A `rejected` one is not: the same bytes would be rejected the
    same way.
    """
    created = conn.execute(
        "INSERT INTO document (kind, sha256, filename, storage_path) VALUES (%s, %s, %s, %s) "
        "ON CONFLICT (sha256) DO NOTHING RETURNING id",
        (kind, upload.sha256, upload.filename, storage_name(upload.sha256)),
    ).fetchone()
    if created is not None:
        _enqueue_ingest(conn, created[0], rerun=False)
        return created[0]

    # The row lock makes two concurrent re-uploads take turns, so the second one sees the job
    # the first one enqueued.
    existing = conn.execute(
        "SELECT id, kind, status FROM document WHERE sha256 = %s FOR UPDATE", (upload.sha256,)
    ).fetchone()
    assert existing is not None  # the conflict above means the row exists
    document_id: UUID = existing[0]
    if existing[1] != kind:
        raise DocumentKindConflict(upload.filename, existing[1])
    # One atomic UPDATE: of two concurrent re-uploads only one flips the status and enqueues.
    requeued = conn.execute(
        "UPDATE document SET status = 'uploaded', status_message = NULL "
        "WHERE id = %s AND status = 'failed' RETURNING id",
        (document_id,),
    ).fetchone()
    if requeued is not None or _is_stalled(conn, document_id, kind, existing[2]):
        _enqueue_ingest(conn, document_id, rerun=True)
    return document_id


def _is_stalled(
    conn: psycopg.Connection[Any], document_id: UUID, kind: DocumentKind, status: str
) -> bool:
    """A document that is not finished and has no ingest job on its way.

    A CV extracted before parsing existed stays `extracted` and nothing ever picks it up. A
    posting is finished once extracted, so only a CV counts in that state.
    """
    if status != "uploaded" and not (status == "extracted" and kind == "cv"):
        return False
    live = conn.execute(
        "SELECT 1 FROM task_queue WHERE job_type = %s AND status IN ('queued', 'running') "
        "AND payload->>'document_id' = %s",
        (INGEST_JOB, str(document_id)),
    ).fetchone()
    return live is None


def _find_or_create_position(conn: psycopg.Connection[Any], sha256: str) -> UUID:
    created = conn.execute(
        "INSERT INTO job_position (source_sha256) VALUES (%s) "
        "ON CONFLICT (source_sha256) DO NOTHING RETURNING id",
        (sha256,),
    ).fetchone()
    if created is not None:
        return created[0]
    found = conn.execute(
        "SELECT id FROM job_position WHERE source_sha256 = %s", (sha256,)
    ).fetchone()
    assert found is not None
    return found[0]


def create_ranking(
    conn: psycopg.Connection[Any], posting: PdfUpload, cvs: list[PdfUpload]
) -> CreatedRanking:
    if posting.sha256 in {cv.sha256 for cv in cvs}:
        raise DocumentKindConflict(posting.filename, "cv")
    position_id = _find_or_create_position(conn, posting.sha256)
    return _submit(conn, position_id, posting, cvs)


def add_cvs(
    conn: psycopg.Connection[Any], position_id: UUID, cvs: list[PdfUpload]
) -> CreatedRanking | None:
    """The same request as `create_ranking` with this position's posting; None if unknown.

    The stored posting goes through the same steps as an uploaded one, so a stalled or failed
    posting heals here too. A CV with the posting's bytes is refused by `register_document`.
    """
    posting = find_posting(conn, position_id)
    if posting is None:
        return None
    return _submit(conn, position_id, posting, cvs)


def find_posting(conn: psycopg.Connection[Any], position_id: UUID) -> StoredFile | None:
    """The posting a position was made from; None for an unknown position."""
    row = conn.execute(
        "SELECT d.filename, d.sha256 FROM job_position p "
        "JOIN document d ON d.sha256 = p.source_sha256 WHERE p.id = %s",
        (position_id,),
    ).fetchone()
    return None if row is None else StoredFile(filename=row[0], sha256=row[1])


def _submit(
    conn: psycopg.Connection[Any], position_id: UUID, posting: StoredFile, cvs: list[PdfUpload]
) -> CreatedRanking:
    # Uploading a posting whose requirement extraction failed is HR asking to try again.
    retry_failed_setup(conn, position_id)
    enqueue_missing_setup(conn, position_id)

    # Registering in hash order gives concurrent requests one lock order on the unique
    # `sha256`, so two uploads that share CVs cannot deadlock each other.
    uploads: dict[str, tuple[DocumentKind, StoredFile]] = {posting.sha256: ("posting", posting)}
    uploads |= {cv.sha256: ("cv", cv) for cv in cvs}
    document_ids: dict[str, UUID] = {}
    for sha256 in sorted(uploads):
        kind, upload = uploads[sha256]
        document_ids[sha256] = register_document(conn, kind, upload)

    request = conn.execute(
        "INSERT INTO ranking_request (type, position_id) VALUES ('submit', %s) RETURNING id",
        (position_id,),
    ).fetchone()
    assert request is not None
    request_id: UUID = request[0]
    for cv in cvs:
        conn.execute(
            "INSERT INTO request_candidate (request_id, document_id) VALUES (%s, %s) "
            "ON CONFLICT DO NOTHING",
            (request_id, document_ids[cv.sha256]),
        )
    # A CV parsed in an earlier request has its candidate already; link it, and judge it unless
    # that was done for this position (the dedup key and the stored assessment make a repeat free).
    conn.execute(
        "UPDATE request_candidate rc SET candidate_id = d.candidate_id FROM document d "
        "WHERE d.id = rc.document_id AND rc.request_id = %s AND rc.candidate_id IS NULL "
        "AND d.candidate_id IS NOT NULL",
        (request_id,),
    )
    enqueue_judgements(conn, position_id, retry_failed=True)
    return CreatedRanking(request_id=request_id, position_id=position_id)


@dataclass(frozen=True)
class DocumentState:
    document_id: UUID
    kind: DocumentKind
    filename: str | None
    status: str
    message: str | None


@dataclass(frozen=True)
class RankingState:
    request_id: UUID
    position_id: UUID
    status: Literal["queued", "running", "done", "failed"]
    documents: list[DocumentState]


def _derive_status(
    documents: list[DocumentState], *, setup_failed: bool = False, unassessed: int = 0
) -> Literal["queued", "running", "done", "failed"]:
    """Request status from its documents and its assessments.

    It is computed at read time on purpose: a stored value would need coordination between the
    independent ingest and judge jobs. `unassessed` counts the CVs of the request that have a
    candidate but no assessment yet (neither `done` nor `failed`).
    """
    posting = next(doc for doc in documents if doc.kind == "posting")
    if posting.status in ("rejected", "failed") or setup_failed:
        return "failed"  # without requirements there is nothing to score against
    # A CV is also pending while extracted but not yet parsed; a posting ends at `extracted`.
    pending = [
        doc
        for doc in documents
        if doc.status == "uploaded" or (doc.kind == "cv" and doc.status == "extracted")
    ]
    if len(pending) == len(documents):
        return "queued"
    return "running" if pending or unassessed else "done"


def _message(stored: str | None, flags: list[dict[str, str]]) -> str | None:
    """The stored message wins; a not-a-CV flag gets one at read time, so old rows show it too."""
    if stored is None and any(flag.get("code") == NOT_A_CV for flag in flags):
        return NOT_A_CV_MESSAGE
    return stored


def get_ranking_state(conn: psycopg.Connection[Any], request_id: UUID) -> RankingState | None:
    request = conn.execute(
        "SELECT position_id FROM ranking_request WHERE id = %s", (request_id,)
    ).fetchone()
    if request is None:
        return None
    rows = conn.execute(
        "SELECT d.id, d.kind, d.filename, d.status, d.status_message, d.flags "
        "FROM document d JOIN job_position p ON p.source_sha256 = d.sha256 "
        "WHERE p.id = %(position)s "
        "UNION ALL "
        "SELECT d.id, d.kind, d.filename, d.status, d.status_message, d.flags "
        "FROM request_candidate rc JOIN document d ON d.id = rc.document_id "
        "WHERE rc.request_id = %(request)s "
        "ORDER BY 2 DESC, 3",  # 'posting' sorts after 'cv', so DESC lists the posting first
        {"position": request[0], "request": request_id},
    ).fetchall()
    documents = [
        DocumentState(row[0], row[1], row[2], row[3], _message(row[4], row[5])) for row in rows
    ]
    setup_failed = conn.execute(
        "SELECT EXISTS (SELECT 1 FROM task_queue WHERE dedup_key = %s AND status = 'failed')",
        (f"position_setup:{request[0]}",),
    ).fetchone()
    unassessed = conn.execute(
        "SELECT count(*) FROM request_candidate rc "
        "JOIN document d ON d.id = rc.document_id "
        "WHERE rc.request_id = %(request)s AND d.status = 'parsed' AND d.candidate_id IS NOT NULL "
        "AND NOT EXISTS (SELECT 1 FROM assessment a WHERE a.candidate_id = d.candidate_id "
        "                AND a.position_id = %(position)s AND a.status IN ('done', 'failed'))",
        {"request": request_id, "position": request[0]},
    ).fetchone()
    return RankingState(
        request_id=request_id,
        position_id=request[0],
        status=_derive_status(
            documents,
            setup_failed=bool(setup_failed and setup_failed[0]),
            unassessed=int(unassessed[0]) if unassessed else 0,
        ),
        documents=documents,
    )
