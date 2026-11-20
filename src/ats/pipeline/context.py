"""What the judge is shown for one CV-position pair (§7, "Refactor before v2").

In v1 `build_context` returns the whole masked CV. In v2 only this function changes: it will
return the retrieved evidence instead, and the judge does not notice.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ContextRequirement:
    # A label inside this pack (1..n or a gold id), which the judge echoes back; never a row id.
    label: int
    text: str
    kind: str
    weight: int
    min_months: int | None
    parent_label: int | None


@dataclass(frozen=True)
class ExperienceFact:
    """One job as the parser read it, with the months that code computed for it."""

    title: str
    organization: str | None
    date_start: str | None
    date_end: str | None
    months: int | None
    approximate: bool


@dataclass(frozen=True)
class ContextPack:
    masked_cv: str
    experience: tuple[ExperienceFact, ...]
    # Months of the union of all experience periods, computed by code as of `as_of` (§2.4).
    total_months: int
    as_of: str
    requirements: tuple[ContextRequirement, ...]
    # Filled from v3 on, with HR's rules; empty in v1.
    rules: tuple[str, ...] = field(default=())


def build_context(
    masked_text: str,
    parsed_json: dict[str, Any],
    requirements: Sequence[ContextRequirement],
) -> ContextPack:
    tenure = parsed_json["tenure"]
    experience = tuple(
        ExperienceFact(
            title=item["title"],
            organization=item.get("organization"),
            date_start=item["date_start"],
            date_end=item["date_end"],
            months=item["months"],
            approximate=bool(item.get("months_approximate", False)),
        )
        for item in parsed_json["experience"]
    )
    return ContextPack(
        masked_cv=masked_text,
        experience=experience,
        total_months=tenure["total_months"],
        as_of=tenure["as_of"],
        requirements=tuple(requirements),
    )
