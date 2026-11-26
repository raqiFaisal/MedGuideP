"""Collect local catalog evidence and abstain when the identity is ambiguous."""
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import re
import sqlite3

from rapidfuzz import fuzz
from rapidfuzz.distance import JaroWinkler

from . import catalog
from .text.dosage_form import detect_dosage_form
from .text.normalize import normalize_text
from .text.strength import parse_strength, strengths_equivalent

ROOT = Path(__file__).resolve().parents[2]
RULES = json.loads((ROOT / "shared/recognition.json").read_text())
STOP = set("THE EACH REG MFG EXP BATCH CONTAINS TABLETS TABLET CAPSULES CAPSULE FILM COATED MG MCG G ML IU FOR ORAL USE PACK LOT".split())
STOP.update("كل يحتوي اقراص قرص كبسوله كبسولات مغ مل مجم ملجم ملغ شراب دواء".split())


def name_terms(text: str) -> list[str]:
    name = normalize_text(text)
    return [token for token in name.split() if token not in STOP and re.search(r"[^0-9]", token)]


def recognize(db: sqlite3.Connection, reads: list[dict], lines: list[dict], visual: dict[int, float]) -> dict:
    counts = Counter(read["gtin"] for read in reads)
    confirmed_gtin = next(iter(counts)) if len(counts) == 1 and max(counts.values()) >= 2 else None
    barcode_ids: dict[int, dict] = {}
    for gtin in counts:
        for product in catalog.search(db, gtin, None, 50):
            barcode_ids[product["id"]] = product

    usable = [line for line in lines if line["confidence"] >= RULES["min_ocr_line"]][:50]
    text = " ".join(line["text"] for line in usable)
    strengths: list[str] = []
    for line in usable:
        value = parse_strength(line["text"])
        if value and not any(strengths_equivalent(value, old) for old in strengths):
            strengths.append(value)
    strength = " + ".join(strengths)
    form = detect_dosage_form(text)
    candidates = dict(barcode_ids)
    text_queries = [(" ".join(name_terms(line["text"])), line["confidence"]) for line in usable]
    for query, _ in text_queries[:12]:
        for token in dict.fromkeys(t for t in query.split() if len(t) >= 3):
            for product in catalog.search(db, token, None, 20):
                candidates[product["id"]] = product
    for pid, score in visual.items():
        if score >= RULES["min_visual_similarity"] and pid not in candidates:
            row = db.execute(catalog.PRODUCT + " WHERE p.id=?", (pid,)).fetchone()
            if row:
                candidates[pid] = dict(row)

    ranked = []
    w = RULES["weights"]
    for pid, product in candidates.items():
        names = [" ".join(name_terms(product[key] or "")) for key in ("brand_name_ar", "brand_name_en")]
        # Remove the published strength from the brand comparison when embedded in the name.
        names = [" ".join(token for token in n.split() if not token.isdigit()) for n in names if n]
        comparisons = [(max(fuzz.token_set_ratio(name, query) / 100, JaroWinkler.similarity(name, query)), conf)
                       for query, conf in text_queries if query for name in names if name]
        similarity, confidence = max(comparisons, default=(0.0, 0.0))
        brand = similarity >= RULES["min_name_similarity"]
        barcode = pid in barcode_ids
        visual_score = visual.get(pid, 0.0)
        visual_match = visual_score >= RULES["min_visual_similarity"]
        if not (barcode or brand or visual_match):
            continue
        expected = product["strength_normalized"] or ""
        match = strengths_equivalent(strength, expected)
        conflict = bool(strength and parse_strength(expected) and not match)
        manufacturer = normalize_text(product["manufacturer"] or "")
        company = bool(manufacturer and f" {manufacturer} " in f" {normalize_text(text)} ")
        form_match = bool(form and form == product.get("dosage_form"))
        score = (w["barcode"] * barcode + w["name"] * similarity + w["ocr"] * confidence * brand +
                 w["strength"] * match + w["manufacturer"] * company + w["form"] * form_match +
                 w["visual"] * max(0, visual_score) - w["strength"] * conflict)
        evidence = [label for label, present in (("barcode", barcode), ("text", brand),
                    ("visual", visual_match), ("strength", match), ("manufacturer", company),
                    ("form", form_match)) if present]
        ranked.append(dict(product=product, score=score, evidence=evidence, strength_conflict=conflict))

    ranked.sort(key=lambda item: (-item["score"], item["product"]["id"]))
    if not ranked:
        state = "NOT_IDENTIFIED"
        reason = "NO_CATALOG_MATCH"
    elif confirmed_gtin and len(barcode_ids) == 1 and not ranked[0]["strength_conflict"] and not (
        "text" not in ranked[0]["evidence"] and any("text" in other["evidence"] for other in ranked[1:])
    ):
        state, reason = "IDENTIFIED", "UNIQUE_REPEATED_GTIN"
    else:
        state = "NEEDS_CONFIRMATION"
        reason = ("SHARED_GTIN" if len(barcode_ids) > 1 else
                  "CONFLICTING_GTIN" if len(counts) > 1 else
                  "CONFLICTING_TEXT" if ranked[0]["strength_conflict"] or confirmed_gtin and len(barcode_ids) == 1 else
                  "REVIEW_EVIDENCE")
    return {"status": state, "reason": reason, "candidates": ranked[:3], "barcodes": reads,
            "ocr": lines, "extracted": {"strength": strength, "dosage_form": form}}
