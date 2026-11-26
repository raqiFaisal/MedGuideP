"""Strength parsing and comparison (mg, g, mcg, ml, IU, %, ratios, combinations).

Mirrored in ``mobile/src/text/strength.ts``; both are tested against
``shared/fixtures/strength.json``. Change them together.
"""

from __future__ import annotations

import re
from math import isfinite
from dataclasses import dataclass

from medguide_engine.text.normalize import normalize_arabic

# Unit spellings -> canonical unit. Arabic forms are written as they look AFTER
# normalize_arabic (e.g. ة -> ه). Order matters: longer spellings first.
_UNIT_ALIASES: list[tuple[str, str]] = [
    ("ميكروغرام", "MCG"),
    ("ميكروجرام", "MCG"),
    ("مكجم", "MCG"),
    ("مكغ", "MCG"),
    ("ملجم", "MG"),
    ("ملغ", "MG"),
    ("مجم", "MG"),
    ("مغ", "MG"),
    ("غرام", "G"),
    ("جرام", "G"),
    ("جم", "G"),
    ("غم", "G"),
    ("مليلتر", "ML"),
    ("ملل", "ML"),
    ("مل", "ML"),
    ("وحده دوليه", "IU"),
    ("٪", "%"),
    ("I.U.", "IU"),
    ("MCG", "MCG"),
    ("UG", "MCG"),
    ("MG", "MG"),
    ("GM", "G"),
    ("ML", "ML"),
    ("IU", "IU"),
    ("G", "G"),
    ("%", "%"),
]
_UNIT_LOOKUP = dict(_UNIT_ALIASES)
_UNIT_PATTERN = "|".join(re.escape(alias) for alias, _ in _UNIT_ALIASES)
_NUM = r"(\d+(?:\.\d+)?)"
_NOT_LETTER = "(?![A-Zء-ي])"
_AMOUNT = re.compile(
    rf"{_NUM}\s*({_UNIT_PATTERN}){_NOT_LETTER}"
    rf"(?:\s*/\s*{_NUM}?\s*({_UNIT_PATTERN}){_NOT_LETTER})?"
)
_THOUSANDS = re.compile(r"(\d),(\d{3})(?!\d)")
_DECIMAL_COMMA = re.compile(r"(\d),(\d)")

_MASS_TO_MG = {"MG": 1.0, "G": 1000.0, "MCG": 0.001}
_VOLUME_OR_MASS_DENOMINATOR = {"ML", "G"}


@dataclass(frozen=True)
class StrengthComponent:
    value: str
    unit: str
    per_value: str | None = None
    per_unit: str | None = None

    def text(self) -> str:
        base = f"{self.value} {self.unit}"
        if self.per_unit is None:
            return base
        per = f"{self.per_value} {self.per_unit}" if self.per_value else self.per_unit
        return f"{base}/{per}"


def _clean_number(num: str) -> str:
    if "." in num:
        num = num.rstrip("0").rstrip(".")
    return num


def _prepare(text: str) -> str:
    text = normalize_arabic(text).upper()
    text = text.replace("µ", "MC").replace("μ", "MC").replace("Μ", "MC")
    text = _THOUSANDS.sub(r"\1\2", text)
    return _DECIMAL_COMMA.sub(r"\1.\2", text)


def parse_components(text: str) -> list[StrengthComponent]:
    components: list[StrengthComponent] = []
    for m in _AMOUNT.finditer(_prepare(text)):
        value = _clean_number(m.group(1))
        unit = _UNIT_LOOKUP[m.group(2)]
        per_value = _clean_number(m.group(3)) if m.group(3) else None
        per_unit = _UNIT_LOOKUP[m.group(4)] if m.group(4) else None
        if per_unit is not None and per_unit not in _VOLUME_OR_MASS_DENOMINATOR:
            # "500mg/125mg": two ingredients, not a concentration.
            components.append(StrengthComponent(value, unit))
            if per_value is not None:
                components.append(StrengthComponent(per_value, per_unit))
            continue
        if per_unit is None and unit == "ML":
            continue  # a standalone volume is a pack size, not a strength
        components.append(StrengthComponent(value, unit, per_value, per_unit))
    return components


def parse_strength(text: str) -> str:
    """Normalized strength string, e.g. '250 MG/5 ML' or '500 MG + 125 MG'; '' if none."""
    return " + ".join(c.text() for c in parse_components(text))


def _key(c: StrengthComponent) -> tuple[str, float]:
    value = float(c.value)
    if c.per_unit is not None:
        per = float(c.per_value) if c.per_value else 1.0
        num = value * _MASS_TO_MG.get(c.unit, 1.0)
        kind = "conc_" + (c.unit if c.unit not in _MASS_TO_MG else "mass") + "_" + c.per_unit
        return kind, num / per if per > 0 else float("inf")
    if c.unit in _MASS_TO_MG:
        return "mass", value * _MASS_TO_MG[c.unit]
    return c.unit, value


def strengths_equivalent(a: str, b: str) -> bool:
    """True if both strengths describe the same amounts (unit-converted, order-insensitive)."""
    ka = sorted(_key(c) for c in parse_components(a))
    kb = sorted(_key(c) for c in parse_components(b))
    if not ka or len(ka) != len(kb):
        return False
    for (kind_a, va), (kind_b, vb) in zip(ka, kb):
        if kind_a != kind_b or not (isfinite(va) and isfinite(vb)) or abs(va - vb) > 1e-9 * max(1.0, abs(va), abs(vb)):
            return False
    return True
