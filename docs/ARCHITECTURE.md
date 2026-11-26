# Architecture

## Decision: everything runs on the phone

No deployed server. All inference runs on the device and the drug database is a
read-only SQLite file bundled with the app. Reasons (CLAUDE.md §2):

- **Privacy:** photos of medicine boxes reveal a person's illnesses; they never leave the phone.
- **Connectivity:** internet in Yemen (a target market) is weak and intermittent.
- **Cost:** free hosting tiers are too small for PyTorch/vision models.

The privacy and offline reasons hold even if free hosting tiers change, so the
decision does not depend on re-checking those tiers.

## Three components

```
 Google Colab + Drive           engine/ (Python, reference)        mobile/ (React Native)
 ───────────────────            ──────────────────────────         ──────────────────────
 inspect datasets               full pipeline: OpenCV, YOLO11,     same pipeline with
 train / evaluate               PaddleOCR, zxing-cpp, DINOv2,      quantized ONNX/TFLite
 export + quantize   ───────►   FAISS, RapidFuzz                   models, offline
 build FAISS index              local FastAPI (dev only)           expo-sqlite DB
          │                              │                                ▲
          └──── models, embeddings ──────┴──── medguide.db ───────────────┘
```

## Parity principle

Every pipeline stage exists in `engine/medguide_engine/` and in `mobile/src/recognition/`
with the same interface. Deterministic logic (normalization, GTIN/GS1, strength parsing,
fuzzy matching, evidence fusion) is tested against the **same fixture files** in
`shared/fixtures/`, loaded by both pytest and Jest. Model-based stages are compared on
the same images through a hidden developer export mode (Phase 8).

## Recognition pipeline (CLAUDE.md §7)

1. Validate image (blur, brightness, resolution)
2. Detect box (YOLO11n; swappable detector interface for licensing reasons)
3. Preprocess (crop, perspective, CLAHE) — keep the full-resolution copy for OCR/barcode
4. Barcode (DataMatrix/GS1, EAN-13) — accepted only after two identical reads + valid check digit
5. OCR (PaddleOCR PP-OCRv5, Arabic + Latin)
6. Field extraction (brand, strength, form, manufacturer)
7. Candidate retrieval + text matching (RapidFuzz)
8. Visual similarity (DINOv2 ViT-S/14) — supporting evidence only
9. Evidence fusion with weights in one config file; thresholds tuned on validation data
10. Result: `IDENTIFIED` / `NEEDS_CONFIRMATION` / `NOT_IDENTIFIED`

## Deviations from CLAUDE.md (recorded as they happen)

| Topic | CLAUDE.md | Actual | Why |
|---|---|---|---|
| Expo Router screens folder | `mobile/app/` | `mobile/src/app/` | Current Expo convention for the `src/` layout (docs.expo.dev/router/installation, Oct 2026) |
| Shared test cases | not specified | `shared/fixtures/*.json` | Enforces identical Python/TS behaviour from one source of truth |
