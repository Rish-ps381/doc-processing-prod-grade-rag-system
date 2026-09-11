from app.core.errors import AppError
from app.domain import FileType
from app.services.parsers.base import DocumentParser
from app.services.parsers.markdown import MarkdownParser
from app.services.parsers.pdf import PDFParser
from app.services.parsers.web import WebParser


class ParserFactory:
    def __init__(self, web_timeout_seconds: float = 15.0):
        self._parsers: dict[str, DocumentParser] = {
            FileType.PDF.value: PDFParser(),
            FileType.MARKDOWN.value: MarkdownParser(),
            "url": WebParser(web_timeout_seconds),
        }

    def get(self, source_type: str, file_type: str | None = None) -> DocumentParser:
        key = file_type if source_type == "file" else "url"
        try:
            return self._parsers[key]
        except KeyError as exc:
            raise AppError("UNSUPPORTED_SOURCE_TYPE", "The source type is not supported.", 422) from exc
