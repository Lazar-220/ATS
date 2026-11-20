"""The fenced data block that carries untrusted text to a model (§4.4, channel separation).

The system message declares the content of the block inert. That only holds if the text inside
cannot close the block and continue as instructions, so every closing tag that a reader (or a
model) could take for the real one is broken with a space: `</CV>`, `</cv >`, `< / cv>`, a
newline inside the tag, and look-alike brackets and slashes (fullwidth, small, angle quotation
marks). Nothing else in the text is changed, so a quote that avoids such a string still matches
the CV exactly.
"""

import re


def _chars(*codepoints: int) -> str:
    return "".join(chr(cp) for cp in codepoints)


# Code points, not literal characters, so that the source says what it means:
# Less-than look-alikes: fullwidth, small, single angle quotation mark, CJK and math brackets.
_LT = "<" + _chars(0xFF1C, 0xFE64, 0x2039, 0x3008, 0x27E8, 0x276E, 0x2329, 0x227A)
# Slash look-alikes (fullwidth, fraction, division, big solidus) and the backslash.
_SLASH = "/\\" + _chars(0xFF0F, 0x2044, 0x2215, 0x29F8)
# Whitespace and zero-width characters between the parts of a tag.
_GAP = r"[\s" + _chars(0x200B, 0x200C, 0x200D, 0x200E, 0x200F, 0x2060, 0xFEFF, 0xAD) + "]*"


def _closing(tag: str) -> re.Pattern[str]:
    return re.compile(
        rf"([{_LT}]{_GAP}[{_SLASH}]{_GAP})({re.escape(tag)})(?=[^a-z0-9_-]|$)",
        re.IGNORECASE,
    )


def fence(text: str, tag: str) -> str:
    # A space after the slash breaks the tag, as the first version did for `</cv>`.
    safe = _closing(tag).sub(lambda m: f"{m.group(1)} {m.group(2)}", text)
    return f"<{tag}>\n{safe}\n</{tag}>"
