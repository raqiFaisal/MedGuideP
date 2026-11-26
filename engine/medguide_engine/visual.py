"""DINOv2 ViT-S/14 embeddings and exact cosine retrieval."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

SIZE, DIM = 224, 384
MEAN = np.array([.485, .456, .406], dtype=np.float32)
STD = np.array([.229, .224, .225], dtype=np.float32)
MODEL_ID = "dinov2_vits14_rgb224_cls_l2"


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def preprocess(rgb: np.ndarray) -> np.ndarray:
    import cv2

    image = cv2.resize(rgb.astype(np.float32), (SIZE, SIZE), interpolation=cv2.INTER_LINEAR)
    return np.ascontiguousarray(((image / 255 - MEAN) / STD).transpose(2, 0, 1)[None])


class Dino:
    def __init__(self, repo: str = "facebookresearch/dinov2", device: str = "cpu"):
        import torch

        self.torch = torch
        self.device = device
        self.backbone = torch.hub.load(repo, "dinov2_vits14", trust_repo=True).eval().to(device)

    def __call__(self, rgb: np.ndarray) -> np.ndarray:
        with self.torch.inference_mode():
            features = self.backbone(self.torch.from_numpy(preprocess(rgb)).to(self.device))
            return self.torch.nn.functional.normalize(features, dim=1).cpu().numpy()


class VisualIndex:
    def __init__(self, directory: Path, embed, database: Path):
        import faiss

        manifest = json.loads((directory / "visual_manifest.json").read_text())
        if manifest["model"] != MODEL_ID or manifest["catalog_sha256"] != sha256(database):
            raise ValueError("Visual index is for a different catalog or embedding model")
        mapping = directory / "visual_mapping.json"
        index = directory / "visual.faiss"
        if any(sha256(path) != manifest["files"][path.name] for path in (mapping, index)):
            raise ValueError("Visual index integrity check failed")
        self.ids = json.loads(mapping.read_text())
        self.index = faiss.read_index(str(index))
        if self.index.ntotal != len(self.ids) or self.index.d != DIM:
            raise ValueError("Visual index dimensions do not match mapping")
        self.embed = embed

    def __call__(self, rgb: np.ndarray, limit: int | None = 20) -> dict[int, float]:
        scores, indices = self.index.search(self.embed(rgb), self.index.ntotal)
        products: dict[int, float] = {}
        for score, idx in zip(scores[0], indices[0], strict=True):
            if idx >= 0:
                pid = self.ids[idx]["product_id"]
                products[pid] = max(products.get(pid, -1.0), float(score))
        ordered = sorted(products, key=lambda pid: (-products[pid], pid))
        return {pid: products[pid] for pid in ordered[:limit]}
