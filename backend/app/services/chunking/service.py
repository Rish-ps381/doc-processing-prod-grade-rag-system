from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.core.config import Settings
from app.core.errors import AppError
from app.domain import ChunkingStatus, DocumentStatus, JobError, new_id, utc_now
from app.repositories.mongo import ChunkRepository, ChunkingJobRepository, DocumentPageRepository, DocumentRepository
from app.services.chunking.splitter import ChunkingSplitter

logger = logging.getLogger(__name__)


class ChunkingService:
    def __init__(self, documents: DocumentRepository, pages: DocumentPageRepository, chunks: ChunkRepository, jobs: ChunkingJobRepository, splitter: ChunkingSplitter, settings: Settings, tenant_id: str):
        self.documents = documents
        self.pages = pages
        self.chunks = chunks
        self.jobs = jobs
        self.splitter = splitter
        self.settings = settings
        self.tenant_id = tenant_id
        self.queue = None
        self.indexing_service = None

    def set_queue(self, queue: object) -> None:
        self.queue = queue

    def set_indexing_service(self, service: object) -> None:
        self.indexing_service = service

    async def queue_document(self, document_id: str, tenant_id: str | None = None) -> None:
        record = await self.documents.get(document_id)
        if record is None:
            raise AppError("DOCUMENT_NOT_FOUND", "Document does not exist.", 404)
        version = self.settings.chunking_version
        job_id = new_id("chunkjob")
        now = utc_now()
        job = {
            "_id": job_id,
            "document_id": document_id,
            "tenant_id": tenant_id or self.tenant_id,
            "job_type": "DOCUMENT_CHUNKING",
            "status": ChunkingStatus.QUEUED.value,
            "version": version,
            "attempt": 0,
            "max_attempts": 3,
            "created_at": now,
            "updated_at": now,
        }
        await self.jobs.insert(job)
        await self.documents.update(document_id, {"chunking_status": ChunkingStatus.QUEUED.value, "chunking_version": version, "updated_at": now})
        if self.queue is not None:
            await self.queue.enqueue(job_id)

    async def process_job(self, job_id: str) -> None:
        job_data = await self.jobs.get(job_id)
        if not job_data:
            logger.error("Chunking job was not found", extra={"job_id": job_id})
            return
        document_id = job_data["document_id"]
        now = utc_now()
        version = job_data["version"]
        attempt = job_data.get("attempt", 0) + 1
        await self.jobs.update(job_id, {"status": ChunkingStatus.PROCESSING.value, "attempt": attempt, "started_at": now, "updated_at": now})
        await self.documents.update(document_id, {"status": DocumentStatus.CHUNKING.value, "chunking_status": ChunkingStatus.PROCESSING.value, "ready_for_ai": False, "updated_at": now})
        try:
            page_docs = await self.pages.collection.find({"document_id": document_id}).sort("page_number", 1).to_list(length=None)
            if not page_docs:
                raise AppError("NO_SOURCE_CONTENT", "No canonical document pages were found for chunking.", 422)
            chunks = self.splitter.chunk_pages(page_docs, document_id=document_id, chunking_version=version)
            if not chunks:
                raise AppError("NO_SOURCE_CONTENT", "Chunking produced no output for the document.", 422)
            await self.chunks.delete_for_document(document_id, version)
            for chunk in chunks:
                chunk["tenant_id"] = job_data.get("tenant_id", self.tenant_id)
            await self.chunks.insert_many(chunks)
            completed = utc_now()
            await self.jobs.update(job_id, {"status": ChunkingStatus.COMPLETED.value, "completed_at": completed, "updated_at": completed, "error": None})
            await self.documents.update(document_id, {"status": DocumentStatus.QUEUED.value, "chunking_status": ChunkingStatus.COMPLETED.value, "chunking_version": version, "ready_for_ai": False, "updated_at": completed})
            if self.indexing_service is None:
                raise AppError("INDEXING_NOT_CONFIGURED", "Document indexing is not configured.", 503)
            await self.indexing_service.index_document(document_id, job_data.get("tenant_id", self.tenant_id), version)
            logger.info("Chunking completed", extra={"job_id": job_id, "document_id": document_id, "chunking_version": version, "chunk_count": len(chunks)})
        except AppError as exc:
            await self._fail(job_id, document_id, version, exc, attempt)
        except Exception as exc:
            logger.exception("Unexpected chunking failure", extra={"job_id": job_id, "document_id": document_id, "version": version, "attempt": attempt})
            await self._fail(job_id, document_id, version, AppError("CHUNKING_FAILED", "Document chunking failed.", 500), attempt)

    async def _fail(self, job_id: str, document_id: str, version: str, error: AppError, attempt: int) -> None:
        now = utc_now()
        terminal = attempt >= 3 or error.status_code < 500
        status = ChunkingStatus.FAILED.value if terminal else ChunkingStatus.QUEUED.value
        updates = {"status": status, "error": JobError(code=error.code, message=error.message).model_dump(), "updated_at": now}
        if terminal:
            updates["completed_at"] = now
        await self.jobs.update(job_id, updates)
        await self.documents.update(document_id, {"chunking_status": status, "chunking_version": version, "ready_for_ai": False, "updated_at": now})
