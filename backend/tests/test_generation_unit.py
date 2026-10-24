"""Pure-logic tests for context building and citation-marker extraction. No network."""

from __future__ import annotations

import uuid

from app.services.generation import build_context_blocks, extract_citations
from app.services.retrieval import RetrievalResult


def _result(content: str, filename: str = "doc.pdf", page: int | None = 1) -> RetrievalResult:
    return RetrievalResult(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        content=content,
        score=1.0,
        filename=filename,
        page_number=page,
        section_title=None,
    )


def test_build_context_blocks_numbers_and_labels_sources() -> None:
    results = [_result("first chunk text", "a.pdf", 3), _result("second chunk text", "b.pdf", 7)]
    context = build_context_blocks(results)
    assert "[1] (source: a.pdf, page 3)" in context
    assert "[2] (source: b.pdf, page 7)" in context
    assert "first chunk text" in context
    assert "second chunk text" in context


def test_extract_citations_maps_markers_to_blocks() -> None:
    results = [_result("alpha"), _result("beta"), _result("gamma")]
    answer = "The answer involves alpha [1] and gamma [3]."
    citations = extract_citations(answer, results)
    assert [c.marker for c in citations] == [1, 3]
    assert citations[0].filename == results[0].filename
    assert citations[1].chunk_id == results[2].chunk_id


def test_extract_citations_drops_out_of_range_markers() -> None:
    results = [_result("alpha")]
    answer = "See [1] and also [99] which does not exist."
    citations = extract_citations(answer, results)
    assert [c.marker for c in citations] == [1]


def test_extract_citations_deduplicates_repeated_markers() -> None:
    results = [_result("alpha"), _result("beta")]
    answer = "First [1], again [1], then [2]."
    citations = extract_citations(answer, results)
    assert [c.marker for c in citations] == [1, 2]


def test_extract_citations_empty_when_no_markers() -> None:
    results = [_result("alpha")]
    assert extract_citations("No markers here.", results) == []
