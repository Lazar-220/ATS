import pymupdf
import pytest
from pdfs import make_pdf, make_scan_pdf, make_two_column_pdf

from ats.pipeline.extract import (
    DEFAULT_STEPS,
    ScannedPdfError,
    UnreadablePdfError,
    extract_text,
)

MIN_CHARS = 100

CV_LINES = [
    "Marko Marković, projektni menadžer",
    "Vođenje tima od osam ljudi u banci, 2019-2023.",
    "Magistar ekonomije, Univerzitet u Beogradu.",
    "Znanje: Python, SQL, upravljanje projektima, Scrum.",
]


def test_extracts_latin_serbian_with_diacritics() -> None:
    result = extract_text(make_pdf("\n".join(CV_LINES)), min_chars_per_page=MIN_CHARS)
    assert result.page_count == 1
    assert "Vođenje tima od osam ljudi" in result.text
    assert "Marković" in result.text


def test_cyrillic_survives_the_round_trip() -> None:
    cyrillic = ["Вођење тима од осам људи у банци, 2019-2023.", "Магистар економије, Београд."] * 2
    result = extract_text(make_pdf("\n".join(cyrillic)), min_chars_per_page=MIN_CHARS)
    # Guards the fixture itself: a font without Cyrillic glyphs would extract as '?' or blanks.
    assert "вођење" in result.text.lower()
    assert sum("Ѐ" <= ch <= "ӿ" for ch in result.text) > 50


def test_pages_are_joined_in_order() -> None:
    lines = [f"Line {i} of a long curriculum vitae with plenty of text" for i in range(60)]
    result = extract_text(make_pdf("\n".join(lines)), min_chars_per_page=MIN_CHARS)
    assert result.page_count == 2
    assert result.text.index("Line 0 ") < result.text.index("Line 59 ")


def test_scanned_pdf_is_rejected_with_a_readable_message() -> None:
    with pytest.raises(ScannedPdfError, match="scan"):
        extract_text(make_scan_pdf(pages=2), min_chars_per_page=MIN_CHARS)


def test_pdf_with_too_little_text_per_page_is_a_scan() -> None:
    with pytest.raises(ScannedPdfError):
        extract_text(make_pdf("Name"), min_chars_per_page=MIN_CHARS)


def test_garbage_is_rejected_as_unreadable() -> None:
    with pytest.raises(UnreadablePdfError, match="could not be opened"):
        extract_text(b"%PDF-1.7 this is not really a pdf", min_chars_per_page=MIN_CHARS)


def test_password_protected_pdf_is_rejected() -> None:
    doc = pymupdf.open(stream=make_pdf("\n".join(CV_LINES)), filetype="pdf")
    locked = doc.tobytes(
        encryption=pymupdf.PDF_ENCRYPT_AES_256,  # pyright: ignore[reportAttributeAccessIssue]
        owner_pw="owner",
        user_pw="user",
    )
    with pytest.raises(UnreadablePdfError, match="password"):
        extract_text(locked, min_chars_per_page=MIN_CHARS)


def test_cleaning_steps_run_in_order_and_can_be_replaced() -> None:
    calls: list[str] = []

    def upper(_page: pymupdf.Page, text: str) -> str:
        calls.append("upper")
        return text.upper()

    def mark(_page: pymupdf.Page, text: str) -> str:
        calls.append("mark")
        return text + " [end]"

    result = extract_text(
        make_pdf("\n".join(CV_LINES)),
        min_chars_per_page=MIN_CHARS,
        steps=(*DEFAULT_STEPS, upper, mark),
    )
    assert calls == ["upper", "mark"]
    # Upper-casing ran before the marker was appended, so the marker keeps its case.
    assert result.text.endswith("ZNANJE: PYTHON, SQL, UPRAVLJANJE PROJEKTIMA, SCRUM. [end]")


def test_whitespace_step_collapses_blank_runs_and_odd_spaces() -> None:
    text = "Line one here   \n\n\n\n\nLine two"
    page = pymupdf.open().new_page()
    assert DEFAULT_STEPS[0](page, text) == "Line one here\n\nLine two"


def test_two_column_layout_interleaves_the_columns() -> None:
    """Known limitation, left for 1.4a (§2.2): reading order is not reconstructed here.

    The cells were written row by row, and the extracted text follows that order, so a
    column's lines are not contiguous ("Work experience" is followed by "Skills").
    """
    left = ["Work experience", "2019-2023 Project Manager", "Led a team of 8 people", "Bank"]
    right = ["Skills", "Python, SQL", "Languages", "Serbian, English"]
    result = extract_text(make_two_column_pdf(left, right), min_chars_per_page=10)
    assert result.text == (
        "Work experience\nSkills\n2019-2023 Project Manager\nPython, SQL\n"
        "Led a team of 8 people\nLanguages\nBank\nSerbian, English"
    )
