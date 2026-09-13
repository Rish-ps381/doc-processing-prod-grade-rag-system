from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase


class MongoRepository:
    def __init__(self, database: AsyncIOMotorDatabase, collection: str):
        self.collection = database[collection]

    async def insert(self, value: dict[str, Any]) -> None:
        await self.collection.insert_one(value)

    async def get(self, identifier: str) -> dict[str, Any] | None:
        return await self.collection.find_one({"_id": identifier})

    async def update(self, identifier: str, updates: dict[str, Any]) -> None:
        await self.collection.update_one({"_id": identifier}, {"$set": updates})

    async def list_for_tenant(self, tenant_id: str, *, limit: int = 100) -> list[dict[str, Any]]:
        return await self.collection.find({"tenant_id": tenant_id}).sort("created_at", -1).to_list(length=limit)


class DocumentRepository(MongoRepository):
    def __init__(self, database: AsyncIOMotorDatabase):
        super().__init__(database, "documents")


class DocumentPageRepository(MongoRepository):
    def __init__(self, database: AsyncIOMotorDatabase):
        super().__init__(database, "document_pages")

    async def insert_many(self, pages: list[dict[str, Any]]) -> None:
        if pages:
            await self.collection.insert_many(pages)

    async def delete_for_document(self, document_id: str) -> None:
        await self.collection.delete_many({"document_id": document_id})


class IngestionJobRepository(MongoRepository):
    def __init__(self, database: AsyncIOMotorDatabase):
        super().__init__(database, "ingestion_jobs")


class ChunkRepository(MongoRepository):
    def __init__(self, database: AsyncIOMotorDatabase):
        super().__init__(database, "chunks")

    async def insert_many(self, chunks: list[dict[str, Any]]) -> None:
        if chunks:
            await self.collection.insert_many(chunks)

    async def delete_for_document(self, document_id: str, version: str) -> None:
        await self.collection.delete_many({"document_id": document_id, "chunking_version": version})

    async def find_for_document(self, document_id: str, version: str) -> list[dict[str, Any]]:
        cursor = self.collection.find({"document_id": document_id, "chunking_version": version}).sort("chunk_index", 1)
        return await cursor.to_list(length=None)

    async def find_by_ids(self, chunk_ids: list[str], tenant_id: str) -> list[dict[str, Any]]:
        return await self.collection.find({"_id": {"$in": chunk_ids}, "tenant_id": tenant_id}).to_list(length=None)


class ChunkingJobRepository(MongoRepository):
    def __init__(self, database: AsyncIOMotorDatabase):
        super().__init__(database, "chunking_jobs")
