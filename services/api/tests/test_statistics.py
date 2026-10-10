"""All numbers and licenses here are test inventions, never actual game evidence."""

import copy
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from app.main import app
from app.models.database import Base
from app.models.statistics import StatisticsRecord
from app.models.community import GuideImport
from app.repositories.catalog import get_catalog
from app.statistics import providers, service
from app.statistics.quality import summarize
from app.statistics.schemas import IngestRequest, Metrics, Observation, SourceRegistry

NOW = datetime(2026, 10, 10, 6, tzinfo=timezone.utc)


def scope(game="TFT", patch="EXAMPLE-1.0"):
    d = get_catalog(game, f"fixture_{game.lower()}_v1")
    return dict(game_id=game, ruleset_id=d.id, patch=patch, set_id=d.set, mode=d.mode)


def observation(record_id="record-1"):
    return dict(
        provider_record_id=record_id,
        cohort_id="test-cohort",
        cohort_definition="Synthetic test participant-game outcomes; not real matches",
        dataset_reference="test-only-export",
        sample_unit="participant_game",
        placement_scale=8,
        region="test-region",
        queue_id="test-queue",
        rank_band="test-rank",
        observed_start=(NOW - timedelta(days=2)).isoformat(),
        observed_end=(NOW - timedelta(days=1)).isoformat(),
        collected_at=NOW.isoformat(),
        context=dict(kind="holder", emblem_id="tft_emblem_0", champion_id="tft_unit_1"),
        metrics=dict(placement_counts=[1] * 8),
        quality=dict(independence="independent", deduplication="verified", population_coverage=1.0),
    )


def request(**kwargs):
    return IngestRequest.model_validate(
        dict(
            schema_version=1,
            provider_id="test-provider",
            scope=scope(),
            data_kind="synthetic",
            observations=[observation()],
            **kwargs,
        )
    )


def authorization(provider_id="test-provider"):
    return dict(
        provider_id=provider_id,
        name="TEST ONLY licensed provider",
        source_kind="licensed_provider",
        access_method="licensed_export",
        attribution="TEST ONLY, not real data or license",
        license_id="TEST-LICENSE",
        permission_reference="Test fixture permission reference; no actual provider grant",
        permission_sha256="a" * 64,
        reviewed_by="TEST REVIEWER",
        reviewed_at=(NOW - timedelta(days=4)).isoformat(),
        valid_from=(NOW - timedelta(days=3)).isoformat(),
        valid_until=(NOW + timedelta(days=3)).isoformat(),
        enabled=True,
        permitted_uses=["ingest", "store", "display", "derive"],
        scopes=[scope(), scope("JCC"), scope(patch="TEST-PATCH-2")],
        data_kinds=["synthetic", "observed"],
        context_kinds=["holder", "composition"],
        metrics=["top_four_rate", "average_placement"],
    )


@pytest.fixture(autouse=True)
def environment(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path}/statistics.db", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    monkeypatch.setattr(service, "Session", sessionmaker(engine))
    monkeypatch.setattr(providers, "utcnow", lambda: NOW)
    monkeypatch.setattr(service, "utcnow", lambda: NOW)
    monkeypatch.setattr("app.statistics.quality.utcnow", lambda: NOW)
    path = tmp_path / "sources.json"
    monkeypatch.setenv("STATISTICS_SOURCES_FILE", str(path))
    monkeypatch.setenv("STATISTICS_INGEST_TOKEN", "test-only-operator-token")

    def configure(sources=None):
        path.write_text(json.dumps(dict(schema_version=1, sources=[authorization()] if sources is None else sources)))

    configure()
    yield configure
    engine.dispose()


@pytest.fixture
def client():
    return TestClient(app)


def post(client, body=None, **kwargs):
    return client.post(
        "/api/v1/statistics/ingest",
        json=body or request().model_dump(mode="json"),
        headers={"Authorization": "Bearer test-only-operator-token"},
        **kwargs,
    )


