from datetime import datetime, timezone

import httpx
from bs4 import BeautifulSoup
from pydantic import HttpUrl, TypeAdapter

from app.core.errors import AppError
from app.domain import CanonicalPage, ContentBlock, ParsedDocument, SourceType


class WebParser:
    def __init__(self, timeout_seconds: float = 15.0):
        self.timeout_seconds = timeout_seconds

    async def parse(self, source: bytes | str, *, source_name: str | None = None) -> ParsedDocument:
        url = str(source)
        try:
            parsed_url = TypeAdapter(HttpUrl).validate_python(url)
            if parsed_url.scheme not in {"http", "https"}:
                raise ValueError("unsupported protocol")
            async with httpx.AsyncClient(timeout=self.timeout_seconds, follow_redirects=True, headers={"User-Agent": "doc-process-rag/1.0"}) as client:
                response = await client.get(url)
                response.raise_for_status()
        except Exception as exc:
            raise AppError("WEB_FETCH_ERROR", "The web page could not be fetched.", 422) from exc
        try:
            soup = BeautifulSoup(response.text, "html.parser")
            for element in soup(["script", "style", "nav", "footer", "header", "aside", "form"]):
                element.decompose()
            title = soup.title.get_text(" ", strip=True) if soup.title else str(parsed_url)
            blocks: list[ContentBlock] = []
            for element in soup.select("h1, h2, h3, h4, h5, h6, p, li"):
                text = element.get_text(" ", strip=True)
                if text:
                    blocks.append(ContentBlock(type="heading" if element.name.startswith("h") else "paragraph", text=text, metadata={"tag": element.name}))
            if not blocks:
                raise AppError("EMPTY_DOCUMENT", "No meaningful text was extracted from the web page.", 422)
            return ParsedDocument(title=title, source_type=SourceType.URL, source_url=parsed_url, canonical_url=parsed_url, pages=[CanonicalPage(content=blocks, plain_text="\n".join(block.text for block in blocks))], retrieved_at=datetime.now(timezone.utc))
        except AppError:
            raise
        except Exception as exc:
            raise AppError("WEB_PARSE_ERROR", "Web page parsing failed.", 422) from exc
