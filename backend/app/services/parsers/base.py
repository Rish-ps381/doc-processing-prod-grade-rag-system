from typing import Protocol

from app.domain import ParsedDocument


class DocumentParser(Protocol):
    async def parse(self, source: bytes | str, *, source_name: str | None = None) -> ParsedDocument: ...
