import json
from datetime import date
from pathlib import Path

import pytest
from pydantic import BaseModel

import ats.eval.__main__ as eval_cli
from ats.eval.golden import GoldSet, load_golden
from ats.eval.harness import (
    EvalError,
    RunPlan,
    format_report,
    plan_run,
    run_eval,
    select_cvs,
    write_result,
)
from ats.eval.matching import THRESHOLD, match_requirements, score_pair, tokenize
from ats.eval.metrics import (
    extraction_metrics_from,
    grounding_metrics,
    quote_exists,
    verdict_metrics,
)
from ats.eval.pricing import rate_on
from ats.eval.schemas import GoldRequirement, Position
from ats.eval.stub import StubJudge
from ats.llm.cache import ResponseCache, cache_key
from ats.llm.fake import FakeLLMClient
from ats.llm.types import LLMRequest, RawCompletion
from ats.pipeline.requirements import RequirementDraft, RequirementList, build_request
from ats.settings import get_settings

MIN_CHARS = 100


@pytest.fixture(scope="module")
def golden() -> GoldSet:
    return load_golden()


def _draft(id_: int, text: str, kind: str = "mandatory") -> RequirementDraft:
    return RequirementDraft.model_validate(
        {"id": id_, "text": text, "kind": kind, "weight": 1, "min_months": None, "parent": None}
    )


def _gold(golden: GoldSet, position_id: str) -> list[GoldRequirement]:
    return golden.positions[position_id].meta.requirements


def _perfect_extraction(position: Position) -> RequirementList:
    return RequirementList(
        requirements=[
            RequirementDraft.model_validate(r.model_dump(exclude={"aliases"}))
            for r in position.requirements
        ]
    )


def _answer_with_gold(golden: GoldSet) -> FakeLLMClient:
    by_text = {
        position.posting_text.split("\n")[0]: position.meta
        for position in golden.positions.values()
    }

    def respond(request: LLMRequest, _schema: type[BaseModel]) -> BaseModel:
        # The first line of the fenced posting is its title, which identifies the position.
        title = request.user.split("\n")[1]
        return _perfect_extraction(by_text[title])

    return FakeLLMClient(responder=respond)


# --- matching ------------------------------------------------------------------------------


def test_every_gold_text_matches_itself_with_score_one(golden: GoldSet) -> None:
    for position_id in golden.positions:
        gold = _gold(golden, position_id)
        result = match_requirements([_draft(r.id, r.text) for r in gold], gold)
        assert [(m.extracted_id, m.gold_id, m.score) for m in result.matches] == [
            (r.id, r.id, 1.0) for r in gold
        ]


def test_numbers_must_agree_so_a_skill_is_not_its_experience(golden: GoldSet) -> None:
    gold = _gold(golden, "backend_developer")
    plain, _ = score_pair("Python", gold[1])  # "3 years of professional experience with Python"
    assert plain == 0.0
    assert match_requirements([_draft(1, "3+ years of Python")], gold).matches[0].gold_id == 2
    assert match_requirements([_draft(1, "Python")], gold).matches[0].gold_id == 1


def test_an_unsplit_compound_counts_once_and_misses_the_other_half(golden: GoldSet) -> None:
    gold = _gold(golden, "backend_developer")
    result = match_requirements([_draft(1, "Git and Docker")], gold)
    # Both halves score 0.5; the lower gold id wins the tie, so Git is matched and Docker missed.
    assert [(m.gold_id, m.score) for m in result.matches] == [(6, 0.5)]
    assert 7 in result.unmatched_gold


def test_a_requirement_is_matched_at_most_once(golden: GoldSet) -> None:
    gold = _gold(golden, "backend_developer")
    result = match_requirements([_draft(1, "Docker"), _draft(2, "Experience with Docker")], gold)
    assert len(result.matches) == 1
    assert result.matches[0].extracted_id == 1  # equal scores: the lower extracted id
    assert result.unmatched_extracted == [2]


def test_a_pair_exactly_at_the_threshold_matches_and_one_below_does_not(golden: GoldSet) -> None:
    gold = _gold(golden, "backend_developer")
    at = match_requirements([_draft(1, "Experience with RabbitMQ")], gold)
    assert (at.matches[0].gold_id, at.matches[0].score) == (10, THRESHOLD)
    assert match_requirements([_draft(1, "Experience with Redis")], gold).matches == []


