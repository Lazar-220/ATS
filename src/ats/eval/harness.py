"""One evaluation run (§5.4): load the golden set, call the pipeline functions, compute metrics.

The pipeline functions are called directly, not over HTTP. Stages:

- `extraction`: the requirement extraction of 1.2 on every golden posting, scored against the gold
  requirements by `matching.py`. This calls the model, once per posting; the response cache
  makes a repeat free.
- `verdicts`: a judge answers every labelled CV-requirement pair of the chosen split, scored
  against the gold verdicts. The judge is `StubJudge`: no model, plumbing only.
- `judge` (variant A, from 1.4b): the same scoring with the real pipeline judge, which calls the
  model twice per CV (parse, judge) and checks the quotes. Reported with the flagged-verdict
  share, the majority-class accuracy, a sensitivity run without the uncertain verdicts, and the
  run count.
"""

import json
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from ats.buildinfo import code_version
from ats.eval.fallback import DEV_SMOKE_LABEL
from ats.eval.golden import GOLDEN_AS_OF, GoldSet
from ats.eval.matching import match_requirements
from ats.eval.metrics import (
    VERDICT_ORDER,
    ExtractionMetrics,
    GroundingMetrics,
    VerdictMetrics,
    extraction_metrics_from,
    grounding_metrics,
    pool_extraction,
    quote_exists,
    verdict_metrics,
)
from ats.eval.pipeline_judge import PipelineJudge
from ats.eval.schemas import Verdict
from ats.eval.stages import (
    ContactTruth,
    MaskingReport,
    ParsingReport,
    Subset,
    UsageRow,
    run_masking,
    run_parsing,
    select_subset,
)
from ats.eval.stub import Judge
from ats.llm.cache import ResponseCache, cache_key
from ats.llm.pricing import RATES, Rate, cost_usd, rate_on
from ats.llm.types import LLMClient, LLMOutputInvalid, RateLimitError
from ats.pipeline.context import ContextRequirement, build_context
from ats.pipeline.extract import extract_text
from ats.pipeline.facts import build_facts
from ats.pipeline.judge import PROMPT_VERSION as JUDGE_PROMPT
from ats.pipeline.judge import JudgeIncomplete, JudgeOutput
from ats.pipeline.judge import build_request as build_judge_request
from ats.pipeline.masking import mask_text
from ats.pipeline.parsing import PROMPT_VERSION as PARSING_PROMPT
from ats.pipeline.parsing import THINKING_LEVEL as PARSING_THINKING
from ats.pipeline.parsing import ParsedCV
from ats.pipeline.parsing import build_request as build_parsing_request
from ats.pipeline.requirements import PROMPT_VERSION as REQUIREMENTS_PROMPT
from ats.pipeline.requirements import RequirementList, build_request, extract_requirements

type Stage = Literal["extraction", "verdicts", "masking", "parsing", "judge"]
type SplitChoice = Literal["dev", "test", "all"]

# Rough sizes for the dry run only. Characters per token is an average for Latin text with
# diacritics; the output figure is the larger of the two real extraction calls on record
# (354 and 508 output tokens, thinking included, docs/PROGRESS.md).
CHARS_PER_TOKEN = 3.5
EXTRACTION_OUTPUT_TOKENS = 500
# A parsed CV is a list of items with snippets: about 1,500 output tokens, a guess until one
# real call is on record.
PARSING_OUTPUT_TOKENS = 1500
# The judge answers a verdict, a quote and a rationale per requirement (about 120 tokens) after
# some thinking (low): a guess until one real call is on record.
JUDGE_OUTPUT_TOKENS_PER_REQUIREMENT = 120
JUDGE_THINKING_TOKENS = 500

# CLAUDE.md: a run that calls the real model more than this many times needs a confirmation.
MAX_CALLS_WITHOUT_CONFIRMATION = 5


class EvalError(Exception):
    pass


# --- The plan: what a run would cost, computed without calling anything --------------------


