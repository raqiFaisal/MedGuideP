"""Regression coverage for the real rules on an isolated catalog."""
import sqlite3

import pytest

from medguide_engine.barcode import parse_barcode, read_barcodes
from medguide_engine.recognition import recognize

GTIN = "04006381333931"
READS = [{"gtin": GTIN}, {"gtin": GTIN}]


@pytest.fixture
def db():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.executescript("""
        CREATE TABLE manufacturers(id INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE products(id INTEGER PRIMARY KEY, brand_name_en TEXT, brand_name_ar TEXT,
            strength_normalized TEXT, dosage_form TEXT, country_code TEXT, category_text TEXT,
            manufacturer_id INT);
        CREATE TABLE product_identifiers(product_id INT, kind TEXT, value TEXT, check_ok INT);
        CREATE VIRTUAL TABLE products_fts USING fts5(brand);
        INSERT INTO products VALUES (1,'SAMPLEMED',NULL,'500 MG','tablet','EG',NULL,NULL),
            (2,'SAMPLEMED',NULL,'250 MG','tablet','EG',NULL,NULL),
            (3,'OTHERMED',NULL,'500 MG','tablet','EG',NULL,NULL);
        INSERT INTO products_fts(rowid,brand) VALUES (1,'SAMPLEMED'),(2,'SAMPLEMED'),(3,'OTHERMED');
        INSERT INTO product_identifiers VALUES (1,'GTIN14','04006381333931',1);
    """)
    yield connection
    connection.close()


def line(text):
    return {"text": text, "confidence": .95}


@pytest.mark.parametrize("value,expected", [
    ("4006381333931", GTIN), ("036000291452", "00036000291452"),
    ("96385074", "00000096385074"), (GTIN, GTIN),
    ("4006381333937", None), ("0123", None), ("12x34567", None),
    ("[01]04006381333931", None), ("(01)04006381333931(01)04006381333931", None),
    ("(01)4006381333931", None), ("]d2010400638133393117280200", GTIN),
    ("(01)04006381333931(17)280229", GTIN), ("(17)281231", None),
    ("0104006381333931\x1d10LOT\x1d21SERIAL", GTIN),
    ("(10)LOT(01)04006381333931", GTIN), ("(01)04006381333932", None),
    ("(01)04006381333931(17)281331", GTIN),
    ("01040063813339311728123110LOT", GTIN),
    ("", None), ("٠٤٠٠٦٣٨١٣٣٣٩٣١", None),
])
def test_gtin_and_gs1(value, expected):
    assert parse_barcode(value).get("gtin") == expected


def test_gs1_fields():
    assert parse_barcode("]d201040063813339311728020010AB12\x1d21XYZ") == {
        "gtin": GTIN, "expiry": "2028-02-29", "lot": "AB12", "serial": "XYZ",
    }
    assert "expiry" not in parse_barcode("(01)04006381333931(17)270229")


def test_unique_repeated_barcode_and_duplicate_ocr_strength(db):
    result = recognize(db, READS, [line("SAMPLEMED 500mg"), line("SAMPLEMED 0.5 g")], {})
    assert result["status"] == "IDENTIFIED"
    assert result["candidates"][0]["product"]["id"] == 1
    assert result["extracted"]["strength"] == "500 MG"


def test_single_read_requires_confirmation(db):
    assert recognize(db, READS[:1], [], {})["status"] == "NEEDS_CONFIRMATION"


def test_shared_barcode_never_confirms(db):
    db.execute("INSERT INTO product_identifiers VALUES (2,'GTIN14',?,1)", (GTIN,))
    result = recognize(db, READS, [], {1: .93})
    assert result["reason"] == "SHARED_GTIN"
    assert result["status"] == "NEEDS_CONFIRMATION"
    assert [c["product"]["id"] for c in result["candidates"]] == [1, 2]


def test_similar_packs_and_conflicting_strength(db):
    result = recognize(db, READS, [line("SAMPLEMED 250 MG")], {2: .95})
    assert result["status"] == "NEEDS_CONFIRMATION"
    assert result["reason"] == "CONFLICTING_TEXT"


def test_brand_conflict_blocks_auto_identification(db):
    result = recognize(db, READS, [line("OTHERMED 500 MG")], {})
    assert result["status"] == "NEEDS_CONFIRMATION"


def test_unknown_and_visual_only(db):
    assert recognize(db, [{"gtin": "00036000291452"}] * 2, [line("UNLISTEDPRODUCT")], {})[
        "status"] == "NOT_IDENTIFIED"
    assert recognize(db, [], [], {1: .99})["status"] == "NEEDS_CONFIRMATION"


def test_actual_barcode_decoder_to_catalog(db, tmp_path):
    np = pytest.importorskip("numpy")
    zxing = pytest.importorskip("zxingcpp")
    pytest.importorskip("cv2")
    from PIL import Image
    from medguide_engine.vision import Analyzer

    code = zxing.create_barcode("4006381333931", zxing.BarcodeFormat.EAN13)
    rendered = np.asarray(zxing.write_barcode_to_image(code, scale=4))
    path = tmp_path / "barcode.png"
    Image.fromarray(rendered).save(path)
    rgb = np.stack([rendered] * 3, axis=-1)
    assert [r["gtin"] for r in read_barcodes(rgb)] == [GTIN, GTIN]
    result = Analyzer()(db, path)
    assert result["status"] == "IDENTIFIED"
    assert result["candidates"][0]["product"]["id"] == 1
    assert result["time_ms"] > 0


def test_unreadable_concentration_does_not_crash(db):
    result = recognize(db, READS, [line("SAMPLEMED 250 MG/0 ML")], {})
    assert result["status"] == "NEEDS_CONFIRMATION"