def test_serbian_matches_across_scripts_and_diacritics_and_through_an_alias(
    golden: GoldSet,
) -> None:
    gold = _gold(golden, "project_manager")
    cyrillic = match_requirements([_draft(1, "Познавање Scrum методологије")], gold)
    assert (cyrillic.matches[0].gold_id, cyrillic.matches[0].score) == (3, 1.0)
    # "alatu" and "alatom" are cut differently at five letters; only the alias "Jira" carries it.
    inflected = match_requirements([_draft(1, "Rad u alatu Jira")], gold)
    assert (inflected.matches[0].gold_id, inflected.matches[0].via) == (5, "Jira")
    assert inflected.matches[0].score == 0.5


def test_content_words_are_cut_to_five_letters_but_java_stays_apart_from_javascript() -> None:
    assert tokenize("projekata").content == tokenize("projekti").content
    assert tokenize("Java").content != tokenize("JavaScript").content


def test_the_kind_label_is_scored_on_matched_pairs_only(golden: GoldSet) -> None:
    gold = _gold(golden, "backend_developer")
    drafts = [_draft(1, "Python", "nice_to_have"), _draft(2, "Docker"), _draft(3, "COBOL")]
    metrics = extraction_metrics_from(match_requirements(drafts, gold))
    assert (metrics.extracted, metrics.gold, metrics.matched) == (3, 11, 2)
    assert metrics.label_accuracy == 0.5
    assert metrics.precision == pytest.approx(2 / 3)
    assert metrics.recall == pytest.approx(2 / 11)


# --- metrics -------------------------------------------------------------------------------


def test_verdict_metrics_agree_with_a_hand_computation() -> None:
    gold = ["met", "met", "partial", "not_met", "not_met", "met"]
    pred = ["met", "partial", "partial", "not_met", "met", "met"]
    metrics = verdict_metrics(list(zip(gold, pred, strict=True)))  # pyright: ignore[reportArgumentType]
    assert metrics.accuracy == pytest.approx(4 / 6)
    assert metrics.macro_f1 == pytest.approx(2 / 3)
    # Rows are the gold verdict, columns the predicted one, in the order not_met, partial, met.
    assert metrics.confusion == [[1, 0, 1], [0, 1, 0], [0, 1, 2]]
    # 1 - sum(W*O) / sum(W*E) with quadratic weights = 1 - 1.25 / 2.0833 = 0.4
    assert metrics.weighted_kappa == pytest.approx(0.4)


def test_kappa_is_none_when_it_is_undefined() -> None:
    assert verdict_metrics([("met", "met"), ("met", "met")]).weighted_kappa is None


def test_a_quote_is_found_across_changed_whitespace() -> None:
    assert quote_exists("Python,  SQL", "Skills\nPython, SQL\nWork")
    assert quote_exists("Python, SQL", "Skills Python,\n SQL Work")
    assert not quote_exists("Python, SQL, Go", "Skills\nPython, SQL\nWork")


def test_grounding_counts_unquoted_positives_apart_from_missing_quotes() -> None:
    cv = "Skills Python SQL"
    metrics = grounding_metrics(
        [
            ("met", "Python", cv),
            ("partial", "Rust", cv),
            ("met", None, cv),
            ("not_met", "Python", cv),  # a quote on a not_met is not evidence and is ignored
        ]
    )
    assert (metrics.quoted, metrics.quote_exists, metrics.unquoted) == (2, 1, 1)
    assert metrics.quote_exists_share == 0.5


# --- pricing -------------------------------------------------------------------------------


def test_the_rate_changes_on_the_first_of_january() -> None:
    assert rate_on("gemini-3.6-flash", date(2026, 12, 31)).input_per_m == 0.75  # pyright: ignore[reportOptionalMemberAccess]
    assert rate_on("gemini-3.6-flash", date(2027, 1, 1)).input_per_m == 1.50  # pyright: ignore[reportOptionalMemberAccess]
    assert rate_on("some-other-model", date(2026, 11, 17)) is None


