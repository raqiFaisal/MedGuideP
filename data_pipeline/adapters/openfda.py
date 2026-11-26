"""openFDA drug-label adapter: ingredient-level label sections (build time only).

Terms (verified 2026-11-21, docs/LICENSES.md): openFDA data is CC0; with a free key
240 requests/minute and 120,000/day. The key is read from ``.env`` (OPENFDA_API_KEY)
and sent with HTTP Basic auth, so it never appears in a URL, log or error message.

Rules from CLAUDE.md §4.د and §8:
- A US label is general information about the ACTIVE INGREDIENT, never presented as
  the leaflet of an Arab product. The app shows it under its own heading with source,
  effective date and the DailyMed link.
- Text is stored verbatim. Dosage sections are NOT fetched (no dose numbers in the app).
- Only single-ingredient labels are used for an ingredient.

Usage:
    python -m adapters.openfda ../data/processed/rxnorm_cache.json ../data/processed/openfda
"""

from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import httpx

BASE_URL = "https://api.fda.gov"
MIN_INTERVAL_S = 0.26  # 240 requests/minute
DAILYMED_SETID_URL = "https://dailymed.nlm.nih.gov/dailymed/lookup.cfm?setid={set_id}"

# openFDA label field -> our section code (schema: ingredient_monographs.section).
SECTION_FIELDS: dict[str, str] = {
    "indications_and_usage": "indications",
    "contraindications": "contraindications",
    "boxed_warning": "boxed_warning",
    "warnings_and_cautions": "warnings",
    "warnings": "warnings",
    "pregnancy": "pregnancy",
    "pediatric_use": "pediatric",
    "geriatric_use": "geriatric",
    "adverse_reactions": "adverse_reactions",
    "drug_interactions": "interactions",
    "storage_and_handling": "storage",
}
PRODUCT_TYPE_PREFERENCE = ("HUMAN PRESCRIPTION DRUG", "HUMAN OTC DRUG")


@dataclass
class IngredientLabel:
    rxcui: str
    ingredient: str
    status: str  # 'found' | 'no_single_ingredient_label'
    set_id: str | None = None
    effective_time: str | None = None
    product_type: str | None = None
    generic_name: str | None = None
    dailymed_url: str | None = None
    sections: dict[str, str] = field(default_factory=dict)


def read_api_key(env_path: Path) -> str:
    key = os.environ.get("OPENFDA_API_KEY", "").strip()
    if not key and env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            name, _, value = line.partition("=")
            if name.strip() == "OPENFDA_API_KEY":
                key = value.strip()
    if not key:
        raise SystemExit("OPENFDA_API_KEY not found in environment or .env")
    return key


def is_single_ingredient(label: dict[str, Any]) -> bool:
    substances = label.get("openfda", {}).get("substance_name", [])
    return isinstance(substances, list) and len(substances) == 1


