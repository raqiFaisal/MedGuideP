"""eg-drugs (Egypt) adapter: reads the CSV and turns each row into a normalized record.

Source: github.com/abduallahJamal/eg-drugs (fork of mahmoudfalous/eg-drugs), data under
CC BY 4.0 (docs/LICENSES.md). Columns verified on the real file (docs/DATA_SOURCES.md):
id, name, arabic, active, company, price, oldprice, barcode, barcode_valid, slug, units,
description, uses.

Nothing is invented: every value comes from the row or from a deterministic parser,
and the raw value is kept next to the parsed one for provenance.
"""

from __future__ import annotations

import csv
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

from adapters.rxnorm import clean_ingredient_name, split_ingredients
from medguide_engine.text.dosage_form import detect_dosage_form
from medguide_engine.text.gtin import is_valid_gtin, to_gtin14
from medguide_engine.text.normalize import normalize_text
from medguide_engine.text.strength import parse_strength

SOURCE_CODE = "eg-drugs"
SOURCE_NAME = "Egyptian Drug Database (eg-drugs) by Mahmoud Mohamed"
SOURCE_URL = "https://github.com/mahmoudfalous/eg-drugs"
SOURCE_LICENSE = "CC BY 4.0"
COUNTRY = "EG"

# The source's own wording; only used to mark IMPORTED, never to infer registration.
_IMPORTED = re.compile(r"illegal\s*import|imported|\bimport\b|مستورد|استيراد", re.IGNORECASE)


@dataclass
class EgDrugRecord:
    source_record_id: str
    name_en: str
    name_ar: str
    brand_normalized: str
    strength_normalized: str
    dosage_form: str | None
    manufacturer: str
    category: str
    uses_ar: str
    ingredients: list[str]  # cleaned ingredient names, source order
    ingredients_raw: str
    price: float | None
    barcode_raw: str
    gtin14: str | None
    barcode_check_ok: bool
    source_barcode_valid: str  # the source's own flag, kept for comparison
    imported: bool
    warnings: list[str] = field(default_factory=list)


def _price(raw: str) -> float | None:
    try:
        value = float(raw.strip())
    except ValueError:
        return None
    return value if value > 0 else None


def parse_row(row: dict[str, str]) -> EgDrugRecord:
    name_en = (row.get("name") or "").strip()
    name_ar = (row.get("arabic") or "").strip()
    barcode = (row.get("barcode") or "").strip()
    warnings: list[str] = []

    strength = parse_strength(name_en) or parse_strength(name_ar)
    form = detect_dosage_form(name_en) or detect_dosage_form(name_ar)
    gtin = to_gtin14(barcode) if barcode else None
    if barcode and gtin is None:
        warnings.append("barcode fails GS1 check")
    source_flag = (row.get("barcode_valid") or "").strip()
    if barcode and source_flag in ("0", "1") and (source_flag == "1") != (gtin is not None):
        warnings.append(f"source barcode_valid={source_flag} disagrees with GS1 check")
    if not name_en and not name_ar:
        warnings.append("no name")

    ingredients_raw = (row.get("active") or "").strip()
    ingredients = [c for c in (clean_ingredient_name(p) for p in split_ingredients(ingredients_raw)) if c]

    return EgDrugRecord(
        source_record_id=(row.get("id") or "").strip(),
        name_en=name_en,
        name_ar=name_ar,
        brand_normalized=normalize_text(name_en or name_ar),
        strength_normalized=strength,
        dosage_form=form,
        manufacturer=(row.get("company") or "").strip(),
        category=(row.get("description") or "").strip(),
        uses_ar=(row.get("uses") or "").strip(),
        ingredients=ingredients,
        ingredients_raw=ingredients_raw,
        price=_price(row.get("price") or ""),
        barcode_raw=barcode,
        gtin14=gtin,
        barcode_check_ok=bool(barcode) and is_valid_gtin(barcode),
        source_barcode_valid=source_flag,
        imported=bool(_IMPORTED.search(name_en) or _IMPORTED.search(name_ar)),
        warnings=warnings,
    )


def read_records(csv_path: Path) -> Iterator[EgDrugRecord]:
    with csv_path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            yield parse_row(row)
