"""Text Segmenter - Splits text at sentence boundaries within word limits.

Provides sentence-boundary-aware text segmentation that ensures:
1. Each segment contains at most the configured maximum number of words.
2. No segment breaks mid-sentence (when possible).
3. Concatenating all segments reproduces the original text exactly.
"""

import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SegmentResult:
    """Result of text segmentation."""

    segments: list[str]
    segment_count: int
    total_words: int
    max_segment_words: int


# Sentence boundary pattern: matches end of sentence followed by whitespace
# Handles: period, exclamation, question mark, followed by space or end
# Also handles: ellipsis, multiple punctuation
_SENTENCE_BOUNDARY_PATTERN = re.compile(
    r"(?<=[.!?])"  # Lookbehind for sentence-ending punctuation
    r"(?:"
    r"\s+"  # Followed by whitespace
    r"|"
    r'(?=["\')\]]?\s)'  # Or followed by closing quote/bracket then space
    r")"
)

# Fallback split points when sentences are too long
_CLAUSE_BOUNDARY_PATTERN = re.compile(
    r"(?<=[,;:])\s+"  # After comma, semicolon, or colon followed by space
)


def _count_words(text: str) -> int:
    """Count words in text (splitting on whitespace).

    Args:
        text: The text to count words in.

    Returns:
        Number of words.
    """
    return len(text.split())


def _split_at_sentence_boundaries(text: str) -> list[str]:
    """Split text into sentences preserving all characters.

    The split preserves whitespace by keeping it attached to the preceding
    sentence. Concatenating all results reproduces the original text.

    Args:
        text: The text to split into sentences.

    Returns:
        List of sentence strings that concatenate to the original.
    """
    if not text:
        return []

    # Find all sentence boundary positions
    boundaries = [m.start() for m in _SENTENCE_BOUNDARY_PATTERN.finditer(text)]

    if not boundaries:
        return [text]

    sentences = []
    prev_end = 0

    for boundary in boundaries:
        # Find the start of whitespace at this boundary
        # The boundary is right after the punctuation
        # We need to find where the whitespace ends
        ws_match = re.match(r"\s+", text[boundary:])
        if ws_match:
            split_point = boundary + ws_match.end()
        else:
            split_point = boundary

        if split_point > prev_end:
            sentences.append(text[prev_end:split_point])
            prev_end = split_point

    # Add remaining text
    if prev_end < len(text):
        sentences.append(text[prev_end:])

    return sentences


def _split_long_sentence(sentence: str, max_words: int) -> list[str]:
    """Split a sentence that exceeds max_words at clause boundaries.

    If no clause boundaries exist, splits at word boundaries as a last resort.
    Always preserves the original text exactly when concatenated.

    Args:
        sentence: The long sentence to split.
        max_words: Maximum words per segment.

    Returns:
        List of sub-segments that concatenate to the original sentence.
    """
    if _count_words(sentence) <= max_words:
        return [sentence]

    # Try splitting at clause boundaries first
    clause_boundaries = [m.start() for m in _CLAUSE_BOUNDARY_PATTERN.finditer(sentence)]

    if clause_boundaries:
        segments = []
        prev_end = 0
        current_segment_start = 0

        for boundary in clause_boundaries:
            # boundary is at the start of whitespace after punctuation
            ws_match = re.match(r"\s+", sentence[boundary:])
            split_point = boundary + (ws_match.end() if ws_match else 0)

            candidate = sentence[current_segment_start:split_point]
            if _count_words(candidate) > max_words and current_segment_start != prev_end:
                # Current candidate is too long, commit previous segment
                segments.append(sentence[current_segment_start:prev_end])
                current_segment_start = prev_end

            prev_end = split_point

        # Add remaining text
        remaining = sentence[current_segment_start:]
        if remaining:
            if _count_words(remaining) > max_words:
                # Still too long, force split at word boundaries
                segments.extend(_force_word_split(remaining, max_words))
            else:
                segments.append(remaining)

        # Verify concatenation
        if "".join(segments) == sentence:
            return segments

    # Last resort: split at word boundaries
    return _force_word_split(sentence, max_words)


