from io import BytesIO

from pypdf import PdfReader

from app.core.errors import AppError
from app.domain import CanonicalPage, ContentBlock, FileType, ParsedDocument, SourceType


class PDFParser:
    async def parse(self, source: bytes | str, *, source_name: str | None = None) -> ParsedDocument:
        try:
            reader = PdfReader(BytesIO(source) if isinstance(source, bytes) else source)
            pages: list[CanonicalPage] = []
            for number, pdf_page in enumerate(reader.pages, start=1):
                text = (pdf_page.extract_text() or "").strip()
                if not text:
                    continue
                blocks = [ContentBlock(type="paragraph", text=paragraph.strip()) for paragraph in text.split("\n\n") if paragraph.strip()]
                pages.append(CanonicalPage(page_number=number, content=blocks, plain_text=text))
            if not pages:
                raise AppError("EMPTY_DOCUMENT", "No readable text was extracted from the PDF.", 422)
            return ParsedDocument(title=source_name or "PDF document", source_type=SourceType.FILE, file_type=FileType.PDF, mime_type="application/pdf", pages=pages)
        except AppError:
            raise
        except Exception as exc:
            raise AppError("PDF_PARSE_ERROR", "PDF parsing failed.", 422) from exc
