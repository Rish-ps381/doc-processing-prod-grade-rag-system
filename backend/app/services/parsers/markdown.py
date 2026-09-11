import re

from app.core.errors import AppError
from app.domain import CanonicalPage, ContentBlock, FileType, ParsedDocument, SourceType, new_id


class MarkdownParser:
    async def parse(self, source: bytes | str, *, source_name: str | None = None) -> ParsedDocument:
        try:
            text = source.decode("utf-8") if isinstance(source, bytes) else source
            if not text.strip():
                raise AppError("EMPTY_DOCUMENT", "The Markdown document is empty.", 422)
            blocks: list[ContentBlock] = []
            heading_path: list[str] = []
            paragraph: list[str] = []

            def flush_paragraph() -> None:
                if paragraph:
                    blocks.append(ContentBlock(type="paragraph", text=" ".join(paragraph), metadata={"heading_path": heading_path.copy()}))
                    paragraph.clear()

            for line in text.splitlines():
                match = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
                if match:
                    flush_paragraph()
                    level, heading = len(match.group(1)), match.group(2)
                    heading_path[:] = heading_path[: level - 1] + [heading]
                    blocks.append(ContentBlock(type="heading", text=heading, metadata={"level": level, "heading_path": heading_path.copy()}))
                elif re.match(r"^\s*[-*+]\s+", line):
                    flush_paragraph()
                    blocks.append(ContentBlock(type="list_item", text=re.sub(r"^\s*[-*+]\s+", "", line), metadata={"heading_path": heading_path.copy()}))
                elif line.strip():
                    paragraph.append(line.strip())
                else:
                    flush_paragraph()
            flush_paragraph()
            if not blocks:
                raise AppError("EMPTY_DOCUMENT", "The Markdown document has no readable content.", 422)
            return ParsedDocument(title=source_name or "Markdown document", source_type=SourceType.FILE, file_type=FileType.MARKDOWN, mime_type="text/markdown", pages=[CanonicalPage(page_number=None, content=blocks, plain_text="\n".join(block.text for block in blocks), metadata={"heading_path": []})])
        except AppError:
            raise
        except Exception as exc:
            raise AppError("MARKDOWN_PARSE_ERROR", "Markdown parsing failed.", 422) from exc
