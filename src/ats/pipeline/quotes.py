"""Checking the judge's quotes against the CV (§3.2).

Code decides whether a quote is real. A quote passes when it exists in the masked text verbatim
after normalization, or when its fuzzy score is at least the threshold; every number in the
quote must also exist verbatim. The judge read masked text, so the quote is found there and the
range is mapped back to `raw_text` through the span map (1.4a), which is where the interface
highlights.

Normalization here is for comparison only and keeps a character-by-character map, so a match can
be turned back into offsets. It does not transliterate or strip diacritics: those change the
length of the text (`đ` to `dj`).
"""

import re
import unicodedata
from dataclasses import dataclass

from rapidfuzz import fuzz

from ats.pipeline.masking import Span, masked_range_to_raw

QUOTE_NOT_FOUND = "quote_not_found"
NO_EVIDENCE = "no_evidence"

_QUOTES = str.maketrans(
    {
        "‘": "'",
        "’": "'",
        "‚": "'",
        "“": '"',
        "”": '"',
        "„": '"',
        "‐": "-",
        "‑": "-",
        "‒": "-",
        "–": "-",
        "—": "-",
        "−": "-",
    }
)
_DIGITS = re.compile(r"\d+")


def normalize_with_map(text: str) -> tuple[str, list[int]]:
    """Normalized text and, for each of its characters, the index it came from in `text`.

    Whitespace runs become one space and leading and trailing whitespace is dropped.
    """
    out: list[str] = []
    origin: list[int] = []
    pending_space = -1
    for index, char in enumerate(text):
        for piece in unicodedata.normalize("NFKC", char).casefold().translate(_QUOTES):
            if piece.isspace():
                if out and pending_space < 0:
                    pending_space = index
                continue
            if pending_space >= 0:
                out.append(" ")
                origin.append(pending_space)
                pending_space = -1
            out.append(piece)
            origin.append(index)
    return "".join(out), origin


def normalize(text: str) -> str:
    return normalize_with_map(text)[0]


@dataclass(frozen=True)
class QuoteMatch:
    # Range in the text that was searched.
    start: int
    end: int
    exact: bool
    score: float


def find_quote(quote: str, text: str, threshold: int) -> QuoteMatch | None:
    """Where `quote` is in `text`, or None when it is not there (§3.2)."""
    needle = normalize(quote)
    if not needle:
        return None
    hay, origin = normalize_with_map(text)
    index = hay.find(needle)
    if index >= 0:
        start, end, exact, score = index, index + len(needle), True, 100.0
    else:
        alignment = fuzz.partial_ratio_alignment(needle, hay, score_cutoff=threshold)
        if alignment is None:
            return None
        start, end = alignment.dest_start, alignment.dest_end
        exact, score = False, float(alignment.score)
        # A near match that changes a number is a different fact.
        window = set(_DIGITS.findall(hay[start:end]))
        if not set(_DIGITS.findall(needle)) <= window:
            return None
    if end <= start:
        return None
    return QuoteMatch(origin[start], origin[end - 1] + 1, exact, score)


@dataclass(frozen=True)
class CheckedQuote:
    flags: tuple[str, ...]
    # Offsets into raw_text; set only for a quote that passed.
    char_start: int | None
    char_end: int | None
    detail: str | None = None


def check_quote(
    verdict: str,
    quote: str | None,
    masked_text: str,
    spans: list[Span],
    threshold: int,
) -> CheckedQuote:
    """Flags and raw offsets for one verdict.

    `not_met` has no evidence to check. `met` or `partial` without a quote is `no_evidence`. A
    quote that is not in the CV is `quote_not_found`. In v1 a flagged verdict stays as the judge
    gave it and keeps its flag; its quote is simply not shown as evidence.
    """
    if verdict == "not_met":
        return CheckedQuote((), None, None)
    if quote is None or not quote.strip():
        return CheckedQuote((NO_EVIDENCE,), None, None, "no quote for a met or partial verdict")
    match = find_quote(quote, masked_text, threshold)
    if match is None:
        return CheckedQuote(
            (QUOTE_NOT_FOUND,), None, None, "the quote is not in the CV (verbatim or fuzzy)"
        )
    raw_start, raw_end = masked_range_to_raw(spans, match.start, match.end)
    return CheckedQuote((), raw_start, raw_end)
