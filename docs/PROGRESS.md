# Progress log

## 2026-11-21 — Phase 1 (foundation)

### Environment check (actual results)

| Tool | Found | Notes |
|---|---|---|
| OS | Windows 11 Pro 22000, i7-1255U, 40 GB RAM | |
| Disk free | C: 23.6 GB, D: 13.7 GB, E: 29.7 GB, **F: 153.8 GB** | Put the Android SDK + Gradle cache on F: |
| Node / npm | 24.21.0 / 11.19.0 | OK |
| Python | 3.11.5, 3.10, 3.14.7 (default) | Engine venv uses **3.11** (matches CLAUDE.md) |
| Git | 2.55.0 | OK |
| Java | OpenJDK 17.0.13 (Temurin), JAVA_HOME set | OK for Gradle/Android |
| Android Studio | installed (2024.1 and 2025.3.4) | |
| **Android SDK / adb** | **MISSING** | No SDK in `%LOCALAPPDATA%\Android\Sdk`, `adb` not on PATH, `ANDROID_HOME` unset |
| Phone | not detectable (no adb) | |

### Done
- Git repo (`main`), folder structure per CLAUDE.md §13, `.gitignore`, AGPL-3.0 `LICENSE` (gnu.org text), README, ARCHITECTURE, LICENSES.
- `shared/fixtures/` — shared normalization (37 cases) and GTIN (12 cases) fixtures.
- `engine/`: text normalization, GTIN check digit / GTIN-14, local FastAPI with `GET /api/v1/health`
  (reports only components that actually exist). **pytest: 65 passed.**
  Health endpoint verified live with uvicorn on 127.0.0.1 → HTTP 200.
- `mobile/`: Expo SDK 58 + RN 0.88.1 + TypeScript strict, Expo Router (`src/app/`), expo-dev-client,
  Jest with the same shared fixtures.
  - **Jest: 63 passed, 100% coverage** of `src/text`. `tsc --noEmit`: clean. `expo-doctor`: 20/20.
  - `expo export --platform android` builds the Hermes bundle (2.4 MB) → app code compiles. Not yet run on a device.
  - Problems hit and fixed: (1) the first `npm install` left out jest-expo/@types/jest because of a peer
    conflict (`react-dom@19.3.1` wants `react@19.3.1`, SDK pins 19.3.0). Fixed with `npx expo install react-dom`
    (→ 19.3.0), no `--force`. (2) TypeScript 6 no longer loads `@types/*` automatically → `"types": ["jest","node"]` in tsconfig.
  - Note: `@types/node` is only present as a transitive dependency; add it explicitly when the network is faster.
- Phase 2 groundwork: eg-drugs license verified (CC BY 4.0), CSV fetched at a pinned commit and profiled
  (docs/DATA_SOURCES.md); `data_pipeline/schema/001_initial.sql` (all 21 tables from §5) loads cleanly in SQLite 3.42 with FTS5 available.
- Network on this machine is very slow (2–10 s per npm registry request); installs take 10+ minutes.

### Blocked
- Running the development build on the phone needs the Android SDK (platform-tools, a platform, build-tools) and a phone with USB debugging.

### Next
- Install Android SDK → `npx expo run:android` on the phone.
- Phase 2: data source adapters (eg-drugs, SFDA, openFDA, RxNorm), DB schema, build.

## 2026-11-21 — Project moved
- The whole repository moved from `Desktop\MedGuide` to `C:\Users\userw\MedGuide2` (same drive, a rename: node_modules and the venv were kept).
  Re-verified after the move: pytest 65/65, Jest 63/63, tsc clean.
- Measured download speed: ~129 KB/s (≈1 Mbit/s) from dl.google.com.
  Build-approach decision (local SDK vs GitHub Actions) is waiting on the user; recommendation: local SDK (see chat / BUILD_AND_RELEASE.md).

## 2026-11-21 — Android SDK + phone
- Android SDK at `F:\Android\Sdk` (ANDROID_HOME), Gradle cache `F:\gradle-home`. Command-line tools 16111833 (SHA-1 verified).
  Google replaced `sdkmanager` with the **Android CLI** (1.1.16919734, self-downloads ~76 MB to `%USERPROFILE%\.android\bin`).
  The user agreed to the Android SDK Terms (developer.android.com/studio/terms). All CLI calls use `--no-metrics`.