@dataclass(frozen=True)
class RunPlan:
    stages: tuple[Stage, ...]
    model: str
    llm_calls: int
    already_cached: int
    est_input_tokens: int
    est_output_tokens: int
    subset: Subset | None = None
    fallback_model: str | None = None
    judge_cvs: int = 0

    @property
    def uncached_calls(self) -> int:
        return self.llm_calls - self.already_cached

    def costs(self) -> list[tuple[Rate, float]]:
        return [
            (rate, cost_usd(rate, self.est_input_tokens, self.est_output_tokens))
            for rate in RATES.get(self.model, ())
        ]

    def describe(self) -> str:
        lines = [
            f"Dry run. Model {self.model}. Stages: {', '.join(self.stages)}.",
            f"LLM calls: {self.llm_calls} ({self.already_cached} already in the response cache, "
            f"{self.uncached_calls} would go to the model).",
        ]
        if "verdicts" in self.stages:
            lines.append("The verdict stage uses the stub judge: no calls, no cost.")
        if "masking" in self.stages:
            lines.append("The masking stage is code only: no calls, no cost.")
        if "judge" in self.stages:
            lines.append(
                f"The judge stage (variant A) calls the model for {self.judge_cvs} CVs of the "
                f"split: one parse call and one judge call each (prompts {PARSING_PROMPT}, "
                f"{JUDGE_PROMPT}); a judge answer that lacks a requirement costs one more."
            )
        if self.subset is not None:
            lines += _describe_subset(self.subset)
        if self.fallback_model:
            lines.append(
                f"Fallback enabled (opt-in): after a daily quota on {self.model} the run "
                f"continues on OpenRouter {self.fallback_model}, at most 50 calls a day and "
                f"20 per minute; the result is labelled '{DEV_SMOKE_LABEL}'. "
                f"The cost estimate above is for {self.model}."
            )
        lines.append(
            f"Estimate for the {self.uncached_calls} uncached calls: about "
            f"{self.est_input_tokens} input and {self.est_output_tokens} output tokens "
            "(a rough guess, not a measurement)."
        )
        costs = self.costs()
        if not costs:
            lines.append(f"No price is on record for {self.model}, so no cost is estimated.")
        for rate, value in costs:
            lines.append(
                f"  at {rate.input_per_m:.2f} / {rate.output_per_m:.2f} USD per million "
                f"tokens in / out ({rate.label}): about ${value:.4f}"
            )
        if len(costs) > 1:
            lines.append(
                "The introductory rate ends on 2026-12-31; the second rate applies from 2027-01-01."
            )
        return "\n".join(lines)


def _describe_subset(subset: Subset) -> list[str]:
    lines = [
        f"Parsing subset: seed {subset.seed}, {len(subset.cv_ids)} dev-split CVs, one call each "
        f"(prompt {PARSING_PROMPT}, thinking_level {PARSING_THINKING}).",
        "Coverage proof (value: selected CVs):",
    ]
    for dim, values in subset.coverage.items():
        lines.append(f"  {dim}")
        lines += [f"    {value}: {', '.join(ids)}" for value, ids in values.items()]
    return lines


def _posting_text(golden: GoldSet, position_id: str, min_chars_per_page: int) -> str:
    pdf = golden.positions[position_id].posting_pdf
    return extract_text(pdf.read_bytes(), min_chars_per_page=min_chars_per_page).text


