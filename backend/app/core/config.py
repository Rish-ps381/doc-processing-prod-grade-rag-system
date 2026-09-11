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
    mongo_database: str = "doc_process_rag"
    local_storage_dir: str = "./storage"
    default_tenant_id: str = "tenant_development"
    worker_count: int = 1
    web_timeout_seconds: float = 15.0
    chunk_target_tokens: int = 600
    chunk_max_tokens: int = 800
    chunk_overlap_tokens: int = 100
    chunking_version: str = "v1"

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
        return self

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
