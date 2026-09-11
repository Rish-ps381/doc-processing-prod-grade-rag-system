from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase


async def create_indexes(database: AsyncIOMotorDatabase) -> None:
    await database.documents.create_index([("tenant_id", 1), ("status", 1)])
    await database.documents.create_index([("tenant_id", 1), ("created_at", -1)])
    await database.document_pages.create_index([("document_id", 1), ("page_number", 1)])
    await database.ingestion_jobs.create_index([("document_id", 1), ("created_at", -1)])
    await database.ingestion_jobs.create_index([("tenant_id", 1), ("status", 1)])
    await database.chunks.create_index([("document_id", 1), ("chunking_version", 1), ("chunk_index", 1)])
    await database.chunks.create_index([("document_id", 1), ("chunking_version", 1)])
    await database.chunking_jobs.create_index([("document_id", 1), ("version", 1), ("created_at", -1)])
    await database.chunking_jobs.create_index([("tenant_id", 1), ("status", 1)])


def create_database(uri: str, database_name: str) -> tuple[AsyncIOMotorClient, AsyncIOMotorDatabase]:
    client = AsyncIOMotorClient(uri)
    return client, client[database_name]
