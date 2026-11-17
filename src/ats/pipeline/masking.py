"""Masking of personal data before any text reaches the LLM (§2.4, "Per CV" step 3).

Name, email, phone and address are replaced with placeholders and kept in a `Contact` for the
`candidate` table. Detection is deterministic code, no model call:

- email and phone by pattern;
- name tokens from the email local part, from a labelled line, and from a 2 to 3 word line near
  the top that agrees with the email; every occurrence of a token is masked, comparing
  diacritic-folded and Latin/Cyrillic-transliterated text, also inside URL slugs;
- address only from a labelled value or a street-and-number pattern. A city inside an
  experience line is employer information and stays.

Known limits (docs/PROGRESS.md): a CV without an email or a recognisable name line can leak the
name; a name inflected in running text ("Stankovićeva") is not matched; an unlabelled address
line (a bare "Novi Sad, Srbija" in a contact block) and a street without a street word stay;
a name that is also a common word of 3+ letters is over-masked.

`Span` keeps raw offsets only. The masked offsets follow from them, so one list is enough to
map a quote found in masked text back to `raw_text`.
"""

import re
from dataclasses import dataclass
from functools import lru_cache

from pydantic import BaseModel

from ats.pipeline.normalize import normalize_for_lexical

NAME = "[NAME]"
EMAIL = "[EMAIL]"
PHONE = "[PHONE]"
ADDRESS = "[ADDRESS]"

MIN_NAME_TOKEN = 3
# Local parts that say nothing about a person.
GENERIC_LOCAL_PARTS = frozenset(
    {"info", "mail", "email", "contact", "kontakt", "office", "cv", "hr", "job", "jobs", "work"}
    | {"admin", "post", "me", "my"}
)

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
# A run that starts like a phone number and holds 8 to 15 digits. Years and dates are filtered
# afterwards; a bare "/" is not allowed inside, so "03/2018 - 02/2020" is not one run.
_PHONE_RE = re.compile(
    r"(?<![\w+/])"
    r"(?:\+|00)?\(?\+?\d[\d\s().\-]{6,}\d(?![\w/])"
    r"|(?<![\w/])0\d{1,2}/\d{3}[\s-]?\d{3,4}(?!\d)"
)
_DATE_RE = re.compile(r"^\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\.?$")
_YEAR_RE = re.compile(r"(?<!\d)(?:19|20)\d{2}(?!\d)")

_NAME_LABEL_RE = re.compile(
    r"^\s*(?:prezime i ime|ime i prezime|full name|name|ime|презиме и име|име и презиме|име)"
    r"\s*[:\-]?\s*(.*)$",
    re.IGNORECASE,
)
_ADDRESS_LABEL_RE = re.compile(
    r"^\s*(?:adresa|address|location|lokacija|mesto|boravište|prebivalište|residence|city|grad"
    r"|адреса|локација|место|град)\s*[:\-]?\s*(.*)$",
    re.IGNORECASE,
)
_STREET_RE = re.compile(
    r"(?:\b(?:ulica|ul\.|bulevar|bul\.|street|улица|булевар|ул\.)\s+[^\n,;]{2,40}?\s\d{1,3}[a-z]?\b"
    r"|\b\d{1,3}[a-z]?\s+[A-Z][\w ]{2,30}\s(?:Street|Road|Avenue)\b)",
    re.IGNORECASE,
)
_WORD_RE = re.compile(r"[^\W\d_]+(?:-[^\W\d_]+)?")
# The top-of-CV name line is looked for only this far down.
HEADER_LINES = 10
# A label alone on its line takes its value from the next line, if that is short.
MAX_VALUE_LINE = 60


class Span(BaseModel):
    """`raw_text[raw_start:raw_end]` was replaced by `placeholder`."""

    raw_start: int
    raw_end: int
    placeholder: str


class Contact(BaseModel):
    """What the `candidate` table receives. None when the CV did not show it."""

    full_name: str | None = None
    email: str | None = None
    phone: str | None = None
    address: str | None = None


@dataclass(frozen=True)
class MaskResult:
    masked_text: str
    spans: list[Span]
    contact: Contact


