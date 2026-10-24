"""Token-aware recursive chunker.

Splitting strategy, tried in order, per paragraph unit that is too large to fit in one
chunk: paragraph breaks -> sentence breaks -> a hard token-count cut. Chunks are packed
greedily up to `chunk_size` tokens and adjacent chunks share `chunk_overlap` tokens of
trailing context. Chunking never crosses a section boundary (a PDF page, or the text
under one heading) so every chunk keeps a single, correct page_number/section_title.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

import tiktoken

from app.config import settings
from app.services.parsing import ParsedDocument

_ENCODING = tiktoken.get_encoding("cl100k_base")
_PARAGRAPH_SPLIT_RE = re.compile(r"\n\s*\n")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_WHITESPACE_RE = re.compile(r"\s+")


@dataclass
class DocumentChunk:
    content: str
    token_count: int
    page_number: Optional[int]
    section_title: Optional[str]
    chunk_index: int


def count_tokens(text: str) -> int:
    return len(_ENCODING.encode(text))


def _split_paragraphs(text: str) -> List[str]:
    """Splits on blank-line boundaries and collapses any remaining internal
    whitespace (soft line-wraps from the source file) to single spaces, so a chunk
    never carries a stray newline in the middle of a sentence.
    """
    return [_WHITESPACE_RE.sub(" ", p).strip() for p in _PARAGRAPH_SPLIT_RE.split(text) if p.strip()]


def _split_sentences(text: str) -> List[str]:
    return [s.strip() for s in _SENTENCE_SPLIT_RE.split(text) if s.strip()]


def _hard_cut(text: str, max_tokens: int) -> List[str]:
    tokens = _ENCODING.encode(text)
    if not tokens:
        return []
    return [_ENCODING.decode(tokens[i : i + max_tokens]) for i in range(0, len(tokens), max_tokens)]


def _split_oversized(text: str, max_tokens: int) -> List[str]:
    """Breaks `text` down into fine-grained units each <= max_tokens: sentences, or a
    hard token cut for any single sentence that is itself still too large. Returns
    small individual units (not pre-packed blobs) so the caller's greedy packing and
    overlap logic - which operates at unit granularity - stays within chunk_size.
    """
    if count_tokens(text) <= max_tokens:
        return [text]

    sentences = _split_sentences(text)
    if len(sentences) <= 1:
        return _hard_cut(text, max_tokens)

    units: List[str] = []
    for sentence in sentences:
        if count_tokens(sentence) > max_tokens:
            units.extend(_hard_cut(sentence, max_tokens))
        else:
            units.append(sentence)
    return units


def _units_for_section(section_text: str, chunk_size: int) -> List[str]:
    units: List[str] = []
    for paragraph in _split_paragraphs(section_text):
        units.extend(_split_oversized(paragraph, chunk_size))
    return units


def _build_overlap(units: List[str], overlap_tokens: int) -> Tuple[List[str], int]:
    if overlap_tokens <= 0:
        return [], 0
    selected: List[str] = []
    total = 0
    for unit in reversed(units):
        unit_tokens = count_tokens(unit)
        if total >= overlap_tokens:
            break
        selected.insert(0, unit)
        total += unit_tokens
    return selected, total


def _pack_units(units: List[str], chunk_size: int, chunk_overlap: int) -> List[str]:
    chunks: List[str] = []
    current: List[str] = []
    current_tokens = 0

    for unit in units:
        unit_tokens = count_tokens(unit)
        if current and current_tokens + unit_tokens > chunk_size:
            chunks.append(" ".join(current))
            current, current_tokens = _build_overlap(current, chunk_overlap)
        current.append(unit)
        current_tokens += unit_tokens

    if current:
        chunks.append(" ".join(current))
    return chunks


def chunk_document(
    parsed: ParsedDocument,
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
    min_chunk_tokens: int | None = None,
) -> List[DocumentChunk]:
    size = chunk_size if chunk_size is not None else settings.CHUNK_SIZE
    overlap = chunk_overlap if chunk_overlap is not None else settings.CHUNK_OVERLAP
    min_tokens = min_chunk_tokens if min_chunk_tokens is not None else settings.MIN_CHUNK_TOKENS

    chunks: List[DocumentChunk] = []
    index = 0
    for section in parsed.sections:
        units = _units_for_section(section.text, size)
        for text in _pack_units(units, size, overlap):
            tokens = count_tokens(text)
            if tokens < min_tokens:
                continue
            chunks.append(
                DocumentChunk(
                    content=text,
                    token_count=tokens,
                    page_number=section.page_number,
                    section_title=section.section_title,
                    chunk_index=index,
                )
            )
            index += 1
    return chunks
