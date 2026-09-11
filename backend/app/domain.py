from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, HttpUrl


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def new_id(prefix: str) -> str:
    from uuid import uuid4

    return f"{prefix}_{uuid4().hex}"


class SourceType(str, Enum):
    FILE = "file"
    URL = "url"


class FileType(str, Enum):
    PDF = "pdf"
    MARKDOWN = "markdown"


class DocumentStatus(str, Enum):
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ChunkingStatus(str, Enum):
    PENDING = "PENDING"
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class JobStatus(str, Enum):
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ContentBlock(BaseModel):
    block_id: str = Field(default_factory=lambda: new_id("blk"))
    type: str
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class CanonicalPage(BaseModel):
    page_number: int | None = None
    content: list[ContentBlock]
    plain_text: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class ParsedDocument(BaseModel):
    title: str
    source_type: SourceType
    file_type: FileType | None = None
    mime_type: str | None = None
    source_url: HttpUrl | None = None
    canonical_url: HttpUrl | None = None
    language: str | None = None
    pages: list[CanonicalPage]
    retrieved_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def character_count(self) -> int:
        return sum(len(page.plain_text) for page in self.pages)


class DocumentRecord(BaseModel):
    id: str
    tenant_id: str
    name: str
    title: str | None = None
    source_type: SourceType
    file_type: FileType | None = None
    mime_type: str | None = None
    status: DocumentStatus
    source: dict[str, Any]
    language: str | None = None
    chunking_status: ChunkingStatus = ChunkingStatus.PENDING
    chunking_version: str | None = None
    ready_for_ai: bool = False
    version: int = 1
    content_stats: dict[str, int] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class JobError(BaseModel):
    code: str
    message: str


class IngestionJobRecord(BaseModel):
    id: str
    document_id: str
    tenant_id: str
    job_type: str = "DOCUMENT_INGESTION"
    status: JobStatus
    attempt: int = 0
    max_attempts: int = 3
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: JobError | None = None
    created_at: datetime
    updated_at: datetime


class ChunkingJobRecord(BaseModel):
    id: str
    document_id: str
    tenant_id: str
    job_type: str = "DOCUMENT_CHUNKING"
    status: ChunkingStatus
    version: str
    attempt: int = 0
    max_attempts: int = 3
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: JobError | None = None
    created_at: datetime
    updated_at: datetime


class ChunkSource(BaseModel):
    page_number: int | None = None
    heading_path: list[str] = Field(default_factory=list)
    block_ids: list[str] = Field(default_factory=list)


class DocumentChunk(BaseModel):
    chunk_id: str = Field(default_factory=lambda: new_id("chk"))
    document_id: str
    chunking_version: str
    chunk_index: int
    text: str
    token_count: int
    source: ChunkSource
    previous_chunk_id: str | None = None
    next_chunk_id: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
