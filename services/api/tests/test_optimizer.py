from itertools import combinations
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.repositories.catalog import get_catalog
from app.schemas.domain import SolveRequest, ReforgeRequest, Ruleset
from app.optimizer.solver import solve, RULES
from app.scoring.engine import score
from app.reforge.service import simulate


@pytest.fixture
def dataset():
    return get_catalog("TFT", "fixture_tft_v1")


def req(**kw):
    return SolveRequest(game_id="TFT", ruleset_id="fixture_tft_v1", top_k=1, **kw)


def test_trait_count(dataset):
    chosen = [c.id for c in dataset.champions[:7]]
    result = RULES.evaluate(dataset, chosen, [])
    for t in result:
        assert t["count"] == sum(t["id"] in c.traits for c in dataset.champions[:7])
        assert t["level"] == sum(t["count"] >= v for v in t["thresholds"])


def test_native_emblem_or(dataset):
    c = dataset.champions[0]
    e = next(e for e in dataset.emblems if e.trait_id in c.traits)
    a = [dict(instance_index=0, emblem_id=e.id, champion_id=c.id)]
    assert RULES.evaluate(dataset, [c.id], a) == RULES.evaluate(dataset, [c.id], [])


def test_multiple_emblems_and_slots(dataset):
    r = req(emblem_ids=[e.id for e in dataset.emblems[:3]])
    out = solve(dataset, r)
    c = out["candidates"][0]
    assert len(c["assignments"]) == 3
    RULES.validate_solution(dataset, r, [u["id"] for u in c["champions"]], c["assignments"])
    assert len({a["instance_index"] for a in c["assignments"]}) == 3


def test_illegal_holder_rejected(dataset):
    r = req(emblem_ids=[dataset.emblems[0].id])
    chosen = [c.id for c in dataset.champions[:8]]
    with pytest.raises(ValueError, match="Illegal"):
        RULES.validate_solution(
            dataset, r, chosen, [dict(instance_index=0, emblem_id=dataset.emblems[0].id, champion_id=chosen[0])]
        )


@pytest.mark.parametrize("size", [7, 8, 9, 10])
def test_board_capacity(dataset, size):
    out = solve(dataset, req(board_size=size))
    assert len(out["candidates"][0]["champions"]) == size


def test_locks_bans_cost(dataset):
    r = req(constraints={"locked_units": ["tft_unit_0"], "banned_units": ["tft_unit_1"], "max_unit_cost": 4})
    c = solve(dataset, r)["candidates"][0]
    ids = {u["id"] for u in c["champions"]}
    assert "tft_unit_0" in ids and "tft_unit_1" not in ids
    assert all(u["cost"] <= 4 for u in c["champions"])


def test_thresholds(dataset):
    assert dataset.traits[0].thresholds[0].count == 2
    assert dataset.traits[1].thresholds[0].count == 3
    assert dataset.traits[0].thresholds[1].utility != 2 * dataset.traits[0].thresholds[0].utility


def test_game_isolation(dataset):
    other = get_catalog("JCC", "fixture_jcc_v1")
    assert not {u.id for u in dataset.champions} & {u.id for u in other.champions}
    with pytest.raises(ValueError):
        get_catalog("TFT", other.id)
    with pytest.raises(ValueError):
        solve(dataset, req(emblem_ids=[other.emblems[0].id]))
    raw = dataset.model_dump()
    raw["champions"][0]["game"] = "JCC"
    with pytest.raises(ValueError):
        Ruleset.model_validate(raw)


def test_infeasible(dataset):
    assert (
        solve(dataset, req(constraints={"locked_units": ["tft_unit_0"], "banned_units": ["tft_unit_0"]}))["status"]
        == "INFEASIBLE"
    )
    assert solve(dataset, req(constraints={"max_unit_cost": 1}))["status"] == "INFEASIBLE"


def test_timeout_status(dataset):
    r = solve(dataset, req(timeout_seconds=0.001))
    assert r["status"] in ["UNKNOWN", "FEASIBLE", "OPTIMAL"]
    for c in r["candidates"]:
        assert c["solver_status"] in ["FEASIBLE", "OPTIMAL"]


def test_diversity(dataset):
    r = SolveRequest(game_id="TFT", ruleset_id=dataset.id, top_k=5)
    cs = solve(dataset, r)["candidates"]
    assert len(cs) >= 3
    for a, b in combinations(cs, 2):
        assert len({c["id"] for c in a["champions"]} - {c["id"] for c in b["champions"]}) >= 2


def test_missing_statistics(dataset):
    c = solve(dataset, req())["candidates"][0]
    assert c["score"]["win_rate"] is None and c["score"]["sample_size"] is None
    assert c["score"]["kind"] == "rules_based_estimate"


