from __future__ import annotations

import json
from pathlib import Path

import httpx

from adapters.rxnorm import (
    RxNavClient,
    clean_ingredient_name,
    map_all,
    split_ingredients,
)

# Responses shaped exactly like real RxNav replies observed on 2026-11-21.
FAKE: dict[str, dict[str, object]] = {
    "/REST/rxcui.json?name=paracetamol&search=2": {"idGroup": {"rxnormId": ["161"]}},
    "/REST/rxcui/161/properties.json": {"properties": {"rxcui": "161", "name": "acetaminophen", "tty": "IN"}},
    "/REST/rxcui.json?name=nonsense%20xyz&search=2": {"idGroup": {}},
    "/REST/rxcui.json?name=twin&search=2": {"idGroup": {"rxnormId": ["1", "2"]}},
    "/REST/rxcui.json?name=panadol&search=2": {"idGroup": {"rxnormId": ["202433"]}},
    "/REST/rxcui/202433/properties.json": {"properties": {"rxcui": "202433", "name": "Panadol", "tty": "BN"}},
}


def make_client(calls: list[str]) -> RxNavClient:
    def handler(request: httpx.Request) -> httpx.Response:
        key = request.url.raw_path.decode()
        calls.append(key)
        if key not in FAKE:
            return httpx.Response(404)
        return httpx.Response(200, json=FAKE[key])

    http = httpx.Client(base_url="https://rxnav.nlm.nih.gov/REST", transport=httpx.MockTransport(handler))
    return RxNavClient(http, min_interval_s=0)


def test_clean_and_split() -> None:
    assert split_ingredients("chlorpheniramine+paracetamol+ pseudoephedrine") == [
        "chlorpheniramine",
        "paracetamol",
        "pseudoephedrine",
    ]
    assert clean_ingredient_name("  Cobalamin(B12) ") == "cobalamin"
    assert clean_ingredient_name("Folic  Acid (b9)") == "folic acid"


def test_lookup_mapped_synonym() -> None:
    r = make_client([]).lookup("paracetamol")
    assert (r.status, r.rxcui, r.name, r.tty) == ("mapped", "161", "acetaminophen", "IN")


def test_lookup_not_found_and_ambiguous() -> None:
    client = make_client([])
    assert client.lookup("nonsense xyz").status == "not_found"
    amb = client.lookup("twin")
    assert amb.status == "ambiguous" and amb.candidates == ("1", "2") and amb.rxcui is None


def test_brand_name_is_not_accepted_as_ingredient() -> None:
    assert make_client([]).lookup("panadol").status == "not_ingredient"


def test_map_all_resumes_from_cache(tmp_path: Path) -> None:
    cache_path = tmp_path / "cache.json"
    cache_path.write_text(json.dumps({"paracetamol": {"query": "paracetamol", "status": "mapped"}}), encoding="utf-8")
    calls: list[str] = []
    result = map_all(["paracetamol", "nonsense xyz"], make_client(calls), cache_path)
    assert calls == ["/REST/rxcui.json?name=nonsense%20xyz&search=2"]  # cached entry not re-requested
    assert result["nonsense xyz"]["status"] == "not_found"
    assert json.loads(cache_path.read_text(encoding="utf-8")).keys() == {"paracetamol", "nonsense xyz"}
