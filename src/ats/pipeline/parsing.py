"""Triage and structured parsing of one masked CV: one LLM call (§2.2, §2.4 step 4, §4.2).

The model returns dates as written, in a fixed format, and never a duration: date arithmetic
is code (`tenure.py`). Every item carries a verbatim snippet of the masked text, which is how
code finds the item again whatever order a two-column PDF extracted in.
"""

import re
from typing import Self

from pydantic import BaseModel, field_validator, model_validator

from ats.llm.types import LLMClient, LLMRequest, LLMResult, ThinkingLevel
from ats.prompts import load_prompt

PROMPT_VERSION = "cv_parse_v1"
THINKING_LEVEL: ThinkingLevel = "minimal"

# "YYYY-MM", "YYYY", or "present" for an open end. Anything else makes the output invalid,
# which costs one retry call (§4.5) instead of a wrong month count later.
_DATE_RE = re.compile(r"^(?:\d{4}(?:-(?:0[1-9]|1[0-2]))?|present)$")


class Item(BaseModel):
    """What every parsed item has: its source text, and a period where the CV gives one."""

    snippet: str
    date_start: str | None
    date_end: str | None

    @field_validator("date_start", "date_end")
    @classmethod
    def _date_format(cls, value: str | None) -> str | None:
        if value is not None and not _DATE_RE.match(value):
            raise ValueError(f"date {value!r} is not YYYY-MM, YYYY or present")
        return value

    @field_validator("snippet")
    @classmethod
    def _snippet_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("an item needs a snippet")
        return value

    @model_validator(mode="after")
    def _start_is_not_present(self) -> Self:
        if self.date_start == "present":
            raise ValueError("a start date cannot be 'present'")
        return self


class ExperienceItem(Item):
    title: str
    organization: str | None


class EducationItem(Item):
    degree: str
    institution: str | None


class SkillItem(Item):
    name: str


class CertificateItem(Item):
    name: str
    issuer: str | None


class LanguageItem(Item):
    language: str
    level: str | None


class ProjectItem(Item):
    name: str


class ParsedCV(BaseModel):
    is_cv: bool
    # The document carries text aimed at an AI system or an automated screener.
    suspected_injection: bool
    experience: list[ExperienceItem]
    education: list[EducationItem]
    skills: list[SkillItem]
    certificates: list[CertificateItem]
    languages: list[LanguageItem]
    projects: list[ProjectItem]


SECTIONS = ("experience", "education", "skills", "certificates", "languages", "projects")


def _fence(masked_text: str) -> str:
    # The CV is data. A literal closing tag inside it must not end the block early (§4.4).
    return f"<cv>\n{masked_text.replace('</cv>', '</ cv>')}\n</cv>"


def build_request(masked_text: str) -> LLMRequest:
    # Instructions first and the CV last, so the stable prefix can be cached (§4.5).
    return LLMRequest(
        system=load_prompt(PROMPT_VERSION),
        user=_fence(masked_text),
        thinking_level=THINKING_LEVEL,
        prompt_version=PROMPT_VERSION,
    )


def parse_cv(client: LLMClient, masked_text: str) -> LLMResult[ParsedCV]:
    return client.generate(build_request(masked_text), ParsedCV)
