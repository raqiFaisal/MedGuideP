"""Prepare and evaluate MedGuide models with explicit data provenance."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from time import perf_counter
import unicodedata

import numpy as np
from rapidfuzz.distance import Levenshtein

from medguide_engine.catalog import open_catalog
from medguide_engine.barcode import parse_barcode
from medguide_engine.text.strength import strengths_equivalent
from medguide_engine.vision import Analyzer, PaddleReader, image_rgb
from medguide_engine.visual import DIM, MODEL_ID, Dino, OnnxDino, VisualIndex, sha256

DATABASE = Path(__file__).resolve().parents[2] / "data/processed/build/medguide.db"


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_suffix(path.suffix + ".tmp")
    pending.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    pending.replace(path)


def records(manifest: Path, images: Path, required: set[str], *, partition: str | None = None) -> list[dict]:
    root = images.resolve()
    seen = set()
    rows = []
    with manifest.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not (required | {"file_name"}) <= set(reader.fieldnames or []):
            raise ValueError(f"Required columns: {sorted(required | {'file_name'})}")
        for row in reader:
            file = (root / row["file_name"]).resolve()
            if not file.is_relative_to(root) or not file.is_file():
                raise ValueError(f"Invalid image path: {row['file_name']}")
            digest = sha256(file)
            identity = (digest, row[partition]) if partition else digest
            if identity in seen:
                raise ValueError(f"Duplicate image bytes in {manifest.name}: {file.name}")
            seen.add(identity)
            rows.append({**row, "path": file, "sha256": digest})
    if not rows:
        raise ValueError(f"Empty manifest: {manifest}")
    return rows


def text_normalize(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).split())


def ocr_report(images: Path, output: Path, manifest: Path | None, model_root: Path | None) -> None:
    if manifest:
        rows = records(manifest, images, {"language", "reference_text", "identity_source"}, partition="language")
        if any(row["language"] not in {"arabic", "latin"} or not row["identity_source"].strip()
               or not row["reference_text"].strip() for row in rows):
            raise ValueError("OCR review requires a script, nonempty transcription and source for each image")
    else:
        rows = [{"file_name": str(p.relative_to(images)), "path": p}
                for p in sorted(images.rglob("*")) if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}]
    if not rows:
        raise ValueError("No OCR crops")
    read = PaddleReader(model_root)
    predictions = []
    totals = {}
    for row in rows:
        start = perf_counter()
        lines = read(image_rgb(row["path"]))
        predictions.append(dict(file_name=row["file_name"], lines=lines, time_ms=(perf_counter() - start) * 1000))
        if manifest:
            subset = [line for line in lines if line["language"] == row["language"]]
            predicted = text_normalize(" ".join(line["text"] for line in subset))
            expected = text_normalize(row["reference_text"])
            total = totals.setdefault(row["language"], [0, 0, 0, 0, 0, 0])
            total[0] += Levenshtein.distance(expected, predicted)
            total[1] += len(expected)
            total[2] += Levenshtein.distance(expected.split(), predicted.split())
            total[3] += len(expected.split())
            total[4] += expected == predicted
            total[5] += 1
            predictions[-1].update(reference_text=expected, predicted_text=predicted,
                                   language=row["language"], identity_source=row["identity_source"])
    metrics = {lang: {"CER": t[0]/t[1], "WER": t[2]/t[3], "exact_text_rate": t[4]/t[5],
                      "reference_count": t[5]} for lang, t in totals.items()}
    write_json(output, {"coordinates": "pixels in input crop", "metrics": metrics or None,
                        "unavailable": None if manifest else "No verified transcriptions (CER/WER)",
                        "predictions": predictions})


def verified_rows(db_path: Path, manifest: Path, images: Path, *, allow_unknown=False, extra=None) -> list[dict]:
    rows = records(manifest, images, {"product_id", "identity_source"} | (extra or set()))
    with open_catalog(db_path) as db:
        for row in rows:
            pid = row["product_id"].strip()
            if not row["identity_source"].strip():
                raise ValueError(f"Missing verified product source: {row['file_name']}")
            if not pid and allow_unknown:
                row["product_id"] = None
            elif pid.isascii() and pid.isdigit() and db.execute(
                "SELECT 1 FROM products WHERE id=?", (int(pid),)
            ).fetchone():
                row["product_id"] = int(pid)
            else:
                raise ValueError(f"Product not verified against supplied catalog: {row['file_name']}")
    return rows


def build_visual(database: Path, manifest: Path, images: Path, out: Path, embed) -> None:
    import faiss

    model_sha = getattr(embed, "model_sha256", None)
    rows = verified_rows(database, manifest, images, extra={"source_code", "source_record_id"} if model_sha else None)
    if model_sha:
        with open_catalog(database) as db:
            for row in rows:
                product = db.execute("""
                    SELECT s.code, p.source_record_id
                    FROM products p JOIN data_sources s ON s.id=p.source_id WHERE p.id=?
                """, (row["product_id"],)).fetchone()
                if tuple(product) != (row["source_code"], row["source_record_id"]):
                    raise ValueError(f"Stale catalog mapping for {row['file_name']}")
    vectors = np.concatenate([embed(image_rgb(row["path"])) for row in rows]).astype("<f4")
    if vectors.shape != (len(rows), DIM) or not np.isfinite(vectors).all() or not np.allclose(
        np.linalg.norm(vectors, axis=1), 1, atol=1e-4
    ):
        raise ValueError("Embeddings must be finite, unit-length ViT-S/14 CLS vectors")
    out.mkdir(parents=True, exist_ok=True)
    index = faiss.IndexFlatIP(DIM)
    index.add(vectors)
    faiss.write_index(index, str(out / "visual.faiss.tmp"))
    (out / "visual.faiss.tmp").replace(out / "visual.faiss")
    (out / "visual.f32.tmp").write_bytes(vectors.tobytes())
    (out / "visual.f32.tmp").replace(out / "visual.f32")
    write_json(out / "visual_mapping.json", [{key: row[key] for key in
               ("file_name", "product_id", "identity_source", "sha256")} for row in rows])
    names = ("visual.faiss", "visual.f32", "visual_mapping.json")
    write_json(out / "visual_manifest.json", dict(model=MODEL_ID, catalog_sha256=sha256(database),
               embedding_onnx_sha256=model_sha, rows=len(rows), dim=DIM, files={name: sha256(out / name) for name in names}))


def require_independent(rows: list[dict], index: VisualIndex | None, detector_manifest: Path | None) -> None:
    seen = {item["sha256"] for item in index.ids} if index else set()
    if detector_manifest:
        seen.update(row[3] for row in json.loads(detector_manifest.read_text()))
    duplicate = [row["file_name"] for row in rows if row["sha256"] in seen]
    if duplicate:
        raise ValueError(f"Test images are byte-identical to reference/training inputs: {duplicate[:10]}")


def retrieval_report(db: Path, manifest: Path, images: Path, index: VisualIndex, out: Path) -> None:
    rows = verified_rows(db, manifest, images)
    require_independent(rows, index, None)
    indexed = {item["product_id"] for item in index.ids}
    if missing := {row["product_id"] for row in rows} - indexed:
        raise ValueError(f"Retrieval queries lack gallery references for catalog IDs: {sorted(missing)}")
    ranks = []
    for row in rows:
        ordered = list(index(image_rgb(row["path"]), limit=None))
        ranks.append(ordered.index(row["product_id"]) + 1)
    write_json(out, {"queries": len(ranks), "Recall@1": float(np.mean(np.array(ranks) <= 1)),
                     "Recall@5": float(np.mean(np.array(ranks) <= 5)),
                     "MRR": float(np.mean(1 / np.array(ranks))), "ranks": ranks})


def summarize(rows: list[dict]) -> dict:
    known = [row for row in rows if row["product_id"] is not None]
    unknown = [row for row in rows if row["product_id"] is None]
    correct = sum(row["status"] == "IDENTIFIED" and row["candidate_ids"][:1] == [row["product_id"]] for row in known)
    wrong = sum(row["status"] == "IDENTIFIED" and row["candidate_ids"][:1] != [row["product_id"]] for row in rows)
    confirmed = sum(row["status"] == "IDENTIFIED" for row in rows)
    def rate(numerator, denominator):
        return numerator / denominator if denominator else None
    barcode_rows = [r for r in rows if r["expected_gtin"]]
    strength_rows = [r for r in rows if r["expected_strength"]]
    times = [r["time_ms"] for r in rows]
    return {"n": len(rows), "known": len(known), "unknown": len(unknown),
            "wrong_identifications": wrong, "false_identification_rate_all": rate(wrong, len(rows)),
            "false_identification_rate_among_identified": rate(wrong, confirmed),
            "correct_identification_rate_all": rate(correct, len(rows)),
            "auto_identification_precision": rate(correct, confirmed), "auto_identification_recall": rate(correct, len(known)),
            "confirmation_rate": rate(sum(r["status"] == "NEEDS_CONFIRMATION" for r in rows), len(rows)),
            "unknown_rejection_rate": rate(sum(r["status"] == "NOT_IDENTIFIED" for r in unknown), len(unknown)),
            "top_1": rate(sum(r["candidate_ids"][:1] == [r["product_id"]] for r in known), len(known)),
            "top_3": rate(sum(r["product_id"] in r["candidate_ids"] for r in known), len(known)),
            "gtin_read_rate": rate(sum(r["expected_gtin"] in r["read_gtins"] for r in barcode_rows), len(barcode_rows)),
            "gtin_wrong_read_rate": rate(sum(any(code != r["expected_gtin"] for code in r["read_gtins"])
                                        for r in barcode_rows), len(barcode_rows)),
            "strength_accuracy": rate(sum(strengths_equivalent(r["expected_strength"], r["read_strength"])
                                          for r in strength_rows), len(strength_rows)),
            "latency_ms": {"median": float(np.median(times)), "p95": float(np.percentile(times, 95))}}


def full_report(db_path: Path, manifest: Path, images: Path, output: Path, analyzer: Analyzer,
                index: VisualIndex | None, detector_manifest: Path | None) -> None:
    rows = verified_rows(db_path, manifest, images, allow_unknown=True, extra={"scenario"})
    require_independent(rows, index, detector_manifest)
    results = []
    with open_catalog(db_path) as db:
        for row in rows:
            scenario = row["scenario"].strip()
            if not scenario:
                raise ValueError("Specify scenario, e.g. similar_pack, shared_gtin or unknown")
            expected = row.get("gtin", "").strip()
            gtin = parse_barcode(expected).get("gtin") if expected else None
            if expected and not gtin:
                raise ValueError(f"Invalid expected GTIN: {row['file_name']}")
            result = analyzer(db, row["path"])
            results.append(dict(file_name=row["file_name"], product_id=row["product_id"], scenario=scenario,
                                status=result["status"], reason=result["reason"], time_ms=result["time_ms"],
                                candidate_ids=[c["product"]["id"] for c in result["candidates"]],
                                expected_gtin=gtin, read_gtins=sorted({r["gtin"] for r in result["barcodes"]}),
                                expected_strength=row.get("strength", ""),
                                read_strength=result["extracted"]["strength"]))
    scenarios = sorted({r["scenario"] for r in results})
    write_json(output, {"stages": {"barcode": True, "detector": analyzer.detector is not None,
               "ocr": analyzer.ocr is not None, "visual": index is not None},
               "metrics": summarize(results),
               "scenarios": {s: summarize([r for r in results if r["scenario"] == s]) for s in scenarios},
               "missing_scenarios": sorted({"similar_pack", "shared_gtin", "unknown"} - set(scenarios)), "predictions": results})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["ocr", "build-visual", "retrieval", "full"])
    parser.add_argument("--images", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--database", type=Path, default=DATABASE)
    parser.add_argument("--model-root", type=Path)
    parser.add_argument("--index", type=Path)
    parser.add_argument("--embedding-onnx", type=Path)
    parser.add_argument("--detector", type=Path)
    parser.add_argument("--detector-manifest", type=Path)
    parser.add_argument("--ocr", action="store_true")
    args = parser.parse_args()
    if args.mode == "ocr":
        ocr_report(args.images, args.output, args.manifest, args.model_root)
        return
    if not args.manifest:
        parser.error("--manifest is required for ground-truth-backed workflows")
    if args.mode == "build-visual":
        build_visual(args.database, args.manifest, args.images, args.output,
                     OnnxDino(args.embedding_onnx) if args.embedding_onnx else Dino())
        return
    if args.mode == "retrieval" and not args.index:
        parser.error("--index is required for retrieval")
    index = VisualIndex(args.index, OnnxDino(args.embedding_onnx) if args.embedding_onnx else Dino(),
                        args.database) if args.index else None
    if args.mode == "retrieval":
        retrieval_report(args.database, args.manifest, args.images, index, args.output)
        return
    if args.detector and not args.detector_manifest:
        parser.error("--detector-manifest is required to check test separation")
    analyzer = Analyzer(args.detector, PaddleReader(args.model_root) if args.ocr else None, index)
    full_report(args.database, args.manifest, args.images, args.output, analyzer, index, args.detector_manifest)


if __name__ == "__main__":
    main()
