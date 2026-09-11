import pytest

from app.services.chunking.splitter import ChunkingSplitter
from app.services.chunking.tokenizer import TiktokenTokenizer


@pytest.fixture
def splitter() -> ChunkingSplitter:
    return ChunkingSplitter(TiktokenTokenizer())


def test_tokenizer_counts_tokens() -> None:
    tokenizer = TiktokenTokenizer()
    count = tokenizer.count_tokens("Access tokens are required for every API request.")
    assert count > 0


def test_section_chunking_preserves_heading_and_provenance(splitter: ChunkingSplitter) -> None:
    pages = [{
        "document_id": "doc_123",
        "page_number": 1,
        "content": [
            {"block_id": "blk_001", "type": "heading", "text": "Authentication", "metadata": {"heading_path": ["Authentication"]}},
            {"block_id": "blk_002", "type": "paragraph", "text": "Access tokens are required for every API request.", "metadata": {"heading_path": ["Authentication"]}},
            {"block_id": "blk_003", "type": "paragraph", "text": "Tokens expire after 60 minutes.", "metadata": {"heading_path": ["Authentication"]}},
            {"block_id": "blk_004", "type": "paragraph", "text": "Clients must provide the token in the Authorization header.", "metadata": {"heading_path": ["Authentication"]}},
        ],
        "plain_text": "Authentication\nAccess tokens are required for every API request.\nTokens expire after 60 minutes.\nClients must provide the token in the Authorization header.",
        "metadata": {"heading_path": ["Authentication"]},
    }]

    chunks = splitter.chunk_pages(pages, document_id="doc_123", chunking_version="v1")
    assert len(chunks) >= 1
    assert chunks[0]["source"]["heading_path"] == ["Authentication"]
    assert set(chunks[0]["source"]["block_ids"]) == {"blk_001", "blk_002", "blk_003", "blk_004"}


def test_oversized_paragraph_is_split(splitter: ChunkingSplitter) -> None:
    paragraph = "This is a long paragraph with repeated content. " * 400
    pages = [{
        "document_id": "doc_456",
        "page_number": 2,
        "content": [{"block_id": "blk_100", "type": "paragraph", "text": paragraph, "metadata": {"heading_path": ["Large Section"]}}],
        "plain_text": paragraph,
        "metadata": {"heading_path": ["Large Section"]},
    }]

    chunks = splitter.chunk_pages(pages, document_id="doc_456", chunking_version="v1")
    assert len(chunks) > 1
    assert all(chunk["token_count"] <= 800 for chunk in chunks)


def test_overlap_is_applied_for_large_section(splitter: ChunkingSplitter) -> None:
    long_text = " ".join(["Sentence number {}.".format(i) for i in range(1, 500)])
    pages = [{
        "document_id": "doc_789",
        "page_number": 1,
        "content": [{"block_id": "blk_200", "type": "paragraph", "text": long_text, "metadata": {"heading_path": ["Policy"]}}],
        "plain_text": long_text,
        "metadata": {"heading_path": ["Policy"]},
    }]

    chunks = splitter.chunk_pages(pages, document_id="doc_789", chunking_version="v1")
    assert len(chunks) > 1
    assert chunks[0]["next_chunk_id"] == chunks[1]["chunk_id"]
    assert chunks[1]["previous_chunk_id"] == chunks[0]["chunk_id"]


def test_chunking_remains_deterministic(splitter: ChunkingSplitter) -> None:
    pages = [{
        "document_id": "doc_abc",
        "page_number": 1,
        "content": [
            {"block_id": "blk_1", "type": "heading", "text": "Overview", "metadata": {"heading_path": ["Overview"]}},
            {"block_id": "blk_2", "type": "paragraph", "text": "A stable chunking algorithm should produce the same chunk sequences for the same input.", "metadata": {"heading_path": ["Overview"]}},
            {"block_id": "blk_3", "type": "paragraph", "text": "The order of blocks must remain deterministic across repeated runs.", "metadata": {"heading_path": ["Overview"]}},
        ],
        "plain_text": "Overview\nA stable chunking algorithm should produce the same chunk sequences for the same input.\nThe order of blocks must remain deterministic across repeated runs.",
        "metadata": {"heading_path": ["Overview"]},
    }]

    first = splitter.chunk_pages(pages, document_id="doc_abc", chunking_version="v1")
    second = splitter.chunk_pages(pages, document_id="doc_abc", chunking_version="v1")
    assert [chunk["text"] for chunk in first] == [chunk["text"] for chunk in second]
