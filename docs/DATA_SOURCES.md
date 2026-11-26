# Data sources

## eg-drugs (Egypt)

- Repo: `abduallahJamal/eg-drugs` (fork of `mahmoudfalous/eg-drugs`). Data license CC BY 4.0, attribution required (see LICENSES.md).
- Local copy: `data/raw/eg-drugs/eg_drugs.csv` at commit `64660b26950a13289d43107a42e4b075bbb73be5` (stored in `SOURCE_COMMIT`), fetched 2026-11-21, 7,457,308 bytes.
- Columns (actual): `id, name, arabic, active, company, price, oldprice, barcode, barcode_valid, slug, units, description, uses`.

Measured on that copy (27,617 rows):

| Field | Non-empty rows |
|---|---|
| `arabic` (Arabic name) | 27,612 |
| `company` | 27,092 |
| `description` (category, English, e.g. "cold products") | 26,286 |
| `active` (ingredients joined with `+`) | 24,689 |
| `barcode` | 10,900 |
| `barcode_valid = 1` | 10,851 |
| `uses` (Arabic) | 8,237 |

Notes for the adapter (Phase 2):
- `name` mixes brand, strength, pack size and form (`"1 2 3 (one two three) 20 f.c.tabs"`), so strength and form must be parsed out.
- Check `barcode_valid` independently with our own GS1 check (`medguide_engine.text.gtin`), and record any disagreement in the quality report.
- `uses` is Arabic text from the source. Show it verbatim with source attribution, never rewritten.
- Prices are not medical information. Whether to show them is a product decision (not decided yet).

### Findings that change how the adapter must behave (measured 2026-11-21)

- **89 rows** have "illegal import" / "imported" / "مستورد" in the name. They must not be marked
  `REGISTERED`. Proposed: `IMPORTED` only when the source says imported, never inferring registration.
  The `(illegal import)` text is the source's own wording, kept verbatim in provenance.
- **398 barcodes** appear on more than one row (up to 6 rows for one barcode). A barcode that maps to several
  products cannot by itself give `IDENTIFIED`; the fusion step must treat it as several candidates.
- Many rows are cosmetics or supplements (`hair care` 976, `skin care` 890, `sun block` 229, ...).
  **Decision (user, 2026-11-21): keep cosmetics and supplements** in the database, with their source category.
- 1,331 rows have an empty `description` (category).
- Arabic micrograms appear as "مكجم" → added to the strength parser.

## SFDA (Saudi Arabia)

- Official open-data snapshots dated 2023-12-12: [local products](https://www.sfda.gov.sa/ar/node/284)
  and [non-local products](https://www.sfda.gov.sa/ar/node/285). Input workbook hashes are in
  `data_sources.version_ref` and the original worksheet coordinates are in `products.source_record_id`.
- The adapter checks the worksheet schema and logs duplicate rows within each workbook and rows with no trade name.
  Pack size comes from Size and SizeUnit. The workbook contains no GTIN, price, or registration number.
  The registration record refers to the dated source. Current market availability is unknown.
- ScientificName is preserved as written and indexed for search. Commas may be part of a chemical
  name, so this field is not split into ingredient links or matched to RxNorm.
