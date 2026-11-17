"""Months of experience, computed by code (§2.2, §2.4: "code computes, the LLM judges").

The parsing prompt returns dates as written, in `YYYY-MM`, `YYYY` or `present`. This module
turns them into month counts. It never reads the clock: `as_of` is passed in, so the eval can
use the golden set's fixed date and production can pass today.

Conventions, the same as the golden labelling (eval/golden/README.md):

- A date is the first day of its month; a period runs from its start month up to its end
  month, so 2019-03 to 2023-06 is 51 months.
- A year-only start is January, a year-only end is December of that year. This is the generous
  reading and the item is marked `approximate`.
- `present` is the month of `as_of`. An end after `as_of` is cut back to it: time that has not
  happened is not experience.
- A missing start or end, or an end before the start, gives no month count and a note saying
  why. A guessed duration would look like a fact.
- Total tenure is the union of periods: overlapping jobs are not counted twice.
"""

from dataclasses import dataclass
from datetime import date

PRESENT = "present"
MONTHS_PER_YEAR = 12


@dataclass(frozen=True)
class ItemTenure:
    months: int | None
    # Why `months` is None, or a caveat about it. None when there is nothing to say.
    note: str | None
    # Half-open month indices (year * 12 + month - 1), set exactly when months is.
    start: int | None = None
    end: int | None = None
    approximate: bool = False


def _month_index(value: str, as_of: date, *, is_end: bool) -> tuple[int, bool]:
    """Month index of a date string, and whether the month was a guess (year-only)."""
    if value == PRESENT:
        return as_of.year * MONTHS_PER_YEAR + as_of.month - 1, False
    if len(value) == len("YYYY"):
        month = MONTHS_PER_YEAR if is_end else 1
        return int(value) * MONTHS_PER_YEAR + month - 1, True
    year, month = value.split("-")
    return int(year) * MONTHS_PER_YEAR + int(month) - 1, False


def item_tenure(date_start: str | None, date_end: str | None, as_of: date) -> ItemTenure:
    if date_start is None and date_end is None:
        return ItemTenure(None, None)
    if date_start is None:
        return ItemTenure(None, "no start date")
    if date_end is None:
        return ItemTenure(None, "no end date")
    start, guessed_start = _month_index(date_start, as_of, is_end=False)
    end, guessed_end = _month_index(date_end, as_of, is_end=True)
    now = as_of.year * MONTHS_PER_YEAR + as_of.month - 1
    if start > now:
        return ItemTenure(None, "starts after the reference date")
    end = min(end, now)
    if end < start:
        return ItemTenure(None, "end before start")
    return ItemTenure(
        end - start, None, start=start, end=end, approximate=guessed_start or guessed_end
    )


def merged_months(periods: list[tuple[int, int]]) -> int:
    """Months covered by the union of half-open `(start, end)` periods."""
    total = 0
    current_end: int | None = None
    current_start = 0
    for start, end in sorted(periods):
        if current_end is None or start > current_end:
            if current_end is not None:
                total += current_end - current_start
            current_start, current_end = start, end
        else:
            current_end = max(current_end, end)
    if current_end is not None:
        total += current_end - current_start
    return total