def plan_run(
    golden: GoldSet,
    stages: Sequence[Stage],
    *,
    model: str,
    cache: ResponseCache,
    min_chars_per_page: int,
    fallback_model: str | None = None,
    split: SplitChoice = "dev",
    limit: int | None = None,
    as_of: date = GOLDEN_AS_OF,
) -> RunPlan:
    calls = cached = in_tokens = out_tokens = 0
    judge_cvs = 0
    subset: Subset | None = None
    if "extraction" in stages:
        for position_id in sorted(golden.positions):
            request = build_request(_posting_text(golden, position_id, min_chars_per_page))
            calls += 1
            if cache.get(cache_key(model, request, RequirementList)) is not None:
                cached += 1
                continue
            in_tokens += int((len(request.system) + len(request.user)) / CHARS_PER_TOKEN)
            out_tokens += EXTRACTION_OUTPUT_TOKENS
    if "parsing" in stages:
        subset = select_subset(golden)
        for cv_id in subset.cv_ids:
            text = extract_text(
                golden.cvs[cv_id].pdf.read_bytes(), min_chars_per_page=min_chars_per_page
            ).text
            request = build_parsing_request(mask_text(text).masked_text)
            calls += 1
            if cache.get(cache_key(model, request, ParsedCV)) is not None:
                cached += 1
                continue
            in_tokens += int((len(request.system) + len(request.user)) / CHARS_PER_TOKEN)
            out_tokens += PARSING_OUTPUT_TOKENS
    if "judge" in stages:
        for cv_id in select_cvs(golden, split, limit):
            judge_cvs += 1
            cv = golden.cvs[cv_id]
            text = extract_text(cv.pdf.read_bytes(), min_chars_per_page=min_chars_per_page).text
            masked = mask_text(text)
            parse_request = build_parsing_request(masked.masked_text)
            calls += 1
            parse_hit = cache.get(cache_key(model, parse_request, ParsedCV))
            if parse_hit is None:
                in_tokens += int(
                    (len(parse_request.system) + len(parse_request.user)) / CHARS_PER_TOKEN
                )
                out_tokens += PARSING_OUTPUT_TOKENS
            else:
                cached += 1
            requirements = golden.positions[cv.profile.position_id].meta.requirements
            context_reqs = [
                ContextRequirement(r.id, r.text, r.kind, r.weight, r.min_months, r.parent)
                for r in requirements
            ]
            calls += 1
            if parse_hit is not None:
                # The parse is cached, so the judge prompt is known exactly and can be looked up.
                parsed = ParsedCV.model_validate_json(parse_hit.text)
                facts = build_facts(parsed, masked.masked_text, masked.spans, as_of)
                judge_request = build_judge_request(
                    build_context(masked.masked_text, facts.parsed_json, context_reqs)
                )
                if cache.get(cache_key(model, judge_request, JudgeOutput)) is not None:
                    cached += 1
                    continue
            else:
                # Parse not cached: the facts are not known yet, so the prompt size is a guess
                # from the masked CV, the rubric and the instructions.
                judge_request = build_judge_request(
                    build_context(
                        masked.masked_text,
                        {
                            "experience": [],
                            "tenure": {"total_months": 0, "as_of": as_of.isoformat()},
                        },
                        context_reqs,
                    )
                )
            in_tokens += int(
                (len(judge_request.system) + len(judge_request.user)) / CHARS_PER_TOKEN
            )
            out_tokens += JUDGE_THINKING_TOKENS + JUDGE_OUTPUT_TOKENS_PER_REQUIREMENT * len(
                requirements
            )
    return RunPlan(
        tuple(stages),
        model,
        calls,
        cached,
        in_tokens,
        out_tokens,
        subset,
        fallback_model,
        judge_cvs,
    )


# --- The result ----------------------------------------------------------------------------


class PipelineVersion(BaseModel):
    code: str  # branch@commit, with -dirty for uncommitted changes
    prompts: dict[str, str]
    model: str
    judge: str

    @property
    def label(self) -> str:
        prompts = ",".join(sorted(self.prompts.values()))
        return f"{self.code} | {prompts} | model={self.model} | judge={self.judge}"


class MatchRecord(BaseModel):
    gold_id: int
    extracted_id: int
    score: float
    via: str
    kind_correct: bool


class ExtractionItem(BaseModel):
    position_id: str
    metrics: ExtractionMetrics
    matches: list[MatchRecord]
    missed_gold_ids: list[int]
    missed_gold: list[str]  # "id: text", for reading the report
    extra_extracted: list[str]  # texts of extracted requirements that matched nothing


class ExtractionReport(BaseModel):
    overall: ExtractionMetrics
    positions: list[ExtractionItem]


class VerdictItem(BaseModel):
    cv_id: str
    requirement_id: int
    gold: Verdict
    predicted: Verdict
    gold_quote: str | None
    predicted_quote: str | None
    quote_exists: bool | None  # None: no quote to check
    # Quote-check flags from the pipeline judge; empty for the stub.
    flags: list[str] = []
    # One of the verdicts the golden-set writers or the audit were unsure of (uncertain.json).
    uncertain: bool = False


class GroupAccuracy(BaseModel):
    n: int
    accuracy: float


class Sensitivity(BaseModel):
    """The same metrics without the uncertain verdicts (docs/PROGRESS.md, carried over from 1.3)."""

    excluded: int
    n: int
    accuracy: float
    macro_f1: float
    majority_class_accuracy: float