- Installed: platform-tools 37.0.3 (adb 1.0.41). Installing: platforms/android-37.0, build-tools/37.0.0, ndk/27.1.12297006.
- **Phone (via adb over USB):** Samsung Galaxy S9+ `SM-G965U`, Android 9 (API 28), Snapdragon 845 (sdm845), arm64-v8a,
  5.6 GB RAM. **Only 2.8 GB free storage (95% full)** → keep the APK and models small; a 200 MB APK still fits.
- First USB attempts were not detected by Windows at all (no PnP device); fixed on the user's side (cable/port).

## 2026-11-24 — Phase 2 data review

- Rebuilt SQLite from the provided eg-drugs CSV, RxNorm cache, and both SFDA 2023 Excel files.
- Egypt: 27,617 products. Saudi Arabia: 10,581 published rows retained after removing duplicate or unnamed rows.
  Scientific names from SFDA are searchable and preserved in provenance. Registration is a dated snapshot.
- Generated a review CSV with 50 records per product source and a manifest with the database SHA-256.
- Python engine: 152 tests passed. Data pipeline: 15 tests passed. Mobile TypeScript: typecheck passed.
- This workspace has no attached Android device or Android SDK. Device launch and APK installation remain unverified.
- No openFDA label cache or API key was available. The release contains no US monographs or translations.
- Review checkpoint 1: inspect the three source samples before proceeding to image-dataset verification and training.
- Mobile Jest: 150 tests passed by invoking the CLI through Node (the imported Windows shims were not executable).

## 2026-11-24 — Image dataset preparation tooling

- Reviewed publisher dataset cards and documented licensing, reported size, and remaining checks in IMAGE_DATA.md.
- Added two Colab notebooks and a shared COCO inspection, conversion and product-disjoint splitting script.
- Data pipeline: 16 tests passed including a controlled image fixture covering conversion and grouped splits.
- Both source connections timed out from this workspace. Original image inspection, training, and metric reporting require the actual licensed files and verified product IDs.

## 2026-11-24 — Local product catalog API

- Added read-only SQLite queries and local FastAPI endpoints for search, details and source provenance.
- Search accepts Arabic or English text and valid GTINs, with an optional country filter. A shared GTIN returns all matching candidates up to the requested limit.
- Ran 153 Python engine tests. Also exercised Arabic and English searches and the detail and source routes against the bundled Egyptian and Saudi database.
- Image ingestion and training deferred at the user's request. Mobile integration and APK verification remain pending.

## 2026-11-24 — Android catalog screens

- Added Arabic search and product details backed by the bundled SQLite catalog. Search and details use local queries with bound parameters. Source links open on demand.
- Setup verifies the database against its manifest and uses a content-specific filename to refresh the on-device copy when the database changes.
- 152 Jest tests passed. Search and detail SQL ran against the bundled database. Expo SDK 58 documents SQLite asset import and FTS support.
- Installing expo-sqlite timed out. TypeScript and ESLint are blocked on resolving that module. Android native build and on-device behavior remain unverified.

## 2026-11-24 — Catalog provenance and market status

- Added a Sources screen reading publisher, license and attribution from SQLite.
- Product details now include the publisher's record identifier and sourced market status. The Saudi 2023 registration snapshot is displayed separately from current availability.
- Verified the actual detail SQL against Egyptian and Saudi records, and verified that the source list returns all four publishers. 152 Jest tests passed.
- Full Expo typecheck, lint dependency resolution and Android execution remain pending because expo-sqlite is unavailable in this environment.

## 2026-11-25 — Local recognition and export

- Verified MedPackID v1 archive hashes and matching image/label inventory. Added the reviewed YOLO11 Colab notebook with provenance-aware product grouping and post-export checks. Colab required sign-in, so training was not run.
- Ran PaddleOCR PP-OCRv5 Arabic and Latin on 36 publisher-box crops, exported the three ONNX models, and compared their tensor outputs against Paddle on CPU.
- Extracted DINOv2 ViT-S/14 vectors, wrote an exploratory FAISS index, and exported and tested a quantized ONNX graph. Verified catalog mappings and independent test images are still needed.
- Added the local reference pipeline, SQLite evidence fusion, constrained barcode parsing and regression coverage. Added the camera/gallery flow and model packaging for Expo. Read the delivery report for the native build and device status.
