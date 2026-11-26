"""RxNorm ingredient mapping through the public RxNav REST API (build time only).

Terms (verified 2026-11-21, see docs/LICENSES.md): NLM-created RxNorm names and
RxCUIs are public domain; at most 20 requests/second per IP; attribution required.

Only EXACT normalized matches are accepted (``search=2``). Approximate matching is
never used, so an ingredient is either mapped to a real RxCUI or left unmapped.
Results are cached on disk so the run can be stopped and resumed.

Usage:
    python -m adapters.rxnorm ../data/raw/eg-drugs/eg_drugs.csv ../data/processed/rxnorm_cache.json
"""

from __future__ import annotations

import csv
import json
import re
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal
from urllib.parse import quote

import httpx

BASE_URL = "https://rxnav.nlm.nih.gov/REST"
ACCEPTED_TTY = {"IN", "PIN", "MIN"}  # ingredient, precise ingredient, multiple ingredients
MIN_INTERVAL_S = 0.06  # stays under 20 requests/second

Status = Literal["mapped", "not_found", "ambiguous", "not_ingredient"]


@dataclass(frozen=True)
class RxNormResult:
    query: str
    status: Status
    rxcui: str | None = None
    name: str | None = None
    tty: str | None = None
    candidates: tuple[str, ...] = ()


_PARENS = re.compile(r"\([^)]*\)")
_SPACES = re.compile(r"\s+")


def clean_ingredient_name(raw: str) -> str:
    """Lowercase, drop parenthetical notes like '(b12)', collapse whitespace."""
    return _SPACES.sub(" ", _PARENS.sub(" ", raw.lower())).strip()


def split_ingredients(active: str) -> list[str]:
    """eg-drugs joins ingredients with '+'."""
    return [p.strip() for p in active.split("+") if p.strip()]


class RxNavClient:
    def __init__(self, client: httpx.Client | None = None, min_interval_s: float = MIN_INTERVAL_S) -> None:
        self._client = client or httpx.Client(base_url=BASE_URL, timeout=60.0)
        self._min_interval = min_interval_s
        self._last = 0.0

    def _get(self, path: str) -> dict[str, object]:
        for attempt in range(5):
            wait = self._min_interval - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()
            try:
                res = self._client.get(path)
                if res.status_code == 429 or res.status_code >= 500:
                    raise httpx.HTTPStatusError("retryable", request=res.request, response=res)
                res.raise_for_status()
                data: dict[str, object] = res.json()
                return data
            except (httpx.TransportError, httpx.HTTPStatusError):
                if attempt == 4:
                    raise
                time.sleep(2**attempt)
        raise RuntimeError("unreachable")

    def lookup(self, name: str) -> RxNormResult:
        data = self._get(f"/rxcui.json?name={quote(name)}&search=2")
        group = data.get("idGroup")
        ids = list(group.get("rxnormId", [])) if isinstance(group, dict) else []
        if not ids:
            return RxNormResult(name, "not_found")
        if len(ids) > 1:
            return RxNormResult(name, "ambiguous", candidates=tuple(str(i) for i in ids))
        rxcui = str(ids[0])
        props = self._get(f"/rxcui/{rxcui}/properties.json").get("properties")
        if not isinstance(props, dict):
            return RxNormResult(name, "not_found")
        tty = str(props.get("tty", ""))
        status: Status = "mapped" if tty in ACCEPTED_TTY else "not_ingredient"
        return RxNormResult(name, status, rxcui=rxcui, name=str(props.get("name", "")), tty=tty)


def load_cache(path: Path) -> dict[str, dict[str, object]]:
    if path.exists():
        cache: dict[str, dict[str, object]] = json.loads(path.read_text(encoding="utf-8"))
        return cache
    return {}


def save_cache(path: Path, cache: dict[str, dict[str, object]]) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(cache, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def map_all(names: list[str], client: RxNavClient, cache_path: Path, save_every: int = 50) -> dict[str, dict[str, object]]:
    cache = load_cache(cache_path)
    todo = [n for n in names if n not in cache]
    for i, name in enumerate(todo, 1):
        cache[name] = asdict(client.lookup(name))
        if i % save_every == 0:
            save_cache(cache_path, cache)
            print(f"{len(cache)}/{len(names)}", flush=True)
    save_cache(cache_path, cache)
    return cache


def ingredient_names_from_eg_drugs(csv_path: Path) -> list[str]:
    names: set[str] = set()
    with csv_path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            for part in split_ingredients(row["active"]):
                cleaned = clean_ingredient_name(part)
                if cleaned:
                    names.add(cleaned)
    return sorted(names)


def main(argv: list[str]) -> int:
    csv_path, cache_path = Path(argv[1]), Path(argv[2])
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    names = ingredient_names_from_eg_drugs(csv_path)
    cache = map_all(names, RxNavClient(), cache_path)
    counts: dict[str, int] = {}
    for entry in cache.values():
        counts[str(entry["status"])] = counts.get(str(entry["status"]), 0) + 1
    print(json.dumps({"total": len(names), **counts}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
