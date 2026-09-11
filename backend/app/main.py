from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.ingest import router as ingest_router
from app.core.config import get_settings
from app.core.errors import AppError, app_error_handler
from app.db.mongo import create_database, create_indexes
from app.repositories.mongo import ChunkRepository, ChunkingJobRepository, DocumentPageRepository, DocumentRepository, IngestionJobRepository
from app.services.chunking.service import ChunkingService
from app.services.chunking.splitter import ChunkingSplitter
from app.services.chunking.tokenizer import TiktokenTokenizer
from app.services.ingestion import IngestionService
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
    service.set_chunking_service(chunking_service)
    queue = InProcessJobQueue(IngestionWorker(service).process)
    chunking_queue = InProcessJobQueue(ChunkingWorker(chunking_service).process)
    chunking_service.set_queue(chunking_queue)
    await queue.start()
    await chunking_queue.start()
    app.state.ingestion_service = service
    app.state.chunking_service = chunking_service
    app.state.job_queue = queue
    app.state.chunking_queue = chunking_queue
    yield
    await queue.stop()
    await chunking_queue.stop()
    client.close()


app = FastAPI(title="doc-process-rag", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
app.add_exception_handler(AppError, app_error_handler)
app.include_router(ingest_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
