from __future__ import annotations

from app.core.errors import AppError


def validate_chunk_config(target_tokens: int, max_tokens: int, overlap_tokens: int) -> None:
    if target_tokens <= 0 or max_tokens <= 0:
        raise AppError("INVALID_CHUNK_CONFIG", "Chunk target and maximum must be positive integers.", 500)
    if overlap_tokens < 0:
        raise AppError("INVALID_CHUNK_CONFIG", "Chunk overlap must be non-negative.", 500)
    if target_tokens > max_tokens:
        raise AppError("INVALID_CHUNK_CONFIG", "Chunk target cannot exceed the maximum chunk size.", 500)
    if overlap_tokens >= target_tokens:
        raise AppError("INVALID_CHUNK_CONFIG", "Chunk overlap must be smaller than the target chunk size.", 500)


def validate_chunk(chunk: dict[str, object], max_tokens: int) -> None:
    text = str(chunk.get("text", "")).strip()
    if not text:
        raise AppError("INVALID_CHUNK", "Chunk text cannot be empty.", 500)
    if not chunk.get("document_id"):
        raise AppError("INVALID_CHUNK", "Chunk document_id is required.", 500)
    if not chunk.get("chunking_version"):
        raise AppError("INVALID_CHUNK", "Chunking version is required.", 500)
    token_count = int(chunk.get("token_count", 0))
    if token_count <= 0:
        raise AppError("INVALID_CHUNK", "Chunk token_count must be positive.", 500)
    if token_count > max_tokens:
        raise AppError("INVALID_CHUNK", "Chunk exceeds configured maximum token size.", 500)
    if not chunk.get("source"):
        raise AppError("INVALID_CHUNK", "Chunk provenance is required.", 500)
