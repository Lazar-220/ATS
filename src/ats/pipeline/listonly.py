"""A skill that exists only in a skills list gives at most `partial` (§4.4, hidden skills lists).

The judge prompt says so (`judge_v1`), and this is the same rule in code, because a model can
slip and "code computes, the LLM judges". A `met` verdict is downgraded to `partial` when its
quote lies in a skills item and

- no experience, project, certificate or education item overlaps the quote, and
- none of the skill names the quote covers is mentioned in an experience, project or
  certificate item.

When it cannot tell (the quote has no position, the items have none, the quote is outside the
skills section) the verdict stays as the judge gave it. This errs toward trusting the judge: a
skill named in a job description counts as confirmed even if the requirement is about another
skill of the same line.
"""

import re
from typing import Any

from ats.pipeline.normalize import normalize_for_lexical
from ats.pipeline.quotes import CheckedQuote

LIST_ONLY_SKILL = "list_only_skill"

_CONFIRMING_TEXT = ("experience", "projects", "certificates")
_CONFIRMING_ZONES = ("experience", "projects", "certificates", "education")


def _overlaps(item: dict[str, Any], start: int, end: int) -> bool:
    item_start, item_end = item.get("char_start"), item.get("char_end")
    if item_start is None or item_end is None:
        return False
    return bool(item_start < end and start < item_end)


# Serbian case endings add up to three letters to a name ("Pythonu", "Excelom", "SQL-u").
_MAX_ENDING = 3
# A name of at least this many letters also confirms through a longer word that starts with it
# ("Python" in "Pythonu") and through a shorter word it starts with ("PostgreSQL" in "Postgres").
_PREFIX_MIN = 4
_SHORTER_WORD_MIN = 5


def _word_confirms(token: str, word: str) -> bool:
    if word == token:
        return True
    if len(token) >= _PREFIX_MIN:
        return word.startswith(token) or (len(word) >= _SHORTER_WORD_MIN and token.startswith(word))
    # Short names ("R", "Go") match whole words only, so they never hide inside "Golang" or
    # "Gorenje"; from three letters on, a case ending of up to three letters is allowed.
    return (
        len(token) == _PREFIX_MIN - 1
        and word.startswith(token)
        and (len(word) - len(token) <= _MAX_ENDING)
    )


def _mentioned(name: str, text: str) -> bool:
    """Whether a skill's name occurs in `text` (already folded), in any case form.

    Both sides are folded and transliterated (`normalize_for_lexical`), so Latin and Cyrillic
    agree. Not covered: a Latin name against its Cyrillic respelling ("Python" and "Питхон").
    """
    tokens = re.findall(r"\w+", normalize_for_lexical(name))
    words = set(re.findall(r"\w+", text))
    return any(_word_confirms(token, word) for token in tokens for word in words)


def list_only_detail(verdict: str, check: CheckedQuote, parsed_json: dict[str, Any]) -> str | None:
    """Why a `met` verdict should be `partial`, or None to leave it."""
    if verdict != "met" or check.char_start is None or check.char_end is None:
        return None
    start, end = check.char_start, check.char_end
    skills: list[dict[str, Any]] = [
        item for item in parsed_json.get("skills", []) if _overlaps(item, start, end)
    ]
    if not skills:
        return None
    for section in _CONFIRMING_ZONES:
        if any(_overlaps(item, start, end) for item in parsed_json.get(section, [])):
            return None
    confirming = normalize_for_lexical(
        " ".join(
            str(item.get("snippet", ""))
            for section in _CONFIRMING_TEXT
            for item in parsed_json.get(section, [])
        )
    )
    if any(_mentioned(str(item.get("name", "")), confirming) for item in skills):
        return None
    return (
        "the evidence is an entry of a skills list that no job, project or certificate mentions: "
        "at most partial"
    )
