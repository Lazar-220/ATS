from typing import Annotated, cast
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
