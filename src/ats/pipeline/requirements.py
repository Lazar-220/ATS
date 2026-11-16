"""Requirements of a posting: the schema, and the one LLM call that extracts them (§2.4)."""

from typing import Literal, Self

from pydantic import BaseModel, Field, field_validator, model_validator

from ats.llm.types import LLMClient, LLMRequest, LLMResult, ThinkingLevel
from ats.prompts import load_prompt

PROMPT_VERSION = "requirements_v1"
# gemini-3.8-flash accepts low, medium and high but not minimal, which §6.1 names for
# extraction. `low` is the lowest level the configured model takes.
THINKING_LEVEL: ThinkingLevel = "low"

MAX_WEIGHT = 5


class RequirementDraft(BaseModel):
    """One requirement as the model proposes it and as HR edits it.

    `id` and `parent` are labels inside one list, not database keys: a list is stored as new
    rows, and the labels say which row refines which.
    """

    id: int
    text: str
    kind: Literal["mandatory", "nice_to_have"]
    weight: int = Field(ge=1, le=MAX_WEIGHT)
    # Set only when the requirement states a duration.
    min_months: int | None = Field(ge=1)
    parent: int | None

    @field_validator("text")
    @classmethod
    def _text_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("a requirement needs text")
        return value


class RequirementList(BaseModel):
    requirements: list[RequirementDraft] = Field(min_length=1)

    @model_validator(mode="after")
    def _parents_form_a_forest(self) -> Self:
        by_id = {req.id: req for req in self.requirements}
        if len(by_id) != len(self.requirements):
            raise ValueError("requirement ids must be unique")
        for req in self.requirements:
            if req.parent is not None and req.parent not in by_id:
                raise ValueError(f"requirement {req.id} has an unknown parent {req.parent}")
            # Walking up at most len() steps without reaching a root means a cycle
            # (a self-parent is the shortest one).
            current, steps = req, 0
            while current.parent is not None:
                current = by_id[current.parent]
                steps += 1
                if steps > len(by_id):
                    raise ValueError(f"requirement {req.id} is its own ancestor")
        return self


def _fence(posting_text: str) -> str:
    # The posting is data. A literal closing tag inside it must not end the block early.
    return f"<posting>\n{posting_text.replace('</posting>', '</ posting>')}\n</posting>"


def extract_requirements(client: LLMClient, posting_text: str) -> LLMResult[RequirementList]:
    # Instructions first and the posting last, so the stable prefix can be cached (§4.5).
    request = LLMRequest(
        system=load_prompt(PROMPT_VERSION),
        user=_fence(posting_text),
        thinking_level=THINKING_LEVEL,
        prompt_version=PROMPT_VERSION,
    )
    return client.generate(request, RequirementList)