class FlaggedReport(BaseModel):
    verdicts: int
    flagged: int
    flagged_share: float
    by_code: dict[str, int]
    # Of the met or partial verdicts, which are the ones that need a quote.
    claims: int
    flagged_claims: int
    flagged_claim_share: float | None
    # Quotes the API would show as evidence: unflagged, so found in the CV by the check.
    evidence_quotes: int


class VerdictReport(BaseModel):
    judge: str
    # How the gold verdicts of the evaluated pairs are spread, and the accuracy of always
    # answering the most common one: a judge has to beat that, not 50%.
    gold_distribution: dict[str, int]
    majority_class_accuracy: float
    cvs: int
    overall: VerdictMetrics
    grounding: GroundingMetrics
    by_style: dict[str, GroupAccuracy]
    by_hard_case: dict[str, GroupAccuracy]
    items: list[VerdictItem]
    flagged: FlaggedReport
    sensitivity: Sensitivity | None = None
    # CVs the judge could not answer (incomplete or invalid output after the retries); they are
    # left out of every number above and listed here.
    failed_cvs: list[str] = []
    # Set when a 429 survived the client's retries: the run stops there.
    stopped: str | None = None


class UsageReport(BaseModel):
    llm_calls: int  # answered by the model
    cache_hits: int
    input_tokens: int
    output_tokens: int
    latency_s: float
    # Nearest-rank 95th percentile over the calls the model answered (cache hits excluded).
    latency_p95_s: float | None = None
    cost_usd: float | None
    rate: str | None


# Until the owner's manual 20% check is done, every result says so (docs/PROGRESS.md).
GOLD_LABEL_STATUS = "gold labels not manually verified"


class RunResult(BaseModel):
    gold_labels: str = GOLD_LABEL_STATUS
    # Set when a fallback model answered any call: such a run is a smoke test, not a baseline.
    label: str | None = None
    models: dict[str, str | None] = {}
    variant: str
    split: str
    limit: int | None
    stages: list[str]
    started_at: str
    # The date "present" means in the golden CVs; tenure is computed as of this day.
    as_of: str
    pipeline_version: PipelineVersion
    extraction: ExtractionReport | None
    verdicts: VerdictReport | None
    # 1 plus the earlier result files with the same variant, split, stages, limit and
    # pipeline_version. Model output is not deterministic (§5.3): read every number with it.
    run_count: int = 1
    masking: MaskingReport | None = None
    parsing: ParsingReport | None = None
    usage: UsageReport


# --- Running -------------------------------------------------------------------------------


def _run_extraction(
    golden: GoldSet, client: LLMClient, min_chars_per_page: int
) -> tuple[ExtractionReport, list[UsageRow]]:
    items: list[ExtractionItem] = []
    usage: list[UsageRow] = []
    for position_id in sorted(golden.positions):
        meta = golden.positions[position_id].meta
        result = extract_requirements(
            client, _posting_text(golden, position_id, min_chars_per_page)
        )
        usage.append(
            (
                result.usage.input_tokens,
                result.usage.output_tokens,
                result.usage.latency_s,
                result.usage.cache_hit,
                result.usage.model,
            )
        )
        drafts = result.output.requirements
        matched = match_requirements(drafts, meta.requirements)
        by_id = {d.id: d.text for d in drafts}
        items.append(
            ExtractionItem(
                position_id=position_id,
                metrics=extraction_metrics_from(matched),
                matches=[
                    MatchRecord(
                        gold_id=m.gold_id,
                        extracted_id=m.extracted_id,
                        score=m.score,
                        via=m.via,
                        kind_correct=m.kind_correct,
                    )
                    for m in matched.matches
                ],
                missed_gold_ids=matched.unmatched_gold,
                missed_gold=[
                    f"{r.id}: {r.text}" for r in meta.requirements if r.id in matched.unmatched_gold
                ],
                extra_extracted=[by_id[i] for i in matched.unmatched_extracted],
            )
        )
    return ExtractionReport(
        overall=pool_extraction([i.metrics for i in items]), positions=items
    ), usage


def _group(rows: dict[str, list[bool]]) -> dict[str, GroupAccuracy]:
    return {
        key: GroupAccuracy(n=len(hits), accuracy=sum(hits) / len(hits))
        for key, hits in sorted(rows.items())
    }


