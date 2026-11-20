"""Canned answers for a walkthrough of the interface with no model and no API key.

`LLM_PROVIDER=fake` selects it (never the default). It is a `FakeLLMClient`, so the pipeline
still calls it through the `LLMClient` interface and it sees only what a real model would see:
masked text. Its judgement is a keyword match, good enough to produce a ranking with real quotes
and nothing more.
"""

import re

from pydantic import BaseModel

from ats.llm.fake import FakeLLMClient
from ats.llm.types import LLMRequest, LLMUsage
from ats.pipeline.judge import JudgeOutput, RequirementVerdict
from ats.pipeline.parsing import ParsedCV
from ats.pipeline.requirements import RequirementDraft, RequirementList

MAX_REQUIREMENTS = 4
MIN_LINE_CHARS = 8
MIN_WORD_CHARS = 4


def _block(text: str, tag: str) -> str:
    found = re.search(rf"<{tag}>\n(.*?)\n</{tag}>", text, re.DOTALL)
    return found.group(1) if found else ""


def _requirements(request: LLMRequest) -> RequirementList:
    lines = [line.strip() for line in _block(request.user, "posting").splitlines()]
    chosen = [line for line in lines if len(line) >= MIN_LINE_CHARS][:MAX_REQUIREMENTS]
    return RequirementList(
        requirements=[
            RequirementDraft(
                id=i, text=line, kind="mandatory", weight=1, min_months=None, parent=None
            )
            for i, line in enumerate(chosen or ["General experience"], start=1)
        ]
    )


def _parsed() -> ParsedCV:
    return ParsedCV(
        is_cv=True,
        suspected_injection=False,
        experience=[],
        education=[],
        skills=[],
        certificates=[],
        languages=[],
        projects=[],
    )


def _verdict(label: int, text: str, cv_lines: list[str]) -> RequirementVerdict:
    words = {w for w in re.findall(r"\w+", text.casefold()) if len(w) >= MIN_WORD_CHARS}
    for line in cv_lines:
        if words & set(re.findall(r"\w+", line.casefold())):
            return RequirementVerdict(
                requirement_id=label, verdict="met", quote=line, rationale="Keyword match (demo)."
            )
    return RequirementVerdict(
        requirement_id=label, verdict="not_met", quote=None, rationale="No keyword match (demo)."
    )


def _judged(request: LLMRequest) -> JudgeOutput:
    cv_lines = [line.strip() for line in _block(request.user, "cv").splitlines() if line.strip()]
    wanted = re.findall(r"^- id (\d+)[^:\n]*: (.*)$", _block(request.user, "requirements"), re.M)
    return JudgeOutput(verdicts=[_verdict(int(i), text, cv_lines) for i, text in wanted])


def _answer(request: LLMRequest, schema: type[BaseModel]) -> BaseModel:
    if schema is RequirementList:
        return _requirements(request)
    if schema is ParsedCV:
        return _parsed()
    if schema is JudgeOutput:
        return _judged(request)
    raise AssertionError(f"the demo client has no answer for {schema.__name__}")


def _estimated_usage(request: LLMRequest, output: BaseModel) -> LLMUsage:
    """About four characters per token. Invented numbers, so that a trace of a walkthrough has
    usage and cost to show; they say nothing about a real model."""
    return LLMUsage(
        input_tokens=(len(request.system) + len(request.user)) // 4,
        output_tokens=len(output.model_dump_json()) // 4,
        latency_s=0.0,
        cache_hit=False,
    )


def create_demo_client() -> FakeLLMClient:
    return FakeLLMClient(responder=_answer, usage=_estimated_usage)
