"""Hidden-text detection and removal for one PDF page (§4.4, extraction layer).

Plain `page.get_text()` returns white, tiny and invisible text as normal text, so the text is
judged span by span from `page.get_texttrace()` (color, size, render mode, position) and, for
what the trace cannot tell, from the rendered page. A span is dropped when

- its render mode is invisible (3: neither fill nor stroke) or it is fully transparent,
- its font is below 4 pt,
- it lies outside the page (per character),
- its color is close to the background around it, or
- its region on the rendered page is a single color (a shape covers it, or it matches the page).

Hidden text is usually a hidden skills list, not an instruction, so it is removed whatever it
says. Removal never rejects a document: the caller logs it and puts a flag on the document.
"""

import logging
from collections import Counter
from dataclasses import dataclass
from typing import Any, cast

import pymupdf

log = logging.getLogger(__name__)

MIN_FONT_PT = 4.0
# Per channel, out of 255. A span color this close to the background is not readable.
COLOR_TOLERANCE = 32
# Per channel: a rendered region whose pixels differ by at most this much is one color.
FLAT_TOLERANCE = 6
_ZOOM = 2.0
_MIN_OPACITY = 0.05

type CharKey = tuple[float, float]

INVISIBLE_MODE = "invisible_render_mode"
TINY_FONT = "font_below_4pt"
OFF_PAGE = "outside_page"
LOW_CONTRAST = "color_close_to_background"
SINGLE_COLOR = "single_color_region"


@dataclass(frozen=True)
class HiddenRemoval:
    page: int
    reason: str
    chars: int


@dataclass(frozen=True)
class _Render:
    samples: bytes
    width: int
    height: int
    stride: int
    scale: float


def _key(origin: Any) -> CharKey:
    return (round(float(origin[0]), 2), round(float(origin[1]), 2))


def _render(page: pymupdf.Page) -> _Render | None:
    # A rotated page's text coordinates and pixels need a transform I do not rely on; the
    # structural checks still run there.
    if cast(int, page.rotation) != 0:  # pyright: ignore[reportUnknownMemberType]
        return None
    pix = cast(Any, page.get_pixmap(matrix=pymupdf.Matrix(_ZOOM, _ZOOM), alpha=False))  # pyright: ignore[reportUnknownMemberType]
    return _Render(bytes(pix.samples), pix.width, pix.height, pix.stride, _ZOOM)


def _region(render: _Render, bbox: Any, page_rect: Any) -> tuple[int, int, int, int] | None:
    x0 = max(int((bbox[0] - page_rect.x0) * render.scale), 0)
    y0 = max(int((bbox[1] - page_rect.y0) * render.scale), 0)
    x1 = min(int((bbox[2] - page_rect.x0) * render.scale) + 1, render.width)
    y1 = min(int((bbox[3] - page_rect.y0) * render.scale) + 1, render.height)
    if x1 - x0 < 2 or y1 - y0 < 2:
        return None
    return x0, y0, x1, y1


def _rows(render: _Render, region: tuple[int, int, int, int]) -> list[bytes]:
    x0, y0, x1, y1 = region
    return [
        render.samples[y * render.stride + x0 * 3 : y * render.stride + x1 * 3]
        for y in range(y0, y1)
    ]


def _is_flat(rows: list[bytes]) -> bool:
    for channel in range(3):
        low = min(min(row[channel::3]) for row in rows)
        high = max(max(row[channel::3]) for row in rows)
        if high - low > FLAT_TOLERANCE:
            return False
    return True


def _background(rows: list[bytes]) -> tuple[int, int, int]:
    """The most common color of the region: ink covers a minority of a line's box."""
    counts: Counter[bytes] = Counter()
    for row in rows[::2]:
        for i in range(0, len(row) - 2, 6):
            counts[row[i : i + 3]] += 1
    top = counts.most_common(1)[0][0]
    return top[0], top[1], top[2]


def _close(color: Any, background: tuple[int, int, int]) -> bool:
    channels = [round(float(value) * 255) for value in color]
    if len(channels) == 1:
        channels *= 3
    if len(channels) != 3:
        return False  # CMYK and the like: the single-color check still applies
    return all(abs(c - b) <= COLOR_TOLERANCE for c, b in zip(channels, background, strict=True))


def _outside(bbox: Any, rect: Any) -> bool:
    return bool(
        bbox[2] <= rect.x0 or bbox[0] >= rect.x1 or bbox[3] <= rect.y0 or bbox[1] >= rect.y1
    )


def _span_reason(span: dict[str, Any], render: _Render | None, rect: Any) -> str | None:
    if span["type"] == 3 or float(span.get("opacity", 1.0)) < _MIN_OPACITY:
        return INVISIBLE_MODE
    if float(span["size"]) < MIN_FONT_PT:
        return TINY_FONT
    if render is None:
        return None
    region = _region(render, span["bbox"], rect)
    if region is None:
        return None
    rows = _rows(render, region)
    if _is_flat(rows):
        return SINGLE_COLOR
    if _close(span["color"], _background(rows)):
        return LOW_CONTRAST
    return None


def find_hidden(page: pymupdf.Page, page_number: int) -> tuple[set[CharKey], list[HiddenRemoval]]:
    """Origins of the characters to drop, and what was found, grouped by reason."""
    trace = cast(list[dict[str, Any]], page.get_texttrace())  # pyright: ignore[reportUnknownMemberType]
    if not trace:
        return set(), []
    rect = page.rect
    render = _render(page)
    hidden: set[CharKey] = set()
    visible: set[CharKey] = set()
    counts: Counter[str] = Counter()
    for span in trace:
        chars = [c for c in span["chars"] if not chr(c[0]).isspace()]
        if not chars:
            continue
        reason = _span_reason(span, render, rect)
        for char in chars:
            char_reason = reason
            if char_reason is None and _outside(char[3], rect):
                char_reason = OFF_PAGE
            if char_reason is None:
                visible.add(_key(char[2]))
            else:
                hidden.add(_key(char[2]))
                counts[char_reason] += 1
    # A character stacked exactly on a visible one is kept: dropping it would drop the visible one.
    hidden -= visible
    removals = [HiddenRemoval(page_number, reason, n) for reason, n in sorted(counts.items())]
    return hidden, removals


def text_without(page: pymupdf.Page, hidden: set[CharKey]) -> str:
    """The page's text in reading order of the extractor, minus the hidden characters."""
    raw = cast(dict[str, Any], page.get_text("rawdict"))  # pyright: ignore[reportUnknownMemberType]
    out: list[str] = []
    for block in raw["blocks"]:
        if block["type"] != 0:
            continue
        for line in block["lines"]:
            text = "".join(
                char["c"]
                for span in line["spans"]
                for char in span["chars"]
                if _key(char["origin"]) not in hidden
            )
            if text.strip():
                out.append(text + "\n")
    return "".join(out)
