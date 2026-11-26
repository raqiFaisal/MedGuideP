# MedGuide — دليلك الدوائي الذكي

An Android app that identifies a medicine box from the camera **entirely on the phone**
(YOLO11 detection, OpenCV preprocessing, barcode/GS1, PaddleOCR, DINOv2 visual
fingerprints, fuzzy matching), then shows sourced information in Arabic and reads it aloud.

> Status: **Phase 2 data review.** Nothing in this repository identifies
> medicines yet. See [docs/PROGRESS.md](docs/PROGRESS.md).

## Repository layout

| Path | What it is |
|---|---|
| `mobile/` | React Native + Expo (development build) app |
| `engine/` | Python reference implementation of the recognition pipeline + local-only FastAPI |
| `data_pipeline/` | Source adapters and the SQLite drug database builder |
| `notebooks/` | Google Colab notebooks (inspection, training, evaluation, export) |
| `shared/fixtures/` | Test cases shared by Python and TypeScript (parity principle) |
| `models/` | Model configs and model card (`models/README.md`); weights are not in Git |
| `docs/` | Architecture, data sources, licenses, progress, testing |

## Quick start (development)

```powershell
# Python engine
cd engine
py -3.11 -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
.venv\Scripts\python -m pytest
.venv\Scripts\python -m uvicorn server:app --port 8000   # local dev only

# Mobile
cd mobile
npm install
npm test
npx expo run:android      # requires Android SDK + a connected phone
```

## License

AGPL-3.0 — see [LICENSE](LICENSE). Ultralytics YOLO11 is AGPL-3.0, so this whole
project is licensed under the same license. Third-party licenses: [docs/LICENSES.md](docs/LICENSES.md).

## Medical disclaimer

MedGuide does not diagnose, prescribe, or replace a doctor or pharmacist.

## Local catalog API

From the project root, after installing the engine and its development dependencies:

```text
python -m uvicorn server:app --app-dir engine --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000/docs to try search, product details and source provenance.
The API reads `data/processed/build/medguide.db` by default. Set the
`MEDGUIDE_DB_PATH` environment variable to use a different build of the database.
A GTIN lookup lists matching catalog entries, including multiple matches when the
identifier is shared. The country filter selects the catalog market.

## Android offline catalog

From the extracted project:

```powershell
cd mobile
npm ci
npm run catalog:setup
npm run typecheck
npx expo run:android
```

Setup copies the bundled database from `data/processed/build`, checks its SHA-256,
and installs the SDK-compatible SQLite dependency through Expo. Build with
Android SDK and an emulator or connected phone. After installation, search can
read the bundled database on the phone. Opening publisher URLs requires internet.

## مسار التعرف وتقييمه

- [تقرير التسليم](docs/DELIVERY_AR.md) يصف المخرجات الفعلية وحالة بناء Android.
- [دليل التشغيل](docs/RUN_VISION.md) يصف تنزيل MedPackID من داخل Colab، تدريب YOLO، OCR، إعداد فهرس DINOv2، التقييم وبناء التطبيق.
- [النماذج وتقارير التصدير](models/README.md) ونتائج التشغيل في `reports/`.
