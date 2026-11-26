"""Read-only SQLite catalog for the local development API."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from medguide_engine.text.gtin import to_gtin14
from medguide_engine.text.normalize import normalize_text

PRODUCT = """
SELECT p.id, p.brand_name_en, p.brand_name_ar, p.strength_normalized, p.dosage_form,
       p.country_code, p.category_text, m.name AS manufacturer
FROM products p LEFT JOIN manufacturers m ON m.id=p.manufacturer_id
"""


@contextmanager
def open_catalog(path: Path) -> Iterator[sqlite3.Connection]:
    db = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, check_same_thread=False)
    db.row_factory = sqlite3.Row
    try:
        yield db
    finally:
        db.close()


def search(db: sqlite3.Connection, query: str, country: str | None, limit: int) -> list[dict]:
    normalized = normalize_text(query)
    if not normalized:
        return []
    gtin = to_gtin14(normalized) if normalized.isascii() and normalized.isdigit() else None
    country_filter = "AND p.country_code=?" if country else ""
    parameters = (country, limit) if country else (limit,)
    if gtin:
        rows = db.execute(
            PRODUCT + " WHERE p.id IN (SELECT product_id FROM product_identifiers "
            "WHERE kind='GTIN14' AND value=? AND check_ok=1) " + country_filter +
            " ORDER BY p.id LIMIT ?", (gtin, *parameters),
        )
    else:
        # Every token is quoted before passing it to the FTS query parser.
        expression = " AND ".join('"' + token.replace('"', '""') + '"*' for token in normalized.split())
        rows = db.execute(
            PRODUCT + " JOIN products_fts ON products_fts.rowid=p.id "
            "WHERE products_fts MATCH ? " + country_filter + " ORDER BY bm25(products_fts), p.id LIMIT ?",
            (expression, *parameters),
        )
    return [dict(row) for row in rows]


def details(db: sqlite3.Connection, product_id: int) -> dict | None:
    row = db.execute(PRODUCT + " WHERE p.id=?", (product_id,)).fetchone()
    if row is None:
        return None
    ingredients = db.execute(
        "SELECT ai.name_en FROM product_ingredients pi JOIN active_ingredients ai"
        " ON ai.id=pi.ingredient_id WHERE pi.product_id=? ORDER BY pi.position, ai.id", (product_id,),
    )
    scientific = db.execute(
        "SELECT original_value FROM information_provenance WHERE table_name='products'"
        " AND row_id=? AND field='ScientificName'", (product_id,),
    ).fetchone()
    availability = db.execute(
        "SELECT country_code,status,verified_at FROM market_availability WHERE product_id=? ORDER BY country_code",
        (product_id,),
    )
    return {**dict(row), "ingredients": [r[0] for r in ingredients],
            "scientific_name_as_published": scientific[0] if scientific else None,
            "market_availability": [dict(r) for r in availability]}


def sources(db: sqlite3.Connection, product_id: int) -> dict | None:
    source = db.execute(
        "SELECT s.code,s.name,s.url,s.license,s.attribution,s.version_ref,p.source_record_id"
        " FROM products p JOIN data_sources s ON s.id=p.source_id WHERE p.id=?", (product_id,),
    ).fetchone()
    if source is None:
        return None
    fields = db.execute(
        "SELECT ip.field,ip.original_value,ip.normalized_value,ip.verification_status,"
        "ip.source_url,ds.code AS source_code,ds.url AS publisher_url FROM information_provenance ip"
        " JOIN data_sources ds ON ds.id=ip.source_id WHERE ip.table_name='products'"
        " AND ip.row_id=? ORDER BY ip.field,ip.id", (product_id,),
    )
    return {"product_id": product_id, "record_source": dict(source), "fields": [dict(row) for row in fields]}
