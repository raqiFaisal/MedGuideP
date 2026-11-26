"""Local image analysis. Dependencies are loaded only when a stage is configured."""
from __future__ import annotations

from pathlib import Path
from time import perf_counter
import warnings

import numpy as np
from PIL import Image, ImageOps

from .barcode import read_barcodes
from .recognition import RULES, recognize


def image_rgb(path: Path) -> np.ndarray:
    with warnings.catch_warnings(), Image.open(path) as original:
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        if original.width * original.height > 30_000_000 or min(original.size) < 32:
            raise ValueError(f"Unsupported image dimensions: {original.size}")
        image = ImageOps.exif_transpose(original).convert("RGB")
        return np.array(image)


MODEL_NAMES = {"arabic": "arabic_PP-OCRv5_mobile_rec", "latin": "latin_PP-OCRv5_mobile_rec"}


class PaddleReader:
    def __init__(self, model_root: Path | None = None):
        from paddleocr import PaddleOCR

        self.pipelines = {}
        for language, name in MODEL_NAMES.items():
            local = {} if model_root is None else {
                "text_detection_model_dir": str(model_root / "PP-OCRv5_mobile_det"),
                "text_recognition_model_dir": str(model_root / name),
            }
            self.pipelines[language] = PaddleOCR(
                text_detection_model_name="PP-OCRv5_mobile_det", text_recognition_model_name=name,
                device="cpu", cpu_threads=2, use_doc_orientation_classify=False, use_doc_unwarping=False,
                use_textline_orientation=False, enable_mkldnn=False,
                text_det_limit_side_len=960, text_det_limit_type="max", **local,
            )

    def __call__(self, rgb: np.ndarray) -> list[dict]:
        lines = []
        bgr = np.ascontiguousarray(rgb[:, :, ::-1])
        for language, pipeline in self.pipelines.items():
            for result in pipeline.predict(bgr):
                for text, confidence, polygon in zip(result["rec_texts"], result["rec_scores"], result["rec_polys"], strict=True):
                    lines.append(dict(language=language, text=text, confidence=float(confidence),
                                      polygon=np.asarray(polygon).tolist()))
        return lines


class Analyzer:
    def __init__(self, detector: Path | None = None, ocr: PaddleReader | None = None, visual=None):
        self.detector = None
        if detector:
            from ultralytics import YOLO
            if not detector.is_file():
                raise FileNotFoundError(detector)
            self.detector = YOLO(str(detector), task="detect")
        self.ocr = ocr
        self.visual = visual

    def __call__(self, db, image: Path) -> dict:
        import cv2

        start = perf_counter()
        rgb = image_rgb(image)
        gray = cv2.cvtColor(
            cv2.resize(rgb, (320, max(1, round(rgb.shape[0] * 320 / rgb.shape[1])))), cv2.COLOR_RGB2GRAY
        )
        quality = {"brightness": float(gray.mean()), "sharpness": float(cv2.Laplacian(gray, cv2.CV_64F).var()),
                   "width": rgb.shape[1], "height": rgb.shape[0]}
        crop, region = rgb, None
        if self.detector is not None:
            prediction = self.detector.predict(np.ascontiguousarray(rgb[:, :, ::-1]), imgsz=640,
                                               conf=RULES["min_detector_score"], iou=.45, rect=False, verbose=False, device="cpu")[0]
            if len(prediction.boxes) == 1:
                x1, y1, x2, y2 = prediction.boxes.xyxy[0].tolist()
                h, w = rgb.shape[:2]
                dx, dy = (x2 - x1) * .04, (y2 - y1) * .04
                region = [max(0, int(x1 - dx)), max(0, int(y1 - dy)),
                          min(w, int(x2 + dx + 1)), min(h, int(y2 + dy + 1))]
                x1, y1, x2, y2 = region
                crop = rgb[y1:y2, x1:x2]
            elif len(prediction.boxes) > 1:
                return {**recognize(db, [], [], {}), "reason": "MULTIPLE_PACKS", "quality": quality,
                        "crop_xyxy": None, "time_ms": (perf_counter() - start) * 1000}

        reads = read_barcodes(crop)
        lines = self.ocr(crop) if self.ocr else []
        visual = self.visual(crop) if self.visual else {}
        return {**recognize(db, reads, lines, visual), "quality": quality, "crop_xyxy": region,
                "time_ms": (perf_counter() - start) * 1000}
