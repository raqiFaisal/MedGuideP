from __future__ import annotations

import pytest

from medguide_engine.text.gtin import gs1_check_digit, is_valid_gtin, to_gtin14
from tests.conftest import load_fixture

CASES = load_fixture("gtin.json")["cases"]


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["note"])
def test_is_valid_gtin(case: dict[str, object]) -> None:
    assert is_valid_gtin(str(case["input"])) is case["valid"]


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["note"])
def test_to_gtin14(case: dict[str, object]) -> None:
    assert to_gtin14(str(case["input"])) == case["gtin14"]


def test_check_digit_examples() -> None:
    assert gs1_check_digit("400638133393") == 1
    assert gs1_check_digit("03600029145") == 2
