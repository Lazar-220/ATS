from pdfs import make_two_column_pdf

from ats.pipeline.extract import extract_text
from ats.pipeline.facts import LOW_COVERAGE, NOT_A_CV, SUSPECTED_INJECTION, build_facts
from ats.pipeline.locate import locate_snippet
from ats.pipeline.masking import mask_text
from ats.pipeline.parsing import ExperienceItem, ParsedCV, SkillItem


def _cv(
    experience: list[ExperienceItem] | None = None,
    skills: list[SkillItem] | None = None,
    *,
    is_cv: bool = True,
    injection: bool = False,
) -> ParsedCV:
    return ParsedCV(
        is_cv=is_cv,
        suspected_injection=injection,
        experience=experience or [],
        education=[],
        skills=skills or [],
        certificates=[],
        languages=[],
        projects=[],
    )


def _job(snippet: str) -> ExperienceItem:
    return ExperienceItem(
        snippet=snippet, date_start="2019-03", date_end="2023-06", title="PM", organization=None
    )


TEXT = "Header\nProject Manager, Acme\n03/2019 - 06/2023\nLed a team of 8\nSkills\nPython, SQL\n"


def test_an_exact_snippet_is_found() -> None:
    found = locate_snippet("Project Manager, Acme\n03/2019 - 06/2023", TEXT)
    assert found is not None and TEXT[found.start : found.end].startswith("Project Manager")


def test_whitespace_differences_do_not_lose_the_snippet() -> None:
    found = locate_snippet("Project Manager, Acme 03/2019 - 06/2023", TEXT)
    assert found is not None
    assert TEXT[found.start : found.end] == "Project Manager, Acme\n03/2019 - 06/2023"


def test_a_snippet_that_is_not_in_the_text_is_not_located() -> None:
    assert locate_snippet("Chief Executive Officer", TEXT) is None


def test_items_that_cover_the_text_leave_no_flag_and_carry_raw_positions() -> None:
    raw = "Nina Stojkovic\nnina.stojkovic@example.com\nProject Manager at Acme 2019 - 2023\n"
    result = mask_text(raw)
    snippet = "Project Manager at Acme 2019 - 2023"
    facts = build_facts(_cv([_job(snippet)]), result.masked_text, result.spans)
    item = facts.parsed_json["experience"][0]
    assert raw[item["char_start"] : item["char_end"]] == snippet
    assert facts.parsed_json["coverage"] == 1.0
    assert facts.flags == []


def test_a_snippet_around_a_placeholder_maps_to_raw_text_with_the_original_inside() -> None:
    raw = "Contact nina.stojkovic@example.com for references\nNina Stojkovic\n"
    result = mask_text(raw)
    facts = build_facts(
        _cv(
            skills=[
                SkillItem(
                    snippet="Contact [EMAIL] for references",
                    name="x",
                    date_start=None,
                    date_end=None,
                )
            ]
        ),
        result.masked_text,
        result.spans,
    )
    item = facts.parsed_json["skills"][0]
    assert raw[item["char_start"] : item["char_end"]] == (
        "Contact nina.stojkovic@example.com for references"
    )


def test_items_covering_under_85_percent_flag_the_document() -> None:
    masked = "aaaa bbbb cccc dddd eeee ffff gggg hhhh\n"
    facts = build_facts(_cv([_job("aaaa bbbb")]), masked, [])
    assert [f["code"] for f in facts.flags] == [LOW_COVERAGE]
    assert facts.parsed_json["coverage"] < 0.85


def test_unlocated_snippets_are_counted_and_cover_nothing() -> None:
    facts = build_facts(_cv([_job("not in the text")]), "some text here", [])
    assert facts.parsed_json["unlocated_items"] == 1
    assert facts.parsed_json["experience"][0]["char_start"] is None
    assert facts.parsed_json["coverage"] == 0.0


def test_coverage_ignores_whitespace_and_masked_personal_data() -> None:
    raw = "a@example.com\n\nWork   history of the candidate\n"
    result = mask_text(raw)
    facts = build_facts(
        _cv([_job("Work history of the candidate")]), result.masked_text, result.spans
    )
    assert facts.parsed_json["coverage"] == 1.0


def test_a_non_cv_is_flagged_and_an_injection_is_flagged() -> None:
    facts = build_facts(_cv(is_cv=False, injection=True), "an invoice", [])
    assert {f["code"] for f in facts.flags} == {NOT_A_CV, SUSPECTED_INJECTION}


def test_a_two_column_cv_keeps_its_items_through_interleaved_extraction() -> None:
    left = [
        "Work experience",
        "2019-2023 Project Manager",
        "Led a team of 8",
        "Skills",
        "Python SQL",
    ]
    right = ["Education", "MSc Economics", "University of Belgrade", "Languages", "English C1"]
    text = extract_text(make_two_column_pdf(left, right), min_chars_per_page=10).text
    # Row by row, the columns are interleaved: the two halves of an item are not adjacent.
    assert text.index("Education") < text.index("Led a team of 8")
    job = locate_snippet("2019-2023 Project Manager\nLed a team of 8", text)
    assert job is not None  # found line by line although the lines are not adjacent
    assert text[job.start : job.end].count("\n") >= 2
    degree = locate_snippet("MSc Economics\nUniversity of Belgrade", text)
    assert degree is not None
    lone = locate_snippet("Python SQL", text)
    assert lone is not None and text[lone.start : lone.end] == "Python SQL"
