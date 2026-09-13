from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "doc-process-rag"
    environment: str = "development"
    api_prefix: str = ""
    backend_base_url: str = "http://127.0.0.1:8000"
    mongo_uri: str = Field(
        default="mongodb://localhost:27017",
        validation_alias=AliasChoices("MONGODB_URI", "MONGO_URI"),
    )
    mongo_database: str = Field("doc_process_rag", validation_alias=AliasChoices("MONGODB_DATABASE", "MONGO_DATABASE"))
    local_storage_dir: str = "./storage"
    default_tenant_id: str = "tenant_development"
    worker_count: int = 1
    web_timeout_seconds: float = 15.0
    chunk_target_tokens: int = 600
    chunk_max_tokens: int = 800
    chunk_overlap_tokens: int = 100
    chunking_version: str = "v1"
    app_version: str = "0.1.0"
    cors_origins: str = "http://127.0.0.1:5173,http://localhost:5173"
    redis_url: str = "redis://localhost:6379/0"
    weaviate_url: str = "http://localhost:8080"
    weaviate_api_key: str | None = None
    weaviate_collection: str = "RetrievalChunk"
    embedding_provider: str = "openai"
    embedding_model: str = "text-embedding-3-small"
    embedding_api_key: str | None = None
    embedding_batch_size: int = 32
    llm_provider: str = "openai"
    llm_model: str = "gpt-4o-mini"
    llm_api_key: str | None = None
    reranker_provider: str = "cohere"
    reranker_model: str = "rerank-v3.5"
    reranker_api_key: str | None = None
    retrieval_top_k: int = 20
    rerank_top_k: int = 10
    final_context_k: int = 5
    hybrid_alpha: float = 0.5
    evidence_min_score: float = 0.05
    retrieval_cache_ttl_seconds: int = 300
    readiness_cache_ttl_seconds: int = 60
    max_upload_bytes: int = 25 * 1024 * 1024

    @model_validator(mode="after")
    def validate_chunking(self) -> "Settings":
        if self.chunk_target_tokens <= 0 or self.chunk_max_tokens <= 0:
            raise ValueError("Chunk target and maximum sizes must be greater than zero.")
        if self.chunk_overlap_tokens < 0:
            raise ValueError("Chunk overlap must be non-negative.")
        if self.chunk_target_tokens > self.chunk_max_tokens:
            raise ValueError("Chunk target size cannot be larger than the maximum chunk size.")
        if self.chunk_overlap_tokens >= self.chunk_target_tokens:
            raise ValueError("Chunk overlap must be smaller than the target chunk size.")
        if not 0 <= self.hybrid_alpha <= 1:
            raise ValueError("Hybrid alpha must be between zero and one.")
        if min(self.retrieval_top_k, self.rerank_top_k, self.final_context_k) <= 0:
            raise ValueError("Retrieval limits must be greater than zero.")
        return self

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def chunking_config(self) -> dict[str, int | str]:
        return {
            "target_tokens": self.chunk_target_tokens,
            "max_tokens": self.chunk_max_tokens,
            "overlap_tokens": self.chunk_overlap_tokens,
            "version": self.chunking_version,
        }

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[3] / ".env",
        env_prefix="",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