def test_a_plan_prints_both_rates_with_the_note_and_says_when_a_model_has_no_price() -> None:
    plan = RunPlan(("extraction",), "gemini-3.6-flash", 6, 0, 6000, 3000)
    text = plan.describe()
    assert "0.75 / 3.75" in text
    assert "1.50 / 7.50" in text
    assert "ends on 2026-12-31" in text
    assert "No price is on record" in RunPlan(("extraction",), "x", 1, 0, 1, 1).describe()


# --- the run -------------------------------------------------------------------------------


def test_a_perfect_judge_scores_one_and_every_gold_quote_exists_in_the_extracted_pdf(
    golden: GoldSet,
) -> None:
    perfect = StubJudge(golden, wrong_verdict_rate=0, invented_quote_rate=0)
    result = run_eval(
        golden, variant="A", split="all", limit=None, stages=["verdicts"],
        judge=perfect, client=None, model="m", min_chars_per_page=MIN_CHARS,
    )  # fmt: skip
    verdicts = result.verdicts
    assert verdicts is not None
    assert verdicts.overall.accuracy == 1.0
    assert verdicts.overall.weighted_kappa == 1.0
    assert verdicts.grounding.quote_exists_share == 1.0
    assert verdicts.grounding.unquoted == 0


def test_the_stub_spoils_some_labels_and_is_deterministic(golden: GoldSet) -> None:
    def run() -> float:
        result = run_eval(
            golden, variant="A", split="all", limit=None, stages=["verdicts"],
            judge=StubJudge(golden), client=None, model="m", min_chars_per_page=MIN_CHARS,
        )  # fmt: skip
        assert result.verdicts is not None
        return result.verdicts.overall.accuracy

    first = run()
    assert 0.4 < first < 1.0
    assert run() == first


def test_extraction_scores_one_when_the_model_returns_the_gold_requirements(
    golden: GoldSet,
) -> None:
    client = _answer_with_gold(golden)
    result = run_eval(
        golden, variant="A", split="dev", limit=1, stages=["extraction"],
        judge=StubJudge(golden), client=client, model="gemini-3.6-flash",
        min_chars_per_page=MIN_CHARS, price_date=date(2026, 11, 17),
    )  # fmt: skip
    assert result.extraction is not None
    assert result.extraction.overall.f1 == 1.0
    assert result.extraction.overall.label_accuracy == 1.0
    assert len(client.calls) == len(golden.positions)
    assert result.usage.llm_calls == len(golden.positions)
    assert result.verdicts is None


def test_extraction_without_a_client_and_unknown_variants_are_refused(golden: GoldSet) -> None:
    common = dict(
        split="dev", limit=None, judge=StubJudge(golden), client=None, model="m",
        min_chars_per_page=MIN_CHARS,
    )  # fmt: skip
    with pytest.raises(EvalError, match="needs an LLM client"):
        run_eval(golden, variant="A", stages=["extraction"], **common)  # pyright: ignore[reportArgumentType]
    with pytest.raises(EvalError, match="variant B"):
        run_eval(golden, variant="B", stages=["verdicts"], **common)  # pyright: ignore[reportArgumentType]


def test_limit_keeps_the_first_n_cvs_of_the_split_in_id_order(golden: GoldSet) -> None:
    dev = golden.cv_ids("dev")
    assert select_cvs(golden, "dev", 2) == dev[:2]
    assert select_cvs(golden, "all", None) == golden.cv_ids()


def test_the_plan_counts_calls_and_notices_what_is_already_cached(
    golden: GoldSet, tmp_path: Path
) -> None:
    cache = ResponseCache(tmp_path)
    plan = plan_run(
        golden, ["extraction"], model="gemini-3.6-flash", cache=cache, min_chars_per_page=MIN_CHARS
    )
    assert (plan.llm_calls, plan.already_cached) == (len(golden.positions), 0)
    assert plan.est_input_tokens > 0

    position_id = sorted(golden.positions)[0]
    from ats.eval.harness import _posting_text  # pyright: ignore[reportPrivateUsage]

    request = build_request(_posting_text(golden, position_id, MIN_CHARS))
    cache.put(
        cache_key("gemini-3.6-flash", request, RequirementList),
        RawCompletion(text="{}", input_tokens=1, output_tokens=1),
    )
    again = plan_run(
        golden, ["extraction"], model="gemini-3.6-flash", cache=cache, min_chars_per_page=MIN_CHARS
    )
    assert again.already_cached == 1
    assert again.uncached_calls == len(golden.positions) - 1


