from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx

from adapters.openfda import (
    OpenFdaClient,
    choose_label,
    extract_sections,
    fetch_all,
    ingredients_from_rxnorm_cache,
    read_api_key,
)

SECRET = "test-key-not-real"


def label(set_id: str, substances: list[str], ptype: str, eff: str, **sections: list[str]) -> dict[str, Any]:
    return {
        "set_id": set_id,
        "effective_time": eff,
        "openfda": {"substance_name": substances, "product_type": [ptype], "generic_name": [" AND ".join(substances)]},
        **sections,
    }


def test_choose_label_prefers_single_rx_recent() -> None:
    labels = [
        label("combo", ["A", "B"], "HUMAN PRESCRIPTION DRUG", "20260101"),
        label("otc-new", ["A"], "HUMAN OTC DRUG", "20260601"),
        label("rx-old", ["A"], "HUMAN PRESCRIPTION DRUG", "20200101"),
        label("rx-new", ["A"], "HUMAN PRESCRIPTION DRUG", "20250101"),
    ]
    chosen = choose_label(labels)
    assert chosen is not None and chosen["set_id"] == "rx-new"
    assert choose_label([labels[0]]) is None


def test_extract_sections_verbatim_and_no_dosage() -> None:
    lab = label(
        "x",
        ["A"],
        "HUMAN PRESCRIPTION DRUG",
        "2026",
        indications_and_usage=["  Use for X.  "],
        warnings_and_cautions=["W1"],
        warnings=["older warnings field"],
        dosage_and_administration=["Take 500 mg"],
    )
    sections = extract_sections(lab)
    assert sections == {"indications": "Use for X.", "warnings": "W1"}
    assert "Take 500 mg" not in json.dumps(sections)


def test_key_sent_in_header_never_in_url(tmp_path: Path) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if "generic_name.exact" in str(request.url):
            return httpx.Response(404, json={"error": {"code": "NOT_FOUND"}})
        return httpx.Response(
            200, json={"results": [label("s1", ["AMLODIPINE BESYLATE"], "HUMAN PRESCRIPTION DRUG", "2026", contraindications=["C"])]}
        )

    http = httpx.Client(base_url="https://api.fda.gov", transport=httpx.MockTransport(handler))
    result = OpenFdaClient(SECRET, http, min_interval_s=0).label_for_ingredient("17767", "amlodipine")
    assert result.status == "found" and result.set_id == "s1"
    assert result.sections == {"contraindications": "C"}
    assert result.dailymed_url is not None and result.dailymed_url.endswith("setid=s1")
    assert len(seen) == 2
    for req in seen:
        assert SECRET not in str(req.url)
        assert req.headers["authorization"].startswith("Basic ")


def test_no_label_found() -> None:
    http = httpx.Client(base_url="https://api.fda.gov", transport=httpx.MockTransport(lambda r: httpx.Response(404)))
    result = OpenFdaClient(SECRET, http, min_interval_s=0).label_for_ingredient("1", "nothing")
    assert result.status == "no_single_ingredient_label" and result.sections == {}


def test_error_message_does_not_leak_key() -> None:
    http = httpx.Client(base_url="https://api.fda.gov", transport=httpx.MockTransport(lambda r: httpx.Response(403)))
    try:
        OpenFdaClient(SECRET, http, min_interval_s=0).search_labels('x:"y"', 1)
    except RuntimeError as err:
        assert SECRET not in str(err) and "403" in str(err)
    else:
        raise AssertionError("expected RuntimeError")


def test_read_api_key_and_ingredient_selection(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.delenv("OPENFDA_API_KEY", raising=False)
    env = tmp_path / ".env"
    env.write_text("OTHER=1\nOPENFDA_API_KEY= abc123 \n", encoding="utf-8")
    assert read_api_key(env) == "abc123"

    cache = tmp_path / "rx.json"
    cache.write_text(
        json.dumps(
            {
                "paracetamol": {"status": "mapped", "rxcui": "161", "name": "acetaminophen", "tty": "IN"},
                "combo": {"status": "mapped", "rxcui": "9", "name": "a / b", "tty": "MIN"},
                "olive oil": {"status": "not_found"},
            }
        ),
        encoding="utf-8",
    )
    assert ingredients_from_rxnorm_cache(cache) == {"161": "acetaminophen"}


def test_fetch_all_is_resumable(tmp_path: Path) -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(404)

    out = tmp_path / "ofda"
    out.mkdir()
    (out / "161.json").write_text(json.dumps({"status": "found"}), encoding="utf-8")
    http = httpx.Client(base_url="https://api.fda.gov", transport=httpx.MockTransport(handler))
    counts = fetch_all({"161": "acetaminophen", "2": "other"}, OpenFdaClient(SECRET, http, min_interval_s=0), out)
    assert counts == {"found": 1, "no_single_ingredient_label": 1}
    assert all("acetaminophen" not in c.lower() for c in calls)  # cached one not re-requested
