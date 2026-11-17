"""The source text of a golden CV, and what a gold quote is checked against.

A single-column source is plain text. A two-column source holds the left column, a line that is
exactly `=== RIGHT COLUMN ===`, then the right column. The renderer writes the two columns row by
row, as real two-column templates do, so a PDF extraction interleaves them (the 1.1b fixture).
A quote therefore has to sit inside one line of one column: only a line survives that.
"""

from dataclasses import dataclass

from ats.eval.schemas import Template

RIGHT_COLUMN_MARKER = "=== RIGHT COLUMN ==="


class CvSourceError(ValueError):
    pass


@dataclass(frozen=True)
class CvSource:
    columns: tuple[tuple[str, ...], ...]

    @property
    def lines(self) -> tuple[str, ...]:
        return tuple(line for column in self.columns for line in column)

    @property
    def text(self) -> str:
        return "\n".join(self.lines)

    def contains_quote(self, quote: str) -> bool:
        return any(quote in line for line in self.lines)


def _strip_blank_edges(lines: list[str]) -> tuple[str, ...]:
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return tuple(line.rstrip() for line in lines)


def parse_cv_source(raw: str, template: Template) -> CvSource:
    lines = raw.replace("\r\n", "\n").split("\n")
    markers = [i for i, line in enumerate(lines) if line.strip() == RIGHT_COLUMN_MARKER]
    if template == "single":
        if markers:
            raise CvSourceError("a single-column CV must not contain the right-column marker")
        return CvSource((_strip_blank_edges(lines),))
    if len(markers) != 1:
        raise CvSourceError(f"a two-column CV needs exactly one {RIGHT_COLUMN_MARKER!r} line")
    split_at = markers[0]
    left = _strip_blank_edges(lines[:split_at])
    right = _strip_blank_edges(lines[split_at + 1 :])
    if not left or not right:
        raise CvSourceError("both columns of a two-column CV need text")
    return CvSource((left, right))
