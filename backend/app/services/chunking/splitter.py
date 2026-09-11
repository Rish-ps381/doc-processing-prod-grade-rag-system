from __future__ import annotations

import re
from typing import Any

from app.core.errors import AppError
from app.domain import DocumentChunk, new_id
from app.services.chunking.tokenizer import Tokenizer


class ChunkingSplitter:
    def __init__(self, tokenizer: Tokenizer, *, target_tokens: int = 600, max_tokens: int = 800, overlap_tokens: int = 100, version: str = "v1") -> None:
        self.tokenizer = tokenizer
        self.target_tokens = target_tokens
        self.max_tokens = max_tokens
        self.overlap_tokens = overlap_tokens
        self.version = version

    def chunk_pages(self, pages: list[dict[str, Any]], *, document_id: str, chunking_version: str | None = None) -> list[dict[str, Any]]:
        version = chunking_version or self.version
        sections: list[dict[str, Any]] = []
        for page in pages:
            heading_path = list(page.get("metadata", {}).get("heading_path") or [])
            blocks = page.get("content", []) or []
            if not blocks:
                continue
            current: dict[str, Any] = {"heading_path": heading_path.copy(), "page_number": page.get("page_number"), "block_ids": [], "text_parts": []}
            for block in blocks:
                block_type = str(block.get("type") or "paragraph")
                text = str(block.get("text") or "").strip()
                if not text:
                    continue
                block_heading_path = list(block.get("metadata", {}).get("heading_path") or heading_path)
                if block_type == "heading":
                    if current["text_parts"]:
                        sections.append({**current, "heading_path": current["heading_path"], "block_ids": current["block_ids"].copy()})
                        current = {"heading_path": block_heading_path, "page_number": page.get("page_number"), "block_ids": [], "text_parts": []}
                    current["heading_path"] = block_heading_path
                    current["text_parts"].append(text)
                    current["block_ids"].append(block.get("block_id"))
                    continue
                current["text_parts"].append(text)
                current["block_ids"].append(block.get("block_id"))
                current["heading_path"] = block_heading_path
            if current["text_parts"]:
                sections.append({**current, "heading_path": current["heading_path"], "block_ids": current["block_ids"].copy()})

        if not sections:
            return []

        chunk_records: list[dict[str, Any]] = []
        for section in sections:
            section_text = "\n".join(part for part in section.get("text_parts", []) if part)
            if not section_text.strip():
                continue
            chunk_records.extend(self._split_section(section, document_id=document_id, version=version, base_index=len(chunk_records)))

        chunk_records = self._apply_overlap(chunk_records)
        for i, record in enumerate(chunk_records):
            if i > 0:
                record["previous_chunk_id"] = chunk_records[i - 1]["chunk_id"]
            if i < len(chunk_records) - 1:
                record["next_chunk_id"] = chunk_records[i + 1]["chunk_id"]
        return chunk_records

    def _split_section(self, section: dict[str, Any], *, document_id: str, version: str, base_index: int) -> list[dict[str, Any]]:
        heading_path = list(section.get("heading_path") or [])
        section_text = "\n".join(part for part in section.get("text_parts", []) if part)
        if self.tokenizer.count_tokens(section_text) <= self.max_tokens:
            return [self._make_chunk(document_id, version, base_index, section_text, section["page_number"], heading_path, section.get("block_ids", []))]

        parts: list[str] = []
        for paragraph in self._split_paragraphs(section_text):
            paragraph = paragraph.strip()
            if paragraph:
                parts.append(paragraph)

        if parts:
            grouped: list[list[str]] = []
            current: list[str] = []
            tokens = 0
            for paragraph in parts:
                paragraph_tokens = self.tokenizer.count_tokens(paragraph)
                if current and tokens + paragraph_tokens > self.target_tokens and tokens > 0:
                    grouped.append(current)
                    current = [paragraph]
                    tokens = paragraph_tokens
                else:
                    current.append(paragraph)
                    tokens += paragraph_tokens
            if current:
                grouped.append(current)
            output: list[str] = []
            for group in grouped:
                text = "\n\n".join(group)
                if self.tokenizer.count_tokens(text) <= self.max_tokens:
                    output.append(text)
                    continue
                output.extend(self._split_by_sentences_or_tokens(text, heading_path))
            if output:
                return [self._make_chunk(document_id, version, base_index + idx, text, section["page_number"], heading_path, section.get("block_ids", [])) for idx, text in enumerate(output)]

        sentences = self._split_sentences(section_text)
        if sentences:
            return [self._make_chunk(document_id, version, base_index + idx, text, section["page_number"], heading_path, section.get("block_ids", [])) for idx, text in enumerate(self._split_by_sentences_or_tokens(section_text, heading_path))]

        raise AppError("NO_SOURCE_CONTENT", "No chunkable content was found in the document.", 422)

    def _split_by_sentences_or_tokens(self, text: str, heading_path: list[str]) -> list[str]:
        sentences = self._split_sentences(text)
        if not sentences:
            return [text]
        chunks: list[str] = []
        current: list[str] = []
        current_tokens = 0
        for sentence in sentences:
            sentence_tokens = self.tokenizer.count_tokens(sentence)
            if current and current_tokens + sentence_tokens > self.target_tokens:
                chunks.append(" ".join(current))
                current = [sentence]
                current_tokens = sentence_tokens
            else:
                current.append(sentence)
                current_tokens += sentence_tokens
        if current:
            chunks.append(" ".join(current))

        for idx, chunk in enumerate(chunks):
            if self.tokenizer.count_tokens(chunk) <= self.max_tokens:
                continue
            token_windows = self._token_window_split(chunk)
            chunks[idx:idx + 1] = token_windows
        return [chunk.strip() for chunk in chunks if chunk.strip()]

    def _split_paragraphs(self, text: str) -> list[str]:
        return [paragraph.strip() for paragraph in re.split(r"\n\s*\n+", text.strip()) if paragraph.strip()]

    def _token_window_split(self, text: str) -> list[str]:
        tokens = self.tokenizer.encode(text)
        if not tokens:
            return []
        windows: list[str] = []
        start = 0
        while start < len(tokens):
            end = min(len(tokens), start + self.max_tokens)
            window_tokens = tokens[start:end]
            if not window_tokens:
                break
            windows.append(self.tokenizer.decode(window_tokens).strip())
            if end >= len(tokens):
                break
            start = max(start + self.target_tokens, end - self.overlap_tokens)
        return [chunk for chunk in windows if chunk]

    def _apply_overlap(self, chunk_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if len(chunk_records) <= 1:
            return chunk_records
        overlapped: list[dict[str, Any]] = []
        for index, record in enumerate(chunk_records):
            if index == 0:
                overlapped.append(record)
                continue
            previous = overlapped[-1]
            previous_tokens = self.tokenizer.encode(previous["text"])
            overlap_tokens = previous_tokens[-self.overlap_tokens :] if self.overlap_tokens else []
            overlap_text = self.tokenizer.decode(overlap_tokens).strip()
            merged_text = (overlap_text + " " + record["text"]).strip() if overlap_text else record["text"]
            if self.tokenizer.count_tokens(merged_text) > self.max_tokens:
                merged_tokens = self.tokenizer.encode(merged_text)
                merged_text = self.tokenizer.decode(merged_tokens[: self.max_tokens]).strip()
            record["text"] = merged_text
            record["token_count"] = self.tokenizer.count_tokens(merged_text)
            overlapped.append(record)
        return overlapped

    def _make_chunk(self, document_id: str, version: str, chunk_index: int, text: str, page_number: int | None, heading_path: list[str], block_ids: list[str]) -> dict[str, Any]:
        token_count = self.tokenizer.count_tokens(text)
        if token_count <= 0:
            raise AppError("INVALID_CHUNK", "Encountered an empty chunk during tokenization.", 500)
        layer = DocumentChunk(
            chunk_id=new_id("chk"),
            document_id=document_id,
            chunking_version=version,
            chunk_index=chunk_index,
            text=text.strip(),
            token_count=token_count,
            source={"page_number": page_number, "heading_path": heading_path, "block_ids": block_ids},
        )
        return layer.model_dump(exclude_none=True)

    def _split_sentences(self, text: str) -> list[str]:
        parts = re.split(r"(?<=[.!?])\s+", text.strip())
        return [part.strip() for part in parts if part.strip()]
