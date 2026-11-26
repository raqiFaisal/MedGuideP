"""Dosage-form detection from free text using shared/dictionaries/dosage_forms.json.

The TypeScript mirror (mobile/src/text/dosageForm.ts) reads the same JSON file,
so both sides always use identical rules.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from medguide_engine.text.normalize import normalize_text

DICTIONARY_PATH = Path(__file__).resolve().parents[3] / "shared" / "dictionaries" / "dosage_forms.json"


@dataclass(frozen=True)
class DosageForm:
    code: str
    label_ar: str
    label_en: str
    pattern: re.Pattern[str]


@lru_cache(maxsize=1)
def load_forms() -> tuple[DosageForm, ...]:
    data = json.loads(DICTIONARY_PATH.read_text(encoding="utf-8"))
    forms = []
    for entry in data["forms"]:
        # Longest phrases first so "F C TABS" is preferred over "F C" inside one rule.
        phrases = sorted(entry["phrases"], key=len, reverse=True)
        alternation = "|".join(re.escape(p) for p in phrases)
        pattern = re.compile(f"(?:^| )(?:{alternation})(?= |$)")
        forms.append(DosageForm(entry["code"], entry["label_ar"], entry["label_en"], pattern))
    return tuple(forms)


def detect_dosage_form(text: str) -> str | None:
    """Return the canonical dosage-form code, or None if no rule matches."""
    normalized = normalize_text(text)
    for form in load_forms():
        if form.pattern.search(normalized):
            return form.code
    return None
