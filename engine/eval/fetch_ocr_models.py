"""Fetch the three pinned official PP-OCRv5 Mobile inference archives."""
from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import tarfile
import tempfile
from urllib.request import urlopen

from medguide_engine.visual import sha256

BASE = "https://paddle-model-ecology.bj.bcebos.com/paddlex/official_inference_model/paddle3.0.0"
ARCHIVES = {
    "PP-OCRv5_mobile_det": "50446e5d01ac2a73d5319c89513281f6578414c888c602f9af13f93feefffc58",
    "arabic_PP-OCRv5_mobile_rec": "a25c1f96cd0cda485b942851b5afb4a95bc4041a56c295bb4439190d53ee0a14",
    "latin_PP-OCRv5_mobile_rec": "b23105a6a1ea38e32a97c5a0ddc7e8a9bbf541d8e47421e2c99e9ccabe29509c",
}
REQUIRED = {"inference.json", "inference.yml", "inference.pdiparams"}


def fetch_models(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for name, expected in ARCHIVES.items():
        destination = root / name
        if destination.is_dir() and all((destination / entry).is_file() for entry in REQUIRED):
            continue
        with tempfile.TemporaryDirectory(prefix="paddleocr-", dir=root) as temporary:
            cache = Path(temporary)
            archive = cache / f"{name}_infer.tar"
            with urlopen(f"{BASE}/{archive.name}", timeout=45) as response, archive.open("wb") as stream:
                shutil.copyfileobj(response, stream)
            if sha256(archive) != expected:
                raise ValueError(f"Publisher archive digest changed: {name}")
            folder = cache / f"{name}_infer"
            folder.mkdir()
            with tarfile.open(archive) as source:
                for entry in REQUIRED:
                    member = source.getmember(f"{folder.name}/{entry}")
                    with source.extractfile(member) as data, (folder / entry).open("wb") as stream:
                        shutil.copyfileobj(data, stream)
            if destination.exists():
                raise FileExistsError(f"Remove or rename incomplete local model directory: {destination}")
            folder.rename(destination)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    fetch_models(parser.parse_args().directory)
