"""Invisible characters and homoglyph words in CV text (§4.4, Unicode layer).

Categories Cf (format: zero-width, bidi controls, tag characters, soft hyphen), Co (private use,
icon fonts) and Cn (unassigned) carry no text a reader sees, so they are deleted. That also
removes a zero-width joiner inside an emoji sequence; the emoji then renders as separate symbols,
which a CV score does not depend on. Control characters (Cc) go too, except newline, tab
and carriage return.

A word that mixes Cyrillic and Latin letters is a homoglyph signal (a Latin "o" inside a Cyrillic
word): it is reported, never altered, because Serbian text legitimately sits next to Latin
product names.
"""

import re
import unicodedata
from dataclasses import dataclass

_REMOVED = {"Cf", "Co", "Cn"}
# Other control characters are not text either, and NUL cannot be stored in Postgres: an
# unmapped tag character comes out of PyMuPDF as NUL.
_KEPT_CONTROLS = {"\n", "\t", "\r"}
_WORD = re.compile(r"[^\W\d_]+")
_CYRILLIC = re.compile(r"[Ѐ-ԯᲀ-᲏ⷠ-ⷿꙀ-ꚟ]")
_LATIN = re.compile(r"[A-Za-zÀ-ɏḀ-ỿ]")

MIXED_SCRIPT = "mixed_script_words"
INVISIBLE_CHARACTERS = "invisible_characters"


def _is_removed(char: str) -> bool:
    category = unicodedata.category(char)
    return category in _REMOVED or (category == "Cc" and char not in _KEPT_CONTROLS)


def remove_invisible(text: str) -> tuple[str, int]:
    """The text without Cf, Co, Cn and stray control characters, and how many were removed."""
    kept = [char for char in text if not _is_removed(char)]
    return "".join(kept), len(text) - len(kept)


@dataclass(frozen=True)
class MixedWords:
    count: int
    examples: tuple[str, ...]


def mixed_script_words(text: str) -> MixedWords:
    found = [word for word in _WORD.findall(text) if _CYRILLIC.search(word) and _LATIN.search(word)]
    return MixedWords(len(found), tuple(dict.fromkeys(found))[:5])