def _majority(items: Sequence[VerdictItem]) -> float:
    counts = Counter(i.gold for i in items)
    return max(counts.values()) / len(items) if items else 0.0


def _flag_report(items: Sequence[VerdictItem]) -> FlaggedReport:
    claims = [i for i in items if i.predicted != "not_met"]
    flagged = [i for i in items if i.flags]
    flagged_claims = [i for i in claims if i.flags]
    return FlaggedReport(
        verdicts=len(items),
        flagged=len(flagged),
        flagged_share=len(flagged) / len(items) if items else 0.0,
        by_code=dict(sorted(Counter(code for i in items for code in i.flags).items())),
        claims=len(claims),
        flagged_claims=len(flagged_claims),
        flagged_claim_share=len(flagged_claims) / len(claims) if claims else None,
        evidence_quotes=sum(1 for i in claims if i.predicted_quote and not i.flags),
    )


def _run_verdicts(
    golden: GoldSet,
    judge: Judge,
    cv_ids: Sequence[str],
    min_chars_per_page: int,
    uncertain: frozenset[tuple[str, int]] = frozenset(),
) -> VerdictReport:
    items: list[VerdictItem] = []
    grounding_input: list[tuple[Verdict, str | None, str]] = []
    by_style: dict[str, list[bool]] = defaultdict(list)
    by_hard_case: dict[str, list[bool]] = defaultdict(list)
    failed: list[str] = []
    stopped: str | None = None
    evaluated = 0
    for cv_id in cv_ids:
        cv = golden.cvs[cv_id]
        position = golden.positions[cv.profile.position_id].meta
        text = extract_text(cv.pdf.read_bytes(), min_chars_per_page=min_chars_per_page).text
        try:
            answers = {a.requirement_id: a for a in judge.judge(cv_id, text, position)}
        except RateLimitError as exc:
            # A daily quota does not come back within the run; keep what is judged and say so.
            stopped = f"rate limit after {evaluated} of {len(cv_ids)} CVs, at {cv_id}: {exc}"
            break
        except (JudgeIncomplete, LLMOutputInvalid) as exc:
            failed.append(f"{cv_id}: {exc}")
            continue
        gold_rows = golden.verdicts_for(cv_id)
        if set(answers) != {row.requirement_id for row in gold_rows}:
            raise EvalError(f"the judge did not answer every requirement of {cv_id} exactly once")
        evaluated += 1
        for row in gold_rows:
            answer = answers[row.requirement_id]
            hit = answer.verdict == row.verdict
            by_style[cv.profile.style].append(hit)
            if cv.profile.hard_case:
                by_hard_case[cv.profile.hard_case.tag].append(hit)
            grounding_input.append((answer.verdict, answer.quote, text))
            items.append(
                VerdictItem(
                    cv_id=cv_id,
                    requirement_id=row.requirement_id,
                    gold=row.verdict,
                    predicted=answer.verdict,
                    gold_quote=row.quote,
                    predicted_quote=answer.quote,
                    quote_exists=quote_exists(answer.quote, text) if answer.quote else None,
                    flags=list(answer.flags),
                    uncertain=(cv_id, row.requirement_id) in uncertain,
                )
            )
    gold_counts = Counter(i.gold for i in items)
    kept = [i for i in items if not i.uncertain]
    sensitivity: Sensitivity | None = None
    if uncertain and kept:
        kept_metrics = verdict_metrics([(i.gold, i.predicted) for i in kept])
        sensitivity = Sensitivity(
            excluded=len(items) - len(kept),
            n=len(kept),
            accuracy=kept_metrics.accuracy,
            macro_f1=kept_metrics.macro_f1,
            majority_class_accuracy=_majority(kept),
        )
    return VerdictReport(
        judge=judge.name,
        gold_distribution={v: gold_counts.get(v, 0) for v in VERDICT_ORDER},
        majority_class_accuracy=_majority(items),
        cvs=evaluated,
        overall=verdict_metrics([(i.gold, i.predicted) for i in items]),
        grounding=grounding_metrics(grounding_input),
        by_style=_group(by_style),
        by_hard_case=_group(by_hard_case),
        items=items,
        flagged=_flag_report(items),
        sensitivity=sensitivity,
        failed_cvs=failed,
        stopped=stopped,
    )


