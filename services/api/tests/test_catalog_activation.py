"""Fictional workflow cases only; not evidence of real JCC readiness."""

import csv
import io
import json
from itertools import combinations
import pytest
from fastapi.testclient import TestClient
from app.catalogs.activation import activate, rollback, registry, registered, encode, digest, prepare, ROOT
from app.data_validation.catalog import CORE_JCC_CHECKS, validate_catalog
from app.importers.game_manual import COLUMNS, LEGACY_COLUMNS, ManualMetadata, import_manual
from app.main import app
from app.optimizer.solver import solve, RULES
from app.repositories.catalog import get_catalog
from app.schemas.domain import SolveRequest
from app.scoring.engine import WEIGHTS


@pytest.fixture
def bundle(tmp_path):
    meta = ManualMetadata(
        game="JCC",
        ruleset_id="jcc_TEST_ONLY",
        patch="TEST_ONLY",
        set="TEST_ONLY",
        set_name="Fictional workflow test, not real JCC",
        mode="unit-test",
        source="Authored test records",
        source_url="https://example.com/test-only",
        license_status="original",
        attribution="Test authors",
        required_champion_ids=[f"jcc_test_u{i}" for i in range(10)],
        allow_duplicate_emblems=True,
        allow_unused_emblems=False,
        source_version="TEST_ONLY",
    )
    base = dict(
        game="JCC",
        patch=meta.patch,
        set=meta.set,
        mode=meta.mode,
        verification_status="VERIFIED",
        evidence="test:fictional-author-reviewed",
        reviewer="fixture-author",
    )
    rows = [
        dict(
            base,
            entity_type="trait",
            id=f"jcc_test_t{i}",
            zh_CN=f"测试羁绊{i}",
            en_US=f"Test trait {i}",
            thresholds="2|4|6",
        )
        for i in range(3)
    ]
    rows += [
        dict(
            base,
            entity_type="champion",
            id=f"jcc_test_u{i}",
            zh_CN=f"测试棋子{i}",
            en_US=f"Test unit {i}",
            cost=str(1 + i % 3),
            trait_ids=f"jcc_test_t{i % 3}",
            board_slots="2" if i == 0 else "1",
            aliases=f"测试别名{i}",
        )
        for i in range(10)
    ]
    rows += [
        dict(
            base,
            entity_type="emblem",
            id=f"jcc_test_e{i}",
            zh_CN=f"测试纹章{i}",
            en_US=f"Test emblem {i}",
            trait_id=f"jcc_test_t{i}",
        )
        for i in range(3)
    ]
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(COLUMNS)
    writer.writerows([[r.get(k, "") for k in COLUMNS] for r in rows])
    content = buffer.getvalue().encode()
    sources = tmp_path / "sources"
    sources.mkdir()
    (sources / "test.csv").write_bytes(content)
    draft = import_manual(content, "test.csv", meta)
    path = tmp_path / "draft.json"
    path.write_bytes(encode(draft["catalog"]))
    review = dict(
        schema_version=1,
        catalog_sha256=digest(path.read_bytes()),
        decision="approve",
        reviewer="Test reviewer A",
        independent_reviewer="Test reviewer B",
        reviewed_at="2026-01-01T00:00:00Z",
        release_date="2026-01-01",
        source_version="TEST_ONLY",
        scope="Fictional test scope; not a JCC release.",
        unsupported_mechanics=[],
        rules=[
            dict(id=k, status="VERIFIED", essential=True, evidence=["test:explicit-fictional-rule"], notes="Test only")
            for k in sorted(CORE_JCC_CHECKS)
        ],
        required_champion_ids=meta.required_champion_ids,
        required_trait_ids=[f"jcc_test_t{i}" for i in range(3)],
        required_emblem_ids=[f"jcc_test_e{i}" for i in range(3)],
        roster_citation="test:complete fictional roster",
        sources=[
            dict(
                filename="test.csv",
                url=str(meta.source_url),
                sha256=digest(content),
                category="manual_original",
                license_status="original",
                permission_evidence=["test:owned fictional text"],
                redistribution_allowed=True,
                attribution="Test author",
            )
        ],
        icons="text_only",
        icon_permission_evidence=[],
        cases=[],
    )
    for n in [0, 1, 3]:
        assignments = [
            dict(instance_index=i, emblem_id=f"jcc_test_e{i}", champion_id=f"jcc_test_u{(i + 1) % 3}") for i in range(n)
        ]
        review["cases"].append(
            dict(
                citation="test:independently counted native 3/2/2, +1 per equipped trait",
                request=dict(
                    game_id="JCC",
                    ruleset_id=meta.ruleset_id,
                    emblem_ids=[f"jcc_test_e{i}" for i in range(n)],
                    board_size=8,
                    top_k=1,
                ),
                selected=[f"jcc_test_u{i}" for i in range(7)],
                assignments=assignments,
                expected_trait_counts={f"jcc_test_t{i}": [3, 2, 2][i] + int(i < n) for i in range(3)},
            )
        )
    approval = tmp_path / "approval.json"
    approval.write_bytes(encode(review))
    root = tmp_path / "data"
    root.mkdir()
    return path, approval, sources, root


