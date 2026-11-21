"""Builders for attacked PDFs: hidden text drawn onto an existing page (§4.4, §5.1).

Used by the hidden-text tests and by the red-team set. Every attack puts `text` where a reader
of the page would not see it but a plain text extraction would return it. Synthetic CVs only.
"""

from typing import Any, Literal, cast

import pymupdf

type HiddenKind = Literal["white_text", "tiny_font", "off_page", "invisible_mode", "covered_text"]

HIDDEN_KINDS: tuple[HiddenKind, ...] = (
    "white_text",
    "tiny_font",
    "off_page",
    "invisible_mode",
    "covered_text",
)

_FONT = "noto"
# The bottom margin of the golden renderer's page is empty below y = 790.
_BOTTOM = 812.0


def add_hidden_text(pdf: bytes, kind: HiddenKind, text: str, *, page_number: int = 0) -> bytes:
    """The same PDF with `text` added as hidden text of the given kind, on one page."""
    doc = pymupdf.open(stream=pdf, filetype="pdf")
    page = cast(Any, doc[page_number])
    font = pymupdf.Font()
    page.insert_font(fontname=_FONT, fontbuffer=font.buffer)  # pyright: ignore[reportUnknownMemberType]
    left = 50.0
    if kind == "white_text":
        page.insert_text((left, _BOTTOM), text, fontname=_FONT, fontsize=9, color=(1, 1, 1))
    elif kind == "tiny_font":
        page.insert_text((left, _BOTTOM), text, fontname=_FONT, fontsize=2, color=(0, 0, 0))
    elif kind == "off_page":
        page.insert_text((page.rect.width + 40, 100), text, fontname=_FONT, fontsize=9)
    elif kind == "invisible_mode":
        # Render mode 3: neither fill nor stroke.
        page.insert_text((left, _BOTTOM), text, fontname=_FONT, fontsize=9, render_mode=3)
    else:
        # Dark text, then a page-colored rectangle over it: the color is not the background's,
        # only the rendered region gives it away.
        page.insert_text((left, _BOTTOM), text, fontname=_FONT, fontsize=9, color=(0, 0, 0))
        width = cast(float, font.text_length(text, fontsize=9)) + 6  # pyright: ignore[reportUnknownMemberType]
        page.draw_rect(
            pymupdf.Rect(left - 3, _BOTTOM - 12, left + width, _BOTTOM + 4),
            color=None,
            fill=(1, 1, 1),
        )
    return doc.tobytes(garbage=4, deflate=True, no_new_id=True)  # pyright: ignore[reportUnknownMemberType]


def add_visible_text(pdf: bytes, text: str, *, page_number: int = 0) -> bytes:
    """The same PDF with one visible line of `text` in the bottom margin of one page.

    For attacks that cleaning cannot remove (a plain instruction), and for the benign line that
    the zero-width attack hides its characters in.
    """
    doc = pymupdf.open(stream=pdf, filetype="pdf")
    page = cast(Any, doc[page_number])
    page.insert_font(fontname=_FONT, fontbuffer=pymupdf.Font().buffer)  # pyright: ignore[reportUnknownMemberType]
    page.insert_text((50.0, _BOTTOM), text, fontname=_FONT, fontsize=9, color=(0, 0, 0))
    return doc.tobytes(garbage=4, deflate=True, no_new_id=True)  # pyright: ignore[reportUnknownMemberType]
