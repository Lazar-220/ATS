from ats.pipeline.masking import (
    ADDRESS,
    EMAIL,
    NAME,
    PHONE,
    Span,
    mask_text,
    masked_range_to_raw,
)

CV = """Nina Stojkovic
Business Analyst
Phone
(+381) 62 5550304
Email
nina.stojkovic@example.com
Location
Serbia, Belgrade
Experience
Senior Business Analyst
Delta Insurance, Belgrade
03/2019 - 02/2023
Orion Bank, Belgrade 2016 - 2019
LinkedIn linkedin.com/in/nina-stojkovic-bg
"""


def test_email_phone_name_and_labelled_address_are_replaced() -> None:
    result = mask_text(CV)
    masked = result.masked_text
    for secret in ("Nina", "Stojkovic", "5550304", "example.com", "Serbia, Belgrade"):
        assert secret not in masked
    assert masked.count(NAME) == 4  # two in the header, two in the slug "nina-stojkovic-bg"
    assert EMAIL in masked and PHONE in masked and ADDRESS in masked
    assert result.contact.email == "nina.stojkovic@example.com"
    assert result.contact.phone == "(+381) 62 5550304"
    assert result.contact.full_name == "Nina Stojkovic"
    assert result.contact.address == "Serbia, Belgrade"


def test_a_city_in_an_experience_line_and_dates_are_kept() -> None:
    masked = mask_text(CV).masked_text
    assert "Delta Insurance, Belgrade" in masked
    assert "03/2019 - 02/2023" in masked
    assert "2016 - 2019" in masked
    assert "Business Analyst" in masked


def test_cyrillic_label_and_latin_email_mask_both_scripts() -> None:
    raw = (
        "Презиме и име Радосављевић Тамара\nТелефон 064 5550733\n"
        "Е-пошта tamara.radosavljevic@example.com\nТамара је радила у банци.\n"
    )
    masked = mask_text(raw).masked_text
    assert "Тамара" not in masked and "Радосављевић" not in masked
    assert "5550733" not in masked and "example.com" not in masked


def test_name_in_a_latin_cv_is_found_when_the_cv_writes_diacritics() -> None:
    raw = "Jovana Đurić\njovana.djuric@example.com\nRadila je kod Đurić doo.\n"
    masked = mask_text(raw).masked_text
    assert "Đurić" not in masked and "Jovana" not in masked


def test_a_title_line_is_not_taken_for_the_name() -> None:
    raw = "Business Analyst\nnina.stojkovic@example.com\nNina Stojkovic\n"
    masked = mask_text(raw).masked_text
    assert "Business Analyst" in masked
    assert "Stojkovic" not in masked


def test_street_pattern_masks_the_address() -> None:
    raw = "Bulevar kralja Aleksandra 15, Beograd\nx@example.com\n"
    assert ADDRESS in mask_text(raw).masked_text


def test_a_date_range_is_not_a_phone_number() -> None:
    raw = "01.2019 - 03.2021\n2019 - 2023\n03.07.1993.\nx@example.com\n"
    assert PHONE not in mask_text(raw).masked_text


def test_a_quote_with_a_placeholder_maps_back_to_the_raw_range() -> None:
    raw = "Reach nina.stojkovic@example.com or (+381) 62 5550304 for the CBAP list.\n"
    result = mask_text(raw)
    masked = result.masked_text
    quote = "Reach [EMAIL] or [PHONE] for"
    start = masked.index(quote)
    raw_start, raw_end = masked_range_to_raw(result.spans, start, start + len(quote))
    assert raw[raw_start:raw_end] == "Reach nina.stojkovic@example.com or (+381) 62 5550304 for"


def test_a_quote_touching_a_placeholder_grows_to_the_whole_raw_span() -> None:
    raw = "mail: nina.stojkovic@example.com ok"
    result = mask_text(raw)
    masked = result.masked_text
    # The quote starts in the middle of the placeholder.
    start = masked.index("EMAIL") + 2
    raw_start, raw_end = masked_range_to_raw(result.spans, start, start + 3)
    assert raw[raw_start:raw_end] == "nina.stojkovic@example.com"


def test_ranges_before_and_after_spans_shift_correctly() -> None:
    spans = [Span(raw_start=5, raw_end=15, placeholder="[X]")]  # shrinks by 7
    assert masked_range_to_raw(spans, 0, 5) == (0, 5)
    assert masked_range_to_raw(spans, 8, 12) == (15, 19)
