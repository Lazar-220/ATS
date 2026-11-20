"""Pattern detection of instruction-like text in a CV (§4.4, detection layer).

Only a flag for HR: nothing here changes a verdict or rejects a candidate. The text is folded to
lowercase ASCII Latin first (Cyrillic is transliterated, diacritics dropped), so one set of
patterns covers English, Serbian Latin, Serbian without diacritics and Serbian Cyrillic.

The patterns want an address to the reader (an imperative, "this candidate is ...", "you are an
AI"), not a topic: a recruiter's CV that says "screening of candidates" must not be flagged. How
often a clean CV is flagged is measured on the golden set (tests and PROGRESS.md). There is no
data on a classifier for Serbian, so regexes are all this layer has (plan §4.4).
"""

import re

from ats.pipeline.normalize import normalize_for_lexical

SUSPECTED_INJECTION = "suspected_injection"

_ARTICLE = r"(?:the |all |any |every |your |these |those )?"
_PREVIOUS = r"(?:previous|prior|above|earlier|preceding|original|initial)"
_ROLE = r"(?:candidate|applicant|cv|resume|profile)"
_ASK = r"(?:please |kindly |you must |you should |you will |always |now |just |make sure to )"
_SR_PREV = r"(?:prethodn\w+|gornj\w+|ranij\w+|sve)"
_SR_RULES = r"(?:instrukcij\w+|uputstv\w+|pravil\w+|naredb\w+|zahtev\w+|zahtjev\w+)"
_SR_CAND = r"(?:kandidat\w*|cv\w*|biografij\w+|aplikant\w*)"

