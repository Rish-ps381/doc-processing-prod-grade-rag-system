from __future__ import annotations

import json
from typing import Protocol, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.core.errors import AppError

OutputModel = TypeVar("OutputModel", bound=BaseModel)


class LLMProvider(Protocol):
    model: str

    async def generate(self, system_prompt: str, user_prompt: str, output_model: type[OutputModel]) -> OutputModel: ...


class OpenAILLMProvider:
    def __init__(self, api_key: str | None, model: str, timeout: float = 60.0) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    async def generate(self, system_prompt: str, user_prompt: str, output_model: type[OutputModel]) -> OutputModel:
        if not self.api_key:
            raise AppError("LLM_NOT_CONFIGURED", "An LLM API key is required to answer questions.", 503)
        schema = output_model.model_json_schema()
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"model": self.model, "temperature": 0, "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}], "response_format": {"type": "json_schema", "json_schema": {"name": "grounded_answer", "strict": True, "schema": schema}}},
            )
        if response.status_code >= 400:
            raise AppError("LLM_FAILED", "The language model could not answer the question.", 502)
        try:
            content = response.json()["choices"][0]["message"]["content"]
            return output_model.model_validate(json.loads(content))
        except (KeyError, IndexError, TypeError, json.JSONDecodeError, ValidationError) as exc:
            raise AppError("INVALID_LLM_RESPONSE", "The language model returned an invalid structured response.", 502) from exc