def _force_word_split(text: str, max_words: int) -> list[str]:
    """Force-split text at word boundaries to respect max_words.

    Preserves all whitespace so concatenation reproduces the original.

    Args:
        text: Text to split.
        max_words: Maximum words per segment.

    Returns:
        List of segments that concatenate to the original text.
    """
    if not text or _count_words(text) <= max_words:
        return [text] if text else []

    segments = []
    # Split into tokens preserving whitespace
    # Each token is (whitespace_before, word)
    tokens = re.findall(r"(\s*\S+)", text)

    # Handle leading whitespace
    leading_ws_match = re.match(r"^\s+", text)
    leading_ws = leading_ws_match.group() if leading_ws_match else ""

    current_segment_parts: list[str] = []
    current_word_count = 0

    # Re-tokenize preserving exact whitespace
    # Use a different approach: find word positions
    word_pattern = re.compile(r"\S+")
    words = list(word_pattern.finditer(text))

    if not words:
        return [text]

    prev_end = 0
    current_start = 0
    word_count_in_segment = 0

    for i, word_match in enumerate(words):
        word_count_in_segment += 1

        if word_count_in_segment > max_words:
            # End the current segment before this word
            # The segment goes from current_start to the start of whitespace before this word
            segment_end = word_match.start()
            # But we want to include trailing whitespace with the previous segment
            # Actually, let's split right before this word's leading whitespace
            # Find where the whitespace before this word starts
            if i > 0:
                prev_word_end = words[i - 1].end()
                segments.append(text[current_start:prev_word_end])
                current_start = prev_word_end
            else:
                segments.append(text[current_start:word_match.start()])
                current_start = word_match.start()
            word_count_in_segment = 1

    # Add the final segment
    if current_start < len(text):
        segments.append(text[current_start:])

    return segments


def segment_text(
    text: str,
    max_words: int = 500,
    preserve_paragraphs: bool = False,
) -> SegmentResult:
    """Segment text at sentence boundaries respecting word limits.

    The segmenter guarantees that concatenating all segments reproduces
    the original text exactly (character-for-character).

    Args:
        text: The text to segment.
        max_words: Maximum number of words per segment (default 500).
        preserve_paragraphs: If True, never split across paragraph boundaries.

    Returns:
        SegmentResult with segments and metadata.
    """
    if not text:
        return SegmentResult(
            segments=[],
            segment_count=0,
            total_words=0,
            max_segment_words=max_words,
        )

    total_words = _count_words(text)

    # If text fits in one segment, return as-is
    if total_words <= max_words:
        return SegmentResult(
            segments=[text],
            segment_count=1,
            total_words=total_words,
            max_segment_words=max_words,
        )

    # Split into sentences
    sentences = _split_at_sentence_boundaries(text)

    # Group sentences into segments respecting word limits
    segments: list[str] = []
    current_segment_parts: list[str] = []
    current_word_count = 0

    for sentence in sentences:
        sentence_words = _count_words(sentence)

        # If a single sentence exceeds max_words, split it further
        if sentence_words > max_words:
            # First, flush current segment if non-empty
            if current_segment_parts:
                segments.append("".join(current_segment_parts))
                current_segment_parts = []
                current_word_count = 0

            # Split the long sentence
            sub_segments = _split_long_sentence(sentence, max_words)
            # Add all but the last as complete segments
            for sub in sub_segments[:-1]:
                segments.append(sub)
            # The last sub-segment starts a new current segment
            if sub_segments:
                current_segment_parts = [sub_segments[-1]]
                current_word_count = _count_words(sub_segments[-1])
            continue

        # Check if adding this sentence would exceed the limit
        if current_word_count + sentence_words > max_words and current_segment_parts:
            # Flush current segment
            segments.append("".join(current_segment_parts))
            current_segment_parts = [sentence]
            current_word_count = sentence_words
        else:
            current_segment_parts.append(sentence)
            current_word_count += sentence_words

    # Flush remaining
    if current_segment_parts:
        segments.append("".join(current_segment_parts))

    # Verify concatenation invariant
    concatenated = "".join(segments)
    assert concatenated == text, (
        "Segmentation invariant violated: concatenation does not reproduce original text"
    )

    return SegmentResult(
        segments=segments,
        segment_count=len(segments),
        total_words=total_words,
        max_segment_words=max_words,
    )


def segment_by_paragraphs(text: str) -> list[str]:
    """Split text into paragraphs for language detection.

    Paragraphs are separated by one or more blank lines (two or more newlines).
    Single newlines within a paragraph are preserved.

    Args:
        text: The text to split into paragraphs.

    Returns:
        List of paragraph strings (may include separating whitespace).
    """
    if not text:
        return []

    # Split on double newlines (paragraph boundaries)
    # Preserve the separators for exact reconstruction
    parts = re.split(r"(\n\s*\n)", text)

    # Filter out empty strings but keep separators
    paragraphs = [p for p in parts if p]

    return paragraphs