def promote(bundle):
    path, approval, sources, root = bundle
    return activate(
        path,
        approval,
        sources,
        actor="test-operator",
        reason="Unit test only",
        expected_revision=digest(encode(registry(root))),
        root=root,
    )


def test_complete_import_review_activation_rollback(bundle, monkeypatch):
    root = bundle[3]
    initial = digest(encode(registry(root)))
    index = promote(bundle)
    datasets, issues = registered(root)
    assert not issues and len(datasets) == 1
    d = datasets[0]
    assert d.champions[0].aliases == ["测试别名0"] and d.champions[0].en_US == "Test unit 0"
    assert d.champions[0].board_slots == 2 and d.data_readiness.optimization_enabled
    monkeypatch.setattr("app.repositories.catalog.ACTIVE_ROOT", root)
    monkeypatch.setenv("PUBLIC_DEMO", "true")
    client = TestClient(app)
    games = client.get("/api/v1/games?include_synthetic=false").json()
    assert [v["ruleset_id"] for v in games[1]["versions"]] == [d.id] and games[1]["versions"][0]["mode"] == "unit-test"
    assert client.get("/api/v1/catalog", params=dict(game_id="JCC", ruleset_id=d.id)).json()["game"] == "JCC"
    assert get_catalog("TFT", "tft_set18_18_4_standard").game == "TFT"
    body = dict(
        game_id="JCC", ruleset_id=d.id, emblem_ids=[e.id for e in d.emblems], board_size=8, top_k=3, timeout_seconds=3
    )
    response = client.post("/api/v1/solve", json=body)
    assert response.status_code == 200
    candidates = response.json()["candidates"]
    assert len(candidates) == 3
    assert len({tuple(c["id"] for c in v["champions"]) for v in candidates}) == 3
    assert all(len(v["assignments"]) == 3 for v in candidates)
    assert client.post("/api/v1/holders/rank", json=body).json()["rankings"]
    assert client.post("/api/v1/solve", json={**body, "game_id": "TFT"}).status_code == 422
    rollback(initial, actor="operator", reason="Test rollback", expected_revision=digest(encode(index)), root=root)
    assert registered(root) == ([], []) and len(registry(root)["audit"]) == 2
    assert get_catalog("TFT", "tft_set18_18_4_standard")


@pytest.mark.parametrize(
    "fault",
    [
        "review_hash",
        "reviewer",
        "rules",
        "entity_evidence",
        "missing_roster",
        "counts",
        "permission",
        "future",
        "sources",
        "icons",
    ],
)
def test_approval_blocks_incomplete_bundle(bundle, fault):
    path, approval, sources, root = bundle
    review = json.loads(approval.read_bytes())
    raw = json.loads(path.read_bytes())
    if fault == "review_hash":
        review["catalog_sha256"] = "0" * 64
    if fault == "reviewer":
        review["independent_reviewer"] = review["reviewer"]
    if fault == "rules":
        review["rules"].pop()
    if fault == "entity_evidence":
        raw["champions"][0]["verification_evidence"] = []
    if fault == "missing_roster":
        review["required_champion_ids"].pop()
    if fault == "counts":
        review["cases"][0]["expected_trait_counts"]["jcc_test_t0"] = 99
    if fault == "permission":
        review["sources"][0]["redistribution_allowed"] = False
    if fault == "future":
        review["reviewed_at"] = "2099-01-01T00:00:00Z"
    if fault == "sources":
        (sources / "test.csv").write_bytes(b"changed")
    if fault == "icons":
        raw["champions"][0]["icon_path"] = "https://example.com/unlicensed.png"
    if fault in ("entity_evidence", "icons"):
        path.write_bytes(encode(raw))
        review["catalog_sha256"] = digest(path.read_bytes())
    approval.write_bytes(encode(review))
    with pytest.raises(ValueError):
        promote(bundle)
    assert registry(root)["active"] == []


@pytest.mark.parametrize(
    "filename", ["catalog.json", "review.json", "validation.json", "input.json", "sources/test.csv"]
)
@pytest.mark.parametrize("fault", ["corrupt", "missing"])
def test_bad_artifact_isolated_from_tft(bundle, monkeypatch, filename, fault):
    root = bundle[3]
    index = promote(bundle)
    path = root / index["active"][0]["artifact"] / filename
    if fault == "corrupt":
        path.write_bytes(b"{}")
    else:
        path.unlink()
    assert not registered(root)[0] and registered(root)[1]
    monkeypatch.setattr("app.repositories.catalog.ACTIVE_ROOT", root)
    monkeypatch.setenv("PUBLIC_DEMO", "true")
    assert get_catalog("TFT", "tft_set18_18_4_standard").game == "TFT"
    with pytest.raises(ValueError):
        get_catalog("JCC", "jcc_TEST_ONLY")


