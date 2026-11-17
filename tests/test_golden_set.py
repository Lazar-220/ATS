"""Checks on the committed golden set itself (eval/golden), not on the loader's logic."""

import pytest

from ats.eval.golden import DEFAULT_ROOT, GoldSet, load_golden
from ats.eval.render import render_golden
from ats.pipeline.extract import extract_text


@pytest.fixture(scope="module")
def golden() -> GoldSet:
    return load_golden()


def _extracted_lines(pdf_bytes: bytes) -> list[str]:
    # min_chars_per_page=0: a short sample CV must not be rejected as a scan here.
    return extract_text(pdf_bytes, min_chars_per_page=0).text.split("\n")


def test_the_committed_set_loads_and_validates(golden: GoldSet) -> None:
    assert golden.positions
    assert golden.cvs


def test_every_position_has_between_8_and_12_requirements(golden: GoldSet) -> None:
    for position in golden.positions.values():
        assert 8 <= len(position.meta.requirements) <= 12, position.meta.id


def test_the_committed_pdfs_are_what_the_sources_render_to() -> None:
    # A source edited without re-rendering would leave the PDF and the labels disagreeing.
    assert render_golden(DEFAULT_ROOT) == []


def test_every_gold_quote_survives_pdf_extraction_inside_one_line(golden: GoldSet) -> None:
    # What the pipeline reads is the extracted text, not the source: the quotes must be there too.
    problems: list[str] = []
    for cv_id, cv in golden.cvs.items():
        lines = _extracted_lines(cv.pdf.read_bytes())
        problems.extend(
            f"{cv_id} requirement {row.requirement_id}: {row.quote!r}"
            for row in golden.verdicts_for(cv_id)
            if row.quote is not None and not any(row.quote in line for line in lines)
        )
    assert problems == []


def test_every_source_line_is_in_the_extracted_pdf(golden: GoldSet) -> None:
    for cv_id, cv in golden.cvs.items():
        extracted = _extracted_lines(cv.pdf.read_bytes())
        wanted = sorted(line for line in cv.source.lines if line.strip())
        assert sorted(line for line in extracted if line.strip()) == wanted, cv_id


def test_every_posting_text_is_in_its_pdf(golden: GoldSet) -> None:
    for position in golden.positions.values():
        extracted = _extracted_lines(position.posting_pdf.read_bytes())
        wanted = [line for line in position.posting_text.split("\n") if line.strip()]
        assert [line for line in extracted if line.strip()] == wanted, position.meta.id


def test_hard_cases_are_tagged_and_not_all_of_the_pool(golden: GoldSet) -> None:
    tagged = [cv for cv in golden.cvs.values() if cv.profile.hard_case is not None]
    assert tagged
    assert len(tagged) < len(golden.cvs)


def test_both_dev_and_test_parts_exist(golden: GoldSet) -> None:
    assert golden.cv_ids("dev")
    assert golden.cv_ids("test")
