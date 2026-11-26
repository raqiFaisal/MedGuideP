-- MedGuide drug database (medguide.db), schema version 1.
-- Read-only on the phone. Built by data_pipeline/build_db.py.
-- Concept (active ingredient) is separate from commercial product and from package (CLAUDE.md §5).

PRAGMA foreign_keys = ON;

CREATE TABLE meta (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE data_sources (
  id            INTEGER PRIMARY KEY,
  code          TEXT NOT NULL UNIQUE,          -- 'eg-drugs', 'sfda', 'openfda', ...
  name          TEXT NOT NULL,
  url           TEXT NOT NULL,
  license       TEXT NOT NULL,
  attribution   TEXT,
  version_ref   TEXT,                          -- commit sha / file date / API version
  fetched_at    TEXT NOT NULL                  -- ISO-8601
);

CREATE TABLE ingestion_jobs (
  id            INTEGER PRIMARY KEY,
  source_id     INTEGER NOT NULL REFERENCES data_sources(id),
  started_at    TEXT NOT NULL,
  finished_at   TEXT,
  status        TEXT NOT NULL CHECK (status IN ('running','succeeded','failed')),
  rows_read     INTEGER NOT NULL DEFAULT 0,
  rows_loaded   INTEGER NOT NULL DEFAULT 0,
  rows_rejected INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE ingestion_logs (
  id        INTEGER PRIMARY KEY,
  job_id    INTEGER NOT NULL REFERENCES ingestion_jobs(id),
  level     TEXT NOT NULL CHECK (level IN ('info','warning','error')),
  record_ref TEXT,
  message   TEXT NOT NULL
);

CREATE TABLE countries (
  code    TEXT PRIMARY KEY,                    -- ISO 3166-1 alpha-2: EG, SA, YE
  name_ar TEXT NOT NULL,
  name_en TEXT NOT NULL
);

CREATE TABLE manufacturers (
  id              INTEGER PRIMARY KEY,
  name            TEXT NOT NULL,
  name_normalized TEXT NOT NULL,
  country_code    TEXT REFERENCES countries(code),
  UNIQUE (name_normalized)
);

CREATE TABLE active_ingredients (
  id              INTEGER PRIMARY KEY,
  name_en         TEXT NOT NULL,               -- preferred name (RxNorm where mapped)
  name_ar         TEXT,
  name_normalized TEXT NOT NULL UNIQUE
);

CREATE TABLE ingredient_synonyms (
  id                INTEGER PRIMARY KEY,
  ingredient_id     INTEGER NOT NULL REFERENCES active_ingredients(id),
  synonym           TEXT NOT NULL,
  synonym_normalized TEXT NOT NULL,
  language          TEXT NOT NULL CHECK (language IN ('en','ar')),
  source_id         INTEGER REFERENCES data_sources(id),
  UNIQUE (ingredient_id, synonym_normalized)
);

CREATE TABLE rxnorm_mappings (
  ingredient_id INTEGER PRIMARY KEY REFERENCES active_ingredients(id),
  rxcui         TEXT NOT NULL,
  tty           TEXT,                          -- RxNorm term type (IN, PIN, MIN)
  mapped_at     TEXT NOT NULL
);

CREATE TABLE products (
  id                 INTEGER PRIMARY KEY,
  brand_name_en      TEXT,
  brand_name_ar      TEXT,
  brand_normalized   TEXT NOT NULL,            -- normalize_text(brand) for matching
  strength_text      TEXT,                     -- as written in the source
  strength_normalized TEXT,                    -- e.g. '500 MG', '250 MG/5 ML'
  dosage_form        TEXT,                     -- unified value from the form dictionary
  manufacturer_id    INTEGER REFERENCES manufacturers(id),
  country_code       TEXT NOT NULL REFERENCES countries(code),
  category_text      TEXT,                     -- source category, verbatim
  uses_ar            TEXT,                     -- verbatim from source; never generated
  source_id          INTEGER NOT NULL REFERENCES data_sources(id),
  source_record_id   TEXT NOT NULL,
  UNIQUE (source_id, source_record_id)
);

CREATE TABLE product_ingredients (
  product_id    INTEGER NOT NULL REFERENCES products(id),
  ingredient_id INTEGER NOT NULL REFERENCES active_ingredients(id),
  strength_text TEXT,
  position      INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (product_id, ingredient_id)
);

CREATE TABLE product_registrations (
  id                  INTEGER PRIMARY KEY,
  product_id          INTEGER NOT NULL REFERENCES products(id),
  country_code        TEXT NOT NULL REFERENCES countries(code),
  registration_number TEXT,
  authority           TEXT,                    -- 'SFDA', 'EDA', ...
  source_id           INTEGER NOT NULL REFERENCES data_sources(id)
);

CREATE TABLE market_availability (
  product_id   INTEGER NOT NULL REFERENCES products(id),
  country_code TEXT NOT NULL REFERENCES countries(code),
  status       TEXT NOT NULL CHECK (status IN ('REGISTERED','MARKETED','IMPORTED','AVAILABILITY_UNKNOWN')),
  source_id    INTEGER REFERENCES data_sources(id),
  verified_at  TEXT,
  PRIMARY KEY (product_id, country_code)
);

CREATE TABLE packages (
  id          INTEGER PRIMARY KEY,
  product_id  INTEGER NOT NULL REFERENCES products(id),
  description TEXT,                            -- pack size as written ("20 tabs")
  price       REAL,
  currency    TEXT,
  price_date  TEXT,
  source_id   INTEGER NOT NULL REFERENCES data_sources(id)
);

CREATE TABLE product_identifiers (
  id         INTEGER PRIMARY KEY,
  product_id INTEGER NOT NULL REFERENCES products(id),
  package_id INTEGER REFERENCES packages(id),
  kind       TEXT NOT NULL CHECK (kind IN ('GTIN14','REGISTRATION')),
  value      TEXT NOT NULL,
  check_ok   INTEGER NOT NULL CHECK (check_ok IN (0,1)),  -- our own GS1 check
  source_id  INTEGER NOT NULL REFERENCES data_sources(id)
);

CREATE TABLE product_images (
  id          INTEGER PRIMARY KEY,
  product_id  INTEGER NOT NULL REFERENCES products(id),
  dataset_id  INTEGER NOT NULL REFERENCES dataset_registry(id),
  image_ref   TEXT NOT NULL,                   -- path inside the dataset
  verified    INTEGER NOT NULL CHECK (verified IN (0,1))
);

CREATE TABLE visual_embeddings (
  id              INTEGER PRIMARY KEY,
  product_image_id INTEGER NOT NULL REFERENCES product_images(id),
  product_id      INTEGER NOT NULL REFERENCES products(id),
  model           TEXT NOT NULL,               -- e.g. 'dinov2-vits14-int8'
  row_index       INTEGER NOT NULL,            -- row in the exported embedding matrix
  UNIQUE (model, row_index)
);

CREATE TABLE ingredient_monographs (
  id                    INTEGER PRIMARY KEY,
  ingredient_id         INTEGER NOT NULL REFERENCES active_ingredients(id),
  section               TEXT NOT NULL CHECK (section IN (
                          'indications','contraindications','boxed_warning','warnings','pregnancy',
                          'pediatric','geriatric','adverse_reactions','interactions','storage')),
  language              TEXT NOT NULL CHECK (language IN ('en','ar')),
  text                  TEXT NOT NULL,
  is_machine_translated INTEGER NOT NULL CHECK (is_machine_translated IN (0,1)),
  original_monograph_id INTEGER REFERENCES ingredient_monographs(id),
  source_id             INTEGER NOT NULL REFERENCES data_sources(id),
  source_url            TEXT NOT NULL,         -- DailyMed setid link
  CHECK (is_machine_translated = 0 OR original_monograph_id IS NOT NULL)
);

CREATE TABLE drug_interactions (
  id              INTEGER PRIMARY KEY,
  ingredient_a_id INTEGER NOT NULL REFERENCES active_ingredients(id),
  ingredient_b_id INTEGER NOT NULL REFERENCES active_ingredients(id),
  severity        TEXT,
  description     TEXT,
  source_id       INTEGER NOT NULL REFERENCES data_sources(id),
  CHECK (ingredient_a_id < ingredient_b_id)
);

CREATE TABLE information_provenance (
  id             INTEGER PRIMARY KEY,
  table_name     TEXT NOT NULL,
  row_id         INTEGER NOT NULL,
  field          TEXT NOT NULL,
  source_id      INTEGER NOT NULL REFERENCES data_sources(id),
  source_url     TEXT,
  original_value TEXT,
  normalized_value TEXT,
  fetched_at     TEXT NOT NULL,
  verified_at    TEXT,
  verification_status TEXT NOT NULL CHECK (verification_status IN ('unverified','auto_checked','manually_verified'))
);

CREATE TABLE dataset_registry (
  id       INTEGER PRIMARY KEY,
  code     TEXT NOT NULL UNIQUE,
  name     TEXT NOT NULL,
  url      TEXT NOT NULL,
  license  TEXT NOT NULL,
  usage    TEXT NOT NULL                       -- 'detection', 'retrieval', 'evaluation'
);

CREATE INDEX idx_products_brand      ON products(brand_normalized);
CREATE INDEX idx_products_country    ON products(country_code);
CREATE INDEX idx_identifiers_value   ON product_identifiers(kind, value);
CREATE INDEX idx_prod_ingr_ingr      ON product_ingredients(ingredient_id);
CREATE INDEX idx_synonyms_norm       ON ingredient_synonyms(synonym_normalized);
CREATE INDEX idx_monographs_ingr     ON ingredient_monographs(ingredient_id, section, language);
CREATE INDEX idx_provenance_row      ON information_provenance(table_name, row_id);

INSERT INTO meta(key, value) VALUES ('schema_version', '1');