def test_ingestion_query_provenance_and_counts(client):
    response = post(client)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["inserted"] == 1 and body["unchanged"] == 0
    row = body["records"][0]
    assert row["metrics"]["sample_size"] == 8
    assert row["metrics"]["top_four_rate"] == 0.5
    assert row["metrics"]["average_placement"] == 4.5
    assert row["metrics"]["origins"]["sample_size"] == "derived_from_histogram"
    assert row["observation"]["metrics"]["sample_size"] is None
    assert row["source"]["license_id"] == "TEST-LICENSE"
    assert row["verification_status"] == "synthetic"
    assert "synthetic_not_match_evidence" in row["data_quality"]["flags"]
    assert row["data_quality"]["quality_verified"] is False
    result = client.get("/api/v1/statistics/observations", params={**scope(), "data_kind": "synthetic"}).json()
    assert result["total"] == 1 and result["statistics_available"] is False
    assert result["aggregation"] == "none"
    assert client.get("/api/v1/statistics/observations", params=scope()).json()["records"] == []
    assert client.get("/api/v1/statistics/observations/" + row["id"]).json() == row
    assert client.get("/api/v1/statistics/sources").json()[0]["provider_id"] == "test-provider"


def test_missing_values_zero_sample_and_reported_only():
    base = observation()
    for metrics in ({}, {"sample_size": 0}, {"sample_size": 200, "top_four_rate": 0.5}):
        obs = Observation.model_validate({**base, "metrics": metrics})
        out = summarize(obs, True, "observed")
        assert out["metrics"]["average_placement"] is None
        assert out["confidence"]["computed_top_four_rate"] is None
        if not metrics.get("sample_size"):
            assert out["metrics"]["top_four_rate"] is None
        else:
            assert out["metrics"]["top_four_rate"] == 0.5
            assert "exact_top_four_count_missing" in out["data_quality"]["flags"]
    unknown = Observation.model_validate({**base, "metrics": {"top_four_rate": 0.4, "average_placement": 4.8}})
    assert summarize(unknown, True, "observed")["metrics"]["sample_size"] is None


@pytest.mark.parametrize(
    "metrics",
    [
        {"sample_size": True},
        {"sample_size": 1.5},
        {"sample_size": -1},
        {"sample_size": "100"},
        {"top_four_rate": 1.1},
        {"top_four_rate": "0.5"},
        {"top_four_rate": float("nan")},
        {"average_placement": 0.9},
        {"average_placement": float("inf")},
        {"sample_size": 0, "top_four_rate": 0.0},
        {"sample_size": 0, "average_placement": 4.0},
        {"sample_size": 10, "top_four_count": 11},
        {"top_four_count": 2},
        {"sample_size": 2, "placement_sum": 17},
        {"sample_size": 2, "placement_sum": 1},
        {"sample_size": 8, "top_four_count": 2, "top_four_rate": 0.5},
        {"sample_size": 8, "placement_sum": 36, "average_placement": 3.0},
        {"sample_size": 4, "placement_counts": [1] * 8},
        {"placement_counts": [1] * 7},
        {"sample_size": 10, "top_four_count": 10, "placement_sum": 80},
        {"top_four_rate": 1.0, "average_placement": 5.0},
        {
            "top_four_rate": 0.5,
            "reported_confidence": {"top_four_rate": {"lower": 0.6, "upper": 0.8, "level": 0.95, "method": "test"}},
        },
        {
            "top_four_rate": 0.5,
            "reported_confidence": {"top_four_rate": {"lower": 0.1, "upper": 0.8, "level": 1.0, "method": "test"}},
        },
        {"win_rate": 0.9},
    ],
)
def test_invalid_metrics(metrics):
    with pytest.raises(ValidationError):
        Metrics.model_validate(metrics)


def test_confidence_reference_and_assumptions():
    base = observation()
    obs = Observation.model_validate(
        {**base, "metrics": {"sample_size": 100, "top_four_count": 50, "placement_sum": 450}}
    )
    out = summarize(obs, True, "observed")
    interval = out["confidence"]["computed_top_four_rate"]
    assert interval["lower"] == pytest.approx(0.4038315303659956)
    assert interval["upper"] == pytest.approx(0.5961684696340044)
    assert interval["method"] == "wilson_score" and interval["level"] == 0.95
    assert out["confidence"]["computed_average_placement"] is None
    for independence in ("unknown", "clustered"):
        modified = obs.model_copy(update={"quality": obs.quality.model_copy(update={"independence": independence})})
        assert summarize(modified, True, "observed")["confidence"]["computed_top_four_rate"] is None
    assert summarize(obs, False, "observed")["metrics"]["top_four_rate"] is None
    assert summarize(obs, False, "observed")["confidence"]["computed_top_four_rate"] is None
    reported = {"lower": 4.0, "upper": 5.0, "level": 0.9, "method": "provider cluster bootstrap"}
    obs = Observation.model_validate(
        {
            **base,
            "metrics": {
                "sample_size": 100,
                "average_placement": 4.5,
                "reported_confidence": {"average_placement": reported},
            },
        }
    )
    assert summarize(obs, True, "observed")["confidence"]["provider_reported"]["average_placement"] == reported


