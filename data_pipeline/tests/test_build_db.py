from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path

from adapters.eg_drugs import parse_row
from build_db import build

COLUMNS = ["id", "name", "arabic", "active", "company", "price", "oldprice", "barcode", "barcode_valid",
           "slug", "units", "description", "uses"]
# Shaped like real eg-drugs rows (see docs/DATA_SOURCES.md); values are test data.
ROWS = [
    ["1", "1 2 3 (one two three) 20 f.c.tabs", "ون تو ثري 20 قرص", "chlorpheniramine+paracetamol+pseudoephedrine",
     "hikma pharma", "40", "24", "6221000000010", "1", "s1", "2", "cold products", "تخفيف أعراض نزلات البرد"],
    ["2", "1 2 3 (one two three) syrup 120 ml", "ون تو ثري شراب 120 مل", "chlorpheniramine+paracetamol+pseudoephedrine",
     "hikma pharma", "40", "32", "6221000000010", "1", "s2", "1", "cold products", ""],
    ["3", "nimotop 30mg 30tabs.(illegal import)", "نيموتوب 30مجم 30 قرص - استيراد", "nimodipine",
     "bayer", "0", "", "4006381333932", "1", "s3", "1", "", ""],
    ["4", "", "", "x", "y", "1", "", "", "0", "s4", "1", "", ""],
]


def write_csv(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(COLUMNS)
        w.writerows(ROWS)
    (path.parent / "SOURCE_COMMIT").write_text("testcommit\n", encoding="utf-8")
    return path


def test_parse_row_fields() -> None:
    rec = parse_row(dict(zip(COLUMNS, ROWS[0])))
    assert rec.strength_normalized == ""  # no strength in this name — not invented
    assert rec.dosage_form == "FILM_COATED_TABLET"
    assert rec.ingredients == ["chlorpheniramine", "paracetamol", "pseudoephedrine"]
    assert rec.gtin14 == "06221000000010" and rec.barcode_check_ok
    assert not rec.imported

    imported = parse_row(dict(zip(COLUMNS, ROWS[2])))
    assert imported.imported and imported.strength_normalized == "30 MG"
    assert imported.gtin14 is None and "barcode fails GS1 check" in imported.warnings
    assert any("disagrees" in w for w in imported.warnings)
    assert imported.price is None  # price 0 is not a real price


def test_build_end_to_end(tmp_path: Path) -> None:
    csv_path = write_csv(tmp_path / "raw" / "eg_drugs.csv")
    rx = tmp_path / "rx.json"
    rx.write_text(json.dumps({"paracetamol": {"status": "mapped", "rxcui": "161", "name": "acetaminophen", "tty": "IN"}}),
                  encoding="utf-8")
    manifest = build(csv_path, rx, tmp_path / "out")
    out = tmp_path / "out"
    assert manifest["size_bytes"] > 0 and len(manifest["sha256"]) == 64
    assert (out / "quality_report.md").exists() and (out / "review_sample.csv").exists()

    con = sqlite3.connect(out / "medguide.db")
    assert con.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 3  # row 4 rejected (no name)
    assert con.execute("SELECT rows_rejected FROM ingestion_jobs").fetchone()[0] == 1
    # Paracetamol stored under its RxNorm name, with the source spelling as a synonym.
    ing = con.execute("SELECT id, name_en FROM active_ingredients WHERE name_en='acetaminophen'").fetchone()
    assert ing is not None
    assert con.execute("SELECT rxcui FROM rxnorm_mappings WHERE ingredient_id=?", (ing[0],)).fetchone()[0] == "161"
    assert con.execute("SELECT synonym FROM ingredient_synonyms WHERE ingredient_id=?", (ing[0],)).fetchone()[0] == "paracetamol"
    # Availability is never inferred.
    statuses = dict(con.execute(
        "SELECT p.source_record_id, ma.status FROM market_availability ma JOIN products p ON p.id=ma.product_id"))
    assert statuses == {"1": "AVAILABILITY_UNKNOWN", "2": "AVAILABILITY_UNKNOWN", "3": "IMPORTED"}
    # The same GTIN on two products is kept on both (the app must then ask the user).
    assert con.execute("SELECT COUNT(*) FROM product_identifiers WHERE value='06221000000010' AND check_ok=1").fetchone()[0] == 2
    # Invalid barcode kept as raw value with check_ok=0.
    assert con.execute("SELECT check_ok FROM product_identifiers WHERE value='4006381333932'").fetchone()[0] == 0
    # Provenance kept for the Arabic uses text, verbatim.
    assert con.execute("SELECT original_value FROM information_provenance WHERE field='uses_ar'").fetchone()[0] == "تخفيف أعراض نزلات البرد"
    # Full-text search finds the product by an ingredient.
    hits = con.execute("SELECT rowid FROM products_fts WHERE products_fts MATCH 'ACETAMINOPHEN'").fetchall()
    assert len(hits) == 2
    assert con.execute("PRAGMA foreign_key_check").fetchall() == []
    report = (out / "quality_report.md").read_text(encoding="utf-8")
    assert "GTINs shared by more than one product | 1 " in report


def test_build_with_sfda_snapshot(tmp_path: Path) -> None:
    from openpyxl import Workbook

    from adapters.sfda import COLUMNS as SFDA_COLUMNS

    csv_path = write_csv(tmp_path / "raw" / "eg_drugs.csv")
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Data"
    sheet.append(SFDA_COLUMNS)
    row = ["TEST BRAND 5 MG TABLET", "ACTIVE ONE, ACTIVE TWO", 30, "tablets",
           "Generic", None, "Prescription", None, "Test Manufacturer", "Saudi Arabia"]
    sheet.append(row)
    sheet.append(row)
    sheet.append([None, "NAME MISSING"])
    path = tmp_path / "sfda.xlsx"
    workbook.save(path)

    out = tmp_path / "out"
    manifest = build(csv_path, None, out, sfda_files={"local": path})
    assert "sfda-2023-local" in manifest["sources"]
    with sqlite3.connect(out / "medguide.db") as con:
        assert con.execute(
            "SELECT rows_read,rows_loaded,rows_rejected FROM ingestion_jobs ORDER BY id DESC LIMIT 1"
        ).fetchone() == (3, 1, 2)
        pid, ref, strength = con.execute(
            "SELECT id,source_record_id,strength_normalized FROM products WHERE country_code='SA'"
        ).fetchone()
        assert (ref, strength) == ("Data!2", "5 MG")
        assert con.execute(
            "SELECT authority,registration_number FROM product_registrations WHERE product_id=?", (pid,)
        ).fetchone() == ("SFDA", None)
        assert con.execute(
            "SELECT status FROM market_availability WHERE product_id=?", (pid,)
        ).fetchone() == ("AVAILABILITY_UNKNOWN",)
        assert con.execute("SELECT rowid FROM products_fts WHERE products_fts MATCH 'ACTIVE TWO'").fetchall() == [(pid,)]
        assert con.execute("PRAGMA foreign_key_check").fetchall() == []
    with (out / "review_sample.csv").open(encoding="utf-8-sig", newline="") as report:
        sa = [record for record in csv.DictReader(report) if record["country"] == "SA"]
    assert len(sa) == 1
    assert sa[0]["ingredients"] == "ACTIVE ONE, ACTIVE TWO"