PATTERNS: dict[str, re.Pattern[str]] = {
    name: re.compile(pattern)
    for name, pattern in {
        "ignore_previous": (
            rf"\b(?:ignore|disregard|forget|override|bypass|skip)\s+{_ARTICLE}(?:{_PREVIOUS}\s+)?"
            rf"(?:instructions?|prompts?|rules?|criteria|requirements?|guidelines?|context)\b"
            rf"|\b(?:ignore|disregard|forget)\s+(?:all\s+)?{_PREVIOUS}\b"
        ),
        "ignore_previous_sr": (
            rf"\b(?:ignorisi\w*|zanemari\w*|zaboravi\w*|preskoci\w*|prenebregni\w*)\s+"
            rf"(?:(?:sve|svu|sva)\s+)?(?:{_SR_PREV}\s+)?{_SR_RULES}\b"
            rf"|\b(?:ignorisi\w*|zanemari\w*|zaboravi\w*)\s+(?:sve\s+)?{_SR_PREV}\b"
        ),
        "rate_candidate": (
            rf"\b{_ASK}?(?:rate|score|rank|grade|mark|evaluate|assess|treat|consider)\s+"
            rf"(?:this|the)\s+{_ROLE}\s+(?:as\s+|highly|at\s+|with\s+|first|the\s+best)"
            rf"|\b{_ASK}(?:rate|score|rank|grade|mark|shortlist|hire|recommend|select|pass)\s+"
            rf"(?:this|the)\s+{_ROLE}\b"
        ),
        "rate_candidate_sr": (
            rf"\b(?:oceni|ocijeni|ocenite|ocjenite|rangiraj\w*|izaberi\w*|zaposli\w*|"
            rf"preporuci\w*|preporucite|odaberi\w*|propusti\w*)\s+(?:ovog\s+|ovu\s+|ovaj\s+)?"
            rf"{_SR_CAND}\b"
        ),
        "candidate_is_perfect": (
            rf"\b(?:this|the)\s+{_ROLE}\s+(?:is|should be|must be|deserves|meets|fulfils|"
            rf"fulfills)\s+(?:a\s+|an\s+|the\s+)?(?:perfect|ideal|excellent|best|top|strong|"
            rf"outstanding|exceptional|all|every|highest|shortlisted|hired)"
        ),
        "candidate_is_perfect_sr": (
            r"\b(?:ovaj|ovog|ova)\s+(?:kandidat\w*|cv|biografij\w+)\s+"
            r"(?:je|treba|mora|zasluzuje|ispunjava)\s+(?:biti\s+)?"
            r"(?:savrsen\w*|idealan|idealn\w+|najbolj\w+|odlic\w+|izuzetan|izuzetn\w+|"
            r"izabran\w*|zaposlen\w*|primljen\w*|sve|svaki|najvis\w+)"
        ),
        "all_requirements_met": (
            r"\b(?:mark|set|give|assign|answer|return|output|rate)\s+(?:all|every|each)\s+"
            r"(?:requirements?|criteria|verdicts?|skills?)\b(?:\s+as)?\s+(?:met|fulfilled|"
            r"satisfied|passed|full|maximum)"
            r"|\b(?:all|every)\s+(?:requirements?|criteria)\s+(?:are|is|have been)\s+"
            r"(?:met|fulfilled|satisfied)\b"
        ),
        "all_requirements_met_sr": (
            r"\b(?:sve|svaki|svaku|svaki od)\s+(?:zahtev\w*|zahtjev\w*|uslov\w*|kriterijum\w*)"
            r"\s+(?:je\s+|su\s+)?(?:ispunjen\w*|zadovoljen\w*|met|ispunjava)\b"
            r"|\b(?:oznaci|postavi|daj|dodeli|vrati)\s+(?:sve|svaki)\s+(?:zahtev\w*|zahtjev\w*|"
            r"uslov\w*|kriterijum\w*)\b"
        ),
        "addresses_ai": (
            r"\b(?:you are|you're|act as|pretend to be|behave as|from now on you)\s+(?:now\s+)?"
            r"(?:an?\s+|the\s+)?(?:ai|a\.i\.|llm|language model|assistant|chatbot|recruiter|"
            r"screener|screening|hr (?:bot|assistant|system)|hiring)\b"
            r"|\b(?:note|message|attention|instruction)s?\s+(?:to|for)\s+(?:the\s+)?"
            r"(?:ai|llm|language model|screener|screening|ats|recruiter|reviewer|model|"
            r"assistant|chatbot|automated)\b"
            r"|\b(?:if|when)\s+you\s+are\s+(?:an?\s+)?(?:ai|llm|language model|assistant|"
            r"automated)\b"
            r"|\b(?:system|developer)\s+(?:prompt|message|instructions?)\b"
            r"|\bnew\s+instructions?\b"
        ),
        "addresses_ai_sr": (
            r"\b(?:ti si|vi ste|ti ces biti|ponasaj se kao)\s+(?:sada\s+)?"
            r"(?:ai|vestacka\w*|jezicki model|asistent\w*|chatbot|recruiter|hr|selektor\w*)\b"
            r"|\b(?:napomena|poruka|obavestenje|obavjestenje|instrukcij\w+|uputstv\w+)\s+"
            r"(?:za|ka)\s+(?:ai|vestack\w+|sistem\w*|ats|recenzent\w*|recruiter\w*|model\w*|"
            r"asistent\w*|automatsk\w+|selektor\w*|jezick\w+)\b"
            r"|\b(?:sistemsk\w+|novo|nova|nove)\s+(?:prompt|instrukcij\w+|uputstv\w+)\b"
        ),
    }.items()
}


def detect_injection(text: str) -> list[str]:
    """Names of the patterns that match, in a fixed order. Empty for a clean text."""
    folded = " ".join(normalize_for_lexical(text).split())
    return [name for name, pattern in PATTERNS.items() if pattern.search(folded)]


def injection_flag(text: str) -> dict[str, str] | None:
    names = detect_injection(text)
    if not names:
        return None
    return {
        "code": SUSPECTED_INJECTION,
        "detail": "text that reads like an instruction to an AI or a screener "
        f"(patterns: {', '.join(names)})",
    }
