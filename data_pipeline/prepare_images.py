"""Inspect one COCO bounding-box export and split it by verified product ID."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
import shutil
from collections import Counter, defaultdict
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image

CLASSES = ("medicine_box", "drug_name", "barcode")


def inspect(root: Path, coco: Path, identities: Path, categories: dict[str, str]):
    """Return usable samples and an exclusion report without changing the input."""
    data = json.loads(coco.read_text(encoding="utf-8"))
    with identities.open(encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))
    products = {r["file_name"].strip(): r["product_id"].strip() for r in rows}
    if len(products) != len(rows):
        raise ValueError("Duplicate file_name in the identity manifest")
    names = {item["id"]: item["name"] for item in data["categories"]}
    if not categories or set(categories) - set(names.values()) or set(categories.values()) - set(CLASSES):
        raise ValueError("Provide an explicit mapping from COCO category names to MedGuide classes")
    by_image = defaultdict(list)
    image_ids = {image["id"] for image in data["images"]}
    if len(image_ids) != len(data["images"]):
        raise ValueError("Duplicate COCO image IDs")
    for box in data["annotations"]:
        if box["image_id"] not in image_ids or box["category_id"] not in names:
            raise ValueError("Orphan COCO annotation")
        by_image[box["image_id"]].append(box)
    root = root.resolve()
    report = {"images": len(image_ids), "annotations": len(data["annotations"]),
              "source_categories": list(names.values()), "accepted": 0, "excluded": []}
    samples = []
    hashes = {}
    for item in data["images"]:
        name = item["file_name"]
        path = (root / name).resolve()
        if not path.is_relative_to(root):
            raise ValueError(f"Image escapes dataset directory: {name}")
        product = products.get(name)
        try:
            if not product:
                raise ValueError("missing verified product_id")
            with Image.open(path) as image:
                width, height = image.size
                if image.format not in ("JPEG", "PNG", "WEBP") or image.getexif().get(274, 1) != 1:
                    raise ValueError("unsupported format or nonstandard EXIF orientation")
                if image.size != (item["width"], item["height"]):
                    raise ValueError("image dimensions differ from COCO")
                image.load()
                extension = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}[image.format]
            labels = []
            for annotation in by_image[item["id"]]:
                category = categories.get(names[annotation["category_id"]])
                if category is None:
                    continue
                if annotation.get("iscrowd"):
                    raise ValueError("mapped crowd annotation")
                x, y, w, h = map(float, annotation["bbox"])
                if not all(map(math.isfinite, (x, y, w, h))) or not (
                    x >= 0 and y >= 0 and w > 0 and h > 0 and x + w <= width and y + h <= height
                ):
                    raise ValueError("invalid bounding box")
                coords = ((x + w / 2) / width, (y + h / 2) / height, w / width, h / height)
                labels.append(f"{CLASSES.index(category)} " + " ".join(f"{v:.10g}" for v in coords))
            if not labels:
                raise ValueError("no mapped bounding boxes")
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
        except (OSError, ValueError, TypeError, Image.DecompressionBombError) as exc:
            report["excluded"].append({"file_name": name, "reason": str(exc)})
            continue
        if digest in hashes:
            if hashes[digest] != product:
                raise ValueError(f"Identical image assigned to different products: {name}")
            report["excluded"].append({"file_name": name, "reason": "exact duplicate"})
            continue
        hashes[digest] = product
        samples.append((product, path, digest, extension, labels))
    report["accepted"] = len(samples)
    report["products"] = len(set(hashes.values()))
    return samples, report


def prepare(samples, report: dict, destination: Path, seed: int = 42) -> dict:
    products = sorted({row[0] for row in samples})
    if len(products) < 3:
        raise ValueError("At least three verified product identities are required")
    random.Random(seed).shuffle(products)
    held_out = max(1, round(len(products) * 0.15))
    assignment = {
        product: "test" if i < held_out else "val" if i < 2 * held_out else "train"
        for i, product in enumerate(products)
    }
    destination = destination.resolve()
    if destination.exists():
        raise FileExistsError(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=destination.parent) as temp:
        output = Path(temp) / "dataset"
        for split in ("train", "val", "test"):
            (output / "images" / split).mkdir(parents=True)
            (output / "labels" / split).mkdir(parents=True)
        records = []
        for product, image, digest, extension, labels in samples:
            split = assignment[product]
            shutil.copyfile(image, output / "images" / split / (digest + extension))
            (output / "labels" / split / (digest + ".txt")).write_text("\n".join(labels) + "\n")
            records.append({"product_id": product, "split": split, "sha256": digest})
        config = {"path": str(destination), "train": "images/train", "val": "images/val",
                  "test": "images/test", "names": list(CLASSES)}
        (output / "dataset.yaml").write_text(json.dumps(config, indent=2), encoding="utf-8")
        result = {**report, "seed": seed, "images_by_split": dict(Counter(r["split"] for r in records)),
                  "products_by_split": dict(Counter(assignment.values())), "manifest": records}
        (output / "report.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        output.rename(destination)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--images", type=Path, required=True)
    parser.add_argument("--coco", type=Path, required=True)
    parser.add_argument("--identities", type=Path, required=True)
    parser.add_argument("--categories", type=json.loads, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    samples, report = inspect(args.images, args.coco, args.identities, args.categories)
    if args.output:
        report = prepare(samples, report, args.output)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
