"""Language and script of a document (§4.2).

Serbian, Croatian and Bosnian are one class: the detector labels Serbian Latin as Bosnian or
Croatian, and the pipeline treats all three the same. The script is read from Unicode ranges,
not from the detector, because the language alone does not tell Latin from Cyrillic.
"""

from functools import lru_cache
from typing import Literal

from lingua import Language, LanguageDetector, LanguageDetectorBuilder

type Lang = Literal["sr", "en", "unknown"]
type Script = Literal["latin", "cyrillic", "mixed", "unknown"]

# The minority script must reach this share of the letters for a text to count as mixed, so a
# Cyrillic CV with a few Latin product names stays Cyrillic.
MIXED_SCRIPT_SHARE = 0.10

_SERBO_CROATIAN = (Language.SERBIAN, Language.CROATIAN, Language.BOSNIAN)


@lru_cache
def _detector() -> LanguageDetector:
    # Built lazily: it loads language models, which only the worker needs.
    return LanguageDetectorBuilder.from_languages(*_SERBO_CROATIAN, Language.ENGLISH).build()


def detect_language(text: str) -> Lang:
    confidence = {c.language: c.value for c in _detector().compute_language_confidence_values(text)}
    serbo_croatian = sum(confidence.get(language, 0.0) for language in _SERBO_CROATIAN)
    english = confidence.get(Language.ENGLISH, 0.0)
    if serbo_croatian == 0 and english == 0:
        return "unknown"
    return "sr" if serbo_croatian >= english else "en"


def _is_cyrillic(char: str) -> bool:
    return "Ѐ" <= char <= "ԯ"


def _is_latin(char: str) -> bool:
    # Basic Latin, Latin-1 and Latin Extended A/B cover Serbian, Croatian and English letters.
    return char.isalpha() and ord(char) < 0x250


def detect_script(text: str) -> Script:
    cyrillic = sum(_is_cyrillic(c) for c in text)
    latin = sum(_is_latin(c) for c in text)
    letters = cyrillic + latin
    if letters == 0:
        return "unknown"
    if min(cyrillic, latin) / letters >= MIXED_SCRIPT_SHARE:
        return "mixed"
    return "cyrillic" if cyrillic > latin else "latin"
