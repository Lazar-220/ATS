from datetime import date
from pathlib import Path

import pytest
from pydantic import BaseModel

from ats.eval.golden import DEFAULT_ROOT, GoldSet, load_golden
from ats.eval.harness import format_report, plan_run, run_eval
from ats.eval.stages import (
    SUBSET_SIZE,
    SubsetError,
    leaked_name_tokens,
    load_contacts,
    run_masking,
    run_parsing,
    select_subset,
)
from ats.eval.stub import StubJudge
from ats.llm.cache import ResponseCache
from ats.llm.fake import FakeLLMClient
from ats.llm.types import LLMRequest, RateLimitError
from ats.pipeline.parsing import ParsedCV

MIN_CHARS = 100
AS_OF = date(2026, 11, 17)


@pytest.fixture(scope="module")
def golden() -> GoldSet:
    return load_golden()


def _empty(is_cv: bool = True) -> ParsedCV:
    return ParsedCV(
        is_cv=is_cv,
        suspected_injection=False,
        experience=[],
        education=[],
        skills=[],
        certificates=[],
        languages=[],
        projects=[],
    )


def test_masking_leaks_nothing_for_email_and_phone_on_the_whole_golden_set(
    golden: GoldSet,
) -> None:
    report = run_masking(golden, load_contacts(DEFAULT_ROOT), golden.cv_ids(), MIN_CHARS)
    assert report.cvs == 80
    assert report.email_leaks == []
    assert report.phone_leaks == []
    assert report.name_leaks == []


def test_the_leak_check_notices_a_name_the_masker_missed() -> None:
    assert leaked_name_tokens("Радосављевић Тамара", "worked with Tamara and Ana") == ["tamara"]
    assert leaked_name_tokens("Ana Ilic", "[NAME] [NAME]") == []


def test_every_contact_truth_has_a_cv() -> None:
    assert set(load_contacts(DEFAULT_ROOT)) == set(load_golden().cv_ids())


def test_the_subset_is_dev_only_deterministic_and_covers_every_value(golden: GoldSet) -> None:
    subset = select_subset(golden)
    assert subset == select_subset(golden)
    assert len(subset.cv_ids) == SUBSET_SIZE
    assert set(subset.cv_ids) <= set(golden.cv_ids("dev"))
    coverage = subset.coverage
    assert set(coverage["language_script"]) == {
        "sr_latin",
        "sr_ascii",
        "sr_cyrillic",
        "en",
        "mixed",
    }
    assert set(coverage["layout"]) == {"single", "two_column"}
    assert len(coverage["position"]) == 6
    dev_hard_cases = {
        hard_case.tag
        for c in golden.cv_ids("dev")
        if (hard_case := golden.cvs[c].profile.hard_case)
    }
    assert set(coverage["hard_case"]) == dev_hard_cases
    assert all(ids for values in coverage.values() for ids in values.values())


def test_a_subset_too_small_to_cover_everything_is_an_error(golden: GoldSet) -> None:
    with pytest.raises(SubsetError):
        select_subset(golden, size=3)


def test_the_dry_run_lists_the_subset_the_calls_and_the_model(
    golden: GoldSet, tmp_path: Path
) -> None:
    plan = plan_run(
        golden,
        ["parsing"],
        model="gemini-3.6-flash",
        cache=ResponseCache(tmp_path),
        min_chars_per_page=MIN_CHARS,
    )
    text = plan.describe()
    assert plan.llm_calls == SUBSET_SIZE == plan.uncached_calls
    assert "seed 20261117" in text and "cv_parse_v1" in text and "thinking_level minimal" in text
    assert "gemini-3.6-flash" in text and "two_column:" in text and "sr_ascii:" in text


def test_a_parsing_run_keeps_masked_text_and_months_and_sees_no_contact_data(
    golden: GoldSet,
) -> None:
    fake = FakeLLMClient(responder=lambda _r, _s: _empty())
    ids = select_subset(golden).cv_ids[:3]
    report, usage = run_parsing(golden, fake, ids, MIN_CHARS, AS_OF)
    contacts = load_contacts(DEFAULT_ROOT)
    assert report.cvs == 3 and report.stopped is None and len(usage) == 3
    for call, cv_id in zip(fake.calls, ids, strict=True):
        assert contacts[cv_id].email not in call.user
    assert all(r.masked_text and "tenure" in r.parsed_json for r in report.records)


def test_a_rate_limit_that_survives_the_retries_stops_the_run_and_keeps_what_is_parsed(
    golden: GoldSet,
) -> None:
    seen: list[LLMRequest] = []

    def respond(request: LLMRequest, _schema: type[BaseModel]) -> BaseModel:
        seen.append(request)
        if len(seen) == 3:
            raise RateLimitError("daily quota exhausted")
        return _empty()

    ids = select_subset(golden).cv_ids
    report, _ = run_parsing(golden, FakeLLMClient(responder=respond), ids, MIN_CHARS, AS_OF)
    assert (report.requested, report.cvs) == (SUBSET_SIZE, 2)
    assert report.stopped is not None and ids[2] in report.stopped
    assert len(seen) == 3  # no CV after the failed one was tried


def test_a_daily_quota_429_stops_the_run_at_once_and_reports_n_of_18(golden: GoldSet) -> None:
    seen: list[str] = []

    def respond(request: LLMRequest, _schema: type[BaseModel]) -> BaseModel:
        seen.append(request.user)
        if len(seen) == 5:
            raise RateLimitError("per-day quota spent", daily=True)
        return _empty()

    ids = select_subset(golden).cv_ids
    report, _ = run_parsing(golden, FakeLLMClient(responder=respond), ids, MIN_CHARS, AS_OF)

    assert (report.requested, report.cvs) == (SUBSET_SIZE, 4)
    assert report.stopped is not None and "4 of 18" in report.stopped
    assert len(seen) == 5


def test_a_full_eval_run_with_masking_and_parsing_reports_both(golden: GoldSet) -> None:
    result = run_eval(
        golden,
        variant="A",
        split="dev",
        limit=None,
        stages=["masking", "parsing"],
        judge=StubJudge(golden),
        client=FakeLLMClient(responder=lambda _r, _s: _empty()),
        model="gemini-3.6-flash",
        min_chars_per_page=MIN_CHARS,
        contacts=load_contacts(DEFAULT_ROOT),
    )
    report = format_report(result)
    assert "MASKING LEAKS (56 CVs" in report and "email 0 (0.0%)" in report
    assert "PARSING (real model, 18 of 18 CVs)" in report
    assert result.pipeline_version.prompts["cv_parse"] == "cv_parse_v1"
