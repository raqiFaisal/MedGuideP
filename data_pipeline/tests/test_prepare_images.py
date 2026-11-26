from __future__ import annotations

import json

from PIL import Image

from prepare_images import inspect, prepare


def test_coco_conversion_and_product_split(tmp_path):
    files = ["a.png", "b.png", "c.png", "d.png", "missing.png"]
    products = ["one", "one", "two", "three", "three"]
    identities = tmp_path / "identities.csv"
    identities.write_text("file_name,product_id\n" + "\n".join(
        f"{file},{product}" for file, product in zip(files, products, strict=True)
    ))
    for index, file in enumerate(files[:-1]):
        Image.new("RGB", (20, 10), (index, 0, 0)).save(tmp_path / file)
    coco = tmp_path / "coco.json"
    coco.write_text(json.dumps({
        "images": [{"id": i, "file_name": file, "width": 20, "height": 10}
                   for i, file in enumerate(files)],
        "categories": [{"id": 1, "name": "box"}],
        "annotations": [{"image_id": i, "category_id": 1, "bbox": [5, 2, 10, 4]}
                        for i in range(len(files))],
    }))
    samples, report = inspect(tmp_path, coco, identities, {"box": "medicine_box"})
    assert report["accepted"] == 4
    assert [row["file_name"] for row in report["excluded"]] == ["missing.png"]
    out = tmp_path / "output"
    result = prepare(samples, report, out)
    assert result["products_by_split"] == {"train": 1, "val": 1, "test": 1}
    assert len({r["split"] for r in result["manifest"] if r["product_id"] == "one"}) == 1
    labels = list((out / "labels").glob("*/*.txt"))
    assert len(labels) == 4
    assert labels[0].read_text().strip() == "0 0.5 0.4 0.5 0.4"