def select_cvs(golden: GoldSet, split: SplitChoice, limit: int | None) -> list[str]:
    """CV ids of the split in id order; `limit` keeps the first n."""
    ids = golden.cv_ids(None if split == "all" else split)
    return ids[:limit] if limit is not None else ids


def run_eval(
    golden: GoldSet,
    *,
    variant: str,
    split: SplitChoice,
    limit: int | None,
    stages: Sequence[Stage],
    judge: Judge,
    client: LLMClient | None,
    model: str,
    min_chars_per_page: int,
    contacts: dict[str, ContactTruth] | None = None,
    fallback_model: str | None = None,
    as_of: date = GOLDEN_AS_OF,
    price_date: date | None = None,
    uncertain: frozenset[tuple[str, int]] = frozenset(),
) -> RunResult:
    if variant != "A":
        raise EvalError(f"variant {variant} does not exist yet; B, C and D arrive in phase 3")
    extraction: ExtractionReport | None = None
    verdicts: VerdictReport | None = None
    usage_rows: list[UsageRow] = []
    if "extraction" in stages:
        if client is None:
            raise EvalError("the extraction stage needs an LLM client")
        extraction, usage_rows = _run_extraction(golden, client, min_chars_per_page)
    if "verdicts" in stages or "judge" in stages:
        if "judge" in stages and not isinstance(judge, PipelineJudge):
            raise EvalError("the judge stage needs the pipeline judge (and so an LLM client)")
        verdicts = _run_verdicts(
            golden, judge, select_cvs(golden, split, limit), min_chars_per_page, uncertain
        )
        if isinstance(judge, PipelineJudge):
            usage_rows += judge.usage_rows

    masking: MaskingReport | None = None
    parsing: ParsingReport | None = None
    if "masking" in stages:
        if contacts is None:
            raise EvalError("the masking stage needs contacts.json")
        masking = run_masking(
            golden, contacts, select_cvs(golden, split, limit), min_chars_per_page
        )
    if "parsing" in stages:
        if client is None:
            raise EvalError("the parsing stage needs an LLM client")
        if split != "dev":
            raise EvalError("the parsing stage runs on the dev split only")
        subset = select_subset(golden)
        parsing, parsing_usage = run_parsing(
            golden, client, subset.cv_ids, min_chars_per_page, as_of
        )
        usage_rows += parsing_usage

    input_tokens = sum(row[0] for row in usage_rows)
    output_tokens = sum(row[1] for row in usage_rows)
    now = datetime.now(UTC)
    # Only calls the primary model answered are priced; the fallback models are free.
    primary_rows = [row for row in usage_rows if row[4] in ("", model)]
    rate = rate_on(model, price_date or now.date()) if primary_rows else None
    answered_by = {row[4] for row in usage_rows if row[4]}
    label = DEV_SMOKE_LABEL if answered_by - {model} else None
    return RunResult(
        label=label,
        models={"primary": model, "fallback": fallback_model},
        variant=variant,
        split=split,
        limit=limit,
        stages=list(stages),
        started_at=now.isoformat(timespec="seconds"),
        as_of=as_of.isoformat(),
        pipeline_version=PipelineVersion(
            code=code_version(),
            prompts={"requirements": REQUIREMENTS_PROMPT}
            | ({"cv_parse": PARSING_PROMPT} if "parsing" in stages or "judge" in stages else {})
            | ({"judge": JUDGE_PROMPT} if "judge" in stages else {}),
            model=model,
            judge=judge.name,
        ),
        extraction=extraction,
        verdicts=verdicts,
        masking=masking,
        parsing=parsing,
        usage=UsageReport(
            llm_calls=sum(1 for row in usage_rows if not row[3]),
            cache_hits=sum(1 for row in usage_rows if row[3]),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_s=sum(row[2] for row in usage_rows),
            latency_p95_s=_p95([row[2] for row in usage_rows if not row[3]]),
            cost_usd=(
                cost_usd(rate, sum(r[0] for r in primary_rows), sum(r[1] for r in primary_rows))
                if rate
                else None
            ),
            rate=rate.label if rate else None,
        ),
    )


