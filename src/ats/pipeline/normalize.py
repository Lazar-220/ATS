"""Text normalization for comparison and lexical search only.

Embeddings and quotes use the original text (§2.2); the stored `raw_text` is never replaced by
the output of this module.
"""

import unicodedata
from typing import cast

import cyrtranslit  # pyright: ignore[reportMissingTypeStubs]


def _to_latin(text: str) -> str:
    return cast(str, cyrtranslit.to_latin(text, "sr"))  # pyright: ignore[reportUnknownMemberType]


def normalize_for_lexical(text: str) -> str:
    """Cyrillic to Latin, lowercase, `đ` to `dj`, diacritics stripped.

    "вођење", "vođenje" and "vodjenje" all become "vodjenje".
    """
    text = _to_latin(text).lower().replace("đ", "dj")
    # NFKD splits a letter from its accent so the accent can be dropped (š, č, ć, ž).
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(char for char in decomposed if not unicodedata.combining(char))
