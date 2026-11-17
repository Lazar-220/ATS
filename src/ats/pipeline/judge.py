"""The judge: one LLM call per CV-position pair, a verdict and a quote each (§2.4 step 6).

Prompt order is the stable prefix first (instructions, then the rubric) and the CV last, so the
provider can cache the prefix across the CVs of one position (§4.5). The CV sits in a fenced
block that the system message declares inert (§4.4). The judge has no tools.
"""

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel

from ats.llm.types import LLMClient, LLMRequest, LLMUsage, ThinkingLevel
from ats.pipeline.context import ContextPack, ContextRequirement
from ats.prompts import load_prompt

PROMPT_VERSION = "judge_v1"
THINKING_LEVEL: ThinkingLevel = "low"

type VerdictValue = Literal["met", "partial", "not_met"]


class RequirementVerdict(BaseModel):
    requirement_id: int
    verdict: VerdictValue
    # At most one quote per requirement (the verdict table has room for one). Code checks it.
    quote: str | None
    rationale: str


class JudgeOutput(BaseModel):
    verdicts: list[RequirementVerdict]


class JudgeIncomplete(Exception):
    """After a second call a requirement still had no verdict, or had two (§3.2)."""


@dataclass(frozen=True)
class JudgeResult:
    verdicts: dict[int, RequirementVerdict]
    # Calls made: 2 when the first answer was incomplete and the judge was called once more.
    calls: int
    usage: LLMUsage


def _fence(text: str, tag: str) -> str:
    # A literal closing tag inside the CV must not end the data block early.
    return f"<{tag}>\n{text.replace(f'</{tag}>', f'</ {tag}>')}\n</{tag}>"


def _requirement_line(req: ContextRequirement) -> str:
    parts = [f"id {req.label} [{req.kind}, weight {req.weight}]"]
    if req.min_months is not None:
        parts.append(f"minimum {req.min_months} months")
    if req.parent_label is not None:
        parts.append(f"refines id {req.parent_label}")
    return f"- {'; '.join(parts)}: {req.text}"


def _facts(pack: ContextPack) -> str:
    lines = [f"Reference date for 'present': {pack.as_of}.", "Jobs, with months computed by code:"]
    for job in pack.experience:
        months = "unknown" if job.months is None else str(job.months)
        approx = " (approximate, year-only dates)" if job.approximate else ""
        place = f" at {job.organization}" if job.organization else ""
        lines.append(
            f"- {job.title}{place}, {job.date_start or '?'} to {job.date_end or '?'}: "
            f"{months} months{approx}"
        )
    if not pack.experience:
        lines.append("- none found")
    lines.append(f"Total months of experience, overlaps merged: {pack.total_months}.")
    return "\n".join(lines)


def build_request(pack: ContextPack) -> LLMRequest:
    requirements = "\n".join(_requirement_line(r) for r in pack.requirements)
    parts = [_fence(requirements, "requirements")]
    if pack.rules:
        parts.append(_fence("\n".join(pack.rules), "rules"))
    # The facts differ per CV, so they come after the rubric and before the CV.
    parts += [_fence(_facts(pack), "facts"), _fence(pack.masked_cv, "cv")]
    return LLMRequest(
        system=load_prompt(PROMPT_VERSION),
        user="\n".join(parts),
        thinking_level=THINKING_LEVEL,
        prompt_version=PROMPT_VERSION,
    )


def _complete(output: JudgeOutput, pack: ContextPack) -> dict[int, RequirementVerdict] | None:
    wanted = {r.label for r in pack.requirements}
    got = [v.requirement_id for v in output.verdicts]
    if len(got) != len(set(got)) or set(got) != wanted:
        return None
    return {v.requirement_id: v for v in output.verdicts}


def _add(a: LLMUsage, b: LLMUsage) -> LLMUsage:
    return LLMUsage(
        input_tokens=a.input_tokens + b.input_tokens,
        output_tokens=a.output_tokens + b.output_tokens,
        latency_s=a.latency_s + b.latency_s,
        cache_hit=a.cache_hit and b.cache_hit,
        model=b.model or a.model,
    )


def judge(client: LLMClient, pack: ContextPack) -> JudgeResult:
    """Every requirement must come back with exactly one verdict. If not, call once more, then fail.

    This is separate from the client's own retry for output that does not parse (§4.5).
    """
    request = build_request(pack)
    first = client.generate(request, JudgeOutput)
    found = _complete(first.output, pack)
    if found is not None:
        return JudgeResult(found, 1, first.usage)
    second = client.generate(request, JudgeOutput)
    found = _complete(second.output, pack)
    if found is None:
        raise JudgeIncomplete("a requirement has no verdict or two, after a second judge call")
    return JudgeResult(found, 2, _add(first.usage, second.usage))
