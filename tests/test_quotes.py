from ats.pipeline.masking import mask_text
from ats.pipeline.quotes import (
    NO_EVIDENCE,
    QUOTE_NOT_FOUND,
    check_quote,
    displayed_quote,
    find_quote,
)

CV = (
    "Backend developer\n"
    "2019-2023  Acme d.o.o.\n"
    "Built REST APIs in Python,\n   served 120 000 users.\n"
    "Radio sam u “Fabrika” – Beograd\n"
)


def _check(verdict: str, quote: str | None, threshold: int = 90):  # type: ignore[no-untyped-def]
    return check_quote(verdict, quote, CV, [], threshold)


def test_a_verbatim_quote_passes_and_its_offsets_point_at_the_text() -> None:
    result = _check("met", "Built REST APIs in Python")
    assert result.flags == ()
    assert result.char_start is not None and result.char_end is not None
    assert CV[result.char_start : result.char_end] == "Built REST APIs in Python"


def test_whitespace_case_and_typographic_quotes_are_normalized() -> None:
    quote = "built rest apis in python, served 120 000 users."
    result = _check("met", quote)
    assert result.flags == ()
    # The span covers the line break and the indent that normalization collapsed.
    assert result.char_start == CV.index("Built")
    assert result.char_end == CV.index("users.") + len("users.")
    assert _check("partial", 'Radio sam u "Fabrika" - Beograd').flags == ()


def test_a_near_miss_passes_at_the_threshold_and_fails_above_it() -> None:
    quote = "Built REST APIs in Pyhton, served 120 000 users"  # one typo
    assert find_quote(quote, CV, 90) is not None
    assert find_quote(quote, CV, 100) is None


def test_a_quote_that_changes_a_number_is_not_found() -> None:
    assert find_quote("Built REST APIs in Python, served 12 000 users.", CV, 90) is None
    assert _check("met", "served 220 000 users").flags == (QUOTE_NOT_FOUND,)


def test_an_invented_quote_is_flagged_and_has_no_offsets() -> None:
    result = _check("met", "Led a team of fifteen engineers at Google")
    assert result.flags == (QUOTE_NOT_FOUND,)
    assert result.char_start is None and result.char_end is None


def test_met_or_partial_without_a_quote_is_no_evidence() -> None:
    assert _check("met", None).flags == (NO_EVIDENCE,)
    assert _check("partial", "   ").flags == (NO_EVIDENCE,)


def test_not_met_needs_no_quote_and_ignores_one() -> None:
    result = _check("not_met", "anything at all")
    assert result.flags == () and result.char_start is None


def test_offsets_are_mapped_from_masked_text_back_to_raw_text() -> None:
    raw = "Ana Petrovic\nana.petrovic@example.com\nWorked as a Java developer for 5 years.\n"
    masked = mask_text(raw)
    assert "example.com" not in masked.masked_text
    result = check_quote("met", "Java developer for 5 years", masked.masked_text, masked.spans, 90)
    assert result.flags == ()
    assert result.char_start is not None and result.char_end is not None
    assert raw[result.char_start : result.char_end] == "Java developer for 5 years"


def test_a_quote_may_not_start_inside_a_number() -> None:
    assert find_quote("5 years", "lead 15 years", 90) is None
    assert find_quote("lead 1", "lead 15 years", 90) is None  # nor end inside one


def test_the_whole_number_is_found_with_the_right_offsets() -> None:
    text = "lead 15 years"
    match = find_quote("15 years", text, 90)
    assert match is not None and match.exact
    assert text[match.start : match.end] == "15 years"


def test_a_later_whole_occurrence_is_taken_when_the_first_cuts_a_number() -> None:
    text = "lead 15 years, then 5 years of Python"
    match = find_quote("5 years", text, 90)
    assert match is not None and text[match.start : match.end] == "5 years"
    assert match.start == text.index("then 5") + len("then ")


def test_a_quote_at_the_very_start_or_end_of_the_text_passes() -> None:
    assert find_quote("5 years", "5 years", 90) is not None
    assert find_quote("2019", "since 2019", 90) is not None
    assert find_quote("since 20", "since 2019", 90) is None


def test_a_quote_may_not_cut_a_decimal_number() -> None:
    assert find_quote("5 years", "experience: 1.5 years", 90) is None
    assert find_quote("5 godina", "iskustvo 1,5 godina", 90) is None
    assert find_quote("lead 1", "lead 1.5", 90) is None
    assert find_quote("1.5 years", "experience: 1.5 years", 90) is not None


def test_a_year_inside_a_date_may_be_quoted_alone() -> None:
    text = "03.2019 - 06.2023 Acme"
    match = find_quote("2019", text, 90)
    assert match is not None and text[match.start : match.end] == "2019"
    assert find_quote("2023", text, 90) is not None
    assert find_quote("since 2019", "since 2019.05 at Acme", 90) is not None


def test_a_near_match_that_cuts_a_number_is_not_accepted() -> None:
    assert find_quote("12 years of Java", "123 years of Java", 90) is None
    assert find_quote("since 2019 at Acme", "since 20190 at Acme", 90) is None


def test_a_fuzzy_alignment_ending_inside_a_number_is_rejected() -> None:
    # The typo sends it down the fuzzy path; the best alignment stops after the "1" of "15",
    # so every digit run of the quote is in the window and only the split check catches it.
    assert find_quote("experience with python 1", "experiance with python 15", 90) is None
    assert find_quote("experience with python 1", "experiance with python 1", 90) is not None


def test_a_fuzzy_or_case_changed_quote_is_displayed_as_the_exact_cv_slice() -> None:
    for model_quote in (
        "BUILT REST APIS IN PYTHON",  # case change
        "• Built REST APIs in Python",  # a bullet glyph added
    ):
        check = _check("met", model_quote)
        assert check.flags == ()
        shown = displayed_quote(model_quote, check, CV)
        assert shown is not None and shown in CV  # byte-verbatim
        assert shown != model_quote
        # The interface highlights cv_text[char_start:char_end]: it is the same string.
        assert check.char_start is not None and check.char_end is not None
        assert shown == CV[check.char_start : check.char_end]


def test_a_flagged_quote_keeps_the_model_string_and_has_no_offsets() -> None:
    check = _check("met", "A sentence that is nowhere in this CV at all")
    assert displayed_quote("A sentence that is nowhere in this CV at all", check, CV) == (
        "A sentence that is nowhere in this CV at all"
    )
    assert displayed_quote(None, _check("not_met", None), CV) is None
