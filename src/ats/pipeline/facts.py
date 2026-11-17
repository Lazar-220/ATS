"""The stored result of parsing: the model's JSON plus what code worked out about it.

`document.parsed_json` holds the parsed items, each with the position of its snippet in
`raw_text`, and the text coverage. `document.flags` holds what HR should see.
"""

from dataclasses import dataclass
from typing import Any

from ats.pipeline.locate import MIN_COVERAGE, Located, coverage, locate_snippet, placeholder_ranges
from ats.pipeline.masking import Span, masked_range_to_raw
from ats.pipeline.parsing import SECTIONS, ParsedCV

NOT_A_CV = "not_a_cv"
SUSPECTED_INJECTION = "suspected_injection"
LOW_COVERAGE = "low_coverage"


@dataclass(frozen=True)
class ParsedFacts:
    parsed_json: dict[str, Any]
    flags: list[dict[str, str]]


def build_facts(parsed: ParsedCV, masked_text: str, spans: list[Span]) -> ParsedFacts:
    document: dict[str, Any] = parsed.model_dump()
    located_all: list[Located] = []
    unlocated = 0
    for section in SECTIONS:
        for item in document[section]:
            found = locate_snippet(item["snippet"], masked_text)
            if found is None:
                unlocated += 1
                item["char_start"] = item["char_end"] = None
                continue
            located_all.append(found)
            # The model read masked text; the interface highlights raw text.
            item["char_start"], item["char_end"] = masked_range_to_raw(
                spans, found.start, found.end
            )
    share = coverage(masked_text, placeholder_ranges(spans), located_all)
    document["coverage"] = round(share, 4)
    document["unlocated_items"] = unlocated

    flags: list[dict[str, str]] = []
    if not parsed.is_cv:
        # Triage decides what happens next with a document; it never rejects a candidate for
        # what the CV says (§4.2). A non-CV is flagged and gets no assessment (phase 1.4b).
        flags.append({"code": NOT_A_CV, "detail": "the model judged the document not to be a CV"})
    else:
        if share < MIN_COVERAGE:
            flags.append(
                {
                    "code": LOW_COVERAGE,
                    "detail": f"items cover {share:.0%} of the text, under {MIN_COVERAGE:.0%}",
                }
            )
    if parsed.suspected_injection:
        flags.append(
            {"code": SUSPECTED_INJECTION, "detail": "the text seems to address an AI or a screener"}
        )
    return ParsedFacts(document, flags)