@lru_cache(maxsize=4096)
def _fold_char(char: str) -> str:
    return normalize_for_lexical(char)


def _fold_with_map(text: str) -> tuple[str, list[int]]:
    """Folded text and, for every folded character, the raw index it came from."""
    out: list[str] = []
    index: list[int] = []
    for i, char in enumerate(text):
        folded = _fold_char(char)
        out.append(folded)
        index.extend([i] * len(folded))
    return "".join(out), index


def _fold(text: str) -> str:
    return normalize_for_lexical(text)


def _lines(text: str) -> list[tuple[int, int, str]]:
    """(start, end, line) for every line, offsets into `text`."""
    result: list[tuple[int, int, str]] = []
    pos = 0
    for line in text.split("\n"):
        result.append((pos, pos + len(line), line))
        pos += len(line) + 1
    return result


def _emails(text: str) -> list[tuple[int, int]]:
    return [(m.start(), m.end()) for m in _EMAIL_RE.finditer(text)]


def _phones(text: str) -> list[tuple[int, int]]:
    found: list[tuple[int, int]] = []
    for m in _PHONE_RE.finditer(text):
        value = m.group(0).strip()
        digits = sum(c.isdigit() for c in value)
        if not 8 <= digits <= 15 or _DATE_RE.match(value) or _YEAR_RE.search(value):
            continue
        found.append((m.start(), m.start() + len(m.group(0).rstrip())))
    return found


def _labelled_values(text: str, label_re: re.Pattern[str]) -> list[tuple[int, int]]:
    """Value ranges after a label: the rest of its line, else the next line."""
    lines = _lines(text)
    found: list[tuple[int, int]] = []
    for n, (start, _end, line) in enumerate(lines):
        match = label_re.match(line)
        if match is None:
            continue
        if match.group(1).strip():
            found.append((start + match.start(1), start + len(line.rstrip())))
        elif n + 1 < len(lines):
            nstart, _nend, nline = lines[n + 1]
            # A comma separates place names ("Serbia, Belgrade"); a two-column CV puts the other
            # column's text on the next line, which must not be taken for an address.
            if (
                "," in nline
                and len(nline) <= MAX_VALUE_LINE
                and not any(c.isdigit() for c in nline)
                and not label_re.match(nline)
            ):
                found.append((nstart, nstart + len(nline.rstrip())))
    return found


def _email_parts(email: str | None) -> list[str]:
    if email is None:
        return []
    local = email.split("@", 1)[0]
    parts = [_fold(p) for p in re.split(r"[._+-]", local)]
    return [
        p
        for p in parts
        if len(p) >= MIN_NAME_TOKEN and p.isalpha() and p not in GENERIC_LOCAL_PARTS
    ]


def _name_words(value: str) -> list[str]:
    return _WORD_RE.findall(value)


def _agrees_with_email(words: list[str], email: str | None) -> bool:
    if email is None:
        return True
    local = _fold(re.sub(r"[._+\-\d]", "", email.split("@", 1)[0]))
    return any(len(_fold(w)) >= MIN_NAME_TOKEN and _fold(w) in local for w in words)


def _is_name_word(word: str) -> bool:
    return len(word) >= 2 and (word[0].isupper() and (word[1:].islower() or word.isupper()))


def _name_phrase(text: str, email: str | None) -> list[str]:
    """Words of the person's name, from a labelled line, else from a header line."""
    lines = _lines(text)
    for n, (_s, _e, line) in enumerate(lines):
        match = _NAME_LABEL_RE.match(line)
        if match is None:
            continue
        value = match.group(1)
        if not value.strip() and n + 1 < len(lines):
            value = lines[n + 1][2]
        words = _name_words(value)
        if 1 <= len(words) <= 4:
            return words
    seen = 0
    for _s, _e, line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        seen += 1
        if seen > HEADER_LINES:
            break
        words = stripped.split()
        if (
            2 <= len(words) <= 3
            and all(_WORD_RE.fullmatch(w) and _is_name_word(w) for w in words)
            and _agrees_with_email(words, email)
        ):
            return words
    return []


