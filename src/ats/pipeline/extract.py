"""PDF text extraction as a sequence of cleaning steps.

A step receives the page and the text so far and returns the new text. Phase 1.7 adds hidden-text
removal by inserting a step that re-reads the page's spans; nothing else here has to change.
"""

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import cast

import pymupdf

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
        for page in doc:
            text = cast(str, page.get_text("text"))  # pyright: ignore[reportUnknownMemberType]
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
    return ExtractedText(text="\n\n".join(page for page in pages if page), page_count=page_count)