def count_prior_runs(directory: Path, result: RunResult) -> int:
    """How many earlier result files describe the same configuration as `result`."""
    count = 0
    for path in sorted(directory.glob("*.json")) if directory.is_dir() else []:
        try:
            earlier = RunResult.model_validate_json(path.read_text(encoding="utf-8"))
        except ValueError:
            continue  # a file from an older result format is not a run of this configuration
        if (
            earlier.variant == result.variant
            and earlier.split == result.split
            and earlier.limit == result.limit
            and earlier.stages == result.stages
            and earlier.pipeline_version == result.pipeline_version
        ):
            count += 1
    return count


def _p95(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, -(-95 * len(ordered) // 100) - 1)]


def write_result(result: RunResult, directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    stamp = result.started_at.replace("-", "").replace(":", "").removesuffix("+0000")
    path = directory / f"{stamp}_{result.variant}_{result.split}.json"
    path.write_text(
        json.dumps(result.model_dump(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return path


# --- The table -----------------------------------------------------------------------------


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:5.1f}%"


def format_report(result: RunResult) -> str:
    version = result.pipeline_version
    lines = [
        f"Eval  variant {result.variant}  split {result.split}"
        + (f"  limit {result.limit}" if result.limit is not None else "")
        + f"  run {result.run_count} of this configuration",
        f"pipeline_version: {version.label}",
        f"gold labels: {result.gold_labels.removeprefix('gold labels ')}",
    ]
    if result.label:
        lines.append(
            f"LABEL: {result.label}. Primary {result.models.get('primary')}, fallback "
            f"{result.models.get('fallback')}: some calls were answered by the fallback model."
        )
    if result.split == "test":
        lines.append("NOTE: the test split is for published numbers; tune on dev only.")
    if result.extraction:
        lines += ["", "REQUIREMENT EXTRACTION (real model)"]
        header = f"  {'position':<22}{'extr':>5}{'gold':>5}{'match':>6}"
        lines.append(header + f"  {'P':>7}{'R':>8}{'F1':>8}{'label':>8}")
        rows = [(i.position_id, i.metrics) for i in result.extraction.positions]
        rows.append(("ALL (pooled)", result.extraction.overall))
        for name, m in rows:
            counts = f"  {name:<22}{m.extracted:>5}{m.gold:>5}{m.matched:>6}  "
            ratios = (m.precision, m.recall, m.f1)
            lines.append(
                counts
                + "".join(f"{_pct(r):>{w}}" for r, w in zip(ratios, (7, 8, 8), strict=True))
                + f"{_pct(m.label_accuracy):>8}"
            )
        # Every unmatched requirement is listed, on both sides, so a matcher error can be told
        # from a model error by reading the two texts.
        for item in result.extraction.positions:
            loose = [m for m in item.matches if m.score < 1.0]
            if not (item.extra_extracted or item.missed_gold or loose):
                continue
            lines += ["", f"  {item.position_id}"]
            lines += [f"    extracted, matched nothing: {text!r}" for text in item.extra_extracted]
            lines += [f"    gold, matched by nothing:   {text!r}" for text in item.missed_gold]
            lines += [
                f"    matched below 1.0: extracted {m.extracted_id} = gold {m.gold_id} "
                f"({m.score:.2f}, via {m.via!r})"
                for m in loose
            ]
    if result.verdicts:
        v = result.verdicts
        lines += ["", f"VERDICTS ({v.cvs} CVs, {v.overall.n} pairs), judge: {v.judge}"]
        spread = ", ".join(f"{k} {n}" for k, n in v.gold_distribution.items())
        lines.append(
            f"  gold verdicts: {spread}; always answering the majority class scores "
            f"{_pct(v.majority_class_accuracy).strip()}"
        )
        if v.judge == "llm":
            lines.append(
                "  Real pipeline judge (variant A); gold labels are not manually verified."
            )
        if v.judge == "stub":
            lines.append("  The judge is a stub that spoils gold labels on purpose; the numbers")
            lines.append("  prove the plumbing and say nothing about the model.")
        kappa = "n/a" if v.overall.weighted_kappa is None else f"{v.overall.weighted_kappa:.3f}"
        lines.append(
            f"  accuracy {_pct(v.overall.accuracy).strip()}   macro-F1 {v.overall.macro_f1:.3f}"
            f"   weighted kappa {kappa}   (run {result.run_count}, "
            f"{result.usage.cache_hits} cache hits)"
        )
        if v.stopped:
            lines.append(f"  STOPPED: {v.stopped}")
        if v.failed_cvs:
            lines.append(f"  {len(v.failed_cvs)} CVs failed and are left out of every number:")
            lines += [f"    {failure}" for failure in v.failed_cvs]
        if v.sensitivity:
            sens = v.sensitivity
            lines.append(
                f"  without the {sens.excluded} uncertain verdicts (n={sens.n}): accuracy "
                f"{_pct(sens.accuracy).strip()}   macro-F1 {sens.macro_f1:.3f}   majority class "
                f"{_pct(sens.majority_class_accuracy).strip()}   (run {result.run_count})"
            )
        f = v.flagged
        codes = ", ".join(f"{code} {n}" for code, n in f.by_code.items()) or "none"
        claim_share = _pct(f.flagged_claim_share).strip()
        lines.append(
            f"  flagged verdicts: {f.flagged}/{f.verdicts} ({_pct(f.flagged_share).strip()}); "
            f"of the {f.claims} met/partial verdicts {f.flagged_claims} ({claim_share}); "
            f"by flag: {codes}; quotes shown as evidence: {f.evidence_quotes} "
            f"(run {result.run_count})"
        )
        lines.append("  confusion (rows gold, columns predicted):")
        lines.append(f"    {'':<10}" + "".join(f"{label:>9}" for label in v.overall.labels))
        for label, row in zip(v.overall.labels, v.overall.confusion, strict=True):
            lines.append(f"    {label:<10}" + "".join(f"{count:>9}" for count in row))
        g = v.grounding
        share = _pct(g.quote_exists_share).strip()
        lines.append(
            f"  quotes that exist in the CV: {g.quote_exists}/{g.quoted} ({share});"
            f" met/partial without a quote: {g.unquoted}"
        )
        for title, groups in (("by style", v.by_style), ("by hard case", v.by_hard_case)):
            if groups:
                text = ", ".join(
                    f"{k} {_pct(a.accuracy).strip()} (n={a.n})" for k, a in groups.items()
                )
                lines.append(f"  accuracy {title}: {text}")
    if result.masking:
        m = result.masking
        lines += ["", f"MASKING LEAKS ({m.cvs} CVs, code only)"]
        lines.append(
            f"  email {len(m.email_leaks)} ({_pct(m.email_rate).strip()}), "
            f"phone {len(m.phone_leaks)} ({_pct(m.phone_rate).strip()}), "
            f"name {len(m.name_leaks)} ({_pct(m.name_rate).strip()})"
        )
        lines += [f"  email leaked: {cv_id}" for cv_id in m.email_leaks]
        lines += [f"  phone leaked: {cv_id}" for cv_id in m.phone_leaks]
        lines += [f"  name leaked: {leak.cv_id} {leak.tokens}" for leak in m.name_leaks]
    if result.parsing:
        p = result.parsing
        lines += ["", f"PARSING (real model, {p.cvs} of {p.requested} CVs)"]
        if p.stopped:
            lines.append(f"  STOPPED: {p.stopped}")
        lines.append(
            f"  not a CV {len(p.not_a_cv)}, low coverage {len(p.low_coverage)} {p.low_coverage}, "
            f"suspected injection {len(p.suspected_injection)}"
        )
        for template, row in p.by_template.items():
            lines.append(
                f"  {template}: {int(row['cvs'])} CVs, mean coverage "
                f"{row['mean_coverage'] * 100:.1f}%, "
                f"unlocated snippets {int(row['unlocated_items'])}"
            )
    u = result.usage
    tokens = f"tokens {u.input_tokens} in / {u.output_tokens} out"
    lines += ["", f"USAGE  LLM calls {u.llm_calls}, cache hits {u.cache_hits}, {tokens}"]
    if u.cost_usd is not None:
        lines.append(f"  cost ${u.cost_usd:.4f} ({u.rate}), latency {u.latency_s:.1f}s")
        if result.verdicts and result.verdicts.cvs and result.verdicts.judge == "llm":
            per_cv = u.cost_usd / result.verdicts.cvs
            lines.append(f"  cost per CV (parse + judge) ${per_cv:.4f}")
    if u.latency_p95_s is not None:
        lines.append(f"  p95 latency per model call {u.latency_p95_s:.1f}s (answered, not cached)")
    return "\n".join(lines)
