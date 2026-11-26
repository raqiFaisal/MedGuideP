from __future__ import annotations

import json

import pytest

from medguide_engine.text.dosage_form import DICTIONARY_PATH, detect_dosage_form, load_forms
from medguide_engine.text.normalize import normalize_text

DATA = json.loads(DICTIONARY_PATH.read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", DATA["cases"], ids=lambda c: c["input"] or "empty")
def test_detect_dosage_form(case: dict[str, str | None]) -> None:
    assert detect_dosage_form(str(case["input"])) == case["expected"]


def test_phrases_are_already_normalized() -> None:
    for entry in DATA["forms"]:
        for phrase in entry["phrases"]:
            assert normalize_text(phrase) == phrase, (entry["code"], phrase)


def test_codes_are_unique() -> None:
    codes = [f.code for f in load_forms()]
    assert len(codes) == len(set(codes))
