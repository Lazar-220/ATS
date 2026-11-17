import json
from collections import Counter
from pathlib import Path

import pytest
from golden_fixture import CV_TEXT, POSITION, profile, write_set
from pydantic import ValidationError

from ats.eval.cvsource import CvSourceError, parse_cv_source
from ats.eval.golden import GoldSetError, build_labels, load_golden
from ats.eval.schemas import Position, ProfileClaim
from ats.eval.split import assign_split, strata_of


def _problems(root: Path) -> str:
    with pytest.raises(GoldSetError) as caught:
        load_golden(root)
    return str(caught.value)


@pytest.fixture
def golden(tmp_path: Path) -> Path:
    write_set(tmp_path, ["cv_a", "cv_b", "cv_c"])
    build_labels(tmp_path)
    return tmp_path


def test_a_consistent_set_loads(golden: Path) -> None:
    loaded = load_golden(golden)
    assert sorted(loaded.cvs) == ["cv_a", "cv_b", "cv_c"]
    assert len(loaded.verdicts) == 9  # 3 CVs x 3 requirements
    assert len(loaded.relevance) == 6  # 3 CVs x 2 positions
    assert len(loaded.cv_ids("dev")) + len(loaded.cv_ids("test")) == 3


def test_a_quote_that_is_not_in_the_cv_is_rejected(tmp_path: Path) -> None:
    write_set(tmp_path, ["cv_a"])
    data = profile("cv_a")
    data["claims"][0]["quote"] = "Python and Go"
    (tmp_path / "profiles" / "cv_a.json").write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(GoldSetError, match="not a verbatim substring"):
        build_labels(tmp_path)


def test_a_quote_may_not_span_two_lines() -> None:
    with pytest.raises(ValidationError, match="inside one line"):
        ProfileClaim(requirement_id=1, verdict="met", fact="x", quote="Skills\nPython")


def test_a_not_met_claim_has_no_quote_and_a_met_claim_needs_one() -> None:
    with pytest.raises(ValidationError, match="no quote"):
        ProfileClaim(requirement_id=1, verdict="not_met", fact="x", quote="Python")
    with pytest.raises(ValidationError, match="needs a quote"):
        ProfileClaim(requirement_id=1, verdict="partial", fact="x")


def test_every_requirement_needs_exactly_one_claim(tmp_path: Path) -> None:
    write_set(tmp_path, ["cv_a"])
    data = profile("cv_a")
    data["claims"].pop()
    (tmp_path / "profiles" / "cv_a.json").write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(GoldSetError, match=r"claims answer \[1, 2\]"):
        build_labels(tmp_path)


def test_a_label_must_reference_an_existing_cv_position_and_requirement(golden: Path) -> None:
    path = golden / "labels" / "verdicts.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    rows.append({**rows[0], "cv_id": "ghost"})
    rows.append({**rows[0], "position_id": "ghost"})
    rows.append({**rows[0], "requirement_id": 99})
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    message = _problems(golden)
    assert "ghost/backend: no such CV" in message
    assert "cv_a/ghost: no such position" in message
    assert "no such requirement 99" in message


def test_labels_that_disagree_with_the_profile_are_rejected(golden: Path) -> None:
    path = golden / "labels" / "verdicts.jsonl"
    path.write_text(path.read_text(encoding="utf-8").replace('"met"', '"partial"', 1))
    assert "differs from the profiles" in _problems(golden)


def test_a_hand_edited_split_is_rejected(golden: Path) -> None:
    path = golden / "split.json"
    split = json.loads(path.read_text(encoding="utf-8"))
    for cv_id, name in split["assignment"].items():
        split["assignment"][cv_id] = "dev" if name == "test" else "test"
    path.write_text(json.dumps(split), encoding="utf-8")
    assert "split.json is not what its seed gives" in _problems(golden)


def test_a_misspelled_key_is_rejected(tmp_path: Path) -> None:
    write_set(tmp_path, ["cv_a"])
    data = profile("cv_a")
    data["hardcase"] = None
    (tmp_path / "profiles" / "cv_a.json").write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(GoldSetError, match="hardcase"):
        build_labels(tmp_path)


def test_requirements_must_form_a_forest() -> None:
    data = json.loads(json.dumps(POSITION))
    data["requirements"][0]["parent"] = 2  # 1 -> 2 -> 1
    with pytest.raises(ValidationError, match="own ancestor"):
        Position.model_validate(data)


def test_build_is_idempotent(golden: Path) -> None:
    before = {p.name: p.read_bytes() for p in (golden / "labels").iterdir()}
    split_before = (golden / "split.json").read_bytes()
    build_labels(golden)
    assert {p.name: p.read_bytes() for p in (golden / "labels").iterdir()} == before
    assert (golden / "split.json").read_bytes() == split_before


def test_the_same_seed_gives_the_same_split_and_another_seed_a_different_one() -> None:
    ids = [f"cv_{n:02d}" for n in range(40)]
    strata = {("p1", "en"): ids[:20], ("p1", "sr_latin"): ids[20:]}
    first = assign_split(strata, seed=7)
    assert first == assign_split(strata, seed=7)
    assert first != assign_split(strata, seed=8)


def test_the_split_is_about_thirty_percent_test_in_every_stratum() -> None:
    ids = [f"cv_{n:03d}" for n in range(80)]
    # Ten strata of eight: 2.4 test CVs each, so every stratum gets 2 or 3, and the total is 24.
    strata = {("p", f"s{i}"): ids[i * 8 : (i + 1) * 8] for i in range(10)}
    split = assign_split(strata, seed=1)
    assert Counter(split.values()) == {"dev": 56, "test": 24}
    for members in strata.values():
        assert sum(split[m] == "test" for m in members) in (2, 3)


def test_tiny_strata_still_reach_the_target_total() -> None:
    cvs = {f"cv_{n}": ("p", f"s{n // 2}") for n in range(10)}  # five strata of two
    split = assign_split(strata_of(cvs), seed=3)
    assert Counter(split.values()) == {"dev": 7, "test": 3}


def test_a_two_column_source_keeps_each_cell_a_line() -> None:
    raw = "Skills\nPython\n=== RIGHT COLUMN ===\nWork\n2019 Engineer\n"
    source = parse_cv_source(raw, "two_column")
    assert source.columns == (("Skills", "Python"), ("Work", "2019 Engineer"))
    assert source.contains_quote("2019 Engineer")
    assert not source.contains_quote("Python\nWork")  # never spans a line


def test_the_column_marker_must_match_the_template() -> None:
    with pytest.raises(CvSourceError):
        parse_cv_source(CV_TEXT, "two_column")
    with pytest.raises(CvSourceError):
        parse_cv_source("a\n=== RIGHT COLUMN ===\nb", "single")