def test_wilson_boundaries():
    for count, expected in [(0, (0.0, 0.03699349820698568)), (100, (0.9630065017930143, 1.0))]:
        obs = Observation.model_validate({**observation(), "metrics": {"sample_size": 100, "top_four_count": count}})
        ci = summarize(obs, True, "observed")["confidence"]["computed_top_four_rate"]
        assert (ci["lower"], ci["upper"]) == pytest.approx(expected)


@pytest.mark.parametrize(
    "change",
    [
        {"enabled": False},
        {"valid_until": (NOW - timedelta(days=1)).isoformat()},
        {"permitted_uses": ["ingest", "store"]},
        {"scopes": [scope("JCC")]},
        {"data_kinds": ["observed"]},
        {"context_kinds": ["composition"]},
        {"metrics": ["average_placement"]},
    ],
)
def test_unauthorized_scopes_and_fields(environment, client, change):
    environment([{**authorization(), **change}])
    assert post(client).status_code == 403
    with service.Session() as session:
        assert session.scalar(select(func.count()).select_from(StatisticsRecord)) == 0


def test_token_empty_registry_and_invalid_registry(environment, client, monkeypatch):
    monkeypatch.delenv("STATISTICS_INGEST_TOKEN")
    assert post(client).status_code == 503
    monkeypatch.setenv("STATISTICS_INGEST_TOKEN", "test-only-operator-token")
    assert client.post("/api/v1/statistics/ingest", json={}).status_code == 401
    environment([])
    assert post(client).status_code == 403
    assert client.get("/api/v1/statistics/sources").json() == []
    path = providers.Path(providers.os.environ["STATISTICS_SOURCES_FILE"])
    path.write_text("broken json")
    assert post(client).status_code == 503
    assert client.get("/api/v1/statistics/observations", params=scope()).status_code == 503


def test_registry_rejects_unreviewed_and_duplicate_sources():
    for change in (
        {"permission_sha256": "unknown"},
        {"source_kind": "public_website"},
        {"permission_reference": ""},
        {"reviewed_by": ""},
        {"valid_until": NOW - timedelta(days=9)},
    ):
        with pytest.raises(ValidationError):
            SourceRegistry.model_validate({"schema_version": 1, "sources": [{**authorization(), **change}]})
    with pytest.raises(ValidationError):
        SourceRegistry.model_validate({"schema_version": 1, "sources": [authorization(), authorization()]})


@pytest.mark.parametrize(
    "change",
    [
        {"patch": "OTHER"},
        {"set_id": "OTHER"},
        {"mode": "OTHER"},
        {"game_id": "JCC"},
    ],
)
def test_version_scope_rejection(environment, client, change):
    modified = {**scope(), **change}
    environment([{**authorization(), "scopes": [modified]}])
    body = request().model_dump(mode="json")
    body["scope"] = modified
    assert post(client, body).status_code == 422


def test_patch_isolation_provider_isolation_and_pagination(environment, client, monkeypatch):
    original = get_catalog("TFT", "fixture_tft_v1")
    alternative = original.model_copy(deep=True)
    alternative.patch = "TEST-PATCH-2"
    for entity in [*alternative.champions, *alternative.traits, *alternative.emblems]:
        entity.patch = alternative.patch
    monkeypatch.setattr(
        service, "get_catalog", lambda game, ruleset: alternative if ruleset == "test_patch_2" else original
    )
    alternative.id = "test_patch_2"
    second_scope = {**scope(), "patch": alternative.patch, "ruleset_id": alternative.id}
    first_source = {**authorization(), "scopes": [scope(), second_scope]}
    second_source = {**first_source, "provider_id": "second-provider"}
    environment([first_source, second_source])
    first = post(client).json()["records"][0]
    body = request().model_dump(mode="json")
    body["scope"] = second_scope
    second = post(client, body).json()["records"][0]
    assert first["id"] != second["id"]
    body["provider_id"] = "second-provider"
    body["scope"] = scope()
    assert post(client, body).status_code == 200
    result = client.get(
        "/api/v1/statistics/observations", params={**scope(), "data_kind": "synthetic", "limit": 1}
    ).json()
    assert result["total"] == 2 and len(result["records"]) == 1
    result2 = client.get(
        "/api/v1/statistics/observations", params={**scope(), "data_kind": "synthetic", "limit": 1, "offset": 1}
    ).json()
    assert result["records"][0]["id"] != result2["records"][0]["id"]
    assert (
        client.get("/api/v1/statistics/observations", params={**second_scope, "data_kind": "synthetic"}).json()["total"]
        == 1
    )
    assert (
        client.get(
            "/api/v1/statistics/observations",
            params={**scope(), "data_kind": "synthetic", "provider_id": "test-provider"},
        ).json()["total"]
        == 1
    )


