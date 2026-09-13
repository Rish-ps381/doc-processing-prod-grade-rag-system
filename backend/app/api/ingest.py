from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile, status
from pydantic import TypeAdapter, ValidationError
from pydantic.networks import HttpUrl

from app.core.errors import AppError
from app.domain import FileType
from app.services.ingestion import IngestionService
from app.workers.queue import JobQueue

router = APIRouter(prefix="/ingest", tags=["ingestion"])
ALLOWED_EXTENSIONS = {".pdf": FileType.PDF, ".md": FileType.MARKDOWN, ".markdown": FileType.MARKDOWN}
ALLOWED_MIME_TYPES = {"application/pdf", "text/markdown", "text/plain"}


def service(request: Request) -> IngestionService:
    return request.app.state.ingestion_service


def queue(request: Request) -> JobQueue:
    return request.app.state.job_queue


@router.post("/create", status_code=status.HTTP_202_ACCEPTED)
async def create_ingestion(request: Request, source_type: str = Form(...), file: UploadFile | None = File(None), url: str | None = Form(None)) -> dict[str, str]:
    if source_type == "file":
        if file is None or not file.filename:
            raise AppError("INVALID_REQUEST", "A file is required for file ingestion.", 422)
        extension = Path(file.filename).suffix.lower()
        file_type = ALLOWED_EXTENSIONS.get(extension)
        if file_type is None or (file.content_type and file.content_type not in ALLOWED_MIME_TYPES):
            raise AppError("UNSUPPORTED_FILE_TYPE", "Only PDF and Markdown files are supported.", 422)
        content = await file.read()
        job = await service(request).create_file_job(file.filename, file.content_type, file_type, content)
    elif source_type == "url":
        if file is not None or not url:
            raise AppError("INVALID_REQUEST", "Provide exactly one URL for URL ingestion.", 422)
        try:
            parsed = TypeAdapter(HttpUrl).validate_python(url)
            if parsed.scheme not in {"http", "https"}:
                raise ValueError
        except (ValidationError, ValueError) as exc:
            raise AppError("INVALID_URL", "A valid HTTP or HTTPS URL is required.", 422) from exc
        job = await service(request).create_url_job(str(parsed))
    else:
        raise AppError("UNSUPPORTED_SOURCE_TYPE", "source_type must be 'file' or 'url'.", 422)
    await queue(request).enqueue(job.id)
    return {"document_id": job.document_id, "job_id": job.id, "status": job.status.value}


@router.get("/{job_id}")
async def get_ingestion(job_id: str, request: Request) -> dict:
    job = await service(request).get_job(job_id)
    if job is None:
        raise AppError("INGESTION_JOB_NOT_FOUND", "The ingestion job does not exist.", 404)
    response = {"job_id": job.id, "document_id": job.document_id, "status": job.status.value, "error": job.error.model_dump() if job.error else None, "created_at": job.created_at, "started_at": job.started_at, "completed_at": job.completed_at}
    get_status = getattr(service(request), "get_document_status", None)
    if get_status is not None:
        document_status = await get_status(job.document_id)
        if document_status:
            response.update(document_status)
    return response
