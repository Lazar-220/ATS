from datetime import date

from ats.pipeline.facts import build_facts
from ats.pipeline.parsing import ExperienceItem, ParsedCV
from ats.pipeline.tenure import item_tenure, merged_months

AS_OF = date(2026, 11, 17)


def test_march_2019_to_june_2023_is_51_months() -> None:
    assert item_tenure("2019-03", "2023-06", AS_OF).months == 51


def test_an_open_ended_job_runs_to_the_injected_date() -> None:
    assert item_tenure("2024-11", "present", AS_OF).months == 24
    # The same CV read a year earlier gives a year less: the clock is never read.
    assert item_tenure("2024-11", "present", date(2025, 11, 1)).months == 12


def test_year_only_dates_are_january_and_december_and_marked_approximate() -> None:
    result = item_tenure("2019", "2023", AS_OF)
    assert result.months == 59
    assert result.approximate
    assert not item_tenure("2019-01", "2023-12", AS_OF).approximate


def test_a_missing_start_or_end_gives_no_count_and_says_why() -> None:
    assert item_tenure("2019-03", None, AS_OF) == item_tenure("2019-03", None, AS_OF)
    assert item_tenure("2019-03", None, AS_OF).months is None
    assert item_tenure("2019-03", None, AS_OF).note == "no end date"
    assert item_tenure(None, "2020-01", AS_OF).note == "no start date"
    assert item_tenure(None, None, AS_OF).note is None


def test_an_end_before_the_start_gives_no_count() -> None:
    result = item_tenure("2022-05", "2021-01", AS_OF)
    assert result.months is None and result.note == "end before start"


def test_an_end_in_the_future_is_cut_back_to_the_reference_date() -> None:
    assert item_tenure("2026-01", "2027-06", AS_OF).months == 10
    assert item_tenure("2027-01", "2027-06", AS_OF).months is None


def test_overlapping_periods_are_not_counted_twice() -> None:
    # Jan 2020 to Jan 2022 and Jan 2021 to Jan 2023 overlap for a year.
    assert merged_months([(2020 * 12, 2022 * 12), (2021 * 12, 2023 * 12)]) == 36


def test_adjacent_nested_and_separate_periods() -> None:
    assert merged_months([(0, 10), (10, 20)]) == 20
    assert merged_months([(0, 30), (5, 10)]) == 30
    assert merged_months([(0, 10), (20, 25)]) == 15
    assert merged_months([]) == 0


def _job(start: str | None, end: str | None) -> ExperienceItem:
    return ExperienceItem(
        snippet="job", date_start=start, date_end=end, title="t", organization=None
    )


def test_stored_tenure_merges_overlaps_and_records_the_reference_date() -> None:
    parsed = ParsedCV(
        is_cv=True,
        suspected_injection=False,
        experience=[
            _job("2019-03", "2023-06"),
            _job("2022-01", "2024-01"),  # overlaps the first by 18 months
            _job("2025-01", None),  # no end: skipped, not guessed
        ],
        education=[],
        skills=[],
        certificates=[],
        languages=[],
        projects=[],
    )
    facts = build_facts(parsed, "job", [], AS_OF)
    tenure = facts.parsed_json["tenure"]
    # 2019-03 to 2024-01 as one period: 58 months.
    assert tenure == {
        "total_months": 58,
        "as_of": "2026-11-17",
        "counted_items": 2,
        "skipped_items": 1,
    }
    months = [item["months"] for item in facts.parsed_json["experience"]]
    assert months == [51, 24, None]
    assert facts.parsed_json["experience"][2]["months_note"] == "no end date"