def _name_tokens(words: list[str], email: str | None) -> list[str]:
    tokens = {_fold(w) for w in words} | set(_email_parts(email))
    # Hyphenated names are matched by their parts too.
    expanded = {part for t in tokens for part in [t, *t.split("-")]}
    return sorted((t for t in expanded if len(t) >= MIN_NAME_TOKEN and t.isalpha()), key=len)


def _name_ranges(text: str, tokens: list[str]) -> list[tuple[int, int]]:
    if not tokens:
        return []
    folded, index = _fold_with_map(text)
    pattern = re.compile(
        r"(?<![^\W_])(?:"
        + "|".join(map(re.escape, sorted(tokens, key=len, reverse=True)))
        + r")(?![^\W_])"
    )
    return [(index[m.start()], index[m.end() - 1] + 1) for m in pattern.finditer(folded)]


def _street_ranges(text: str) -> list[tuple[int, int]]:
    return [(m.start(), m.end()) for m in _STREET_RE.finditer(text)]


def _resolve(
    candidates: list[tuple[int, int, str]],
) -> list[Span]:
    """Earlier start wins, then the longer range; a range overlapping an accepted one is dropped.

    Email and phone are listed before names, so a name token inside an address is already
    covered by the email span and is not masked twice.
    """
    accepted: list[Span] = []
    last_end = -1
    for start, end, placeholder in sorted(candidates, key=lambda c: (c[0], -(c[1] - c[0]))):
        if start >= last_end:
            accepted.append(Span(raw_start=start, raw_end=end, placeholder=placeholder))
            last_end = end
    return accepted


def mask_text(raw_text: str) -> MaskResult:
    emails = _emails(raw_text)
    phones = _phones(raw_text)
    email = raw_text[emails[0][0] : emails[0][1]] if emails else None
    words = _name_phrase(raw_text, email)
    tokens = _name_tokens(words, email)
    addresses = _labelled_values(raw_text, _ADDRESS_LABEL_RE) + _street_ranges(raw_text)

    candidates = (
        [(s, e, EMAIL) for s, e in emails]
        + [(s, e, PHONE) for s, e in phones]
        + [(s, e, ADDRESS) for s, e in addresses]
        + [(s, e, NAME) for s, e in _name_ranges(raw_text, tokens)]
    )
    spans = _resolve(candidates)

    parts: list[str] = []
    cursor = 0
    for span in spans:
        parts.append(raw_text[cursor : span.raw_start])
        parts.append(span.placeholder)
        cursor = span.raw_end
    parts.append(raw_text[cursor:])

    def first(placeholder: str) -> str | None:
        for span in spans:
            if span.placeholder == placeholder:
                return raw_text[span.raw_start : span.raw_end].strip()
        return None

    full_name = " ".join(words) if words else None
    if full_name is None and tokens:
        full_name = " ".join(p.title() for p in _email_parts(email))
    contact = Contact(
        full_name=full_name or None,
        email=first(EMAIL),
        phone=first(PHONE),
        address=first(ADDRESS),
    )
    return MaskResult("".join(parts), spans, contact)


def masked_range_to_raw(spans: list[Span], start: int, end: int) -> tuple[int, int]:
    """Map `masked_text[start:end]` to the raw range it came from.

    A range that touches a placeholder grows to cover the whole raw span the placeholder
    replaced, so the highlighted raw text always contains what the quote meant.
    """
    raw_start: int | None = None
    shift = 0  # masked offset minus raw offset, before the span being looked at
    for span in spans:
        masked_start = span.raw_start + shift
        masked_end = masked_start + len(span.placeholder)
        if raw_start is None:
            if start < masked_start:
                raw_start = start - shift
            elif start < masked_end:
                raw_start = span.raw_start
        if end <= masked_start:
            break
        if end <= masked_end:
            return (raw_start if raw_start is not None else start - shift, span.raw_end)
        shift += len(span.placeholder) - (span.raw_end - span.raw_start)
    if raw_start is None:
        raw_start = start - shift
    return raw_start, end - shift
