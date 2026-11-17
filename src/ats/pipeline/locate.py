"""Find where each parsed item's snippet sits in the masked text, and how much text items cover.

The model copies a snippet from the CV; code finds it (§2.2). A two-column PDF extracts
interleaved, row by row, so the lines of one item can be separated by lines of the other column.
The model is told to copy one contiguous block, and when the whole snippet is not found, each of
its lines is looked for on its own.
"""

import re
from dataclasses import dataclass

from ats.pipeline.masking import Span

# Items covering less of the text than this flag the document (§2.2). The paragraph fallback
# that follows from the flag belongs to chunking in phase 2.1.
MIN_COVERAGE = 0.85
# Shorter lines ("SQL") occur in too many places to say where an item is.
MIN_LINE_CHARS = 4


@dataclass(frozen=True)
class Located:
    start: int
    end: int
    # The ranges that were actually matched. Equal to (start, end) unless the match was line by
    # line, where the bounding range also holds other lines.
    covered: tuple[tuple[int, int], ...]


def _whitespace_tolerant(snippet: str) -> re.Pattern[str] | None:
    words = snippet.split()
    if not words:
        return None
    return re.compile(r"\s+".join(re.escape(word) for word in words))


def _find(snippet: str, text: str) -> tuple[int, int] | None:
    index = text.find(snippet)
    if index >= 0:
        return index, index + len(snippet)
    pattern = _whitespace_tolerant(snippet)
    match = pattern.search(text) if pattern else None
    return (match.start(), match.end()) if match else None


def locate_snippet(snippet: str, text: str) -> Located | None:
    """Exact match, else a match that ignores differences in whitespace, else line by line
    (located when at least half of the lines are found)."""
    whole = _find(snippet.strip(), text)
    if whole is not None:
        return Located(whole[0], whole[1], (whole,))
    lines = [line.strip() for line in snippet.split("\n") if len(line.strip()) >= MIN_LINE_CHARS]
    found = [hit for line in lines if (hit := _find(line, text)) is not None]
    if not lines or len(found) * 2 < len(lines):
        return None
    return Located(min(s for s, _ in found), max(e for _, e in found), tuple(found))


def coverage(
    masked_text: str, placeholders: list[tuple[int, int]], covered: list[Located]
) -> float:
    """Share of the text's characters inside some located item.

    Whitespace and the placeholders of masked personal data are not counted: neither is CV
    content an item could carry.
    """
    counted = [not c.isspace() for c in masked_text]
    for start, end in placeholders:
        for i in range(start, end):
            counted[i] = False
    total = sum(counted)
    if total == 0:
        return 0.0
    inside = [False] * len(masked_text)
    for located in covered:
        for start, end in located.covered:
            for i in range(start, end):
                inside[i] = True
    return sum(1 for c, i in zip(counted, inside, strict=True) if c and i) / total


def placeholder_ranges(spans: list[Span]) -> list[tuple[int, int]]:
    """The placeholders' ranges in the masked text."""
    ranges: list[tuple[int, int]] = []
    shift = 0
    for span in spans:
        start = span.raw_start + shift
        ranges.append((start, start + len(span.placeholder)))
        shift += len(span.placeholder) - (span.raw_end - span.raw_start)
    return ranges
