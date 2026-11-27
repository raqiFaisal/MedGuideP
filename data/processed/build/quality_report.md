# Quality report — medguide.db

Built 2026-11-26T22:52:45+00:00 · DB version 0.2.0 · eg-drugs commit `64660b26950a13289d43107a42e4b075bbb73be5`

All numbers below are measured on this build. Nothing is estimated.

## eg-drugs (Egypt)

| Measure | Value |
|---|---|
| Rows read | 27,617 |
| Products loaded | 27,617 |
| Rejected (no id or no name) | 0 |
| Strength parsed | 16,894 (61.2%) |
| Dosage form detected | 24,952 (90.4%) |
| Has a barcode | 10,900 (39.5%) |
| Barcode passes our GS1 check | 10,851 (39.3%) |
| GTINs shared by more than one product | 396 (covering 812 products) |
| Marked imported by the source → IMPORTED | 96 |
| All others → AVAILABILITY_UNKNOWN (not inferred) | 27,521 |
| Has Arabic `uses` text (verbatim) | 8,237 (29.8%) |
| Product–ingredient links | 62,361 |
| FTS5 search index | built |

### Parser warnings

| Warning | Rows |
|---|---|
| barcode fails GS1 check | 49 |

### Dosage forms

| Form | Products |
|---|---|
| TABLET | 4,780 |
| CAPSULE | 3,513 |
| FILM_COATED_TABLET | 3,331 |
| INJECTION | 2,739 |
| (none) | 2,665 |
| CREAM | 2,515 |
| SYRUP | 1,409 |
| GEL | 1,088 |
| SACHET | 1,083 |
| SUSPENSION | 580 |
| LOTION | 568 |
| SPRAY | 532 |
| DROPS | 501 |
| SHAMPOO | 484 |
| EYE_DROPS | 445 |
| SOLUTION | 340 |
| OINTMENT | 266 |
| CHEWABLE_TABLET | 233 |
| SUPPOSITORY | 188 |
| NASAL_SPRAY | 144 |
| POWDER | 114 |
| EFFERVESCENT_TABLET | 99 |

### Top 15 categories (source wording; cosmetics/supplements kept by user decision)

| Category | Products |
|---|---|
| (empty) | 1,331 |
| hair care | 976 |
| skin care | 890 |
| multivitamin | 863 |
| multivitamins | 501 |
| antineoplastic | 436 |
| dietary supplement | 351 |
| psychiatric.antipsychotics | 305 |
| antibiotic.quinolone | 295 |
| peptic ulcer.proton pump inhibitor | 281 |
| antibiotic.cephalosporin.third-generation | 280 |
| iron supplement | 277 |
| massage | 261 |
| psychiatric.antidepressants | 260 |
| sun block | 229 |

## Active ingredients and RxNorm

- Distinct active ingredients in the DB: 8,510
- Mapped to an RxNorm ingredient (exact match only): 0 (0.0%)
- RxNorm lookup cache used: 0 names looked up; status counts {}
- Ingredients not in the cache yet are stored with their source name and no RxCUI.

## SFDA (Saudi Arabia)

| Source | Rows read | Products loaded | Duplicates or missing name |
|---|---:|---:|---:|
| sfda-2023-local | 3,073 | 2,637 | 436 |
| sfda-2023-nonlocal | 10,295 | 7,944 | 2,351 |

The supplied lists are a December 2023 snapshot. They have no GTIN or registration number.
Scientific names are stored verbatim in provenance. Current market availability is unknown.

## Not included in this build

- openFDA ingredient information: not fetched yet.
- DDInter: terms not verified (site unreachable) — excluded.
