"""Schemas of the golden set (§5.1).

Everything forbids unknown fields, because the files are written by hand and a misspelled key
should fail loudly instead of being ignored.
"""

import re
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from ats.pipeline.requirements import RequirementDraft, RequirementList

Verdict = Literal["met", "partial", "not_met"]
# Language and script of a CV in one label, because the distribution in §5.1 is stated that way:
# Serbian Latin with diacritics, Serbian Latin without, Serbian Cyrillic, English, and mixed
# (Serbian and English in the same CV).
Style = Literal["sr_latin", "sr_ascii", "sr_cyrillic", "en", "mixed"]
Template = Literal["single", "two_column"]
SplitName = Literal["dev", "test"]
# The hard cases named in §5.1.
HardCaseTag = Literal[
    "implicit_evidence",
    "overlapping_periods",
    "basic_knowledge",
    "list_only",
    "course_in_progress",
    "career_change",
]
Relevance = Annotated[int, Field(ge=0, le=3)]

_ID = re.compile(r"^[a-z0-9][a-z0-9_]*$")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _check_id(value: str) -> str:
    if not _ID.fullmatch(value):
        raise ValueError(f"{value!r} must be lowercase letters, digits and underscores")
    return value


class GoldRequirement(RequirementDraft):
    """A requirement as the posting states it, written by hand.

    `aliases` are other wordings of the same condition that an extraction may produce. The
    matching rule (matching.py) takes the best score over the text and the aliases.
    """

    model_config = ConfigDict(extra="forbid")

    aliases: list[str] = Field(default_factory=list)


class Position(_Strict):
    id: str
    title: str
    lang: Literal["en", "sr"]
    requirements: list[GoldRequirement] = Field(min_length=1)

    @field_validator("id")
    @classmethod
    def _id_shape(cls, value: str) -> str:
        return _check_id(value)

    @model_validator(mode="after")
    def _requirements_form_a_forest(self) -> Self:
        # The extraction schema already knows how to reject duplicate ids and parent cycles.
        drafts = [
            RequirementDraft.model_validate(r.model_dump(exclude={"aliases"}))
            for r in self.requirements
        ]
        try:
            RequirementList(requirements=drafts)
        except ValidationError as exc:
            raise ValueError(str(exc)) from exc
        return self


class HardCase(_Strict):
    tag: HardCaseTag
    note: str = Field(min_length=1)


class ProfileClaim(_Strict):
    """What is true of the candidate for one requirement, and the words in the CV that show it."""

    requirement_id: int
    verdict: Verdict
    # The fact the CV was written to carry, in the profile's own words. Not shown to the judge.
    fact: str = Field(min_length=1)
    # Verbatim, inside one line of the CV source. `not_met` has none: absence has no span.
    quote: str | None = None

    @model_validator(mode="after")
    def _quote_matches_verdict(self) -> Self:
        if self.verdict == "not_met":
            if self.quote is not None:
                raise ValueError("a not_met claim has no quote")
            return self
        if not self.quote or self.quote != self.quote.strip():
            raise ValueError(f"a {self.verdict} claim needs a quote without edge whitespace")
        if "\n" in self.quote:
            raise ValueError("a quote must sit inside one line of the CV")
        return self


class Profile(_Strict):
    """The planned outcome for one CV. The CV text is written from this, never the reverse."""

    cv_id: str
    # The position whose requirements the claims answer (endpoint 1 pairs the CV with it).
    position_id: str
    style: Style
    template: Template
    hard_case: HardCase | None = None
    claims: list[ProfileClaim]
    # Relevance 0-3 for every position of the set, the target one included (endpoint 2).
    relevance: dict[str, Relevance]

    @field_validator("cv_id", "position_id")
    @classmethod
    def _id_shape(cls, value: str) -> str:
        return _check_id(value)

    @model_validator(mode="after")
    def _one_claim_per_requirement(self) -> Self:
        ids = [claim.requirement_id for claim in self.claims]
        if len(set(ids)) != len(ids):
            raise ValueError("two claims answer the same requirement")
        return self


class VerdictLabel(_Strict):
    """One row of labels/verdicts.jsonl: the gold verdict for a CV-requirement pair."""

    cv_id: str
    position_id: str
    requirement_id: int
    verdict: Verdict
    quote: str | None


class RelevanceLabel(_Strict):
    """One row of labels/relevance.jsonl: how well a CV fits a position, 0 to 3."""

    cv_id: str
    position_id: str
    relevance: Relevance


class SplitFile(_Strict):
    seed: int
    test_fraction: float = Field(gt=0, lt=1)
    assignment: dict[str, SplitName]
