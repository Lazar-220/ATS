from ats.pipeline.masking import mask_text
from ats.pipeline.quotes import NO_EVIDENCE, QUOTE_NOT_FOUND, check_quote, find_quote

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
