from ats.pipeline.context import ContextRequirement, build_context

PARSED = {
    "experience": [
        {
            "title": "Developer",
            "organization": "Acme",
            "date_start": "2019-03",
            "date_end": "2023-06",
            "months": 51,
            "months_approximate": False,
        }
    ],
    "tenure": {"total_months": 51, "as_of": "2026-11-17"},
}


def test_v1_context_holds_the_whole_cv_the_facts_and_an_empty_rule_slot() -> None:
    reqs = [ContextRequirement(1, "Python", "mandatory", 3, None, None)]
    pack = build_context("the whole masked cv", PARSED, reqs)
    assert pack.masked_cv == "the whole masked cv"
    assert pack.total_months == 51 and pack.as_of == "2026-11-17"
    assert pack.experience[0].months == 51
    assert pack.requirements == tuple(reqs)
    assert pack.rules == ()
