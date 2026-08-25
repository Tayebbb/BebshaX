"""Text cleaning and document chunking for semantic evidence retrieval.

Splits cleaned documents into sentence-boundary preserved chunks for pgvector embedding.
"""

from __future__ import annotations

import re


def clean_text(raw: str) -> str:
    """Clean raw content by stripping HTML tags, scripts, and repetitive whitespace."""
    if not raw:
        return ""
    # Strip script and style blocks
    cleaned = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", raw, flags=re.IGNORECASE | re.DOTALL)
    # Strip remaining HTML tags
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    # Strip URLs
    cleaned = re.sub(r"https?://\S+", "", cleaned)
    # Fix spacing before punctuation
    cleaned = re.sub(r"\s+([.,!?;:])", r"\1", cleaned)
    # Normalize multiple newlines and spaces
    cleaned = re.sub(r"[\r\n]+", "\n", cleaned)
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    return cleaned.strip()


def chunk_document(
    text: str,
    chunk_size: int = 450,
    chunk_overlap: int = 50,
) -> list[str]:
    """Chunk text into semantic segments respecting sentence boundaries.

    Args:
        text: Cleaned input text.
        chunk_size: Target maximum characters per chunk.
        chunk_overlap: Number of characters to overlap between chunks.

    Returns:
        List of non-empty string chunks.
    """
    cleaned = clean_text(text)
    if not cleaned:
        return []

    if len(cleaned) <= chunk_size:
        return [cleaned]

    # Split into sentences
    sentences = re.split(r"(?<=[.?!;])\s+", cleaned)
    chunks: list[str] = []
    current_chunk: list[str] = []
    current_len = 0

    for sentence in sentences:
        s_len = len(sentence)
        if current_len + s_len > chunk_size and current_chunk:
            combined = " ".join(current_chunk).strip()
            if combined:
                chunks.append(combined)

            # Preserve overlap
            overlap_chunk: list[str] = []
            overlap_len = 0
            for prev_s in reversed(current_chunk):
                if overlap_len + len(prev_s) <= chunk_overlap:
                    overlap_chunk.insert(0, prev_s)
                    overlap_len += len(prev_s)
                else:
                    break

            current_chunk = overlap_chunk
            current_len = overlap_len

        current_chunk.append(sentence)
        current_len += s_len

    if current_chunk:
        combined = " ".join(current_chunk).strip()
        if combined and (not chunks or chunks[-1] != combined):
            chunks.append(combined)

    return chunks
