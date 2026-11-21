"""A skill that exists only in a skills list gives at most `partial` (§4.4, hidden skills lists).

The judge prompt says so (`judge_v1`), and this is the same rule in code, because a model can
slip and "code computes, the LLM judges". A `met` verdict is downgraded to `partial` when its
quote lies in a skills item and

- no experience, project, certificate or education item overlaps the quote, and
- none of the skill names the quote covers is mentioned in an experience, project or
  certificate item: every word of the name, in order within a 3-word window of one snippet,
  allowing case endings (see `_word_confirms`).

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


# Words of one snippet in which the next word of a multi-word name must follow the previous one:
# at most two other words in between ("Machine Learning" in "machine and deep learning").
_WINDOW = 3


def _follows(tokens: list[str], words: list[str], start: int) -> bool:
    """Whether `tokens` match words from `start` on, in order, each within the window."""
    if not tokens:
        return True
    return any(
        _word_confirms(tokens[0], words[i]) and _follows(tokens[1:], words, i + 1)
        for i in range(start, min(start + _WINDOW, len(words)))
    )


def _mentioned(name: str, snippets: list[str]) -> bool:
    """Whether a skill's name occurs in one of the (folded) snippets, in any case form.

    Every word of a multi-word name must match, in order and close together, inside one snippet:
    "Project Management" is not confirmed by "project" alone, nor "Power BI" by "power plant".
    Both sides are folded and transliterated (`normalize_for_lexical`), so Latin and Cyrillic
    agree. Not covered: a Latin name against its Cyrillic respelling ("Python" and "Питхон"), and
    a translation ("Project Management" and "upravljanje projektima").
    """
    tokens = re.findall(r"\w+", normalize_for_lexical(name))
    if not tokens:
        return False
    for snippet in snippets:
        words = re.findall(r"\w+", snippet)
        # The first word may start anywhere; the rest follow inside the window.
        if any(
            _word_confirms(tokens[0], word) and _follows(tokens[1:], words, i + 1)
            for i, word in enumerate(words)
        ):
            return True
    return False


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
    confirming = [
        normalize_for_lexical(str(item.get("snippet", "")))
        for section in _CONFIRMING_TEXT
        for item in parsed_json.get(section, [])
    ]
    if any(_mentioned(str(item.get("name", "")), confirming) for item in skills):
        return None
    return (
        "the evidence is an entry of a skills list that no job, project or certificate mentions: "
        "at most partial"
    )
