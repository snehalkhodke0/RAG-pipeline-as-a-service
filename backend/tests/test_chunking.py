"""Chunker unit tests: overlap correctness, page number preservation, minimum size
filtering. No database required.
"""

from __future__ import annotations

from app.services.chunking import chunk_document, count_tokens
from app.services.parsing import ParsedDocument, ParsedSection


def _make_paragraph(word: str, n_words: int) -> str:
    return " ".join([word] * n_words)


def test_page_number_preserved_per_section() -> None:
    parsed = ParsedDocument(
        sections=[
            ParsedSection(text=_make_paragraph("alpha", 100), page_number=1, section_title=None),
            ParsedSection(text=_make_paragraph("beta", 100), page_number=2, section_title=None),
        ],
        page_count=2,
    )
    chunks = chunk_document(parsed, chunk_size=512, chunk_overlap=64, min_chunk_tokens=1)
    assert chunks, "expected at least one chunk"
    assert all(c.page_number in (1, 2) for c in chunks)
    page_1_chunks = [c for c in chunks if c.page_number == 1]
    page_2_chunks = [c for c in chunks if c.page_number == 2]
    assert all("alpha" in c.content and "beta" not in c.content for c in page_1_chunks)
    assert all("beta" in c.content and "alpha" not in c.content for c in page_2_chunks)


def test_minimum_size_filtering_drops_tiny_chunks() -> None:
    parsed = ParsedDocument(
        sections=[ParsedSection(text="too short", page_number=1, section_title=None)],
        page_count=1,
    )
    chunks = chunk_document(parsed, chunk_size=512, chunk_overlap=64, min_chunk_tokens=30)
    assert chunks == []


def test_minimum_size_respects_custom_threshold() -> None:
    parsed = ParsedDocument(
        sections=[ParsedSection(text="too short", page_number=1, section_title=None)],
        page_count=1,
    )
    chunks = chunk_document(parsed, chunk_size=512, chunk_overlap=64, min_chunk_tokens=1)
    assert len(chunks) == 1


def test_overlap_correctness_between_consecutive_chunks() -> None:
    # Build one long paragraph (no blank-line breaks) long enough to force multiple
    # sentence-boundary splits, each sentence individually well under chunk_size.
    sentences = [f"Sentence number {i} carries unique content here." for i in range(80)]
    text = " ".join(sentences)
    parsed = ParsedDocument(
        sections=[ParsedSection(text=text, page_number=1, section_title="Intro")],
        page_count=1,
    )
    chunk_size = 60
    overlap = 20
    chunks = chunk_document(parsed, chunk_size=chunk_size, chunk_overlap=overlap, min_chunk_tokens=1)
    assert len(chunks) >= 2

    for c in chunks:
        assert c.token_count <= chunk_size + 5  # small slack for whole-sentence packing

    # Consecutive chunks must share at least one sentence of trailing/leading overlap.
    for prev, nxt in zip(chunks, chunks[1:]):
        prev_sentences = [s for s in prev.content.split(". ") if s]
        next_sentences = [s for s in nxt.content.split(". ") if s]
        shared = set(prev_sentences) & set(next_sentences)
        assert shared, f"expected shared overlap content between chunk {prev.chunk_index} and {nxt.chunk_index}"


def test_chunk_index_is_sequential_across_sections() -> None:
    parsed = ParsedDocument(
        sections=[
            ParsedSection(text=_make_paragraph("alpha", 50), page_number=1, section_title=None),
            ParsedSection(text=_make_paragraph("beta", 50), page_number=2, section_title=None),
        ],
        page_count=2,
    )
    chunks = chunk_document(parsed, chunk_size=512, chunk_overlap=64, min_chunk_tokens=1)
    indices = [c.chunk_index for c in chunks]
    assert indices == list(range(len(chunks)))


def test_section_title_preserved() -> None:
    parsed = ParsedDocument(
        sections=[ParsedSection(text=_make_paragraph("word", 60), page_number=None, section_title="Chapter 1")],
        page_count=None,
    )
    chunks = chunk_document(parsed, chunk_size=512, chunk_overlap=64, min_chunk_tokens=1)
    assert all(c.section_title == "Chapter 1" for c in chunks)


def test_count_tokens_nonzero_for_text() -> None:
    assert count_tokens("hello world") > 0
    assert count_tokens("") == 0
