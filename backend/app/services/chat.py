from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.core.errors import AppError
from app.domain import DocumentStatus, new_id, utc_now
from app.providers.llm import LLMProvider
from app.repositories.mongo import ConversationRepository, DocumentRepository, MessageRepository
from app.services.retrieval import Evidence, RetrievalService


class Citation(BaseModel):
    chunk_id: str
    document_id: str


class GroundedAnswer(BaseModel):
    answer: str
    can_answer: bool
    citations: list[Citation] = Field(default_factory=list)


class ChatResult(BaseModel):
    answer: str
    citations: list[dict[str, Any]]
    refused: bool = False
    prompt_version: str
    model: str


class ChatService:
    def __init__(self, documents: DocumentRepository, conversations: ConversationRepository, messages: MessageRepository, retrieval: RetrievalService, llm: LLMProvider, prompt_path: str) -> None:
        self.documents = documents
        self.conversations = conversations
        self.messages = messages
        self.retrieval = retrieval
        self.llm = llm
        self.prompt_path = Path(prompt_path)
        self.prompt_version = "grounded_answer_v1"

    async def create_conversation(self, tenant_id: str, user_id: str, document_ids: list[str], title: str | None = None) -> dict[str, Any]:
        now = utc_now()
        record = {"_id": new_id("conv"), "tenant_id": tenant_id, "user_id": user_id, "title": title or "New conversation", "selected_document_ids": document_ids, "created_at": now, "updated_at": now}
        await self.conversations.insert(record)
        return self._public(record)

    async def get_conversation(self, conversation_id: str, tenant_id: str) -> dict[str, Any] | None:
        record = await self.conversations.get(conversation_id)
        return self._public(record) if record and record.get("tenant_id") == tenant_id else None

    async def list_conversations(self, tenant_id: str, user_id: str) -> list[dict[str, Any]]:
        return [self._public(record) for record in await self.conversations.list_for_user(tenant_id, user_id)]

    async def list_messages(self, conversation_id: str, tenant_id: str) -> list[dict[str, Any]]:
        return [self._public(record) for record in await self.messages.list_for_conversation(conversation_id, tenant_id)]

    async def ask(self, conversation_id: str, tenant_id: str, user_id: str, question: str, document_ids: list[str] | None = None) -> ChatResult:
        conversation = await self.conversations.get(conversation_id)
        if not conversation or conversation.get("tenant_id") != tenant_id or conversation.get("user_id") != user_id:
            raise AppError("CONVERSATION_NOT_FOUND", "The conversation does not exist.", 404)
        scope = document_ids or conversation.get("selected_document_ids", [])
        records = [await self.documents.get(document_id) for document_id in scope]
        if any(record is None or record.get("tenant_id") != tenant_id for record in records):
            raise AppError("DOCUMENT_NOT_FOUND", "One or more selected documents do not exist.", 404)
        if any(record.get("status") != DocumentStatus.READY.value or not record.get("ready_for_ai") for record in records if record):
            raise AppError("DOCUMENT_NOT_READY", "Your document is still being processed. AI will be able to answer questions once processing is complete.", 409)
        if not question.strip():
            raise AppError("INVALID_REQUEST", "A question is required.", 422)
        evidence = await self.retrieval.retrieve(question, tenant_id, scope)
        self.retrieval.require_evidence(evidence)
        context = self._context(evidence)
        generated = await self.llm.generate(self._system_prompt(), f"QUESTION:\n{question.strip()}\n\nDOCUMENT EVIDENCE:\n{context}", GroundedAnswer)
        valid_ids = {item.chunk_id: item for item in evidence}
        citations = []
        for citation in generated.citations:
            item = valid_ids.get(citation.chunk_id)
            if item is None or item.document_id != citation.document_id:
                raise AppError("INVALID_LLM_RESPONSE", "The generated citations could not be verified.", 502)
            citations.append(self._citation(item))
        if not generated.can_answer or not citations:
            return await self._persist_result(conversation, question, "I couldn't find enough information in the selected documents to answer that question reliably.", [], refused=True)
        return await self._persist_result(conversation, question, generated.answer, citations)

    async def _persist_result(self, conversation: dict[str, Any], question: str, answer: str, citations: list[dict[str, Any]], refused: bool = False) -> ChatResult:
        now = utc_now()
        common = {"tenant_id": conversation["tenant_id"], "conversation_id": conversation["_id"], "created_at": now}
        await self.messages.insert({"_id": new_id("msg"), **common, "role": "user", "content": question})
        await self.messages.insert({"_id": new_id("msg"), **common, "role": "assistant", "content": answer, "citations": citations, "model": self.llm.model, "prompt_version": self.prompt_version, "retrieval_metadata": {"citation_count": len(citations), "refused": refused}})
        await self.conversations.update(conversation["_id"], {"updated_at": now})
        return ChatResult(answer=answer, citations=citations, refused=refused, prompt_version=self.prompt_version, model=self.llm.model)

    def _system_prompt(self) -> str:
        content = self.prompt_path.read_text(encoding="utf-8") if self.prompt_path.exists() else "Answer only from DOCUMENT EVIDENCE. Refuse when evidence is insufficient."
        return content

    @staticmethod
    def _context(evidence: list[Evidence]) -> str:
        return "\n\n".join(f"[{index}] chunk_id={item.chunk_id} document_id={item.document_id} page={item.page_number} heading={' > '.join(item.heading_path)}\n{item.text}" for index, item in enumerate(evidence, 1))

    @staticmethod
    def _citation(item: Evidence) -> dict[str, Any]:
        return {"chunk_id": item.chunk_id, "document_id": item.document_id, "document_name": item.document_name, "page_number": item.page_number, "heading_path": item.heading_path, "excerpt": item.text}

    @staticmethod
    def _public(record: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in record.items() if key != "_id"} | {"id": record["_id"]}
