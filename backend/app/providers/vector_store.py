from __future__ import annotations

import json
from typing import Any, Protocol

import httpx

from app.core.errors import AppError


class VectorStore(Protocol):
    async def upsert(self, objects: list[dict[str, Any]]) -> None: ...

    async def hybrid_search(self, query: str, vector: list[float], tenant_id: str, document_ids: list[str], limit: int, alpha: float) -> list[dict[str, Any]]: ...


class WeaviateVectorStore:
    def __init__(self, url: str, collection: str, api_key: str | None = None, timeout: float = 30.0) -> None:
        self.url = url.rstrip("/")
        self.collection = collection
        self.api_key = api_key
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}

    async def ensure_collection(self) -> None:
        schema = {
            "class": self.collection,
            "vectorizer": "none",
            "properties": [
                {"name": "chunk_id", "dataType": ["text"]},
                {"name": "document_id", "dataType": ["text"]},
                {"name": "tenant_id", "dataType": ["text"]},
                {"name": "chunking_version", "dataType": ["text"]},
                {"name": "text", "dataType": ["text"]},
                {"name": "document_name", "dataType": ["text"]},
                {"name": "page_number", "dataType": ["int"]},
                {"name": "heading_path", "dataType": ["text[]"]},
                {"name": "content_hash", "dataType": ["text"]},
                {"name": "embedding_model", "dataType": ["text"]},
            ],
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(f"{self.url}/v1/schema/{self.collection}", headers=self._headers())
            if response.status_code == 200:
                return
            if response.status_code != 404:
                raise AppError("VECTOR_STORE_UNAVAILABLE", "Weaviate schema could not be inspected.", 502)
            response = await client.post(f"{self.url}/v1/schema", headers=self._headers(), json=schema)
        if response.status_code not in {200, 201}:
            raise AppError("VECTOR_STORE_UNAVAILABLE", "Weaviate collection could not be created.", 502)

    async def upsert(self, objects: list[dict[str, Any]]) -> None:
        if not objects:
            return
        payload = {"objects": [{"class": self.collection, "id": item["id"], "properties": item["properties"], "vector": item["vector"]} for item in objects]}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(f"{self.url}/v1/batch/objects", headers=self._headers(), json=payload)
        if response.status_code >= 400:
            raise AppError("INDEXING_FAILED", "Weaviate rejected the chunk batch.", 502)

    async def hybrid_search(self, query: str, vector: list[float], tenant_id: str, document_ids: list[str], limit: int, alpha: float) -> list[dict[str, Any]]:
        if not document_ids:
            return []
        escaped_query = json.dumps(query)
        document_operands = ", ".join(
            f'{{path: ["document_id"], operator: Equal, valueText: {json.dumps(document_id)}}}'
            for document_id in document_ids
        )
        document_filter = document_operands if len(document_ids) == 1 else f"{{operator: Or, operands: [{document_operands}]}}"
        graphql = {
            "query": f"""{{ Get {{ {self.collection}(hybrid: {{query: {escaped_query}, vector: {vector}, alpha: {alpha}}}, where: {{operator: And, operands: [{{path: [\"tenant_id\"], operator: Equal, valueText: {json.dumps(tenant_id)}}}, {document_filter}]}}, limit: {limit}) {{ chunk_id document_id text document_name page_number heading_path content_hash _additional {{ score }} }} }} }}"""
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(f"{self.url}/v1/graphql", headers=self._headers(), json=graphql)
        if response.status_code >= 400:
            raise AppError("RETRIEVAL_FAILED", "Weaviate retrieval failed.", 502)
        try:
            payload = response.json()
            if payload.get("errors"):
                raise AppError("RETRIEVAL_FAILED", "Weaviate returned a retrieval error.", 502, payload["errors"])
            return payload["data"]["Get"][self.collection]
        except (KeyError, TypeError) as exc:
            raise AppError("RETRIEVAL_FAILED", "Weaviate returned an invalid response.", 502) from exc
