"""Hosted profile isolation without changing local optimizer semantics."""
from fastapi.testclient import TestClient
import pytest
from app.main import app
from app.public_demo import SLOTS

ID = "tft_set18_18_4_standard"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("PUBLIC_DEMO", "true")
    return TestClient(app)


def test_real_only(client):
    games = client.get("/api/v1/games?include_synthetic=true").json()
    assert games[1]["versions"] == []
    assert [v["ruleset_id"] for v in games[0]["versions"]] == [ID]
    health = client.get("/api/v1/data-health").json()
    assert [d["id"] for d in health["datasets"]] == [ID]
    assert client.get(f"/api/v1/catalog?ruleset_id={ID}").status_code == 200
    assert client.get("/api/v1/catalog?ruleset_id=fixture_tft_v1").status_code == 422


@pytest.mark.parametrize("method,path", [
    ("post", "/api/v1/guides/import"), ("patch", "/api/v1/guides/1/rows/1"),
    ("post", "/api/v1/statistics/import"), ("post", "/api/v1/data/manual/validate"),
    ("post", "/api/v1/reforge/simulate"), ("post", "/api/v1/reforge/analyze"),
    ("get", "/docs"), ("get", "/api/v1/guides"),
])
def test_disabled_interfaces(client, method, path):
    assert getattr(client, method)(path).status_code == 403


@pytest.mark.parametrize("changes", [
    {"timeout_seconds": 6}, {"top_k": 10}, {"ruleset_id": "fixture_tft_v1"},
    {"game_id": "JCC"}, {"timeout_seconds": "NaN"},
])
def test_public_limits(client, changes):
    assert client.post("/api/v1/solve", json={"game_id": "TFT", "ruleset_id": ID, **changes}).status_code == 422


def test_busy_returns_retry_and_releases(client):
    assert SLOTS.acquire(blocking=False)
    assert SLOTS.acquire(blocking=False)
    try:
        response = client.post("/api/v1/solve", json={"game_id": "TFT", "ruleset_id": ID})
        assert response.status_code == 429
        assert response.headers["Retry-After"] == "5"
    finally:
        SLOTS.release()
        SLOTS.release()


def test_actual_real_solver_and_repeated_request(client):
    for _ in range(2):
        response = client.post("/api/v1/solve", json={
            "game_id": "TFT", "ruleset_id": ID, "board_size": 8,
            "top_k": 1, "timeout_seconds": 3,
        })
        assert response.status_code == 200
        assert response.json()["candidates"]


def test_cors_preflight(client):
    response = client.options("/api/v1/solve", headers={
        "Origin": "http://localhost:3000", "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type",
    })
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_invalid_and_large_body(client):
    assert client.post("/api/v1/solve", content="{").status_code == 422
    assert client.post("/api/v1/solve", content=" " * 65537).status_code == 413


def test_local_profile_preserved(monkeypatch):
    monkeypatch.delenv("PUBLIC_DEMO", raising=False)
    response = TestClient(app).get("/api/v1/catalog")
    assert response.status_code == 200
    assert response.json()["verification_status"] == "synthetic"


def test_same_origin_static_host(client, monkeypatch, tmp_path):
    from app.main import create_app
    (tmp_path / "index.html").write_text("<h1>EmblemLab public preview</h1>")
    (tmp_path / "catalog").mkdir()
    (tmp_path / "catalog/index.html").write_text("<h1>Catalog</h1>")
    (tmp_path / "_next").mkdir()
    (tmp_path / "_next/test.js").write_text("console.log('preview')")
    monkeypatch.setenv("PUBLIC_WEB_DIR", str(tmp_path))
    static_client = TestClient(create_app())
    assert "EmblemLab public preview" in static_client.get("/").text
    assert static_client.get("/catalog/").status_code == 200
    assert static_client.get("/_next/test.js").status_code == 200
    assert static_client.get("/health").json()["status"] == "ok"
    assert static_client.get(f"/api/v1/catalog?ruleset_id={ID}").json()["id"] == ID
    assert static_client.post("/api/v1/data/manual/validate").status_code == 403
    assert static_client.get("/docs").status_code == 403
    assert static_client.get("/Dockerfile").status_code == 403
    assert static_client.get("/_next/../Dockerfile").status_code == 403
    assert static_client.get("/_next/%2e%2e/%2e%2e/Dockerfile").status_code == 404
