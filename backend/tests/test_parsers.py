import pytest

from app.core.errors import AppError
from app.services.parsers.markdown import MarkdownParser
from app.services.parsers.web import WebParser


@pytest.mark.asyncio
async def test_markdown_preserves_headings_and_lists() -> None:
    parsed = await MarkdownParser().parse("# Authentication\n\n## Access Tokens\n\nAccess tokens expire.\n\n- Rotate keys", source_name="guide.md")
    assert parsed.pages[0].content[0].type == "heading"
    assert parsed.pages[0].content[1].metadata["heading_path"] == ["Authentication", "Access Tokens"]
    assert parsed.pages[0].content[-1].type == "list_item"


@pytest.mark.asyncio
async def test_empty_markdown_fails() -> None:
    with pytest.raises(AppError) as error:
        await MarkdownParser().parse("  ")
    assert error.value.code == "EMPTY_DOCUMENT"


@pytest.mark.asyncio
async def test_web_parser_extracts_meaningful_elements(monkeypatch: pytest.MonkeyPatch) -> None:
    class Response:
        text = "<html><title>Guide</title><nav>Menu</nav><main><h1>Guide</h1><p>Useful content.</p></main></html>"

        def raise_for_status(self) -> None:
            return None

    class Client:
        async def __aenter__(self) -> "Client":
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def get(self, url: str) -> Response:
            return Response()

    monkeypatch.setattr("app.services.parsers.web.httpx.AsyncClient", lambda **kwargs: Client())
    parsed = await WebParser().parse("https://example.com")
    assert parsed.title == "Guide"
    assert "Useful content." in parsed.pages[0].plain_text
    assert "Menu" not in parsed.pages[0].plain_text
