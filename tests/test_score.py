import pytest

from ats.pipeline.score import ScoredRequirement, compute_score, ranking_key


def _req(
    key: int, kind: str = "mandatory", weight: float = 1, parent: int | None = None
) -> ScoredRequirement:
    return ScoredRequirement(key, parent, kind, weight)  # type: ignore[arg-type]


def test_all_met_is_100() -> None:
    reqs = [_req(1), _req(2, "nice_to_have")]
    result = compute_score(reqs, {1: "met", 2: "met"})
    assert result.score == 100.0 and not result.mandatory_failed


def test_all_not_met_is_0_and_fails_the_mandatory_flag() -> None:
    reqs = [_req(1), _req(2, "nice_to_have")]
    result = compute_score(reqs, {1: "not_met", 2: "not_met"})
    assert result.score == 0.0 and result.mandatory_failed


def test_a_failed_mandatory_requirement_sets_the_flag_and_ranks_below_unflagged() -> None:
    reqs = [_req(1), _req(2), _req(3, "nice_to_have")]
    failed = compute_score(reqs, {1: "met", 2: "not_met", 3: "met"})
    clean = compute_score(reqs, {1: "partial", 2: "partial", 3: "not_met"})
    assert failed.mandatory_failed and not clean.mandatory_failed
    assert failed.score > clean.score  # the higher score still ranks lower
    ranked = sorted(
        [("failed", failed), ("clean", clean)],
        key=lambda item: ranking_key(item[1].mandatory_failed, item[1].score),
    )
    assert [name for name, _ in ranked] == ["clean", "failed"]


def test_partial_does_not_fail_a_mandatory_requirement() -> None:
    assert not compute_score([_req(1)], {1: "partial"}).mandatory_failed


def test_weights_and_the_70_30_split() -> None:
    reqs = [_req(1, weight=3), _req(2, weight=1), _req(3, "nice_to_have", weight=2)]
    result = compute_score(reqs, {1: "met", 2: "not_met", 3: "partial"})
    # mandatory 3/4, nice to have 0.5: 100 * (0.7 * 0.75 + 0.3 * 0.5)
    assert result.score == pytest.approx(67.5)


def test_without_nice_to_have_the_score_is_renormalized_not_capped_at_70() -> None:
    reqs = [_req(i) for i in range(1, 6)]
    verdicts = {1: "met", 2: "met", 3: "met", 4: "met", 5: "not_met"}  # M = 0.8
    result = compute_score(reqs, verdicts)
    assert result.nice_to_have_coverage is None
    assert result.score == 80.0


def test_without_mandatory_the_score_is_the_nice_to_have_coverage() -> None:
    result = compute_score([_req(1, "nice_to_have")], {1: "partial"})
    assert result.score == 50.0 and not result.mandatory_failed


def test_parent_and_child_are_one_unit_with_the_parents_weight() -> None:
    # Backend developer: "Python" (weight 3) refined by "3 years of Python" (weight 1).
    reqs = [_req(1, weight=3), _req(2, weight=1, parent=1)]
    result = compute_score(reqs, {1: "met", 2: "partial"})
    # One unit of weight 3 with the mean score 0.75; the child's weight 1 is ignored.
    assert result.mandatory_coverage == pytest.approx(0.75)
    assert result.score == 75.0


def test_the_worked_example_of_the_decision() -> None:
    # Unit {1, 2}: weight 3, met and partial -> 0.75. Singles 3..9 with weights 3,1,1,1,1,1,1
    # and verdicts met, met, met, not_met, met, met, partial.
    weights = {3: 3, 4: 1, 5: 1, 6: 1, 7: 1, 8: 1, 9: 1}
    reqs = [_req(1, weight=3), _req(2, parent=1)] + [_req(k, weight=w) for k, w in weights.items()]
    verdicts = {1: "met", 2: "partial", 3: "met", 4: "met", 5: "met", 6: "not_met"}
    verdicts |= {7: "met", 8: "met", 9: "partial"}
    result = compute_score(reqs, verdicts)
    # (3*0.75 + 3 + 1 + 1 + 0 + 1 + 1 + 0.5) / 12 = 9.75 / 12
    assert result.mandatory_coverage == pytest.approx(9.75 / 12)
    assert result.mandatory_failed  # req 6 is not_met


def test_a_child_that_fails_sets_the_mandatory_flag_even_when_its_parent_is_met() -> None:
    result = compute_score([_req(1), _req(2, parent=1)], {1: "met", 2: "not_met"})
    assert result.mandatory_failed and result.score == 50.0


def test_nested_refinements_belong_to_the_root_unit() -> None:
    reqs = [_req(1, weight=2), _req(2, parent=1), _req(3, parent=2), _req(4)]
    result = compute_score(reqs, {1: "met", 2: "met", 3: "not_met", 4: "met"})
    # Unit {1,2,3}: mean(1, 1, 0) = 2/3 at weight 2; req 4: 1 at weight 1.
    assert result.mandatory_coverage == pytest.approx((2 * 2 / 3 + 1) / 3)
