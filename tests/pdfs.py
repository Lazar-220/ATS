"""Builds the test PDFs in memory, so no binary fixtures are committed.

PyMuPDF's default font (Noto Serif) carries Latin Extended and Cyrillic glyphs, so the same
helper writes Serbian in both scripts without a font file.
"""

import pymupdf

_LINE_HEIGHT = 16
_LINES_PER_PAGE = 45


def _new_page(doc: pymupdf.Document) -> pymupdf.Page:
    page = doc.new_page()
    page.insert_font(fontname="noto", fontbuffer=pymupdf.Font().buffer)
    return page


def make_pdf(text: str) -> bytes:
    """A text PDF: one line of `text` per line, a new page every 45 lines."""
    doc = pymupdf.open()
    lines = text.split("\n")
    for start in range(0, len(lines), _LINES_PER_PAGE):
        page = _new_page(doc)
        for row, line in enumerate(lines[start : start + _LINES_PER_PAGE]):
            page.insert_text((60, 60 + row * _LINE_HEIGHT), line, fontname="noto", fontsize=11)
    return doc.tobytes()


def make_scan_pdf(pages: int = 1) -> bytes:
    """An image-only PDF, which is what a scanner produces: no text layer at all."""
    doc = pymupdf.open()
    for _ in range(pages):
        page = doc.new_page()
        pixmap = pymupdf.Pixmap(pymupdf.csGRAY, pymupdf.IRect(0, 0, 200, 280), False)
        pixmap.clear_with(210)
        page.insert_image(page.rect, pixmap=pixmap)
    return doc.tobytes()


def make_two_column_pdf(left: list[str], right: list[str]) -> bytes:
    """Two columns written row by row, left cell then right cell, as many CV templates do."""
    doc = pymupdf.open()
    page = _new_page(doc)
    for row, (left_cell, right_cell) in enumerate(zip(left, right, strict=True)):
        y = 60 + row * _LINE_HEIGHT
        page.insert_text((50, y), left_cell, fontname="noto", fontsize=10)
        page.insert_text((320, y), right_cell, fontname="noto", fontsize=10)
    return doc.tobytes()
