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

INGEST_JOB = "ingest"

type DocumentKind = Literal["cv", "posting"]


@dataclass(frozen=True)
class PdfUpload:
    filename: str
    content: bytes
    sha256: str


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
    return PdfUpload(filename, content, hashlib.sha256(content).hexdigest())


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


def register_document(conn: psycopg.Connection[Any], kind: DocumentKind, upload: PdfUpload) -> UUID:
    """Find or create the document for these bytes; enqueue ingest only when it is needed.

    A new document is ingested once. A `failed` one is ingested again on re-upload. A
    `rejected` one is not: the same bytes would be rejected the same way.
    """
    created = conn.execute(
        "INSERT INTO document (kind, sha256, filename, storage_path) VALUES (%s, %s, %s, %s) "
        "ON CONFLICT (sha256) DO NOTHING RETURNING id",
        (kind, upload.sha256, upload.filename, storage_name(upload.sha256)),
    ).fetchone()
    if created is not None:
        _enqueue_ingest(conn, created[0], rerun=False)
        return created[0]

    existing = conn.execute(
        "SELECT id, kind FROM document WHERE sha256 = %s", (upload.sha256,)
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
    if requeued is not None:
        _enqueue_ingest(conn, document_id, rerun=True)
    return document_id


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

    # Registering in hash order gives concurrent requests one lock order on the unique
    # `sha256`, so two uploads that share CVs cannot deadlock each other.
    uploads: dict[str, tuple[DocumentKind, PdfUpload]] = {posting.sha256: ("posting", posting)}
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
    documents: list[DocumentState],
) -> Literal["queued", "running", "done", "failed"]:
    """Request status from its documents.

    It is computed at read time on purpose: until the scoring phases exist there is no stage
    after ingest, and a stored value would need coordination between the ingest jobs.
    """
    posting = next(doc for doc in documents if doc.kind == "posting")
    if posting.status in ("rejected", "failed"):
        return "failed"  # without the posting there is nothing to score against
    pending = [doc for doc in documents if doc.status == "uploaded"]
    if len(pending) == len(documents):
        return "queued"
    return "running" if pending else "done"


def get_ranking_state(conn: psycopg.Connection[Any], request_id: UUID) -> RankingState | None:
    request = conn.execute(
        "SELECT position_id FROM ranking_request WHERE id = %s", (request_id,)
    ).fetchone()
    if request is None:
        return None
    rows = conn.execute(
        "SELECT d.id, d.kind, d.filename, d.status, d.status_message "
        "FROM document d JOIN job_position p ON p.source_sha256 = d.sha256 "
        "WHERE p.id = %(position)s "
        "UNION ALL "
        "SELECT d.id, d.kind, d.filename, d.status, d.status_message "
        "FROM request_candidate rc JOIN document d ON d.id = rc.document_id "
        "WHERE rc.request_id = %(request)s "
        "ORDER BY 2 DESC, 3",  # 'posting' sorts after 'cv', so DESC lists the posting first
        {"position": request[0], "request": request_id},
    ).fetchall()
    documents = [DocumentState(*row) for row in rows]
    return RankingState(
        request_id=request_id,
        position_id=request[0],
        status=_derive_status(documents),
        documents=documents,
    )
