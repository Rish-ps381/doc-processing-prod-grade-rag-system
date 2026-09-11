from __future__ import annotations

from typing import Protocol

import tiktoken


class Tokenizer(Protocol):
    def count_tokens(self, text: str) -> int: ...
    def encode(self, text: str) -> list[int]: ...
    def decode(self, tokens: list[int]) -> str: ...


class TiktokenTokenizer:
    """Tokenizer wrapper for the GPT-style token ecosystem used in later RAG stages."""

    def __init__(self, model: str = "gpt-4o-mini") -> None:
        self.model = model
        self._encoder = tiktoken.encoding_for_model(model)

    def count_tokens(self, text: str) -> int:
        if not text:
            return 0
        return len(self._encoder.encode(text))

    def encode(self, text: str) -> list[int]:
        return self._encoder.encode(text)

    def decode(self, tokens: list[int]) -> str:
        return self._encoder.decode(tokens)
