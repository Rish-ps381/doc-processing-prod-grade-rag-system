from __future__ import annotations

import logging
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from app.core.errors import AppError
from app.domain import DocumentStatus, utc_now
from app.providers.embeddings import EmbeddingProvider
from app.providers.vector_store import VectorStore
from app.repositories.mongo import ChunkRepository, DocumentRepository

logger = logging.getLogger(__name__)


class IndexingService:
    def __init__(self, documents: DocumentRepository, chunks: ChunkRepository, embeddings: EmbeddingProvider, vector_store: VectorStore, batch_size: int, embedding_model: str) -> None:
        self.documents = documents
        self.chunks = chunks
        self.embeddings = embeddings
        self.vector_store = vector_store
        self.batch_size = batch_size
        self.embedding_model = embedding_model

    async def index_document(self, document_id: str, tenant_id: str, version: str) -> None:
        document = await self.documents.get(document_id)
        if not document or document.get("tenant_id") != tenant_id:
            raise AppError("DOCUMENT_NOT_FOUND", "Document does not exist.", 404)
        await self.documents.update(document_id, {"status": DocumentStatus.EMBEDDING.value, "ready_for_ai": False, "updated_at": utc_now()})
        records = await self.chunks.find_for_document(document_id, version)
        if not records:
            raise AppError("NO_SOURCE_CONTENT", "No chunks are available for indexing.", 422)
        await self.documents.update(document_id, {"status": DocumentStatus.INDEXING.value, "updated_at": utc_now()})
        for start in range(0, len(records), self.batch_size):
            batch = records[start : start + self.batch_size]
            vectors = await self.embeddings.embed([record["text"] for record in batch])
            objects: list[dict[str, Any]] = []
            for record, vector in zip(batch, vectors, strict=True):
                source = record.get("source", {})
                objects.append({"id": str(uuid5(NAMESPACE_URL, record["_id"])), "vector": vector, "properties": {"chunk_id": record["_id"], "document_id": document_id, "tenant_id": tenant_id, "chunking_version": version, "text": record["text"], "document_name": document.get("name"), "page_number": source.get("page_number"), "heading_path": source.get("heading_path", []), "content_hash": record.get("content_hash"), "embedding_model": self.embedding_model}})
            await self.vector_store.upsert(objects)
        completed = utc_now()
        await self.documents.update(document_id, {"status": DocumentStatus.READY.value, "ready_for_ai": True, "embedding_model": self.embedding_model, "indexed_at": completed, "updated_at": completed})
        logger.info("Document indexed", extra={"document_id": document_id, "tenant_id": tenant_id, "chunk_count": len(records), "embedding_model": self.embedding_model})