@pytest.mark.parametrize("objective", ["MAX_ACTIVE_TRAITS", "MAX_BREAKPOINT", "BALANCED", "LOW_COST", "LATE_GAME"])
def test_bruteforce_optimal(dataset, objective):
    # Small exhaustive reference: 9 units choose 7, 1 emblem, all legal holders or unused.
    small = dataset.model_copy(deep=True)
    small.champions = small.champions[:9]
    for e in small.emblems:
        e.banned_holders = []
    r = req(board_size=7, emblem_ids=[small.emblems[0].id], objective=objective)
    best = -(10**9)
    for board in combinations(small.champions, 7):
        choices = [None] + [u for u in board if RULES.legal(u, small.emblems[0])]
        for holder in choices:
            a = [] if holder is None else [dict(instance_index=0, emblem_id=small.emblems[0].id, champion_id=holder.id)]
            traits = RULES.evaluate(small, [u.id for u in board], a)
            best = max(best, score(traits, board, a, objective)["total"])
    out = solve(small, r)
    assert out["status"] == "OPTIMAL"
    assert out["candidates"][0]["score"]["total"] == best


def test_unknown_reforge_and_locks(dataset):
    r = ReforgeRequest(
        game_id="TFT",
        ruleset_id=dataset.id,
        emblem_ids=[e.id for e in dataset.emblems[:3]],
        locked_emblem_indices=[1],
        timeout_seconds=0.05,
    )
    result = simulate(dataset, r)
    assert len(result["scenarios"]) == 8
    assert result["probabilities"] is None and result["expected_value"] is None
    assert sum(s["allowed"] for s in result["scenarios"]) == 4
    with pytest.raises(ValueError):
        simulate(dataset, r.model_copy(update={"action": "actual_reforge"}))


def test_item_slots(dataset):
    for c in dataset.champions:
        c.item_slots = 0
    out = solve(dataset, req(emblem_ids=["tft_emblem_0"]))
    assert not out["candidates"][0]["assignments"]
    dataset.allow_unused_emblems = False
    assert solve(dataset, req(emblem_ids=["tft_emblem_0"]))["status"] == "INFEASIBLE"


def test_duplicate_rules(dataset):
    assert solve(dataset, req(emblem_ids=["tft_emblem_0"] * 3))["candidates"]
    jcc = get_catalog("JCC", "fixture_jcc_v1")
    with pytest.raises(ValueError):
        solve(jcc, SolveRequest(game_id="JCC", ruleset_id=jcc.id, emblem_ids=["jcc_emblem_0"] * 2))


def test_unsupported_mechanic(dataset):
    dataset.traits[0].special_conditions = "unknown mechanic"
    with pytest.raises(ValueError, match="Unsupported"):
        solve(dataset, req())


client = TestClient(app)


@pytest.mark.parametrize(
    "payload",
    [
        {"board_size": 6},
        {"top_k": 0},
        {"timeout_seconds": 0},
        {"emblem_ids": ["x"] * 4},
        {"objective": "bad"},
        {"unknown": True},
        {"game_id": "other"},
    ],
)
def test_api_validation(payload):
    body = {"game_id": "TFT", "ruleset_id": "fixture_tft_v1"}
    body.update(payload)
    assert client.post("/api/v1/solve", json=body).status_code == 422


def test_api_flow():
    assert client.get("/health").status_code == 200
    assert len(client.get("/api/v1/games").json()) == 2
    data = client.get("/api/v1/catalog").json()
    body = {
        "game_id": "TFT",
        "ruleset_id": data["id"],
        "emblem_ids": [e["id"] for e in data["emblems"][:3]],
        "top_k": 2,
    }
    r = client.post("/api/v1/solve", json=body)
    assert r.status_code == 200 and len(r.json()["candidates"]) == 2
    holders = client.post("/api/v1/holders/rank", json=body)
    assert holders.status_code == 200 and holders.json()["rankings"]
    assert client.get("/api/v1/data-health").json()["current_patch_verified"] is False
    body["emblem_ids"] = ["jcc_emblem_0"]
    assert client.post("/api/v1/solve", json=body).status_code == 422


def test_multiple_emblems_on_same_holder(dataset):
    chosen = [c.id for c in dataset.champions[:8]]
    holder = dataset.champions[0]
    eligible = [e for e in dataset.emblems if RULES.legal(holder, e)][:3]
    r = req(emblem_ids=[e.id for e in eligible])
    assignments = [dict(instance_index=i, emblem_id=e.id, champion_id=holder.id) for i, e in enumerate(eligible)]
    RULES.validate_solution(dataset, r, chosen, assignments)
    holder.item_slots = 2
    with pytest.raises(ValueError, match="Item slots"):
        RULES.validate_solution(dataset, r, chosen, assignments)


def test_database_roundtrip(dataset, tmp_path, monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.models.database import Base, VersionedRecord
    from app.importers import manual

    engine = create_engine("sqlite:///" + str(tmp_path / "test.db"))
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine)
    monkeypatch.setattr(manual, "Session", factory)
    path = tmp_path / "fixture.json"
    path.write_text(dataset.model_dump_json())
    manual.import_json(path)
    output = tmp_path / "export.json"
    manual.export_json(dataset.game, dataset.id, output)
    assert Ruleset.model_validate_json(output.read_text()) == dataset
    with factory() as session:
        assert session.get(VersionedRecord, ("JCC", dataset.id, "Ruleset", dataset.id)) is None


def test_unavailable_unlock(dataset):
    dataset.champions[0].unlock_condition = "unsupported quest"
    assert solve(dataset, req(constraints={"locked_units": [dataset.champions[0].id]}))["status"] == "INFEASIBLE"
