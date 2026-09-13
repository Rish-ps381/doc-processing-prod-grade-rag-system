from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.ingest import router as ingest_router
from app.core.config import get_settings
from app.core.errors import AppError, app_error_handler
from app.db.mongo import create_database, create_indexes
from app.repositories.mongo import ChunkRepository, ChunkingJobRepository, DocumentPageRepository, DocumentRepository, IngestionJobRepository
from app.providers.embeddings import OpenAIEmbeddingProvider
from app.providers.reranker import CohereReranker
from app.providers.vector_store import WeaviateVectorStore
from app.services.chunking.service import ChunkingService
from app.services.chunking.splitter import ChunkingSplitter
from app.services.chunking.tokenizer import TiktokenTokenizer
from app.services.ingestion import IngestionService
from app.services.indexing import IndexingService
from app.services.parser_factory import ParserFactory
from app.storage.base import LocalObjectStorage
from app.workers.chunking_worker import ChunkingWorker
from app.workers.ingestion_worker import IngestionWorker
from app.workers.queue import InProcessJobQueue


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    client, database = create_database(settings.mongo_uri, settings.mongo_database)
    await create_indexes(database)
    service = IngestionService(DocumentRepository(database), DocumentPageRepository(database), IngestionJobRepository(database), LocalObjectStorage(settings.local_storage_dir), ParserFactory(settings.web_timeout_seconds), settings.default_tenant_id)
    chunking_service = ChunkingService(
        DocumentRepository(database),
        DocumentPageRepository(database),
        ChunkRepository(database),
        ChunkingJobRepository(database),
        ChunkingSplitter(TiktokenTokenizer()),
        settings,
        settings.default_tenant_id,
    )
    indexing_service = IndexingService(
        DocumentRepository(database),
        ChunkRepository(database),
        OpenAIEmbeddingProvider(settings.embedding_api_key, settings.embedding_model),
        WeaviateVectorStore(settings.weaviate_url, settings.weaviate_collection, settings.weaviate_api_key),
        settings.embedding_batch_size,
        settings.embedding_model,
    )
    chunking_service.set_indexing_service(indexing_service)
    service.set_chunking_service(chunking_service)
    queue = InProcessJobQueue(IngestionWorker(service).process)
    chunking_queue = InProcessJobQueue(ChunkingWorker(chunking_service).process)
    chunking_service.set_queue(chunking_queue)
    await queue.start()
    await chunking_queue.start()
    app.state.ingestion_service = service
    app.state.chunking_service = chunking_service
    app.state.indexing_service = indexing_service
    app.state.job_queue = queue
    app.state.chunking_queue = chunking_queue
    yield
    await queue.stop()
    await chunking_queue.stop()
    client.close()


app = FastAPI(title="doc-process-rag", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
app.add_exception_handler(AppError, app_error_handler)
app.include_router(ingest_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/version")
async def version() -> dict[str, str]:
    return {"version": get_settings().app_version}
