from __future__ import annotations

import pytest

from medguide_engine.text.strength import parse_strength, strengths_equivalent
from tests.conftest import load_fixture

CASES = load_fixture("strength.json")


@pytest.mark.parametrize("case", CASES["parse"], ids=lambda c: c["input"] or "empty")
def test_parse_strength(case: dict[str, str]) -> None:
    assert parse_strength(case["input"]) == case["expected"]


@pytest.mark.parametrize("case", CASES["equivalent"], ids=lambda c: f"{c['a']}~{c['b']}")
def test_strengths_equivalent(case: dict[str, object]) -> None:
    assert strengths_equivalent(str(case["a"]), str(case["b"])) is case["expected"]
    assert strengths_equivalent(str(case["b"]), str(case["a"])) is case["expected"]


def test_parse_is_stable_on_its_own_output() -> None:
    for case in CASES["parse"]:
        once = parse_strength(case["input"])
        assert parse_strength(once) == once
