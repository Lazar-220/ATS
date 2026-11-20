"""Variant A end to end against a scripted model: no real call is made anywhere in this file."""

import re
from datetime import date
from pathlib import Path

import pytest
from pydantic import BaseModel

import ats.eval.__main__ as eval_cli
from ats.eval.golden import DEFAULT_ROOT, GOLDEN_AS_OF, GoldSet, load_golden
from ats.eval.harness import (
    count_prior_runs,
    format_report,
    plan_run,
    run_eval,
    select_cvs,
    write_result,
)
from ats.eval.pipeline_judge import PipelineJudge
from ats.eval.stages import load_uncertain
from ats.eval.stub import StubJudge
from ats.llm.cache import ResponseCache
from ats.llm.fake import FakeLLMClient
from ats.llm.types import LLMRequest, RateLimitError
from ats.pipeline.extract import extract_text
from ats.pipeline.judge import JudgeOutput, RequirementVerdict
from ats.pipeline.masking import mask_text
from ats.pipeline.parsing import ParsedCV

MODEL = "gemini-3.6-flash"
MIN_CHARS = 100
LIMIT = 4


@pytest.fixture(scope="module")
def golden() -> GoldSet:
    return load_golden()


def _empty_cv() -> ParsedCV:
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


def _scripted(golden: GoldSet, *, spoil: tuple[str, int] | None = None) -> FakeLLMClient:
    """Answers the parse call with an empty CV and the judge call with the gold verdicts and quotes.

    The golden CV is found from the masked text inside the request's `<cv>` block.
    """
    by_masked: dict[str, str] = {}
    for cv_id in select_cvs(golden, "dev", None):
        text = extract_text(golden.cvs[cv_id].pdf.read_bytes(), min_chars_per_page=MIN_CHARS).text
        by_masked[mask_text(text).masked_text] = cv_id

    def respond(request: LLMRequest, schema: type[BaseModel]) -> BaseModel:
        if schema is ParsedCV:
            return _empty_cv()
        match = re.search(r"<cv>\n(.*)\n</cv>\s*$", request.user, re.DOTALL)
        assert match is not None
        cv_id = by_masked[match.group(1)]
        verdicts: list[RequirementVerdict] = []
        for row in golden.verdicts_for(cv_id):
            quote = row.quote
            if spoil == (cv_id, row.requirement_id):
                quote = "A sentence that is nowhere in this CV, about leading a rocket programme"
            verdicts.append(
                RequirementVerdict(
                    requirement_id=row.requirement_id,
                    verdict=row.verdict,
                    quote=quote,
                    rationale="gold",
                )
            )
        return JudgeOutput(verdicts=verdicts)

    return FakeLLMClient(responder=respond)


def _run(golden: GoldSet, client: FakeLLMClient, **kwargs: object):  # type: ignore[no-untyped-def]
    return run_eval(
        golden,
        variant="A",
        split="dev",
        limit=LIMIT,
        stages=["judge"],
        judge=PipelineJudge(client, as_of=GOLDEN_AS_OF, quote_threshold=90),
        client=client,
        model=MODEL,
        min_chars_per_page=MIN_CHARS,
        uncertain=load_uncertain(DEFAULT_ROOT, golden),
        **kwargs,  # type: ignore[arg-type]
    )


def test_the_pipeline_judge_scores_a_gold_answering_model_and_flags_an_invented_quote(
    golden: GoldSet,
) -> None:
    ids = select_cvs(golden, "dev", LIMIT)
    row = next(r for r in golden.verdicts_for(ids[0]) if r.verdict != "not_met")
    client = _scripted(golden, spoil=(ids[0], row.requirement_id))

    result = _run(golden, client)

    assert result.verdicts is not None
    verdicts = result.verdicts
    assert verdicts.judge == "llm" and verdicts.cvs == LIMIT
    # The invented quote does not change the verdict (v1 keeps it as the judge gave it)...
    assert verdicts.overall.accuracy == 1.0
    # ...it is flagged, and every other met or partial quote passed the check.
    assert verdicts.flagged.flagged == 1
    assert verdicts.flagged.by_code == {"quote_not_found": 1}
    assert verdicts.flagged.evidence_quotes == verdicts.flagged.claims - 1
    assert verdicts.failed_cvs == [] and verdicts.stopped is None
    # Two model calls per CV: the parse and the judge.
    assert len(client.calls) == 2 * LIMIT
    assert result.usage.llm_calls == 2 * LIMIT
    assert result.usage.latency_p95_s == 0.0  # the fake client reports no latency
    assert result.pipeline_version.prompts["judge"] == "judge_v1"
    assert result.pipeline_version.judge == "llm"


