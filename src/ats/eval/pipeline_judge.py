"""Variant A judge: the production judge path, run on a golden CV (§5.4).

Same functions as the worker calls: mask, parse (one call), computed tenure, `build_context`,
judge (one call), quote check. Requirements are the gold ones, so judge accuracy is not mixed with
extraction quality; production gives the judge the position's stored requirements instead.
"""

from collections.abc import Sequence
from datetime import date

from ats.eval.schemas import Position
from ats.eval.stages import UsageRow
from ats.eval.stub import JudgedVerdict
from ats.llm.types import LLMClient, LLMUsage
from ats.pipeline.context import ContextRequirement, build_context
from ats.pipeline.facts import build_facts
from ats.pipeline.judge import judge
from ats.pipeline.listonly import list_only_detail
from ats.pipeline.masking import mask_text
from ats.pipeline.parsing import parse_cv
from ats.pipeline.quotes import check_quote


def _row(usage: LLMUsage) -> UsageRow:
    return (
        usage.input_tokens,
        usage.output_tokens,
        usage.latency_s,
        usage.cache_hit,
        usage.model,
    )


class PipelineJudge:
    name = "llm"

    def __init__(self, client: LLMClient, *, as_of: date, quote_threshold: int) -> None:
        self._client = client
        self._as_of = as_of
        self._threshold = quote_threshold
        # One row per model call group: the parse call, then the judge call (a completeness
        # retry adds its tokens to the judge row).
        self.usage_rows: list[UsageRow] = []
        self.judge_calls = 0

    def judge(self, cv_id: str, cv_text: str, position: Position) -> Sequence[JudgedVerdict]:
        del cv_id
        masked = mask_text(cv_text)
        parsed = parse_cv(self._client, masked.masked_text)
        self.usage_rows.append(_row(parsed.usage))
        facts = build_facts(parsed.output, masked.masked_text, masked.spans, self._as_of)
        pack = build_context(
            masked.masked_text,
            facts.parsed_json,
            [
                ContextRequirement(
                    label=r.id,
                    text=r.text,
                    kind=r.kind,
                    weight=r.weight,
                    min_months=r.min_months,
                    parent_label=r.parent,
                )
                for r in position.requirements
            ],
        )
        result = judge(self._client, pack)
        self.usage_rows.append(_row(result.usage))
        self.judge_calls += result.calls
        answers: list[JudgedVerdict] = []
        for label, verdict in sorted(result.verdicts.items()):
            check = check_quote(
                verdict.verdict, verdict.quote, masked.masked_text, masked.spans, self._threshold
            )
            quote = verdict.quote if verdict.verdict != "not_met" else None
            # The list-only rule in code, as in production. The downgrade is not added to the
            # quote-check flags: those say the quote failed, and this quote is fine.
            downgraded = list_only_detail(verdict.verdict, check, facts.parsed_json) is not None
            answers.append(
                JudgedVerdict(
                    label, "partial" if downgraded else verdict.verdict, quote, check.flags
                )
            )
        return answers
