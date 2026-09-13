from typing import Any

from fastapi import APIRouter, Request, status
from pydantic import BaseModel, Field

from app.core.errors import AppError
from app.services.chat import ChatService

router = APIRouter(prefix="/chat", tags=["chat"])


def service(request: Request) -> ChatService:
    return request.app.state.chat_service


class ConversationCreate(BaseModel):
    document_ids: list[str] = Field(default_factory=list)
    title: str | None = None


class MessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=20_000)
    document_ids: list[str] | None = None


@router.post("/conversations", status_code=status.HTTP_201_CREATED)
async def create_conversation(payload: ConversationCreate, request: Request) -> dict[str, Any]:
    return await service(request).create_conversation("tenant_development", "user_development", payload.document_ids, payload.title)


@router.get("/conversations")
async def list_conversations(request: Request) -> list[dict[str, Any]]:
    return await service(request).list_conversations("tenant_development", "user_development")


@router.get("/conversations/{conversation_id}")
async def get_conversation(conversation_id: str, request: Request) -> dict[str, Any]:
    conversation = await service(request).get_conversation(conversation_id, "tenant_development")
    if conversation is None:
        raise AppError("CONVERSATION_NOT_FOUND", "The conversation does not exist.", 404)
    return conversation


@router.get("/conversations/{conversation_id}/messages")
async def list_messages(conversation_id: str, request: Request) -> list[dict[str, Any]]:
    return await service(request).list_messages(conversation_id, "tenant_development")


@router.post("/conversations/{conversation_id}/messages")
async def send_message(conversation_id: str, payload: MessageCreate, request: Request) -> dict[str, Any]:
    result = await service(request).ask(conversation_id, "tenant_development", "user_development", payload.content, payload.document_ids)
    return result.model_dump()