def test_the_report_carries_the_majority_class_the_sensitivity_run_and_the_run_count(
    golden: GoldSet,
) -> None:
    result = _run(golden, _scripted(golden))
    assert result.verdicts is not None
    sens = result.verdicts.sensitivity
    assert sens is not None
    uncertain = load_uncertain(DEFAULT_ROOT, golden)
    in_run = {(i.cv_id, i.requirement_id) for i in result.verdicts.items}
    assert sens.excluded == len(in_run & uncertain)
    assert sens.n + sens.excluded == len(result.verdicts.items)
    assert 0 < result.verdicts.majority_class_accuracy < 1

    text = format_report(result)
    assert "run 1 of this configuration" in text
    assert "majority class" in text and "uncertain verdicts" in text
    assert "flagged verdicts: 0/" in text
    assert "not manually verified" in text


def test_a_second_result_of_the_same_configuration_counts_as_run_two(
    golden: GoldSet, tmp_path: Path
) -> None:
    result = _run(golden, _scripted(golden))
    assert count_prior_runs(tmp_path, result) == 0
    write_result(result, tmp_path)
    assert count_prior_runs(tmp_path, result) == 1
    other = _run(golden, _scripted(golden))
    other.limit = LIMIT + 1  # a different configuration is not a run of the same one
    assert count_prior_runs(tmp_path, other) == 0


def test_a_daily_quota_stops_the_run_and_keeps_what_was_judged(golden: GoldSet) -> None:
    inner = _scripted(golden)

    def respond(request: LLMRequest, schema: type[BaseModel]) -> BaseModel:
        if len(inner.calls) > 4:  # two CVs fully answered (parse + judge each)
            raise RateLimitError("daily quota", daily=True)
        assert inner.responder is not None
        return inner.responder(request, schema)

    client = FakeLLMClient(responder=respond)
    # the wrapper's own call list is separate, so count through `inner.calls` by hand
    original = client.generate

    def counting(request: LLMRequest, schema: type[BaseModel]):  # type: ignore[no-untyped-def]
        inner.calls.append(request)
        return original(request, schema)

    client.generate = counting  # type: ignore[method-assign]
    result = _run(golden, client)
    assert result.verdicts is not None
    assert result.verdicts.cvs == 2 and result.verdicts.stopped is not None
    assert "2 of 4 CVs" in result.verdicts.stopped


def test_an_incomplete_judge_answer_fails_that_cv_and_leaves_it_out(golden: GoldSet) -> None:
    inner = _scripted(golden)

    def respond(request: LLMRequest, schema: type[BaseModel]) -> BaseModel:
        assert inner.responder is not None
        answer = inner.responder(request, schema)
        if isinstance(answer, JudgeOutput):
            return JudgeOutput(verdicts=answer.verdicts[1:])  # a requirement is missing, always
        return answer

    result = _run(golden, FakeLLMClient(responder=respond))
    assert result.verdicts is not None
    assert result.verdicts.cvs == 0 and len(result.verdicts.failed_cvs) == LIMIT
    assert "failed and are left out" in format_report(result)


def test_the_judge_stage_without_a_pipeline_judge_is_refused(golden: GoldSet) -> None:
    from ats.eval.harness import EvalError

    with pytest.raises(EvalError):
        run_eval(
            golden, variant="A", split="dev", limit=1, stages=["judge"],
            judge=StubJudge(golden), client=None, model=MODEL, min_chars_per_page=MIN_CHARS,
        )  # fmt: skip


def test_the_dry_run_counts_two_calls_per_cv_and_notices_the_cache(
    golden: GoldSet, tmp_path: Path
) -> None:
    cache = ResponseCache(tmp_path)
    plan = plan_run(
        golden, ["judge"], model=MODEL, cache=cache, min_chars_per_page=MIN_CHARS,
        split="dev", limit=3, as_of=date(2026, 11, 17),
    )  # fmt: skip
    assert (plan.llm_calls, plan.already_cached, plan.uncached_calls) == (6, 0, 6)
    assert plan.est_input_tokens > 0 and plan.est_output_tokens > 0
    text = plan.describe()
    assert "judge stage" in text and "3 CVs" in text


def test_the_command_dry_run_for_the_judge_stage_calls_nothing(
    capsys: pytest.CaptureFixture[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(eval_cli, "RESULTS_DIR", tmp_path)
    monkeypatch.setenv("LLM_CACHE_DIR", str(tmp_path / "cache"))
    from ats.settings import get_settings

    get_settings.cache_clear()
    try:
        assert eval_cli.main(["run", "--stages", "judge", "--split", "test", "--dry-run"]) == 0
    finally:
        get_settings.cache_clear()
    out = capsys.readouterr().out
    assert "Dry run" in out and "LLM calls: 48" in out
    assert list(tmp_path.glob("*.json")) == []


def test_uncertain_json_names_only_pairs_that_have_a_gold_verdict(golden: GoldSet) -> None:
    pairs = load_uncertain(DEFAULT_ROOT, golden)
    assert ("sm_13", 11) in pairs and ("sm_07", 9) in pairs and ("sm_11", 4) in pairs
    assert len(pairs) == 32
