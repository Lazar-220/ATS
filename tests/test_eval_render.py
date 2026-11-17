from pathlib import Path

import pytest
from golden_fixture import write_set

from ats.eval.cvsource import parse_cv_source
from ats.eval.render import LineTooWideError, render_cv, render_golden, render_posting
from ats.pipeline.extract import extract_text

_MIN_CHARS = 100

SERBIAN_LATIN = (
    "KONTAKT\n"
    "Šđčćž ŠĐČĆŽ: Đorđe Žarković, Čačak\n"
    "Radno iskustvo\n"
    "2019-2023 Rukovodilac projekta, Ćuprija\n"
    "Vođenje tima od 12 ljudi, planiranje u Jira alatu\n"
    "\n"
    "OBRAZOVANJE\n"
    "Fakultet organizacionih nauka, Beograd (2012-2016)\n"
)
SERBIAN_CYRILLIC = (
    "КОНТАКТ\n"
    "Ђорђе Жарковић, Чачак, Љубица Њ Џ\n"
    "Радно искуство\n"
    "2019-2023 Руководилац пројекта, Ћуприја\n"
    "Вођење тима од 12 људи, планирање у алату Jira\n"
    "\n"
    "ОБРАЗОВАЊЕ\n"
    "Факултет организационих наука, Београд (2012-2016)\n"
)
LEFT = "Skills\nPython, SQL, Docker\nLanguages\nEnglish C1\nSerbian native"
RIGHT = (
    "Work experience\n2019-2023 Backend developer, Acme\n"
    "Built REST services in Python\n2016-2019 Junior developer\nMaintained a billing system"
)


def _extracted_lines(pdf: bytes) -> list[str]:
    text = extract_text(pdf, min_chars_per_page=_MIN_CHARS).text
    return [line for line in text.split("\n") if line.strip()]


@pytest.mark.parametrize("text", [SERBIAN_LATIN, SERBIAN_CYRILLIC], ids=["latin", "cyrillic"])
def test_single_column_text_survives_extraction_line_for_line(text: str) -> None:
    source = parse_cv_source(text, "single")
    pdf = render_cv(source, "single")
    assert _extracted_lines(pdf) == [line for line in source.lines if line.strip()]


def test_two_column_text_survives_and_is_interleaved_row_by_row() -> None:
    source = parse_cv_source(f"{LEFT}\n=== RIGHT COLUMN ===\n{RIGHT}", "two_column")
    lines = _extracted_lines(render_cv(source, "two_column"))
    assert sorted(lines) == sorted(line for line in source.lines if line.strip())
    # The flaw is the point: row 1 is "Skills", then "Work experience", not the whole sidebar first.
    assert lines[:4] == [
        "Skills",
        "Work experience",
        "Python, SQL, Docker",
        "2019-2023 Backend developer, Acme",
    ]


def test_every_quote_inside_one_source_line_is_inside_one_extracted_line() -> None:
    source = parse_cv_source(f"{LEFT}\n=== RIGHT COLUMN ===\n{RIGHT}", "two_column")
    extracted = _extracted_lines(render_cv(source, "two_column"))
    for quote in ("Python, SQL, Docker", "2019-2023 Backend developer, Acme", "English C1"):
        assert any(quote in line for line in extracted)


def test_a_long_cv_flows_onto_more_pages() -> None:
    text = "\n".join(f"Line number {n} of a long CV" for n in range(120))
    pdf = render_cv(parse_cv_source(text, "single"), "single")
    assert extract_text(pdf, min_chars_per_page=_MIN_CHARS).page_count == 3


def test_a_line_that_does_not_fit_is_an_error_not_a_wrap() -> None:
    with pytest.raises(LineTooWideError, match="column holds"):
        render_cv(parse_cv_source("word " * 60, "single"), "single")
    narrow = parse_cv_source(
        "a sidebar line that is far too long for a narrow left column\n=== RIGHT COLUMN ===\nb",
        "two_column",
    )
    with pytest.raises(LineTooWideError):
        render_cv(narrow, "two_column")


def test_rendering_is_byte_stable() -> None:
    source = parse_cv_source(SERBIAN_LATIN, "single")
    assert render_cv(source, "single") == render_cv(source, "single")


def test_a_posting_renders_as_a_single_column() -> None:
    pdf = render_posting("Backend developer\nRequirements\n" + "Python and SQL experience\n" * 6)
    assert _extracted_lines(pdf)[:2] == ["Backend developer", "Requirements"]


def test_render_golden_writes_missing_pdfs_and_leaves_unchanged_ones(tmp_path: Path) -> None:
    write_set(tmp_path, ["cv_a"])
    for pdf in tmp_path.rglob("*.pdf"):
        pdf.unlink()
    first = render_golden(tmp_path)
    assert sorted(p.name for p in first) == ["cv_a.pdf", "posting.pdf", "posting.pdf"]
    assert render_golden(tmp_path) == []
