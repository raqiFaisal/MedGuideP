"""Text normalization shared by the data pipeline and the recognition engine.

The exact same rules are implemented in TypeScript in
``mobile/src/text/normalize.ts``. Both implementations are checked against
``shared/fixtures/text_normalization.json``. Change the two together.
"""

from __future__ import annotations

import re

_DIGITS: dict[str, str] = {}
for _i in range(10):
    _DIGITS[chr(0x0660 + _i)] = str(_i)  # Arabic-Indic ٠-٩
    _DIGITS[chr(0x06F0 + _i)] = str(_i)  # Extended Arabic-Indic ۰-۹

_LETTER_MAP: dict[str, str] = {
    "أ": "ا",  # أ -> ا
    "إ": "ا",  # إ -> ا
    "آ": "ا",  # آ -> ا
    "ٱ": "ا",  # ٱ -> ا
    "ى": "ي",  # ى -> ي
    "ی": "ي",  # ی (Farsi yeh) -> ي
    "ک": "ك",  # ک (keheh) -> ك
    "ة": "ه",  # ة -> ه
    "ؤ": "و",  # ؤ -> و
    "ئ": "ي",  # ئ -> ي
    "ء": "",  # ء removed
    "٫": ".",  # ٫ Arabic decimal separator
    "٬": "",  # ٬ Arabic thousands separator
    "ـ": "",  # ـ tatweel
}

_TASHKEEL = re.compile("[ً-ٰٟ]")
_WHITESPACE = re.compile(r"\s+")
_DIGIT_LETTER = re.compile("([0-9])([A-Zء-ي])")
_LETTER_DIGIT = re.compile("([A-Zء-ي])([0-9])")


def _is_kept(ch: str) -> bool:
    return ("A" <= ch <= "Z") or ("0" <= ch <= "9") or ("ء" <= ch <= "ي") or ch == " "


def normalize_arabic(text: str) -> str:
    """Remove diacritics/tatweel, unify letter variants, convert digits, collapse spaces."""
    text = _TASHKEEL.sub("", text)
    out = []
    for ch in text:
        if ch in _DIGITS:
            out.append(_DIGITS[ch])
        elif ch in _LETTER_MAP:
            out.append(_LETTER_MAP[ch])
        else:
            out.append(ch)
    return _WHITESPACE.sub(" ", "".join(out)).strip()


def normalize_text(text: str) -> str:
    """Full normalization for matching: Arabic rules, uppercase Latin, strip symbols,
    keep decimal points between digits, split digits from letters."""
    text = normalize_arabic(text).upper()
    text = text.replace("µ", "MC").replace("μ", "MC").replace("Μ", "MC")
    chars: list[str] = []
    n = len(text)
    for i, ch in enumerate(text):
        if ch == ".":
            prev_digit = i > 0 and text[i - 1].isascii() and text[i - 1].isdigit()
            next_digit = i + 1 < n and text[i + 1].isascii() and text[i + 1].isdigit()
            chars.append("." if prev_digit and next_digit else " ")
        elif _is_kept(ch):
            chars.append(ch)
        else:
            chars.append(" ")
    text = "".join(chars)
    text = _DIGIT_LETTER.sub(r"\1 \2", text)
    text = _LETTER_DIGIT.sub(r"\1 \2", text)
    return _WHITESPACE.sub(" ", text).strip()
