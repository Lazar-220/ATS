from typing import Annotated, Literal, cast
from uuid import UUID

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from psycopg_pool import ConnectionPool
from pydantic import BaseModel

from ats.services import rankings
from ats.services.rankings import DocumentKindConflict, PdfUpload
from ats.settings import get_settings

router = APIRouter()

# The PDF specification allows the header anywhere in the first 1024 bytes.
_HEADER_WINDOW = 1024


class RankingAccepted(BaseModel):
    request_id: UUID
    position_id: UUID


class DocumentStatus(BaseModel):
    document_id: UUID
    kind: Literal["cv", "posting"]
    filename: str | None
    status: str
    # Why a document was rejected or failed, or why a parsed one is not ranked (judged not to be
    # a CV), written for HR; null otherwise.
    message: str | None


class RankingStatus(BaseModel):
    request_id: UUID
    position_id: UUID
    status: Literal["queued", "running", "done", "failed"]
    documents: list[DocumentStatus]


def _read_pdf(file: UploadFile, max_bytes: int) -> PdfUpload:
    name = (file.filename or "upload").replace("\\", "/").rsplit("/", 1)[-1][:255]
    content = file.file.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise HTTPException(413, f"{name!r} is larger than {max_bytes // (1024 * 1024)} MB")
    if b"%PDF-" not in content[:_HEADER_WINDOW]:
        raise HTTPException(422, f"{name!r} is not a PDF file")
    return rankings.make_upload(name, content)


@router.post("/rankings", status_code=202)
def create_ranking(
    request: Request,
    posting: Annotated[UploadFile, File(description="The job posting as a PDF")],
    cvs: Annotated[list[UploadFile], File(description="One or more CVs as PDFs")],
) -> RankingAccepted:
    settings = get_settings()
    max_bytes = settings.max_upload_mb * 1024 * 1024
    # Every file is validated before anything is stored or written to the database.
    posting_pdf = _read_pdf(posting, max_bytes)
    cv_pdfs = [_read_pdf(cv, max_bytes) for cv in cvs]

    # Files first: a row never points at a file that is missing. A file left behind by a
    # failed transaction is harmless, because it is named by its hash.
    for pdf in (posting_pdf, *cv_pdfs):
        rankings.store_file(settings.upload_dir, pdf)

    pool = cast(ConnectionPool, request.app.state.pool)
    try:
        with pool.connection() as conn:
            created = rankings.create_ranking(conn, posting_pdf, cv_pdfs)
    except DocumentKindConflict as exc:
        raise HTTPException(422, str(exc)) from exc
    return RankingAccepted(request_id=created.request_id, position_id=created.position_id)


@router.get("/rankings/{request_id}")
def get_ranking(request_id: UUID, request: Request) -> RankingStatus:
    pool = cast(ConnectionPool, request.app.state.pool)
    with pool.connection() as conn:
        state = rankings.get_ranking_state(conn, request_id)
    if state is None:
        raise HTTPException(404, "No such ranking request")
    return RankingStatus(
        request_id=state.request_id,
        position_id=state.position_id,
        status=state.status,
        documents=[
            DocumentStatus(
                document_id=doc.document_id,
                kind=doc.kind,
                filename=doc.filename,
                status=doc.status,
                message=doc.message,
            )
            for doc in state.documents
        ],
    )
