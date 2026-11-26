from __future__ import annotations

import pytest

from medguide_engine.text.normalize import normalize_arabic, normalize_text
from tests.conftest import load_fixture

CASES = load_fixture("text_normalization.json")


@pytest.mark.parametrize("case", CASES["normalize_arabic"], ids=lambda c: c["rule"])
def test_normalize_arabic(case: dict[str, str]) -> None:
    assert normalize_arabic(case["input"]) == case["expected"]


@pytest.mark.parametrize("case", CASES["normalize_text"], ids=lambda c: c["rule"])
def test_normalize_text(case: dict[str, str]) -> None:
    assert normalize_text(case["input"]) == case["expected"]


def test_normalize_text_is_idempotent() -> None:
    for group in ("normalize_arabic", "normalize_text"):
        for case in CASES[group]:
            once = normalize_text(case["input"])
            assert normalize_text(once) == once
