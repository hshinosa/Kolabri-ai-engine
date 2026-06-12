from __future__ import annotations

from app.services.document_processing.chunking import (
    ChunkSpec,
    clean_text,
    create_chunks,
)


def test_clean_text_collapses_whitespace_and_strips_control():
    src = "hello   world\x00\nfoo\n\n\n\nbar"
    assert clean_text(src) == "hello world foo bar"


def test_clean_text_returns_empty_for_blank():
    assert clean_text("   \n\t  ") == ""


def test_create_chunks_returns_single_chunk_when_under_size():
    chunks = create_chunks(
        text="short text",
        document_id="d1",
        filename="a.pdf",
        page_number=1,
        chunk_size=1000,
        chunk_overlap=200,
    )
    assert len(chunks) == 1
    assert chunks[0].text == "short text"
    assert chunks[0].chunk_id == "d1_p1_c0"
    assert chunks[0].metadata["chunk_count"] == 1


def test_create_chunks_returns_empty_for_blank_text():
    chunks = create_chunks(
        text="   ",
        document_id="d1",
        filename="a.pdf",
        page_number=1,
        chunk_size=10,
        chunk_overlap=2,
    )
    assert chunks == []


def test_create_chunks_splits_with_overlap_and_advances():
    text = "Sentence one. Sentence two. Sentence three. Sentence four. Sentence five. Sentence six. Sentence seven."
    chunks = create_chunks(
        text=text,
        document_id="d1",
        filename="a.pdf",
        page_number=1,
        chunk_size=30,
        chunk_overlap=10,
    )
    assert len(chunks) >= 2
    for i, c in enumerate(chunks):
        assert c.chunk_id == f"d1_p1_c{i}"
        assert c.metadata["chunk_count"] == len(chunks)
        assert c.metadata["chunk_index"] == i


def test_create_chunks_metadata_pass_through():
    chunks = create_chunks(
        text="x" * 200,
        document_id="d1",
        filename="a.pdf",
        page_number=2,
        chunk_size=80,
        chunk_overlap=20,
        metadata={"course": "math", "section": "intro"},
    )
    for c in chunks:
        assert c.metadata["course"] == "math"
        assert c.metadata["section"] == "intro"
        assert c.metadata["page"] == 2


def test_create_chunks_prefers_sentence_boundary_when_splitting():
    text = "Alpha sentence here. Beta sentence follows. Gamma ends the block."
    chunks = create_chunks(
        text=text,
        document_id="d1",
        filename="a.pdf",
        page_number=1,
        chunk_size=35,
        chunk_overlap=5,
    )
    assert len(chunks) >= 2
    assert all(c.text.endswith(".") or "sentence" in c.text for c in chunks)


def test_create_chunks_handles_zero_overlap_progress():
    chunks = create_chunks(
        text="a" * 250,
        document_id="d1",
        filename="a.pdf",
        page_number=1,
        chunk_size=50,
        chunk_overlap=0,
    )
    assert len(chunks) >= 4
    char_ranges = [(c.metadata["char_start"], c.metadata["char_end"]) for c in chunks]
    for i in range(len(char_ranges) - 1):
        assert char_ranges[i + 1][0] >= char_ranges[i][1]


def test_create_chunks_advances_past_whitespace_padding_between_segments():
    text = "segmentone " * 4 + " " * 50 + "segmenttwo " * 4
    chunks = create_chunks(text, "d1", "f.txt", 1, 32, 8)
    assert chunks
    assert all(chunk.text.strip() for chunk in chunks)
