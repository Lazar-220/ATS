"""PDF text extraction as a sequence of cleaning steps.

Per page: hidden spans are found from the text trace and the rendered page and dropped (§4.4),
then the cleaning steps run. A step receives the page and the text so far and returns the new
text. What was removed is logged and returned as flags for HR; nothing here rejects a CV for it.
"""

import logging
import re
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import cast

import pymupdf

from ats.pipeline.hidden import find_hidden, text_without

log = logging.getLogger(__name__)

HIDDEN_TEXT = "hidden_text"

CleaningStep = Callable[[pymupdf.Page, str], str]

# Spaces that PDF producers emit for layout and that break exact matching of quotes later.
_ODD_SPACES = str.maketrans({" ": " ", " ": " ", " ": " "})
_TRAILING_SPACE = re.compile(r"[ \t]+$", re.MULTILINE)
_BLANK_RUNS = re.compile(r"\n{3,}")


class PdfRejected(Exception):
    """The document cannot be processed. The message is written for HR and shown as is."""


class UnreadablePdfError(PdfRejected):
    pass


class ScannedPdfError(PdfRejected):
    pass


@dataclass(frozen=True)
class ExtractedText:
    text: str
    page_count: int
    # For HR, in the shape of `document.flags` (hidden_text).
    flags: list[dict[str, str]] = field(default_factory=lambda: list[dict[str, str]]())


def normalize_whitespace(_page: pymupdf.Page, text: str) -> str:
    text = text.translate(_ODD_SPACES)
    text = _TRAILING_SPACE.sub("", text)
    return _BLANK_RUNS.sub("\n\n", text).strip()


DEFAULT_STEPS: tuple[CleaningStep, ...] = (normalize_whitespace,)


def extract_text(
    pdf: bytes,
    *,
    min_chars_per_page: int,
    steps: Sequence[CleaningStep] = DEFAULT_STEPS,
) -> ExtractedText:
    """Extract text page by page. Raises `PdfRejected` for unreadable and scanned files."""
    try:
        doc = pymupdf.open(stream=pdf, filetype="pdf")
    except Exception as exc:
        raise UnreadablePdfError("The file could not be opened as a PDF.") from exc
    with doc:
        # PyMuPDF is only partly typed; the casts pin down what its calls return.
        if cast(bool, doc.needs_pass):  # pyright: ignore[reportUnknownMemberType]
            raise UnreadablePdfError("The PDF is password-protected.")
        page_count = cast(int, doc.page_count)  # pyright: ignore[reportUnknownMemberType]
        if page_count == 0:
            raise UnreadablePdfError("The PDF has no pages.")
        pages: list[str] = []
        hidden_by_reason: Counter[str] = Counter()
        hidden_pages: set[int] = set()
        for page in doc:
            number = cast(int, page.number) + 1  # pyright: ignore[reportUnknownMemberType]
            hidden, removals = find_hidden(page, number)
            for removal in removals:
                hidden_by_reason[removal.reason] += removal.chars
                hidden_pages.add(removal.page)
                # Counts only: the removed text is CV content and does not belong in a log.
                log.warning(
                    "hidden text removed: page %s, %s, %s characters",
                    removal.page,
                    removal.reason,
                    removal.chars,
                )
            # A page with nothing hidden keeps the extractor's own text, byte for byte.
            plain = cast(str, page.get_text("text"))  # pyright: ignore[reportUnknownMemberType]
            text = text_without(page, hidden) if hidden else plain
            for step in steps:
                text = step(page, text)
            pages.append(text)

    # Counted after cleaning, so text a step removes (hidden text, from 1.7) does not count.
    characters = sum(len("".join(page.split())) for page in pages)
    if characters / page_count < min_chars_per_page:
        raise ScannedPdfError(
            "The PDF contains little or no selectable text and looks like a scan. "
            "Upload a PDF exported from a text editor, not an image."
        )
    text = "\n\n".join(page for page in pages if page)
    flags: list[dict[str, str]] = []
    if hidden_by_reason:
        reasons = ", ".join(f"{reason} ({n})" for reason, n in sorted(hidden_by_reason.items()))
        flags.append(
            {
                "code": HIDDEN_TEXT,
                "detail": f"removed {sum(hidden_by_reason.values())} characters of hidden text "
                f"on page(s) {', '.join(map(str, sorted(hidden_pages)))}: {reasons}",
            }
        )
    return ExtractedText(text=text, page_count=page_count, flags=flags)
