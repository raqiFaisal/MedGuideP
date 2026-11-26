"""Builds medguide.db + manifest.json + quality_report.md + review_sample.csv.

Usage (from data_pipeline/):
    python build_db.py --eg-drugs ../data/raw/eg-drugs/eg_drugs.csv \
        --rxnorm-cache ../data/processed/rxnorm_cache.json --out ../data/processed/build

Only verified sources are loaded (docs/LICENSES.md). Market availability is never
inferred: rows the source marks as imported get IMPORTED, everything else
AVAILABILITY_UNKNOWN.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import sqlite3
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from adapters import eg_drugs, sfda
from medguide_engine.text.dosage_form import detect_dosage_form
from medguide_engine.text.strength import parse_strength
from adapters.eg_drugs import EgDrugRecord
from medguide_engine.text.normalize import normalize_arabic, normalize_text

SCHEMA_DIR = Path(__file__).resolve().parent / "schema"
DB_VERSION = "0.2.0"
REVIEW_SAMPLE_SIZE = 50
REVIEW_SEED = 20261122

COUNTRIES = [("EG", "مصر", "Egypt"), ("SA", "السعودية", "Saudi Arabia"), ("YE", "اليمن", "Yemen")]

RXNORM_SOURCE = {
    "code": "rxnorm",
    "name": "RxNorm (U.S. National Library of Medicine) via RxNav",
    "url": "https://rxnav.nlm.nih.gov/REST/",
    "license": "Public domain (NLM-created names and RxCUIs)",
    "attribution": "This product uses publicly available data from the U.S. National Library of Medicine (NLM), "
    "National Institutes of Health, Department of Health and Human Services; NLM is not responsible for "
    "the product and does not endorse or recommend this or any other product.",
}


@dataclass
class BuildStats:
    rows: int = 0
    loaded: int = 0
    rejected: int = 0
    warnings: Counter[str] = field(default_factory=Counter)
    with_strength: int = 0
    with_form: int = 0
    forms: Counter[str] = field(default_factory=Counter)
    with_valid_gtin: int = 0
    with_barcode: int = 0
    imported: int = 0
    with_uses: int = 0
    categories: Counter[str] = field(default_factory=Counter)
    ingredient_links: int = 0
    gtin_products: dict[str, int] = field(default_factory=dict)


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def create_db(path: Path) -> sqlite3.Connection:
    if path.exists():
        path.unlink()
    con = sqlite3.connect(path)
    con.execute("PRAGMA foreign_keys = ON")
    for sql_file in sorted(SCHEMA_DIR.glob("*.sql")):
        con.executescript(sql_file.read_text(encoding="utf-8"))
    return con


def _add_source(con: sqlite3.Connection, code: str, name: str, url: str, license_: str,
                attribution: str | None, version_ref: str | None, fetched_at: str) -> int:
    cur = con.execute(
        "INSERT INTO data_sources(code,name,url,license,attribution,version_ref,fetched_at) VALUES (?,?,?,?,?,?,?)",
        (code, name, url, license_, attribution, version_ref, fetched_at),
    )
    return int(cur.lastrowid or 0)


class Loader:
    def __init__(self, con: sqlite3.Connection, rxnorm: dict[str, dict[str, Any]], rx_source_id: int) -> None:
        self.con = con
        self.rxnorm = rxnorm
        self.rx_source_id = rx_source_id
        self._manufacturers: dict[str, int] = {}
        self._ingredients: dict[str, int] = {}

    def manufacturer_id(self, name: str) -> int | None:
        key = normalize_text(name)
        if not key:
            return None
        if key not in self._manufacturers:
            cur = self.con.execute(
                "INSERT INTO manufacturers(name,name_normalized,country_code) VALUES (?,?,NULL)", (name, key)
            )
            self._manufacturers[key] = int(cur.lastrowid or 0)
        return self._manufacturers[key]

    def ingredient_id(self, cleaned: str, source_id: int) -> int:
        mapping = self.rxnorm.get(cleaned, {})
        mapped = mapping.get("status") == "mapped" and mapping.get("tty") in ("IN", "PIN")
        preferred = str(mapping["name"]) if mapped else cleaned
        key = normalize_text(preferred)
        if key not in self._ingredients:
            cur = self.con.execute(
                "INSERT INTO active_ingredients(name_en,name_ar,name_normalized) VALUES (?,NULL,?)", (preferred, key)
            )
            ing_id = int(cur.lastrowid or 0)
            self._ingredients[key] = ing_id
            if mapped:
                self.con.execute(
                    "INSERT INTO rxnorm_mappings(ingredient_id,rxcui,tty,mapped_at) VALUES (?,?,?,?)",
                    (ing_id, mapping["rxcui"], mapping["tty"], _now()),
                )
        ing_id = self._ingredients[key]
        syn_key = normalize_text(cleaned)
        self.con.execute(
            "INSERT OR IGNORE INTO ingredient_synonyms(ingredient_id,synonym,synonym_normalized,language,source_id) "
            "VALUES (?,?,?,?,?)",
            (ing_id, cleaned, syn_key, "en", source_id),
        )
        return ing_id

    def provenance(self, table: str, row_id: int, fld: str, source_id: int, original: str,
                   normalized: str | None, fetched_at: str, status: str = "unverified") -> None:
        self.con.execute(
            "INSERT INTO information_provenance(table_name,row_id,field,source_id,source_url,original_value,"
            "normalized_value,fetched_at,verified_at,verification_status) VALUES (?,?,?,?,?,?,?,?,NULL,?)",
            (table, row_id, fld, source_id, eg_drugs.SOURCE_URL, original, normalized, fetched_at, status),
        )

    def load_eg_record(self, rec: EgDrugRecord, source_id: int, fetched_at: str, stats: BuildStats) -> int | None:
        stats.rows += 1
        for w in rec.warnings:
            stats.warnings[w] += 1
        if not rec.source_record_id or not (rec.name_en or rec.name_ar):
            stats.rejected += 1
            return None
        cur = self.con.execute(
            "INSERT INTO products(brand_name_en,brand_name_ar,brand_normalized,strength_text,strength_normalized,"
            "dosage_form,manufacturer_id,country_code,category_text,uses_ar,source_id,source_record_id) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                rec.name_en or None,
                rec.name_ar or None,
                rec.brand_normalized,
                rec.strength_normalized or None,
                rec.strength_normalized or None,
                rec.dosage_form,
                self.manufacturer_id(rec.manufacturer),
                eg_drugs.COUNTRY,
                rec.category or None,
                rec.uses_ar or None,
                source_id,
                rec.source_record_id,
            ),
        )
        pid = int(cur.lastrowid or 0)
        for pos, ing in enumerate(dict.fromkeys(rec.ingredients)):
            ing_id = self.ingredient_id(ing, source_id)
            self.con.execute(
                "INSERT OR IGNORE INTO product_ingredients(product_id,ingredient_id,strength_text,position) VALUES (?,?,NULL,?)",
                (pid, ing_id, pos),
            )
            stats.ingredient_links += 1
        package_id: int | None = None
        if rec.price is not None:
            cur = self.con.execute(
                "INSERT INTO packages(product_id,description,price,currency,price_date,source_id) VALUES (?,NULL,?,?,NULL,?)",
                (pid, rec.price, "EGP", source_id),
            )
            package_id = int(cur.lastrowid or 0)
        if rec.barcode_raw:
            stats.with_barcode += 1
            value = rec.gtin14 or rec.barcode_raw
            self.con.execute(
                "INSERT INTO product_identifiers(product_id,package_id,kind,value,check_ok,source_id) VALUES (?,?,?,?,?,?)",
                (pid, package_id, "GTIN14", value, 1 if rec.gtin14 else 0, source_id),
            )
            if rec.gtin14:
                stats.with_valid_gtin += 1
                stats.gtin_products[rec.gtin14] = stats.gtin_products.get(rec.gtin14, 0) + 1
        status = "IMPORTED" if rec.imported else "AVAILABILITY_UNKNOWN"
        self.con.execute(
            "INSERT INTO market_availability(product_id,country_code,status,source_id,verified_at) VALUES (?,?,?,?,NULL)",
            (pid, eg_drugs.COUNTRY, status, source_id),
        )
        for fld, original, normalized in (
            ("brand_name_en", rec.name_en, rec.brand_normalized),
            ("brand_name_ar", rec.name_ar, normalize_arabic(rec.name_ar)),
            ("active_ingredients", rec.ingredients_raw, " + ".join(rec.ingredients)),
            ("manufacturer", rec.manufacturer, normalize_text(rec.manufacturer)),
            ("uses_ar", rec.uses_ar, None),
            ("barcode", rec.barcode_raw, rec.gtin14),
            ("price", "" if rec.price is None else str(rec.price), None),
        ):
            if original:
                self.provenance("products", pid, fld, source_id, original, normalized, fetched_at)
        stats.loaded += 1
        stats.with_strength += bool(rec.strength_normalized)
        stats.with_form += bool(rec.dosage_form)
        stats.forms[rec.dosage_form or "(none)"] += 1
        stats.imported += rec.imported
        stats.with_uses += bool(rec.uses_ar)
        stats.categories[rec.category or "(empty)"] += 1
        return pid


def load_sfda(loader: Loader, kind: str, path: Path, fetched_at: str) -> None:
    con = loader.con
    name, url = sfda.SOURCES[kind]
    source = _add_source(con, f"sfda-2023-{kind}", name, url, sfda.SOURCE_LICENSE,
                         name, f"2023-12-12; sha256:{sha256(path)}", fetched_at)
    job = con.execute(
        "INSERT INTO ingestion_jobs(source_id,started_at,status) VALUES (?,?,'running')",
        (source, fetched_at),
    ).lastrowid
    seen: dict[tuple[str, ...], int] = {}
    read = loaded = rejected = 0
    for number, row in sfda.read_rows(path):
        read += 1
        ref = f"Data!{number}"
        identity = tuple(row.values())
        trade = row["TradeName"]
        if not trade or identity in seen:
            rejected += 1
            reason = f"exact duplicate of Data!{seen[identity]}" if trade else "missing TradeName"
            con.execute(
                "INSERT INTO ingestion_logs(job_id,level,record_ref,message) VALUES (?,'warning',?,?)",
                (job, ref, reason),
            )
            continue
        seen[identity] = number
        product = con.execute(
            "INSERT INTO products(brand_name_en,brand_normalized,strength_normalized,"
            "dosage_form,manufacturer_id,country_code,category_text,source_id,source_record_id)"
            " VALUES (?,?,?,?,?,'SA',?,?,?)",
            (trade, normalize_text(trade), parse_strength(trade) or None, detect_dosage_form(trade),
             loader.manufacturer_id(row["Manufacturer_Name"]), row["DrugType"] or None, source, ref),
        ).lastrowid
        # Keep the scientific name intact, since commas may be part of a chemical name.
        for field, value in row.items():
            if value:
                loader.provenance("products", product, field, source, value, None, fetched_at)
        con.execute(
            "INSERT INTO product_registrations(product_id,country_code,authority,source_id)"
            " VALUES (?,'SA','SFDA',?)", (product, source),
        )
        con.execute(
            "INSERT INTO market_availability(product_id,country_code,status,source_id)"
            " VALUES (?,'SA','AVAILABILITY_UNKNOWN',?)", (product, source),
        )
        if row["Size"] and row["SizeUnit"]:
            con.execute(
                "INSERT INTO packages(product_id,description,source_id) VALUES (?,?,?)",
                (product, f'{row["Size"]} {row["SizeUnit"]}', source),
            )
        loaded += 1
    con.execute(
        "UPDATE ingestion_jobs SET finished_at=?,status='succeeded',rows_read=?,rows_loaded=?,rows_rejected=?"
        " WHERE id=?", (_now(), read, loaded, rejected, job),
    )


def build_fts(con: sqlite3.Connection) -> bool:
    """Full-text index for search. Returns False if this SQLite has no FTS5."""
    try:
        con.execute(
            "CREATE VIRTUAL TABLE products_fts USING fts5(brand, brand_ar, ingredients, content='', tokenize='unicode61')"
        )
    except sqlite3.OperationalError:
        return False
    rows = con.execute(
        "SELECT p.id, p.brand_normalized, COALESCE(p.brand_name_ar,''), "
        "COALESCE((SELECT group_concat(ai.name_normalized,' ') FROM product_ingredients pi "
        "JOIN active_ingredients ai ON ai.id=pi.ingredient_id WHERE pi.product_id=p.id), "
        "ip.original_value,'') FROM products p LEFT JOIN information_provenance ip"
        " ON ip.table_name='products' AND ip.row_id=p.id AND ip.field='ScientificName'"
    ).fetchall()
    con.executemany(
        "INSERT INTO products_fts(rowid,brand,brand_ar,ingredients) VALUES (?,?,?,?)",
        [(r[0], r[1], normalize_arabic(r[2]), normalize_text(r[3])) for r in rows],
    )
    return True


def write_review_sample(con: sqlite3.Connection, path: Path) -> None:
    rng = random.Random(REVIEW_SEED)
    sample = []
    for (source,) in con.execute("SELECT DISTINCT source_id FROM products ORDER BY source_id"):
        ids = [r[0] for r in con.execute("SELECT id FROM products WHERE source_id=? ORDER BY id", (source,))]
        sample.extend(sorted(rng.sample(ids, min(REVIEW_SAMPLE_SIZE, len(ids)))))
    cols = ["product_id", "source_record_id", "brand_name_en", "brand_name_ar", "ingredients", "strength",
            "dosage_form", "manufacturer", "gtin14", "availability", "check_ok_(fill_in)", "reviewer_note",
            "country", "source"]
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for pid in sample:
            r = con.execute(
                "SELECT p.id,p.source_record_id,p.brand_name_en,p.brand_name_ar,"
                "(SELECT group_concat(ai.name_en,' + ') FROM product_ingredients pi JOIN active_ingredients ai "
                " ON ai.id=pi.ingredient_id WHERE pi.product_id=p.id),p.strength_normalized,p.dosage_form,m.name,"
                "(SELECT value FROM product_identifiers WHERE product_id=p.id AND check_ok=1 LIMIT 1),ma.status,p.country_code,ds.url "
                "FROM products p JOIN data_sources ds ON ds.id=p.source_id LEFT JOIN manufacturers m ON m.id=p.manufacturer_id "
                "LEFT JOIN market_availability ma ON ma.product_id=p.id WHERE p.id=?",
                (pid,),
            ).fetchone()
            values = list(r)
            if values[4] is None:
                raw = con.execute(
                    "SELECT original_value FROM information_provenance WHERE table_name='products'"
                    " AND row_id=? AND field='ScientificName'", (pid,),
                ).fetchone()
                values[4] = raw[0] if raw else None
            w.writerow(values[:-2] + ["", ""] + values[-2:])


def quality_report(stats: BuildStats, con: sqlite3.Connection, fts: bool, path: Path, eg_ref: str,
                   rx_total: int, rx_status: Counter[str]) -> None:
    def pct(n: int, d: int) -> str:
        return f"{n:,} ({(100 * n / d) if d else 0:.1f}%)"

    shared = {g: n for g, n in stats.gtin_products.items() if n > 1}
    ing_total = con.execute("SELECT COUNT(*) FROM active_ingredients").fetchone()[0]
    ing_mapped = con.execute("SELECT COUNT(*) FROM rxnorm_mappings").fetchone()[0]
    sfda_jobs = con.execute(
        "SELECT ds.code, j.rows_read, j.rows_loaded, j.rows_rejected FROM ingestion_jobs j"
        " JOIN data_sources ds ON ds.id=j.source_id WHERE ds.code LIKE 'sfda-%' ORDER BY ds.code"
    ).fetchall()
    lines = [
        "# Quality report — medguide.db",
        "",
        f"Built {_now()} · DB version {DB_VERSION} · eg-drugs commit `{eg_ref}`",
        "",
        "All numbers below are measured on this build. Nothing is estimated.",
        "",
        "## eg-drugs (Egypt)",
        "",
        "| Measure | Value |",
        "|---|---|",
        f"| Rows read | {stats.rows:,} |",
        f"| Products loaded | {stats.loaded:,} |",
        f"| Rejected (no id or no name) | {stats.rejected:,} |",
        f"| Strength parsed | {pct(stats.with_strength, stats.loaded)} |",
        f"| Dosage form detected | {pct(stats.with_form, stats.loaded)} |",
        f"| Has a barcode | {pct(stats.with_barcode, stats.loaded)} |",
        f"| Barcode passes our GS1 check | {pct(stats.with_valid_gtin, stats.loaded)} |",
        f"| GTINs shared by more than one product | {len(shared):,} (covering {sum(shared.values()):,} products) |",
        f"| Marked imported by the source → IMPORTED | {stats.imported:,} |",
        f"| All others → AVAILABILITY_UNKNOWN (not inferred) | {stats.loaded - stats.imported:,} |",
        f"| Has Arabic `uses` text (verbatim) | {pct(stats.with_uses, stats.loaded)} |",
        f"| Product–ingredient links | {stats.ingredient_links:,} |",
        f"| FTS5 search index | {'built' if fts else 'NOT available in this SQLite'} |",
        "",
        "### Parser warnings",
        "",
        "| Warning | Rows |",
        "|---|---|",
        *[f"| {w} | {n:,} |" for w, n in stats.warnings.most_common()],
        "",
        "### Dosage forms",
        "",
        "| Form | Products |",
        "|---|---|",
        *[f"| {f} | {n:,} |" for f, n in stats.forms.most_common()],
        "",
        "### Top 15 categories (source wording; cosmetics/supplements kept by user decision)",
        "",
        "| Category | Products |",
        "|---|---|",
        *[f"| {c} | {n:,} |" for c, n in stats.categories.most_common(15)],
        "",
        "## Active ingredients and RxNorm",
        "",
        f"- Distinct active ingredients in the DB: {ing_total:,}",
        f"- Mapped to an RxNorm ingredient (exact match only): {pct(ing_mapped, ing_total)}",
        f"- RxNorm lookup cache used: {rx_total:,} names looked up; status counts {dict(rx_status)}",
        "- Ingredients not in the cache yet are stored with their source name and no RxCUI.",
        "",
        "## SFDA (Saudi Arabia)",
        "",
        "| Source | Rows read | Products loaded | Duplicates or missing name |",
        "|---|---:|---:|---:|",
        *[f"| {code} | {read:,} | {loaded:,} | {rejected:,} |" for code, read, loaded, rejected in sfda_jobs],
        "",
        "The supplied lists are a December 2023 snapshot. They have no GTIN or registration number.",
        "Scientific names are stored verbatim in provenance. Current market availability is unknown.",
        "",
        "## Not included in this build",
        "",
        *([] if sfda_jobs else ["- SFDA: no workbook supplied for this build."]),
        "- openFDA ingredient information: not fetched yet.",
        "- DDInter: terms not verified (site unreachable) — excluded.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build(eg_csv: Path, rxnorm_cache: Path | None, out_dir: Path, *, sfda_files: dict[str, Path] | None = None) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    db_path = out_dir / "medguide.db"
    con = create_db(db_path)
    fetched_at = _now()
    eg_ref_file = eg_csv.parent / "SOURCE_COMMIT"
    eg_ref = eg_ref_file.read_text(encoding="utf-8").strip() if eg_ref_file.exists() else "unknown"
    rxnorm: dict[str, dict[str, Any]] = (
        json.loads(rxnorm_cache.read_text(encoding="utf-8")) if rxnorm_cache and rxnorm_cache.exists() else {}
    )

    with con:
        con.executemany("INSERT INTO countries(code,name_ar,name_en) VALUES (?,?,?)", COUNTRIES)
        eg_id = _add_source(con, eg_drugs.SOURCE_CODE, eg_drugs.SOURCE_NAME, eg_drugs.SOURCE_URL,
                            eg_drugs.SOURCE_LICENSE, f"{eg_drugs.SOURCE_NAME} ({eg_drugs.SOURCE_URL})", eg_ref, fetched_at)
        rx_id = _add_source(con, RXNORM_SOURCE["code"], RXNORM_SOURCE["name"], RXNORM_SOURCE["url"],
                            RXNORM_SOURCE["license"], RXNORM_SOURCE["attribution"], "RxNav REST", fetched_at)
        job = con.execute(
            "INSERT INTO ingestion_jobs(source_id,started_at,status) VALUES (?,?, 'running')", (eg_id, fetched_at)
        ).lastrowid
        loader = Loader(con, rxnorm, rx_id)
        stats = BuildStats()
        for rec in eg_drugs.read_records(eg_csv):
            pid = loader.load_eg_record(rec, eg_id, fetched_at, stats)
            if pid is None:
                con.execute(
                    "INSERT INTO ingestion_logs(job_id,level,record_ref,message) VALUES (?,?,?,?)",
                    (job, "warning", rec.source_record_id or None, "rejected: no id or no name"),
                )
        con.execute(
            "UPDATE ingestion_jobs SET finished_at=?, status='succeeded', rows_read=?, rows_loaded=?, rows_rejected=? WHERE id=?",
            (_now(), stats.rows, stats.loaded, stats.rejected, job),
        )
        for kind, path in sorted((sfda_files or {}).items()):
            load_sfda(loader, kind, path, fetched_at)
        fts = build_fts(con)
        con.executemany(
            "INSERT OR REPLACE INTO meta(key,value) VALUES (?,?)",
            [("db_version", DB_VERSION), ("built_at", _now()), ("eg_drugs_commit", eg_ref)],
        )
    problems = con.execute("PRAGMA foreign_key_check").fetchall()
    if problems:
        raise RuntimeError(f"foreign key problems: {problems[:5]}")
    quality_report(stats, con, fts, out_dir / "quality_report.md", eg_ref, len(rxnorm),
                   Counter(str(v.get("status")) for v in rxnorm.values()))
    write_review_sample(con, out_dir / "review_sample.csv")
    con.execute("VACUUM")
    sources = [row[0] for row in con.execute("SELECT code FROM data_sources ORDER BY id")]
    con.close()

    manifest = {
        "db_version": DB_VERSION,
        "schema_version": 1,
        "built_at": _now(),
        "file": db_path.name,
        "size_bytes": db_path.stat().st_size,
        "sha256": sha256(db_path),
        "download_url": None,  # set when published to GitHub Releases (Phase 10)
        "sources": sources,
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--eg-drugs", type=Path, required=True)
    ap.add_argument("--rxnorm-cache", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--sfda-local", type=Path)
    ap.add_argument("--sfda-nonlocal", type=Path)
    args = ap.parse_args()
    sfda_files = {kind: path for kind, path in (("local", args.sfda_local), ("nonlocal", args.sfda_nonlocal)) if path}
    print(json.dumps(build(args.eg_drugs, args.rxnorm_cache, args.out, sfda_files=sfda_files), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