def choose_label(labels: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Single-ingredient label; prescription before OTC; then most recent effective_time."""
    singles = [lab for lab in labels if is_single_ingredient(lab)]

    def rank(lab: dict[str, Any]) -> tuple[int, str]:
        ptype = (lab.get("openfda", {}).get("product_type") or [""])[0]
        pref = PRODUCT_TYPE_PREFERENCE.index(ptype) if ptype in PRODUCT_TYPE_PREFERENCE else len(PRODUCT_TYPE_PREFERENCE)
        return pref, "".join(chr(255 - ord(c)) for c in str(lab.get("effective_time", "")))

    return min(singles, key=rank) if singles else None


def extract_sections(label: dict[str, Any]) -> dict[str, str]:
    sections: dict[str, str] = {}
    for fld, code in SECTION_FIELDS.items():
        value = label.get(fld)
        if isinstance(value, list) and value and code not in sections:
            text = "\n\n".join(str(v).strip() for v in value if str(v).strip())
            if text:
                sections[code] = text
    return sections


class OpenFdaClient:
    def __init__(self, api_key: str, client: httpx.Client | None = None, min_interval_s: float = MIN_INTERVAL_S) -> None:
        self._client = client or httpx.Client(base_url=BASE_URL, timeout=120.0)
        self._auth = httpx.BasicAuth(api_key, "")
        self._min_interval = min_interval_s
        self._last = 0.0

    def search_labels(self, search: str, limit: int) -> list[dict[str, Any]]:
        params = {"search": search, "limit": str(limit), "sort": "effective_time:desc"}
        for attempt in range(5):
            wait = self._min_interval - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()
            try:
                res = self._client.get("/drug/label.json", params=params, auth=self._auth)
            except httpx.TransportError:
                if attempt == 4:
                    raise RuntimeError("openFDA unreachable after retries") from None
                time.sleep(2**attempt)
                continue
            if res.status_code == 404:  # openFDA answers 404 when nothing matches
                return []
            if res.status_code == 429 or res.status_code >= 500:
                time.sleep(2**attempt * 5)
                continue
            if res.status_code != 200:
                raise RuntimeError(f"openFDA HTTP {res.status_code}")  # no URL: it is safe to log
            results = res.json().get("results", [])
            return list(results) if isinstance(results, list) else []
        raise RuntimeError("openFDA kept failing after retries")

    def label_for_ingredient(self, rxcui: str, ingredient: str) -> IngredientLabel:
        name = ingredient.upper().replace('"', "")
        searches = [
            (f'openfda.generic_name.exact:"{name}"', 3),  # exact = single-ingredient name
            (f'openfda.substance_name:"{name}"', 10),  # salts, e.g. AMLODIPINE BESYLATE
        ]
        for search, limit in searches:
            label = choose_label(self.search_labels(search, limit))
            if label is not None:
                ofda = label.get("openfda", {})
                set_id = str(label.get("set_id", "")) or None
                return IngredientLabel(
                    rxcui=rxcui,
                    ingredient=ingredient,
                    status="found",
                    set_id=set_id,
                    effective_time=str(label.get("effective_time", "")) or None,
                    product_type=(ofda.get("product_type") or [None])[0],
                    generic_name=(ofda.get("generic_name") or [None])[0],
                    dailymed_url=DAILYMED_SETID_URL.format(set_id=set_id) if set_id else None,
                    sections=extract_sections(label),
                )
        return IngredientLabel(rxcui=rxcui, ingredient=ingredient, status="no_single_ingredient_label")


def ingredients_from_rxnorm_cache(cache_path: Path) -> dict[str, str]:
    """rxcui -> RxNorm ingredient name, for mapped single ingredients (IN/PIN)."""
    cache: dict[str, dict[str, Any]] = json.loads(cache_path.read_text(encoding="utf-8"))
    out: dict[str, str] = {}
    for entry in cache.values():
        if entry.get("status") == "mapped" and entry.get("tty") in ("IN", "PIN") and entry.get("rxcui"):
            out[str(entry["rxcui"])] = str(entry["name"])
    return out


def fetch_all(ingredients: dict[str, str], client: OpenFdaClient, out_dir: Path) -> dict[str, int]:
    out_dir.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    for i, (rxcui, name) in enumerate(sorted(ingredients.items()), 1):
        target = out_dir / f"{rxcui}.json"
        if target.exists():
            status = json.loads(target.read_text(encoding="utf-8"))["status"]
        else:
            result = client.label_for_ingredient(rxcui, name)
            tmp = target.with_suffix(".tmp")
            tmp.write_text(json.dumps(asdict(result), ensure_ascii=False, indent=1), encoding="utf-8")
            tmp.replace(target)
            status = result.status
        counts[status] = counts.get(status, 0) + 1
        if i % 25 == 0:
            print(f"{i}/{len(ingredients)} {counts}", flush=True)
    return counts


def main(argv: list[str]) -> int:
    cache_path, out_dir = Path(argv[1]), Path(argv[2])
    repo_root = Path(__file__).resolve().parents[2]
    client = OpenFdaClient(read_api_key(repo_root / ".env"))
    ingredients = ingredients_from_rxnorm_cache(cache_path)
    print(f"ingredients to fetch: {len(ingredients)}", flush=True)
    counts = fetch_all(ingredients, client, out_dir)
    print(json.dumps({"total": len(ingredients), **counts}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
