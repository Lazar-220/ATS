"""Matches extracted requirements to gold requirements, by a rule a person can follow (§5.4).

No model is involved: the metric must not share a blind spot with the thing it measures.

For one extracted text E and one gold requirement G (its text, or any of its aliases A):

1. Both texts are normalized with `normalize_for_lexical` (Cyrillic to Latin, lowercase, no
   diacritics, `đ` as `dj`) and split into words.
2. Whole-number words are set aside. E and A must contain the same set of numbers, otherwise they
   are different requirements: "Java" is not "3 years of Java", and "2 years of Scrum" is not
   "4 years of project management".
3. The rest are content words: stop words (`STOP_WORDS`) are dropped, and every word is cut to
   its first `PREFIX` letters. The cut is a crude stemmer for Serbian inflection (`projekata`
   and `projekti` agree) that leaves `java` and `javascript` apart.
4. The score is the Jaccard overlap of the two sets of content words: shared / all.
5. G's score is the best over its text and aliases. A pair needs at least `THRESHOLD`.
6. Pairs are taken greedily, highest score first, ties by the lower gold id and then the lower
   extracted id, each requirement at most once. Two extracted requirements for one gold one
   therefore count once as correct and once as wrong, and so does an unsplit compound.

Where the rule is wrong (an inflection that the cut does not join, a number written as a word),
the fix is an alias on the gold requirement, never a looser rule.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass

from ats.eval.schemas import GoldRequirement
from ats.pipeline.normalize import normalize_for_lexical
from ats.pipeline.requirements import RequirementDraft

PREFIX = 5
THRESHOLD = 0.5

# Written in normalized form: lowercase ASCII, `dj` for `đ`. Words that carry no requirement of
# their own, English and Serbian, plus the single letters that apostrophes and hyphens leave behind.
STOP_WORDS = frozenset(
    [
        "a",
        "an",
        "the",
        "of",
        "in",
        "on",
        "with",
        "and",
        "or",
        "for",
        "to",
        "at",
        "as",
        "by",
        "from",
        "is",
        "are",
        "be",
        "such",
        "least",
        "s",
        "u",
        "i",
        "years",
        "year",
        "experience",
        "experienced",
        "knowledge",
        "working",
        "strong",
        "solid",
        "good",
        "excellent",
        "extensive",
        "proven",
        "professional",
        "level",
        "higher",
        "ideally",
        "preferably",
        "skills",
        "ability",
        "daily",
        "ili",
        "sa",
        "na",
        "za",
        "od",
        "do",
        "po",
        "uz",
        "kod",
        "bar",
        "preko",
        "kao",
        "je",
        "su",
        "se",
        "koji",
        "koja",
        "godina",
        "godine",
        "godinu",
        "iskustvo",
        "iskustva",
        "iskustvu",
        "najmanje",
        "poznavanje",
        "poznavanja",
        "poznavanju",
        "odlicno",
        "odlicna",
        "dobro",
        "vrlo",
        "veoma",
        "rad",
        "rada",
        "radu",
        "radom",
        "jezik",
        "jezika",
        "znanje",
        "znanja",
        "nivo",
        "nivou",
        "vestine",
        "vestina",
        "sposobnost",
        "minimum",
    ]
)

_WORD = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True)
class Tokens:
    content: frozenset[str]
    numbers: frozenset[str]


def tokenize(text: str) -> Tokens:
    words = _WORD.findall(normalize_for_lexical(text))
    numbers = frozenset(word for word in words if word.isdigit())
    content = frozenset(
        word[:PREFIX] for word in words if not word.isdigit() and word not in STOP_WORDS
    )
    return Tokens(content, numbers)


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    union = a | b
    return len(a & b) / len(union) if union else 0.0


@dataclass(frozen=True)
class Match:
    extracted_id: int
    gold_id: int
    score: float
    # The gold text or alias that produced the score, so a reader sees what was compared.
    via: str
    kind_correct: bool


@dataclass(frozen=True)
class MatchResult:
    matches: list[Match]
    unmatched_extracted: list[int]
    unmatched_gold: list[int]


def score_pair(extracted_text: str, gold: GoldRequirement) -> tuple[float, str]:
    """Best score of the extracted text against the gold text and its aliases, and which one."""
    extracted = tokenize(extracted_text)
    best, via = 0.0, gold.text
    for candidate in (gold.text, *gold.aliases):
        other = tokenize(candidate)
        if extracted.numbers != other.numbers:
            continue
        value = _jaccard(extracted.content, other.content)
        if value > best:
            best, via = value, candidate
    return best, via


def match_requirements(
    extracted: Sequence[RequirementDraft], gold: Sequence[GoldRequirement]
) -> MatchResult:
    candidates: list[tuple[float, int, int, str]] = []
    for ext in extracted:
        for ref in gold:
            value, via = score_pair(ext.text, ref)
            if value >= THRESHOLD:
                candidates.append((value, ref.id, ext.id, via))
    candidates.sort(key=lambda c: (-c[0], c[1], c[2]))

    used_extracted: set[int] = set()
    used_gold: set[int] = set()
    kinds = {ext.id: ext.kind for ext in extracted}
    gold_kinds = {ref.id: ref.kind for ref in gold}
    matches: list[Match] = []
    for value, gold_id, extracted_id, via in candidates:
        if gold_id in used_gold or extracted_id in used_extracted:
            continue
        used_gold.add(gold_id)
        used_extracted.add(extracted_id)
        matches.append(
            Match(extracted_id, gold_id, value, via, kinds[extracted_id] == gold_kinds[gold_id])
        )
    return MatchResult(
        matches=sorted(matches, key=lambda m: m.gold_id),
        unmatched_extracted=[e.id for e in extracted if e.id not in used_extracted],
        unmatched_gold=[g.id for g in gold if g.id not in used_gold],
    )
