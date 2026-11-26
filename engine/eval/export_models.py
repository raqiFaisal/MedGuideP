"""Export OCR and DINOv2 for ONNX Runtime, and test the resulting graphs."""
from __future__ import annotations

import argparse
import csv
from pathlib import Path
import subprocess
from time import perf_counter

import numpy as np
import onnxruntime as ort
import yaml

from engine.eval.workflows import write_json
from medguide_engine.vision import MODEL_NAMES, image_rgb
from medguide_engine.visual import Dino, preprocess, sha256

DET = "PP-OCRv5_mobile_det"


def session(path: Path) -> ort.InferenceSession:
    options = ort.SessionOptions()
    options.intra_op_num_threads = 2
    options.log_severity_level = 3
    return ort.InferenceSession(str(path), sess_options=options, providers=["CPUExecutionProvider"])


def export_ocr(root: Path, out: Path) -> dict:
    import paddle.inference as paddle_infer

    results = {}
    for role, name in {"ocr_detection": DET, **{f"ocr_{k}": v for k, v in MODEL_NAMES.items()}}.items():
        model = root / name
        config = yaml.safe_load((model / "inference.yml").read_text(encoding="utf-8"))
        path = out / f"{role}.onnx"
        subprocess.run(["paddle2onnx", "--model_dir", str(model), "--model_filename", "inference.json",
                        "--params_filename", "inference.pdiparams", "--save_file", str(path),
                        "--opset_version", "17", "--optimize_tool", "None"], check=True)
        shape = (1, 3, 320, 480) if name == DET else (1, 3, 48, 320)
        data = np.random.default_rng(42).normal(size=shape).astype(np.float32)
        runtime = session(path)
        prediction = runtime.run(None, {runtime.get_inputs()[0].name: data})[0]
        if not np.isfinite(prediction).all():
            raise ValueError(f"Nonfinite inference output: {name}")
        pc = paddle_infer.Config(str(model / "inference.json"), str(model / "inference.pdiparams"))
        pc.disable_gpu()
        pc.disable_mkldnn()
        pc.set_cpu_math_library_num_threads(2)
        pc.disable_glog_info()
        predictor = paddle_infer.create_predictor(pc)
        predictor.get_input_handle(predictor.get_input_names()[0]).copy_from_cpu(data)
        predictor.run()
        expected = predictor.get_output_handle(predictor.get_output_names()[0]).copy_to_cpu()
        np.testing.assert_allclose(expected, prediction, atol=3e-3, rtol=3e-3)
        records = {"model": name, "onnx_size_bytes": path.stat().st_size, "onnx_sha256": sha256(path),
                   "test_input_shape": shape, "output_shape": list(prediction.shape),
                   "max_abs_export_difference": float(np.max(np.abs(expected - prediction)))}
        if name != DET:
            labels = config["PostProcess"]["character_dict"]
            if prediction.shape[-1] == len(labels) + 2:
                labels = [*labels, " "]
            classes = prediction.shape[-1]
            if classes != len(labels) + 1:
                raise ValueError(f"Unexpected character dictionary dimensions: {name}")
            alphabet = out / f"{role}_alphabet.json"
            write_json(alphabet, labels)
            records["alphabet_sha256"] = sha256(alphabet)
        results[role] = records
    return results


def export_dino(out: Path, images: Path) -> dict:
    import faiss
    import torch
    from onnxruntime.quantization import QuantType, quantize_dynamic

    torch.set_num_threads(2)
    embed = Dino()

    class NormalizedBackbone(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.model = embed.backbone

        def forward(self, image):
            return torch.nn.functional.normalize(self.model(image), dim=1)

    fp = out / "dinov2_fp32.onnx"
    quantized = out / "dinov2_int8.onnx"
    sample = torch.zeros((1, 3, 224, 224))
    torch.onnx.export(NormalizedBackbone().eval(), (sample,), str(fp), input_names=["image"],
                      output_names=["embedding"], opset_version=17, dynamo=False)
    quantize_dynamic(str(fp), str(quantized), weight_type=QuantType.QInt8, op_types_to_quantize=["MatMul"])
    baseline, reduced = session(fp), session(quantized)
    rows = sorted(images.glob("crop-*.jpg"))
    if not rows:
        raise ValueError("At least one real reference crop is required to verify the export")
    reference_vectors, reduced_vectors, checks = [], [], []
    for path in rows:
        rgb = image_rgb(path)
        x = preprocess(rgb)
        reference = embed(rgb)[0]
        native = baseline.run(None, {"image": x})[0][0]
        np.testing.assert_allclose(reference, native, rtol=5e-4, atol=5e-4)
        start = perf_counter()
        exported = reduced.run(None, {"image": x})[0][0]
        elapsed = (perf_counter() - start) * 1000
        if not np.isfinite(exported).all() or not np.isclose(np.linalg.norm(exported), 1, atol=1e-3):
            raise ValueError("Invalid exported embedding")
        reference_vectors.append(reference)
        reduced_vectors.append(exported)
        checks.append({"file_name": path.name, "fp32_max_abs_difference": float(np.max(np.abs(reference - native))),
                       "quantized_embedding_cosine": float(reference @ exported), "quantized_time_ms": elapsed})
    gallery = np.asarray(reference_vectors, dtype="<f4")
    index = faiss.IndexFlatIP(gallery.shape[1])
    index.add(gallery)
    scores, ranked = index.search(np.asarray(reduced_vectors, dtype=np.float32), min(5, len(rows)))
    faiss.write_index(index, str(out / "exploratory_unmapped.faiss"))
    (out / "exploratory_unmapped.f32").write_bytes(gallery.tobytes())
    with (out / "exploratory_unmapped.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["row_index", "file_name", "image_sha256", "product_id"])
        writer.writerows((i, path.name, sha256(path), "") for i, path in enumerate(rows))
    return {"image_count": len(rows), "embedding_dimension": gallery.shape[1],
            "quantized_cosine_min": min(c["quantized_embedding_cosine"] for c in checks),
            "same_input_index_at_1": int(np.sum(ranked[:, 0] == np.arange(len(rows)))),
            "independent_product_metrics": None, "reason": "No verified product mappings or independent queries.",
            "onnx_size_bytes": quantized.stat().st_size, "onnx_sha256": sha256(quantized), "checks": checks}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("ocr", "dino"))
    parser.add_argument("--source", required=True, type=Path, help="Paddle model directory or DINOv2 reference crops")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    report = export_ocr(args.source, args.output) if args.stage == "ocr" else export_dino(args.output, args.source)
    write_json(args.output / f"{args.stage}_export_report.json", report)


if __name__ == "__main__":
    main()
