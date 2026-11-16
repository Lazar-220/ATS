import pytest

from ats.pipeline.language import Lang, Script, detect_language, detect_script
from ats.pipeline.normalize import normalize_for_lexical

SERBIAN_LATIN = (
    "Vođenje tima od osam ljudi u banci. Magistar ekonomije, Univerzitet u Beogradu. "
    "Znanje: Python, SQL, upravljanje projektima."
)
SERBIAN_CYRILLIC = (
    "Вођење тима од осам људи у банци. Магистар економије, Универзитет у Београду. "
    "Знање: Python, SQL, управљање пројектима."
)
ENGLISH = (
    "Led a team of eight people at a bank. Master of Economics, University of Belgrade. "
    "Skills: Python, SQL, project management."
)


@pytest.mark.parametrize(
    ("text", "lang", "script"),
    [
        (SERBIAN_LATIN, "sr", "latin"),
        (SERBIAN_CYRILLIC, "sr", "cyrillic"),
        (ENGLISH, "en", "latin"),
        # Without diacritics the detector still lands in the Serbo-Croatian class.
        ("Vodjenje tima od osam ljudi u banci. Magistar ekonomije, Beograd.", "sr", "latin"),
    ],
)
def test_language_and_script(text: str, lang: Lang, script: Script) -> None:
    assert detect_language(text) == lang
    assert detect_script(text) == script


def test_serbian_latin_is_not_reported_as_a_separate_language() -> None:
    # The detector says Bosnian or Croatian for this text (§4.2); the class hides that.
    assert detect_language(SERBIAN_LATIN) == "sr"


def test_text_without_letters_is_unknown() -> None:
    assert detect_language("12345 +381 11 222 333") == "unknown"
    assert detect_script("12345 +381 11 222 333") == "unknown"


def test_a_few_latin_words_do_not_make_a_cyrillic_text_mixed() -> None:
    assert detect_script(SERBIAN_CYRILLIC) == "cyrillic"


def test_comparable_shares_of_both_scripts_are_mixed() -> None:
    assert detect_script("Искуство рада: Senior developer у Београду, Python backend") == "mixed"


def test_lexical_normalization_maps_the_three_spellings_to_one_string() -> None:
    forms = {normalize_for_lexical(word) for word in ("вођење", "vođenje", "vodjenje")}
    assert forms == {"vodjenje"}


def test_lexical_normalization_strips_diacritics_and_case() -> None:
    assert normalize_for_lexical("ŠĆČŽ Đorđe") == "sccz djordje"
    assert normalize_for_lexical("Ђорђе Љубиша Џон") == "djordje ljubisa dzon"


def test_normalization_leaves_the_input_untouched() -> None:
    original = "Вођење"
    normalize_for_lexical(original)
    assert original == "Вођење"
