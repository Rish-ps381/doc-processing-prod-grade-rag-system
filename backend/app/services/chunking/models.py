from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.domain import ChunkSource, DocumentChunk, new_id, utc_now


class ChunkingConfig(BaseModel):
    target_tokens: int = 600
    max_tokens: int = 800
    overlap_tokens: int = 100
    version: str = "v1"

    @property
    def overlap_size(self) -> int:
        return max(0, self.overlap_tokens)

    @property
    def safe_target(self) -> int:
        return min(self.target_tokens, self.max_tokens)


class ChunkCandidate(BaseModel):
    text: str
    source_page_number: int | None = None
    heading_path: list[str] = Field(default_factory=list)
    block_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChunkingResult(BaseModel):
    document_id: str
    version: str
    chunks: list[DocumentChunk]
    created_at: datetime = Field(default_factory=utc_now)


class ChunkingJob(BaseModel):
    id: str = Field(default_factory=lambda: new_id("chunkjob"))
    document_id: str
    tenant_id: str
    version: str
    status: str = "QUEUED"
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