def test_stale_revision_fails(bundle):
    path, approval, sources, root = bundle
    with pytest.raises(ValueError, match="Registry changed"):
        activate(path, approval, sources, actor="a", reason="b", expected_revision="0" * 64, root=root)
    assert registry(root)["active"] == []
    with pytest.raises((ValueError, OSError)):
        prepare(path, approval, sources / "missing")


def test_corrupted_registry_isolated(bundle, monkeypatch):
    root = bundle[3]
    promote(bundle)
    (root / "active/index.json").write_text("{")
    assert registered(root)[1]
    monkeypatch.setattr("app.repositories.catalog.ACTIVE_ROOT", root)
    assert get_catalog("TFT", "tft_set18_18_4_standard")


def test_jcc_ready_flag_cannot_bypass_rules(bundle):
    raw = json.loads(bundle[0].read_bytes())
    raw["data_readiness"].update(
        optimization_enabled=True,
        rule_checks=[dict(id="made_up", status="VERIFIED", essential=True, evidence=["test"], notes="")],
    )
    assert not validate_catalog(raw)["optimization_enabled"]


@pytest.mark.parametrize("objective", list(WEIGHTS))
def test_fictional_solver_against_independent_reference(bundle, objective):
    promote(bundle)
    d = registered(bundle[3])[0][0]
    request = SolveRequest(
        game_id="JCC",
        ruleset_id=d.id,
        board_size=7,
        emblem_ids=["jcc_test_e0"],
        objective=objective,
        top_k=1,
        timeout_seconds=3,
    )
    best = None
    for n in range(1, 9):
        for units in combinations(d.champions, n):
            if sum(u.board_slots for u in units) != 7:
                continue
            for holder in units:
                if "jcc_test_t0" in holder.traits:
                    continue
                counts = {t.id: sum(t.id in u.traits for u in units) + int(t.id == "jcc_test_t0") for t in d.traits}
                active = sum(counts[t.id] >= 2 for t in d.traits)
                utility = sum(sum(counts[t.id] >= threshold for threshold in (2, 4, 6)) for t in d.traits)
                w = WEIGHTS[objective]
                score = w[0] * active + w[1] * utility + w[2] * sum(u.cost for u in units) + w[3]
                best = score if best is None else max(best, score)
    result = solve(d, request)
    assert result["status"] == "OPTIMAL" and result["candidates"][0]["score"]["total"] == best


def test_constraints_duplicate_population_and_native_count(bundle):
    promote(bundle)
    d = registered(bundle[3])[0][0]
    r = SolveRequest(
        game_id="JCC",
        ruleset_id=d.id,
        board_size=8,
        emblem_ids=["jcc_test_e0"] * 2,
        top_k=1,
        constraints=dict(locked_units=["jcc_test_u0"], banned_units=["jcc_test_u9"]),
    )
    c = solve(d, r)["candidates"][0]
    assert sum(u["board_slots"] for u in c["champions"]) == 8
    ids = [u["id"] for u in c["champions"]]
    assert "jcc_test_u0" in ids and "jcc_test_u9" not in ids
    assert len({a["champion_id"] for a in c["assignments"]}) == 2
    native = [dict(instance_index=0, emblem_id="jcc_test_e0", champion_id="jcc_test_u0")]
    with pytest.raises(ValueError, match="Illegal emblem"):
        RULES.validate_solution(d, r, ids, native)
    assert next(t for t in RULES.evaluate(d, ["jcc_test_u0"], native) if t["id"] == "jcc_test_t0")["count"] == 1
    d.traits[0].special_conditions = "unmodeled"
    assert not validate_catalog(d.model_dump())["optimization_enabled"]


def test_real_jcc_not_falsely_claimed():
    assert not registered(ROOT)[0], "Replace with genuine reviewed data assertions when available"


def test_legacy_manual_csv_still_parses():
    from app.importers.game_manual import parse_rows

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(LEGACY_COLUMNS)
    writer.writerow(["test"] + [""] * (len(LEGACY_COLUMNS) - 1))
    assert parse_rows(buffer.getvalue().encode(), "test.csv")[0]["board_slots"] == ""


@pytest.mark.parametrize("raw", [[], None, {"schema_version": 1, "generation": 0, "active": [None], "audit": []}])
def test_wrong_registry_shape_cannot_break_tft(bundle, monkeypatch, raw):
    root = bundle[3]
    (root / "active").mkdir()
    (root / "active/index.json").write_text(json.dumps(raw))
    monkeypatch.setattr("app.repositories.catalog.ACTIVE_ROOT", root)
    assert registered(root)[1] and get_catalog("TFT", "tft_set18_18_4_standard")
    health = TestClient(app).get("/api/v1/data-health")
    assert health.status_code == 200
    assert health.json()["catalog_activation_issues"]