def test_the_verdict_only_plan_calls_nothing(golden: GoldSet, tmp_path: Path) -> None:
    plan = plan_run(
        golden, ["verdicts"], model="gemini-3.6-flash", cache=ResponseCache(tmp_path),
        min_chars_per_page=MIN_CHARS,
    )  # fmt: skip
    assert (plan.llm_calls, plan.est_input_tokens, plan.est_output_tokens) == (0, 0, 0)


def test_the_result_file_names_the_pipeline_version_and_the_model(
    golden: GoldSet, tmp_path: Path
) -> None:
    result = run_eval(
        golden, variant="A", split="dev", limit=2, stages=["verdicts"],
        judge=StubJudge(golden), client=None, model="gemini-3.6-flash",
        min_chars_per_page=MIN_CHARS,
    )  # fmt: skip
    path = write_result(result, tmp_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert path.name.endswith("_A_dev.json")
    assert data["pipeline_version"]["model"] == "gemini-3.6-flash"
    assert data["pipeline_version"]["prompts"] == {"requirements": "requirements_v1"}
    assert data["pipeline_version"]["code"]  # branch@commit, or "unknown" outside git
    assert data["limit"] == 2
    assert len(data["verdicts"]["items"]) > 0
    assert "judge=stub" in format_report(result)


def test_the_command_runs_end_to_end_and_writes_a_result(
    capsys: pytest.CaptureFixture[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(eval_cli, "RESULTS_DIR", tmp_path)
    assert eval_cli.main(["run", "--variant", "A", "--split", "dev", "--limit", "3"]) == 0
    out = capsys.readouterr().out
    assert "VERDICTS (3 CVs" in out
    assert "weighted kappa" in out
    assert len(list(tmp_path.glob("*_A_dev.json"))) == 1


def test_the_command_dry_run_calls_nothing_and_writes_nothing(
    capsys: pytest.CaptureFixture[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(eval_cli, "RESULTS_DIR", tmp_path)
    assert eval_cli.main(["run", "--stages", "extraction,verdicts", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "Dry run" in out
    assert "LLM calls: " in out
    assert list(tmp_path.iterdir()) == []


def test_a_run_of_more_than_five_uncached_calls_is_refused_without_yes(
    capsys: pytest.CaptureFixture[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # An empty cache in tmp, and a limit of 1 instead of 5: the mini set has two postings.
    monkeypatch.setenv("LLM_CACHE_DIR", str(tmp_path / "cache"))
    get_settings.cache_clear()
    monkeypatch.setattr(eval_cli, "MAX_CALLS_WITHOUT_CONFIRMATION", 1)
    monkeypatch.setattr(eval_cli, "RESULTS_DIR", tmp_path)

    def must_not_be_called(_settings: object) -> None:
        raise AssertionError("the model client must not be created before confirmation")

    monkeypatch.setattr(eval_cli, "create_llm_client", must_not_be_called)
    try:
        assert eval_cli.main(["run", "--stages", "extraction"]) == 2
    finally:
        get_settings.cache_clear()
    captured = capsys.readouterr()
    assert "would call the model 2 times" in captured.err
    assert "Dry run" in captured.out  # the estimate is shown first
    assert list(tmp_path.glob("*.json")) == []


def test_the_report_lists_every_unmatched_requirement_on_both_sides(golden: GoldSet) -> None:
    def respond(_request: LLMRequest, _schema: type[BaseModel]) -> BaseModel:
        # Every posting: drop the last gold requirement, add one that is not in any posting.
        position = golden.positions["backend_developer"].meta
        kept = [
            RequirementDraft.model_validate(r.model_dump(exclude={"aliases"}))
            for r in position.requirements[:-1]
        ]
        extra = _draft(99, "COBOL mainframe experience")
        return RequirementList(requirements=[*kept, extra])

    result = run_eval(
        golden, variant="A", split="dev", limit=1, stages=["extraction"],
        judge=StubJudge(golden), client=FakeLLMClient(responder=respond),
        model="m", min_chars_per_page=MIN_CHARS,
    )  # fmt: skip
    report = format_report(result)
    assert "extracted, matched nothing: 'COBOL mainframe experience'" in report
    assert "gold, matched by nothing:   '11: Experience with a cloud provider" in report
    assert result.as_of == "2026-11-17"
