import json
from pathlib import Path

import pytest

from ats.eval.golden import DEFAULT_ROOT, GoldSet, load_golden
from ats.eval.label_review import FROZEN_PAIRS, format_rows, review_rows
from ats.eval.stages import load_uncertain


@pytest.fixture(scope="module")
def golden() -> GoldSet:
    return load_golden()


def _result(golden: GoldSet, wrong: tuple[str, int], flagged: tuple[str, int]) -> dict[str, object]:
    items: list[dict[str, object]] = []
    for cv_id in golden.cv_ids("test"):
        for row in golden.verdicts_for(cv_id):
            pair = (cv_id, row.requirement_id)
            predicted = "not_met" if pair == wrong and row.verdict != "not_met" else row.verdict
            items.append(
                {
                    "cv_id": cv_id,
                    "requirement_id": row.requirement_id,
                    "gold": row.verdict,
                    "predicted": predicted,
                    "flags": ["quote_not_found"] if pair == flagged else [],
                }
            )
    return {"verdicts": {"items": items}}


def test_the_listing_has_the_frozen_pairs_the_uncertain_test_pairs_and_the_misses(
    golden: GoldSet,
) -> None:
    test = golden.cv_ids("test")
    wrong = next(
        (c, r.requirement_id)
        for c in test
        for r in golden.verdicts_for(c)
        if r.verdict != "not_met" and (c, r.requirement_id) not in FROZEN_PAIRS
    )
    flagged = next(
        (c, r.requirement_id)
        for c in reversed(test)
        for r in golden.verdicts_for(c)
        if (c, r.requirement_id) not in FROZEN_PAIRS and (c, r.requirement_id) != wrong
    )
    uncertain = load_uncertain(DEFAULT_ROOT, golden)

    rows = review_rows(golden, uncertain, _result(golden, wrong, flagged))

    listed = {(r.cv_id, r.requirement_id) for r in rows}
    assert set(FROZEN_PAIRS) <= listed
    assert {p for p in uncertain if p[0] in test} <= listed
    assert wrong in listed and flagged in listed
    assert all(r.cv_id in test for r in rows)  # no dev CV is listed
    by_pair = {(r.cv_id, r.requirement_id): r for r in rows}
    assert any("wrong" in why for why in by_pair[wrong].reasons)
    assert any("flagged" in why for why in by_pair[flagged].reasons)
    text = format_rows(rows)
    assert "listed because" in text and rows[0].requirement in text


def test_the_command_reads_a_result_and_writes_nothing(
    golden: GoldSet, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from ats.eval.__main__ import main

    result = tmp_path / "result.json"
    result.write_text(json.dumps(_result(golden, ("x", 0), ("x", 0))), encoding="utf-8")
    before = sorted(p.name for p in tmp_path.iterdir())

    assert main(["label-review", "--result", str(result)]) == 0

    assert "test-split verdicts to review" in capsys.readouterr().out
    assert sorted(p.name for p in tmp_path.iterdir()) == before
