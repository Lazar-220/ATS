"""Renders golden CV and posting sources to PDF, in two templates (§5.1).

`single` is one column of lines. `two_column` is a narrow left column and a wide right one,
written row by row: left cell, right cell, next row. That is how the 1.1b fixture and many real
templates lay out their text, and a PDF extraction reads it back interleaved. Reading order is
deliberately not made clean here: the golden set should carry the flaw the pipeline will meet.

A line is never wrapped. A line that does not fit its column raises, so a quote that sits inside
one source line is guaranteed to sit inside one extracted line as well.

PyMuPDF's built-in font covers Latin Extended and Cyrillic, so no font file is needed. Fonts are
subset and the document id is fixed, which makes the output byte-stable: re-rendering an
unchanged source changes nothing in git.
"""

from collections.abc import Callable
from pathlib import Path
from typing import cast

import pymupdf

from ats.eval.cvsource import CvSource, parse_cv_source
from ats.eval.schemas import Profile, Template

PAGE_WIDTH, PAGE_HEIGHT = 595.0, 842.0  # A4 in points
_MARGIN_X, _MARGIN_Y = 50.0, 56.0
_FONT_SIZE = 10.0
_HEADING_SIZE = 11.5
_LINE_HEIGHT = 14.0
_FONT = "noto"

# Two-column geometry: a sidebar on the left, the body on the right.
_LEFT_X, _LEFT_WIDTH = 40.0, 185.0
_RIGHT_X, _RIGHT_WIDTH = 250.0, 305.0


class LineTooWideError(ValueError):
    pass


def _is_heading(line: str) -> bool:
    letters = [char for char in line if char.isalpha()]
    return len(letters) >= 3 and all(char.isupper() for char in letters)


def _size(line: str) -> float:
    return _HEADING_SIZE if _is_heading(line) else _FONT_SIZE


def _new_page(doc: pymupdf.Document, font: pymupdf.Font) -> pymupdf.Page:
    page = doc.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
    buffer = cast(bytes, font.buffer)  # pyright: ignore[reportUnknownMemberType]
    page.insert_font(fontname=_FONT, fontbuffer=buffer)  # pyright: ignore[reportUnknownMemberType]
    return page


def _check_width(line: str, width: float, font: pymupdf.Font) -> None:
    # PyMuPDF is only partly typed; the casts pin down what its calls return.
    measured = cast(float, font.text_length(line, fontsize=_size(line)))  # pyright: ignore[reportUnknownMemberType, reportArgumentType]
    if measured > width:
        raise LineTooWideError(
            f"line is {measured:.0f}pt wide but the column holds {width:.0f}pt: {line!r}"
        )


def _finish(doc: pymupdf.Document) -> bytes:
    doc.subset_fonts()  # pyright: ignore[reportUnknownMemberType]
    return doc.tobytes(garbage=4, deflate=True, no_new_id=True)  # pyright: ignore[reportUnknownMemberType]


def _draw(page: pymupdf.Page, x: float, y: float, line: str) -> None:
    if line.strip():
        page.insert_text((x, y), line, fontname=_FONT, fontsize=_size(line))  # pyright: ignore[reportUnknownMemberType]


def render_single_column(source: CvSource) -> bytes:
    (lines,) = source.columns
    font = pymupdf.Font()
    doc = pymupdf.open()
    per_page = int((PAGE_HEIGHT - 2 * _MARGIN_Y) / _LINE_HEIGHT)
    width = PAGE_WIDTH - 2 * _MARGIN_X
    for line in lines:
        _check_width(line, width, font)
    for start in range(0, len(lines), per_page):
        page = _new_page(doc, font)
        for row, line in enumerate(lines[start : start + per_page]):
            _draw(page, _MARGIN_X, _MARGIN_Y + row * _LINE_HEIGHT, line)
    return _finish(doc)


def render_two_column(source: CvSource) -> bytes:
    left, right = source.columns
    font = pymupdf.Font()
    doc = pymupdf.open()
    for line in left:
        _check_width(line, _LEFT_WIDTH, font)
    for line in right:
        _check_width(line, _RIGHT_WIDTH, font)
    per_page = int((PAGE_HEIGHT - 2 * _MARGIN_Y) / _LINE_HEIGHT)
    rows = max(len(left), len(right))
    for start in range(0, rows, per_page):
        page = _new_page(doc, font)
        for row in range(start, min(start + per_page, rows)):
            y = _MARGIN_Y + (row - start) * _LINE_HEIGHT
            # Left cell first, then right, row by row: this order is the interleaving.
            if row < len(left):
                _draw(page, _LEFT_X, y, left[row])
            if row < len(right):
                _draw(page, _RIGHT_X, y, right[row])
    return _finish(doc)


_RENDERERS: dict[Template, Callable[[CvSource], bytes]] = {
    "single": render_single_column,
    "two_column": render_two_column,
}


def render_cv(source: CvSource, template: Template) -> bytes:
    return _RENDERERS[template](source)


def render_posting(text: str) -> bytes:
    return render_single_column(parse_cv_source(text, "single"))


def render_golden(root: Path) -> list[Path]:
    """Render every posting and CV under `root`. Returns the files whose bytes changed."""
    jobs: list[tuple[Path, bytes]] = []
    for text_path in sorted((root / "positions").glob("*/posting.txt")):
        jobs.append(
            (text_path.with_suffix(".pdf"), render_posting(text_path.read_text(encoding="utf-8")))
        )
    for profile_path in sorted((root / "profiles").glob("*.json")):
        profile = Profile.model_validate_json(profile_path.read_text(encoding="utf-8"))
        text = (root / "cvs" / f"{profile.cv_id}.txt").read_text(encoding="utf-8")
        source = parse_cv_source(text, profile.template)
        jobs.append((root / "cvs" / f"{profile.cv_id}.pdf", render_cv(source, profile.template)))
    changed: list[Path] = []
    for path, data in jobs:
        if not path.is_file() or path.read_bytes() != data:
            path.write_bytes(data)
            changed.append(path)
    return changed
