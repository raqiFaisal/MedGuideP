from __future__ import annotations

from fastapi.testclient import TestClient

from server import app

client = TestClient(app)


def test_health_ok(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("MEDGUIDE_DB_PATH", str(tmp_path / "missing.db"))
    res = client.get("/api/v1/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    names = {c["name"]: c["available"] for c in body["components"]}
    assert names["text_normalization"] is True
    # Components that do not exist yet must not be reported as available.
    assert names["yolo_detector"] is False
    assert names["drug_database"] is False


def test_unknown_route_404() -> None:
    assert client.get("/api/v1/nope").status_code == 404


def test_catalog_search_and_provenance(monkeypatch, tmp_path) -> None:
    import sqlite3
    from pathlib import Path

    path = tmp_path / "catalog.db"
    schema = Path(__file__).resolve().parents[2] / "data_pipeline/schema/001_initial.sql"
    with sqlite3.connect(path) as db:
        db.executescript(schema.read_text(encoding="utf-8"))
        db.executescript("""
        INSERT INTO countries VALUES ('EG','مصر','Egypt'),('SA','السعودية','Saudi Arabia');
        INSERT INTO data_sources(id,code,name,url,license,fetched_at)
          VALUES (1,'fixture','Test source','https://example.test','fixture','2026-11-24');
        INSERT INTO products(id,brand_name_ar,brand_normalized,country_code,source_id,source_record_id)
          VALUES (1,'تجربة','TEST ONE','EG',1,'1'),(2,NULL,'TEST TWO','SA',1,'2');
        CREATE VIRTUAL TABLE products_fts USING fts5(brand,brand_ar,ingredients);
        INSERT INTO products_fts(rowid,brand,brand_ar,ingredients)
          VALUES (1,'TEST ONE','تجربه','EXAMPLE'),(2,'TEST TWO','','EXAMPLE');
        INSERT INTO product_identifiers(product_id,kind,value,check_ok,source_id)
          VALUES (1,'GTIN14','06221000000010',1,1),(2,'GTIN14','06221000000010',1,1);
        """)
    monkeypatch.setenv("MEDGUIDE_DB_PATH", str(path))
    base = "/api/v1/products"
    for params, expected in [
        ({"q": "تجربة"}, {1}),
        ({"q": "exam", "country": "SA"}, {2}),
        ({"q": "6221000000010"}, {1, 2}),
        ({"q": "*"}, set()),
    ]:
        response = client.get(f"{base}/search", params=params)
        assert response.status_code == 200
        assert {row["id"] for row in response.json()["items"]} == expected
    assert client.get(f"{base}/1").json()["market_availability"] == []
    assert client.get(f"{base}/1/sources").json()["record_source"]["code"] == "fixture"
    assert client.get(f"{base}/999").status_code == 404
    assert client.get(f"{base}/999/sources").status_code == 404
    assert client.get(f"{base}/search", params={"q": "test", "limit": 51}).status_code == 422
    components = client.get("/api/v1/health").json()["components"]
    assert next(row for row in components if row["name"] == "drug_database")["available"]


def test_image_input_validation(monkeypatch):
    import pytest

    pytest.importorskip("numpy")
    pytest.importorskip("PIL")
    monkeypatch.delenv("MEDGUIDE_PADDLE_MODELS", raising=False)
    monkeypatch.delenv("MEDGUIDE_VISUAL_INDEX", raising=False)
    monkeypatch.delenv("MEDGUIDE_DETECTOR", raising=False)
    endpoint = "/api/v1/recognition/analyze"
    assert client.post(endpoint, content=b"some text").status_code == 415
    assert client.post(endpoint, content=b"", headers={"Content-Type": "image/png"}).status_code == 422
    assert client.post(endpoint, content=b"unknown bytes", headers={"Content-Type": "image/png"}).status_code == 422
    assert client.post(endpoint, content=b"x" * (12 * 1024 * 1024 + 1),
                       headers={"Content-Type": "image/png"}).status_code == 413
