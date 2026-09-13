from __future__ import annotations

from typing import Protocol

import httpx

from app.core.errors import AppError


class Reranker(Protocol):
    model: str

    async def rerank(self, query: str, documents: list[str], top_k: int) -> list[tuple[int, float]]: ...


class CohereReranker:
    def __init__(self, api_key: str | None, model: str, timeout: float = 20.0) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    async def rerank(self, query: str, documents: list[str], top_k: int) -> list[tuple[int, float]]:
        if not self.api_key:
            raise AppError("RERANKER_NOT_CONFIGURED", "A reranker API key is required for retrieval.", 503)
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                "https://api.cohere.com/v2/rerank",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"model": self.model, "query": query, "documents": documents, "top_n": top_k},
            )
        if response.status_code >= 400:
            raise AppError("RERANKING_FAILED", "The reranker provider rejected the request.", 502)
        results = response.json().get("results", [])
        return [(int(item["index"]), float(item["relevance_score"])) for item in results]
