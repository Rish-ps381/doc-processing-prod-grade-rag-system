from __future__ import annotations

from typing import Protocol

import httpx

from app.core.errors import AppError


class EmbeddingProvider(Protocol):
    model: str

    async def embed(self, texts: list[str]) -> list[list[float]]: ...


class OpenAIEmbeddingProvider:
    def __init__(self, api_key: str | None, model: str, timeout: float = 30.0) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not self.api_key:
            raise AppError("EMBEDDING_NOT_CONFIGURED", "An embedding API key is required for indexing.", 503)
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                "https://api.openai.com/v1/embeddings",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"model": self.model, "input": texts},
            )
        if response.status_code == 429:
            raise AppError("EMBEDDING_QUOTA_EXCEEDED", "The embedding provider has no remaining credits. Add credits or configure a different embedding provider.", 429)
        if response.status_code >= 400:
            raise AppError("EMBEDDING_FAILED", "The embedding provider rejected the request.", 502)
        payload = response.json()
        data = sorted(payload.get("data", []), key=lambda item: item.get("index", 0))
        vectors = [item.get("embedding") for item in data]
        if len(vectors) != len(texts) or any(not vector for vector in vectors):
            raise AppError("EMBEDDING_FAILED", "The embedding provider returned an invalid response.", 502)
        return vectors