def test_context_validation_and_canonical_order(client):
    body = request().model_dump(mode="json")
    body["observations"][0]["context"] = {
        "kind": "composition",
        "composition": {
            "champion_ids": ["tft_unit_3", "tft_unit_1"],
            "matching_rule": "unit_subset",
            "emblem_assignments": [{"emblem_id": "tft_emblem_0", "champion_id": "tft_unit_1"}],
        },
    }
    response = post(client, body)
    assert response.status_code == 200, response.text
    row = response.json()["records"][0]
    assert row["observation"]["context"]["composition"]["champion_ids"] == ["tft_unit_1", "tft_unit_3"]
    params = {**scope(), "data_kind": "synthetic", "context_kind": "holder"}
    assert client.get("/api/v1/statistics/observations", params=params).json()["total"] == 0
    params.update(context_kind="composition", context_key=row["context_key"])
    assert client.get("/api/v1/statistics/observations", params=params).json()["total"] == 1
    body["observations"][0]["provider_record_id"] = "bad-context"
    body["observations"][0]["context"]["composition"]["champion_ids"] = ["jcc_unit_1"]
    assert post(client, body).status_code == 422
    for ctx in (
        {"kind": "holder", "emblem_id": "jcc_emblem_0", "champion_id": "tft_unit_1"},
        {"kind": "holder", "emblem_id": "tft_emblem_0", "champion_id": "tft_unit_0"},
    ):
        body["observations"][0]["context"] = ctx
        assert post(client, body).status_code == 422


def test_idempotency_conflict_atomicity_and_no_community_rows(client):
    first = post(client).json()
    assert first["inserted"] == 1
    second = post(client).json()
    assert second["inserted"] == 0 and second["unchanged"] == 1
    body = request().model_dump(mode="json")
    body["observations"] = [observation("new-id"), observation()]
    body["observations"][1]["metrics"] = {"sample_size": 10, "top_four_count": 5}
    assert post(client, body).status_code == 409
    with service.Session() as session:
        assert session.scalar(select(func.count()).select_from(StatisticsRecord)) == 1
        assert session.scalar(select(func.count()).select_from(GuideImport)) == 0
    body["observations"][1] = copy.deepcopy(body["observations"][0])
    assert post(client, body).status_code == 422


def test_concurrent_ingestion():
    with ThreadPoolExecutor(max_workers=4) as pool:
        outputs = list(pool.map(lambda _: service.ingest(request()), range(4)))
    assert sum(o["inserted"] for o in outputs) == 1
    assert len({o["records"][0]["id"] for o in outputs}) == 1


def test_revocation_expiration_changed_license_and_catalog(environment, client, monkeypatch):
    row = post(client).json()["records"][0]
    for change in (
        {"enabled": False},
        {"permission_sha256": "b" * 64},
        {"metrics": ["average_placement"]},
        {"valid_until": (NOW - timedelta(days=1)).isoformat()},
    ):
        environment([{**authorization(), **change}])
        assert client.get("/api/v1/statistics/observations/" + row["id"]).status_code == 403
        assert (
            client.get("/api/v1/statistics/observations", params={**scope(), "data_kind": "synthetic"}).json()["total"]
            == 0
        )
    environment()
    changed = get_catalog("TFT", "fixture_tft_v1").model_copy(deep=True)
    changed.champions[0].zh_CN = "Changed"
    monkeypatch.setattr(service, "get_catalog", lambda *_: changed)
    assert client.get("/api/v1/statistics/observations/" + row["id"]).status_code == 403
    assert post(client).status_code == 409


