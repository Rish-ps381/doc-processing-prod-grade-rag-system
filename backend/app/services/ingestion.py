import logging
from datetime import datetime, timezone
from pathlib import Path

from app.core.errors import AppError
from app.domain import DocumentStatus, FileType, IngestionJobRecord, JobError, JobStatus, ParsedDocument, SourceType, new_id, utc_now
from app.repositories.mongo import DocumentPageRepository, DocumentRepository, IngestionJobRepository
from app.services.chunking.service import ChunkingService
from app.services.parser_factory import ParserFactory
from app.storage.base import ObjectStorage

logger = logging.getLogger(__name__)


class IngestionService:
    def __init__(self, documents: DocumentRepository, pages: DocumentPageRepository, jobs: IngestionJobRepository, storage: ObjectStorage, parser_factory: ParserFactory, tenant_id: str):
        self.documents, self.pages, self.jobs = documents, pages, jobs
        self.storage, self.parser_factory, self.tenant_id = storage, parser_factory, tenant_id
        self.chunking_service: ChunkingService | None = None

    def set_chunking_service(self, service: ChunkingService) -> None:
        self.chunking_service = service

    async def create_file_job(self, filename: str, mime_type: str | None, file_type: FileType, content: bytes) -> IngestionJobRecord:
        if not content:
            raise AppError("EMPTY_DOCUMENT", "The uploaded file is empty.", 422)
        now = utc_now()
        document_id, job_id = new_id("doc"), new_id("job")
        storage_key = f"documents/{document_id}/original{Path(filename).suffix.lower()}"
        await self.storage.save(storage_key, content)
        await self.documents.insert({"_id": document_id, "tenant_id": self.tenant_id, "name": filename, "title": Path(filename).stem, "source_type": SourceType.FILE.value, "file_type": file_type.value, "mime_type": mime_type, "status": DocumentStatus.QUEUED.value, "source": {"filename": filename, "url": None, "storage_key": storage_key}, "version": 1, "content_stats": {}, "created_at": now, "updated_at": now})
        job = IngestionJobRecord(id=job_id, document_id=document_id, tenant_id=self.tenant_id, status=JobStatus.QUEUED, created_at=now, updated_at=now)
        await self.jobs.insert(job.model_dump(by_alias=True, exclude_none=True) | {"_id": job_id})
        return job

    async def create_url_job(self, url: str) -> IngestionJobRecord:
        now = utc_now()
        document_id, job_id = new_id("doc"), new_id("job")
        await self.documents.insert({"_id": document_id, "tenant_id": self.tenant_id, "name": url, "title": None, "source_type": SourceType.URL.value, "file_type": None, "mime_type": "text/html", "status": DocumentStatus.QUEUED.value, "source": {"filename": None, "url": url, "storage_key": None}, "version": 1, "content_stats": {}, "created_at": now, "updated_at": now})
        job = IngestionJobRecord(id=job_id, document_id=document_id, tenant_id=self.tenant_id, status=JobStatus.QUEUED, created_at=now, updated_at=now)
        await self.jobs.insert(job.model_dump(exclude_none=True) | {"_id": job_id})
        return job

    async def get_job(self, job_id: str) -> IngestionJobRecord | None:
        data = await self.jobs.get(job_id)
        if not data:
            return None
        data["id"] = data.pop("_id")
        return IngestionJobRecord.model_validate(data)

    async def process_job(self, job_id: str) -> None:
        job_data = await self.jobs.get(job_id)
        if not job_data:
            logger.error("Queued job was not found", extra={"job_id": job_id})
            return
        document = await self.documents.get(job_data["document_id"])
        now = utc_now()
        attempt = job_data.get("attempt", 0) + 1
        await self.jobs.update(job_id, {"status": JobStatus.PROCESSING.value, "attempt": attempt, "started_at": now, "updated_at": now})
        await self.documents.update(job_data["document_id"], {"status": DocumentStatus.PROCESSING.value, "updated_at": now})
        try:
            source_type = document["source_type"]
            file_type = document.get("file_type")
            parser = self.parser_factory.get(source_type, file_type)
            source = await self.storage.get(document["source"]["storage_key"]) if source_type == SourceType.FILE.value else document["source"]["url"]
            parsed = await parser.parse(source, source_name=document.get("name"))
            await self._persist_parsed(job_data["document_id"], parsed)
            completed = utc_now()
            await self.jobs.update(job_id, {"status": JobStatus.COMPLETED.value, "completed_at": completed, "updated_at": completed, "error": None})
            await self.documents.update(job_data["document_id"], {"status": DocumentStatus.COMPLETED.value, "language": parsed.language, "title": parsed.title, "content_stats": {"page_count": len(parsed.pages), "character_count": parsed.character_count}, "chunking_status": "PENDING", "ready_for_ai": False, "updated_at": completed})
            if self.chunking_service is not None:
                await self.chunking_service.queue_document(job_data["document_id"], self.tenant_id)
        except AppError as exc:
            await self._fail(job_id, job_data["document_id"], exc, attempt)
        except Exception as exc:
            logger.exception("Unexpected ingestion failure", extra={"job_id": job_id, "document_id": job_data["document_id"], "attempt": attempt})
            await self._fail(job_id, job_data["document_id"], AppError("INGESTION_ERROR", "Document ingestion failed.", 500), attempt)

    async def _persist_parsed(self, document_id: str, parsed: ParsedDocument) -> None:
        now = utc_now()
        await self.pages.delete_for_document(document_id)
        records = []
        for page in parsed.pages:
            records.append({"_id": new_id("page"), "document_id": document_id, "tenant_id": self.tenant_id, "page_number": page.page_number, "content": [block.model_dump() for block in page.content], "plain_text": page.plain_text, "metadata": page.metadata, "created_at": now, "updated_at": now})
        await self.pages.insert_many(records)

    async def _fail(self, job_id: str, document_id: str, error: AppError, attempt: int) -> None:
        now = utc_now()
        terminal = attempt >= 3 or error.status_code < 500
        status = JobStatus.FAILED.value if terminal else JobStatus.QUEUED.value
        updates = {"status": status, "error": JobError(code=error.code, message=error.message).model_dump(), "updated_at": now}
        if terminal:
            updates["completed_at"] = now
        await self.jobs.update(job_id, updates)
        await self.documents.update(document_id, {"status": DocumentStatus.FAILED.value if terminal else DocumentStatus.QUEUED.value, "updated_at": now})
