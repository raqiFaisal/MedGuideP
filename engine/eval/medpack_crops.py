"""Extract reference crops using the publisher's box annotations, without assigning identities."""
from __future__ import annotations

import argparse
import csv
from io import BytesIO
import math
from pathlib import Path, PurePosixPath
from zipfile import ZipFile

from PIL import Image


def crop_archives(root: Path, out: Path, limit: int) -> None:
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    with ZipFile(root / "images.zip") as images, ZipFile(root / "labels.zip") as labels:
        by_stem = {}
        for name in images.namelist():
            path = PurePosixPath(name)
            if path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}:
                continue
            if path.stem in by_stem:
                raise ValueError(f"Duplicate image stem: {path.stem}")
            by_stem[path.stem] = name
        filenames = sorted(labels.namelist())
        # Sample across the publisher splits while keeping the selection reproducible.
        import random
        random.Random(42).shuffle(filenames)
        for label in filenames:
            stem = PurePosixPath(label).stem
            if stem not in by_stem or not label.endswith(".txt"):
                continue
            boxes = []
            for line in labels.read(label).decode("utf-8-sig").splitlines():
                if line.split()[:1] != ["0"]:
                    continue
                x, y, w, h = map(float, line.split()[1:])
                bounds = [x - w/2, y - h/2, x + w/2, y + h/2]
                if w > 0 and h > 0 and all(-1e-5 <= point <= 1.00001 for point in bounds):
                    boxes.append(bounds)
            if not boxes:
                continue
            name = by_stem[stem]
            with Image.open(BytesIO(images.read(name))) as original:
                if original.getexif().get(274, 1) != 1:
                    continue
                for i, (x1, y1, x2, y2) in enumerate(boxes):
                    bounds = [max(0, math.floor(x1 * original.width)), max(0, math.floor(y1 * original.height)),
                              min(original.width, math.ceil(x2 * original.width)), min(original.height, math.ceil(y2 * original.height))]
                    if min(bounds[2] - bounds[0], bounds[3] - bounds[1]) < 32:
                        continue
                    file = f"crop-{len(rows)+1:05}.jpg"
                    original.crop(tuple(bounds)).convert("RGB").save(out / file, quality=95)
                    rows.append([file, name, label, i, *bounds, "10.17632/d23kndp3sv.1"])
                    if limit and len(rows) >= limit:
                        break
            if limit and len(rows) >= limit:
                break
    if not rows:
        raise ValueError("No reference crop was extracted")
    with (out / "crop_provenance.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["file_name", "source_image", "source_label", "box_index", "x1", "y1", "x2", "y2", "doi"])
        writer.writerows(rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archives", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--limit", type=int, default=30, help="0 extracts all qualifying crops")
    args = parser.parse_args()
    crop_archives(args.archives, args.output, args.limit)