def test_observed_requires_verified_catalog(environment, client, monkeypatch):
    body = request().model_dump(mode="json")
    body["data_kind"] = "observed"
    assert post(client, body).status_code == 422
    catalog = get_catalog("TFT", "fixture_tft_v1").model_copy(deep=True)
    # Deliberately simulated verified catalog for code-path testing, not actual verification.
    for entity in [catalog, *catalog.champions, *catalog.traits, *catalog.emblems]:
        entity.verification_status = "verified"
    monkeypatch.setattr(service, "get_catalog", lambda *_: catalog)
    response = post(client, body)
    assert response.status_code == 200, response.text
    assert response.json()["records"][0]["verification_status"] == "provider_reported"
    assert client.get("/api/v1/statistics/observations", params=scope()).json()["statistics_available"] is True


def test_body_limits_errors_times_and_cors(client):
    headers = {"Authorization": "Bearer test-only-operator-token", "Content-Type": "application/json"}
    assert (
        client.post("/api/v1/statistics/ingest", content=b"x" * (2 * 1024 * 1024 + 1), headers=headers).status_code
        == 413
    )
    assert client.post("/api/v1/statistics/ingest", content="broken", headers=headers).status_code == 422
    assert (
        client.post(
            "/api/v1/statistics/ingest", content="text", headers={"Authorization": headers["Authorization"]}
        ).status_code
        == 415
    )
    body = request().model_dump(mode="json")
    body["observations"][0]["collected_at"] = (NOW + timedelta(minutes=6)).isoformat()
    assert post(client, body).status_code == 422
    body["observations"][0]["observed_start"] = "2026-10-10T00:00:00"
    assert post(client, body).status_code == 422
    assert client.get("/api/v1/statistics/observations/not-found").status_code == 404
    assert client.get("/api/v1/statistics/observations", params={**scope(), "limit": 101}).status_code == 422
    assert (
        client.options(
            "/api/v1/statistics/ingest",
            headers={
                "Origin": "http://127.0.0.1:3000",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Authorization,Content-Type",
            },
        ).status_code
        == 200
    )


def test_existing_optimizer_contract_unchanged(client):
    from app.schemas.domain import SolveRequest
    from app.optimizer.solver import solve

    catalog = get_catalog("TFT", "fixture_tft_v1")
    req = SolveRequest(game_id="TFT", ruleset_id=catalog.id, emblem_ids=[e.id for e in catalog.emblems[:3]], top_k=1)
    before = solve(catalog, req)["candidates"][0]
    assert post(client).status_code == 200
    after = solve(catalog, req)["candidates"][0]
    assert before["score"] == after["score"] and before["traits"] == after["traits"]
    assert after["score"]["sample_size"] is None
    assert after["score"]["win_rate"] is None
    response = client.post("/api/v1/holders/rank", json=req.model_dump()).json()
    assert response["statistics"] is None
    assert client.get("/api/v1/data-health").json()["statistics_available"] is False


def test_permission_does_not_allow_derivation(environment, client):
    environment([{**authorization(), "permitted_uses": ["ingest", "store", "display"]}])
    row = post(client).json()["records"][0]
    assert row["metrics"]["sample_size"] is None
    assert row["metrics"]["top_four_rate"] is None
    assert row["metrics"]["average_placement"] is None
    assert row["confidence"]["computed_top_four_rate"] is None
    assert row["observation"]["metrics"]["placement_counts"] == [1] * 8


def test_sample_bounds_staleness_and_coverage():
    obs = Observation.model_validate(
        {
            **observation(),
            "observed_end": (NOW - timedelta(days=10)).isoformat(),
            "observed_start": (NOW - timedelta(days=11)).isoformat(),
            "quality": {"independence": "clustered", "population_coverage": 0.2},
            "metrics": {"sample_size": 2, "top_four_count": 1},
        }
    )
    result = summarize(obs, True, "observed")
    assert {
        "sample_below_100",
        "partial_population_coverage",
        "observation_window_older_than_7_days",
        "deduplication_unknown",
        "independence_clustered",
    } <= set(result["data_quality"]["flags"])
    for values in ({"sample_size": 10**12 + 1}, {"placement_counts": [10**12] * 8}):
        with pytest.raises(ValidationError):
            Metrics.model_validate(values)
    zero = Observation.model_validate({**observation(), "metrics": {"placement_counts": [0] * 8}})
    assert summarize(zero, True, "observed")["metrics"] == {
        "sample_size": 0,
        "top_four_rate": None,
        "average_placement": None,
        "origins": {
            "sample_size": "derived_from_histogram",
            "top_four_rate": "missing",
            "average_placement": "missing",
        },
    }


