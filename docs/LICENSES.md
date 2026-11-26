# Licenses

Every library, model, dataset, and font that ships in the app or is used to build it
is listed here **after** its license has been checked. Status values: `verified`
(license text read from the official source), `to-verify` (not yet checked — must not
ship until verified).

## Project

| Item | License | Status |
|---|---|---|
| MedGuide source code | AGPL-3.0-only (`LICENSE`, text from gnu.org) | verified |

## Tooling and libraries in use (Phase 1)

| Item | Version | License | Status |
|---|---|---|---|
| Expo SDK | 58 | MIT | to-verify |
| React Native | 0.88.1 | MIT | to-verify |
| Expo Router | (SDK 58) | MIT | to-verify |
| expo-sqlite | Expo SDK 58 (~58.0.18) | MIT | publisher documentation reviewed, install pending |
| FastAPI | see `engine/pyproject.toml` | MIT | to-verify |
| Uvicorn | 0.x | BSD-3-Clause | to-verify |
| Pydantic | 2.x | MIT | to-verify |
| RapidFuzz | 3.x | MIT | to-verify |
| openpyxl | 3.1.5 (tested) | MIT | verified from installed distribution metadata (build only) |
| Pillow | 13.0.0 (tested) | MIT-CMU | verified from installed distribution metadata (build only) |
| pytest | 9.x | MIT | to-verify (dev only) |
| Jest / jest-expo | — | MIT | to-verify (dev only) |

## Data sources

| Source | License | Status | Attribution required |
|---|---|---|---|
| eg-drugs (`abduallahJamal/eg-drugs`, fork of `mahmoudfalous/eg-drugs`), `data/` folder | CC BY 4.0 (`LICENSE-DATA`); repo code is MIT | verified 2026-11-21 from the repo's `LICENSE` and `LICENSE-DATA` | Yes — "Egyptian Drug Database (`eg-drugs`) by Mahmoud Mohamed (https://github.com/mahmoudfalous/eg-drugs)" must appear in the app's Sources screen |

| SFDA 2023 registered human drugs (local and non-local) | [SFDA open-data terms](https://www.sfda.gov.sa/ar/open-data?page=2) | Official listing reviewed 2026-11-24 | Attribute the SFDA and date both snapshots |
| openFDA (drug label, NDC) | CC0 1.0 (open.fda.gov/terms, /license); page warns some data may not be public domain | verified 2026-11-21 | Not required; we show "Data provided by the U.S. Food and Drug Administration (https://open.fda.gov)" |
| RxNorm via RxNav API (NLM-created names and RxCUIs only) | Public domain (nlm.nih.gov RxNorm terms of service). Third-party sources inside full RxNorm are restricted, so we keep only `RXNORM`-sourced names | verified 2026-11-21 | Yes: "This product uses publicly available data from the U.S. National Library of Medicine (NLM)..." and must say if data is not the most current |
| DailyMed | Only setid **links** are stored, not label text (copyright of company-submitted SPL text is not settled on NLM pages) | verified 2026-11-21 | "Courtesy of the U.S. National Library of Medicine" |
| MedlinePlus | Links only. ASHP drug monographs and A.D.A.M. content are copyrighted → never copied | verified 2026-11-21 | "Courtesy of MedlinePlus from the National Library of Medicine" |
| DDInter 2.0 | **Not verified** — site unreachable from this machine (proxy error, 2 tries). Excluded until its terms are read | blocked | — |

## Planned (from CLAUDE.md, not yet used — verify before first use)

Ultralytics YOLO11 (AGPL-3.0), PaddleOCR (Apache-2.0), DINOv2 weights (check),
FAISS (MIT), zxing-cpp (Apache-2.0), OpenCV (Apache-2.0), react-native-vision-camera,
react-native-fast-tflite, onnxruntime-react-native, react-native-fast-opencv,
IBM Plex Sans / Plex Sans Arabic (OFL-1.1), MADLAD-400 or opus-mt-en-ar,
eg-drugs (CC BY 4.0), openFDA, DailyMed, RxNorm, DDInter 2.0, image datasets (CLAUDE.md §4.ب).

## إضافات مسار التعرف

- [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR/blob/main/LICENSE) و[Paddle2ONNX](https://github.com/PaddlePaddle/Paddle2ONNX/blob/develop/LICENSE): Apache-2.0. نماذج PP-OCRv5 Mobile الرسمية من PaddleOCR/PaddleX.
- [Meta DINOv2](https://github.com/facebookresearch/dinov2/blob/main/MODEL_CARD.md): Apache-2.0 لـ ViT-S/14، بما في ذلك الأوزان المستخدمة. الإصدار المرجعي: `dinov2_vits14_pretrain.pth` من رابط Meta في مستودع DINOv2. النسخة هنا محوّلة ومكمّمة.
- [ONNX Runtime](https://github.com/microsoft/onnxruntime/blob/main/LICENSE): MIT. الهاتف يستخدم `onnxruntime-react-native` 1.24.3.
- [FAISS](https://github.com/facebookresearch/faiss/blob/main/LICENSE): MIT. [ZXing-C++](https://github.com/zxing-cpp/zxing-cpp/blob/master/LICENSE): Apache-2.0. [OpenCV](https://github.com/opencv/opencv/blob/4.x/LICENSE): Apache-2.0.
- [Expo modules](https://github.com/expo/expo/blob/main/LICENSE): MIT. SDK 58 مع `expo-camera` و`expo-image-picker` و`expo-image-manipulator` و`expo-file-system` و`expo-asset` و`expo-sqlite`. يستخدم Expo Camera مكتبة Google ML Kit المضمّنة لمسح الباركود في Android. [مكتبة jpeg-js](https://github.com/jpeg-js/jpeg-js/blob/master/LICENSE): BSD-3-Clause.
- [MedPackID v1](https://data.mendeley.com/datasets/d23kndp3sv/1)، DOI 10.17632/d23kndp3sv.1، تأليف Qory Hidayati وHendra Kusuma وMuhammad Attamimi، CC BY 4.0. المخرجات الاستكشافية مشتقة من قص المربعات المنشورة ثم توليد بصمات وقراءات نصية. الصور الأصلية غير مضمّنة في ملف التسليم.
- [Medication Boxes Arabe Latin](https://huggingface.co/datasets/ApyHTML19/Medication_Boxes_Arabe_Latin)، MIT حسب بطاقة الناشر. تُستخدم عينة قصاصات من مربعات COCO مع حفظ أسماء المصدر والإحداثيات.
