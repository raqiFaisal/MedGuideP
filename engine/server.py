"""Local development API for the MedGuide engine.

FOR LOCAL DEVELOPMENT AND TESTING ONLY. Never deploy this publicly.
Run with:  .venv/Scripts/python -m uvicorn server:app --port 8000
"""

from __future__ import annotations

import os
import platform
import sqlite3
from collections.abc import Iterator
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Lock
from functools import lru_cache
from importlib.util import find_spec
from typing import Annotated
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel

from medguide_engine import __version__, catalog

DEFAULT_DB = Path(__file__).resolve().parents[1] / "data/processed/build/medguide.db"
ANALYZER_LOCK = Lock()


def database_path() -> Path:
    return Path(os.environ.get("MEDGUIDE_DB_PATH", DEFAULT_DB))

app = FastAPI(
    title="MedGuide engine (local dev only)",
    version=__version__,
    docs_url="/docs",
)


class ComponentStatus(BaseModel):
    name: str
    available: bool
    detail: str


class HealthResponse(BaseModel):
    status: Literal["ok"]
    engine_version: str
    python_version: str
    components: list[ComponentStatus]


def _component_status() -> list[ComponentStatus]:
    """Report what is actually loaded right now. Nothing is claimed that is not present."""
    components = [
        ComponentStatus(name="text_normalization", available=True, detail="medguide_engine.text"),
        ComponentStatus(name="gtin_validation", available=True, detail="medguide_engine.text.gtin"),
    ]
    try:
        with catalog.open_catalog(database_path()) as db:
            db.execute("SELECT id FROM products LIMIT 1").fetchone()
            db.execute("SELECT rowid FROM products_fts LIMIT 1").fetchone()
        components.append(ComponentStatus(name="drug_database", available=True, detail="read-only SQLite catalog"))
    except sqlite3.Error:
        components.append(ComponentStatus(name="drug_database", available=False, detail="catalog unavailable"))
    barcode = find_spec("zxingcpp") is not None
    components.append(ComponentStatus(name="barcode_reader", available=barcode,
                                      detail="ZXing-C++ installed" if barcode else "Requires zxing-cpp"))
    loaded = _analyzer.cache_info().currsize > 0
    for name, setting in (("yolo_detector", "MEDGUIDE_DETECTOR"), ("ocr", "MEDGUIDE_PADDLE_MODELS"),
                          ("visual_embeddings", "MEDGUIDE_VISUAL_INDEX")):
        configured = bool(os.environ.get(setting))
        detail = f"Set {setting} to configure"
        if configured:
            detail = "Loaded" if loaded else "Configured; loads on first analysis"
        components.append(ComponentStatus(name=name, available=configured and loaded, detail=detail))

    return components


@app.get("/api/v1/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        engine_version=__version__,
        python_version=platform.python_version(),
        components=_component_status(),
    )


def catalog_connection() -> Iterator[sqlite3.Connection]:
    # FastAPI can schedule the dependency and endpoint on different worker threads.
    try:
        with catalog.open_catalog(database_path()) as db:
            yield db
    except sqlite3.Error as exc:
        raise HTTPException(503, detail="Drug catalog unavailable") from exc


Catalog = Annotated[sqlite3.Connection, Depends(catalog_connection)]


@app.get("/api/v1/products/search")
def search_products(
    db: Catalog,
    q: Annotated[str, Query(min_length=1, max_length=120)],
    country: Literal["EG", "SA", "YE"] | None = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> dict:
    return {"items": catalog.search(db, q, country, limit)}


@app.get("/api/v1/products/{product_id}")
def get_product(product_id: int, db: Catalog) -> dict:
    result = catalog.details(db, product_id)
    if result is None:
        raise HTTPException(404, detail="Product not found")
    return result


@app.get("/api/v1/products/{product_id}/sources")
def get_product_sources(product_id: int, db: Catalog) -> dict:
    result = catalog.sources(db, product_id)
    if result is None:
        raise HTTPException(404, detail="Product not found")
    return result


@lru_cache(maxsize=1)
def _analyzer():
    from medguide_engine.vision import Analyzer, PaddleReader
    from medguide_engine.visual import Dino, VisualIndex

    detector = os.environ.get("MEDGUIDE_DETECTOR")
    ocr = os.environ.get("MEDGUIDE_PADDLE_MODELS")
    gallery = os.environ.get("MEDGUIDE_VISUAL_INDEX")
    visual = VisualIndex(Path(gallery), Dino(), database_path()) if gallery else None
    return Analyzer(Path(detector) if detector else None, PaddleReader(Path(ocr)) if ocr else None, visual)


def _analyze_locally(path: Path) -> dict:
    try:
        from PIL import Image, UnidentifiedImageError
    except ImportError as exc:
        raise HTTPException(503, detail="Vision dependencies unavailable") from exc
    # The Paddle predictors are mutable and shared by local requests.
    with ANALYZER_LOCK:
        try:
            analyzer = _analyzer()
        except (ImportError, OSError, RuntimeError, ValueError) as exc:
            raise HTTPException(503, detail="Vision dependencies or configured models unavailable") from exc
        try:
            with catalog.open_catalog(database_path()) as db:
                return analyzer(db, path)
        except (UnidentifiedImageError, Image.DecompressionBombError, Image.DecompressionBombWarning,
                ValueError, OSError) as exc:
            raise HTTPException(422, detail="Invalid or unsupported image") from exc
        except (ImportError, RuntimeError, sqlite3.Error) as exc:
            raise HTTPException(503, detail="Local analysis unavailable") from exc


@app.post("/api/v1/recognition/analyze")
async def analyze_photo(request: Request) -> dict:
    """Accept raw JPEG, PNG or WebP on the local development API."""
    kinds = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
    suffix = kinds.get(request.headers.get("content-type", "").split(";")[0].strip().lower())
    if suffix is None:
        raise HTTPException(415, detail="Send JPEG, PNG or WebP bytes")
    with TemporaryDirectory(prefix="medguide-") as directory:
        path = Path(directory) / ("photo" + suffix)
        size = 0
        with path.open("wb") as stream:
            async for chunk in request.stream():
                size += len(chunk)
                if size > 12 * 1024 * 1024:
                    raise HTTPException(413, detail="Maximum image size is 12 MiB")
                stream.write(chunk)
        if not size:
            raise HTTPException(422, detail="Image required")
        return await run_in_threadpool(_analyze_locally, path)


class ConfirmationRequest(BaseModel):
    product_id: int


@app.post("/api/v1/recognition/confirm")
def confirm_product(selection: ConfirmationRequest, db: Catalog) -> dict:
    return {"user_selected": True, "product": get_product(selection.product_id, db)}