def test_structural_and_time_errors(client):
    for changes in ({"observed_start": NOW.isoformat()}, {"placement_scale": 4}, {"sample_unit": "matches"}):
        body = request().model_dump(mode="json")
        body["observations"][0].update(changes)
        assert post(client, body).status_code == 422
    body = request().model_dump(mode="json")
    body["observations"] = [observation(str(i)) for i in range(501)]
    assert post(client, body).status_code == 422
    assert client.get("/api/v1/statistics/observations", params={**scope(), "context_key": "bad"}).status_code == 422
    schema = client.get("/openapi.json").json()["paths"]["/api/v1/statistics/ingest"]["post"]["requestBody"]
    assert "observations" in schema["content"]["application/json"]["schema"]["properties"]
    assert "$ref" not in json.dumps(schema)
    assert "#/$defs/" not in json.dumps(schema)


def test_context_equipment_limits_and_holder_board(client):
    body = request().model_dump(mode="json")
    base = {
        "kind": "composition",
        "composition": {
            "champion_ids": ["tft_unit_1"],
            "matching_rule": "exact_board",
            "emblem_assignments": [{"emblem_id": "tft_emblem_0", "champion_id": "tft_unit_1"}] * 4,
        },
    }
    body["observations"][0]["context"] = base
    assert post(client, body).status_code == 422
    body["observations"][0]["context"] = {
        "kind": "holder",
        "emblem_id": "tft_emblem_0",
        "champion_id": "tft_unit_1",
        "composition": {"champion_ids": ["tft_unit_1"], "matching_rule": "exact_board", "emblem_assignments": []},
    }
    assert post(client, body).status_code == 422
    body["observations"][0]["context"]["composition"]["emblem_assignments"] = [
        {"emblem_id": "tft_emblem_0", "champion_id": "tft_unit_1"}
    ]
    assert post(client, body).status_code == 200


def test_statistics_migration_preserves_guides(tmp_path, monkeypatch):
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import inspect, text

    url = f"sqlite:///{tmp_path}/migration.db"
    monkeypatch.setenv("DATABASE_URL", url)
    config = Config("alembic.ini")
    command.upgrade(config, "0002")
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO community_imports (id, metadata_json) VALUES ('existing', '{}')"))
    command.upgrade(config, "head")
    assert "statistics_observations" in inspect(engine).get_table_names()
    with engine.connect() as connection:
        assert connection.execute(text("SELECT id FROM community_imports")).scalar_one() == "existing"
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "0003"
    command.downgrade(config, "0002")
    assert "statistics_observations" not in inspect(engine).get_table_names()
    command.upgrade(config, "head")
    engine.dispose()


def test_both_games_and_first_party_scope(environment, client):
    environment([{**authorization(), "source_kind": "first_party", "access_method": "official_api"}])
    first = post(client).json()["records"][0]
    body = request().model_dump(mode="json")
    body["scope"] = scope("JCC")
    body["observations"][0]["context"] = {"kind": "holder", "emblem_id": "jcc_emblem_0", "champion_id": "jcc_unit_1"}
    response = post(client, body)
    assert response.status_code == 200, response.text
    second = response.json()["records"][0]
    assert first["id"] != second["id"]
    for game, expected in [("TFT", first["id"]), ("JCC", second["id"])]:
        rows = client.get("/api/v1/statistics/observations", params={**scope(game), "data_kind": "synthetic"}).json()
        assert [r["id"] for r in rows["records"]] == [expected]
        assert rows["records"][0]["source"]["source_kind"] == "first_party"


def test_empty_observed_metrics_do_not_claim_statistics_available(client, monkeypatch):
    catalog = get_catalog("TFT", "fixture_tft_v1").model_copy(deep=True)
    for entity in [catalog, *catalog.champions, *catalog.traits, *catalog.emblems]:
        entity.verification_status = "verified"  # simulated catalog for this test only
    monkeypatch.setattr(service, "get_catalog", lambda *_: catalog)
    body = request().model_dump(mode="json")
    body["data_kind"] = "observed"
    for index, metrics in enumerate(({}, {"sample_size": 0})):
        body["observations"][0]["provider_record_id"] = f"empty-{index}"
        body["observations"][0]["metrics"] = metrics
        assert post(client, body).status_code == 200
    result = client.get("/api/v1/statistics/observations", params=scope()).json()
    assert result["total"] == 2 and result["statistics_available"] is False
    assert all(r["metrics"]["top_four_rate"] is None for r in result["records"])
