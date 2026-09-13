from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.errors import AppError
from app.providers.embeddings import EmbeddingProvider
from app.providers.reranker import Reranker
from app.providers.vector_store import VectorStore


@dataclass(frozen=True)
class Evidence:
    chunk_id: str
    document_id: str
    text: str
    document_name: str | None
    page_number: int | None
    heading_path: list[str]
    score: float
    retrieval_source: str = "hybrid"


class RetrievalService:
    def __init__(self, vector_store: VectorStore, embeddings: EmbeddingProvider, reranker: Reranker, initial_k: int, rerank_k: int, final_k: int, alpha: float, minimum_score: float) -> None:
        self.vector_store = vector_store
        self.embeddings = embeddings
        self.reranker = reranker
        self.initial_k = initial_k
        self.rerank_k = rerank_k
        self.final_k = final_k
        self.alpha = alpha
        self.minimum_score = minimum_score

    async def retrieve(self, query: str, tenant_id: str, document_ids: list[str]) -> list[Evidence]:
        if not query.strip() or not document_ids:
            return []
        vectors = await self.embeddings.embed([query.strip()])
        candidates = await self.vector_store.hybrid_search(query.strip(), vectors[0], tenant_id, document_ids, self.initial_k, self.alpha)
        if not candidates:
            return []
        reranked = await self.reranker.rerank(query.strip(), [str(item.get("text", "")) for item in candidates], min(self.rerank_k, len(candidates)))
        evidence: list[Evidence] = []
        for index, score in reranked:
            item: dict[str, Any] = candidates[index]
            if score < self.minimum_score or not item.get("text"):
                continue
            evidence.append(Evidence(chunk_id=item["chunk_id"], document_id=item["document_id"], text=item["text"], document_name=item.get("document_name"), page_number=item.get("page_number"), heading_path=item.get("heading_path") or [], score=score))
        return evidence[: self.final_k]

    @staticmethod
    def require_evidence(evidence: list[Evidence]) -> None:
        if not evidence:
            raise AppError("INSUFFICIENT_EVIDENCE", "I couldn't find enough information in the selected documents to answer that question reliably.", 422)
