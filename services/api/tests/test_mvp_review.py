"""Independent reference checks: no production rules/counting/scoring in the oracle."""

from collections import Counter
from itertools import combinations, product

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.optimizer.solver import RULES, solve
from app.repositories.catalog import get_catalog
from app.schemas.domain import SolveRequest

OBJECTIVES = {
    "MAX_ACTIVE_TRAITS": (10000, 10, -1, 1),
    "MAX_BREAKPOINT": (10, 100, -1, 1),
    "BALANCED": (100, 10, -2, 5),
    "LOW_COST": (10000, 1, -100, 1),
    "LATE_GAME": (100, 10, 30, 5),
}


def reference(dataset, board, emblem_ids, placement, objective):
    """Returns independent objective/counts or None for an illegal assignment."""
    emblems = {e.id: e for e in dataset.emblems}
    units = {u.id: u for u in board}
    slots = Counter()
    duplicates = Counter()
    contributions = {u.id: set(u.traits) for u in board}
    for eid, uid in zip(emblem_ids, placement):
        if uid is None:
            if not dataset.allow_unused_emblems:
                return None
            continue
        u, e = units[uid], emblems[eid]
        if (
            not u.available
            or u.unlock_condition
            or uid in e.banned_holders
            or (not e.allow_native and e.trait_id in u.traits)
        ):
            return None
        slots[uid] += 1
        duplicates[uid, eid] += 1
        if slots[uid] > u.item_slots or duplicates[uid, eid] > dataset.max_same_emblem_per_holder:
            return None
        contributions[uid].add(e.trait_id)
    counts = {t.id: sum(t.id in owned for owned in contributions.values()) for t in dataset.traits}
    active = sum(counts[t.id] >= t.thresholds[0].count for t in dataset.traits)
    utility = sum(max([0] + [b.utility for b in t.thresholds if counts[t.id] >= b.count]) for t in dataset.traits)
    cost = sum(u.cost for u in board)
    assigned = sum(uid is not None for uid in placement)
    total = sum(value * weight for value, weight in zip((active, utility, cost, assigned), OBJECTIVES[objective]))
    return total, counts


@pytest.mark.parametrize("game,duplicate", [("TFT", False), ("TFT", True), ("JCC", False)])
@pytest.mark.parametrize("objective", list(OBJECTIVES))
def test_three_emblem_exhaustive_reference(game, duplicate, objective):
    dataset = get_catalog(game, f"fixture_{game.lower()}_v1").model_copy(deep=True)
    dataset.champions = dataset.champions[:9]
    # Preserve valid references while keeping the exhaustive search small.
    for e in dataset.emblems:
        e.banned_holders = [u for u in e.banned_holders if any(c.id == u for c in dataset.champions)]
    dataset.champions[0].item_slots = 1
    emblem_ids = [dataset.emblems[0].id] * 3 if duplicate else [e.id for e in dataset.emblems[:3]]
    locked, banned = dataset.champions[0].id, dataset.champions[1].id
    request = SolveRequest(
        game_id=game,
        ruleset_id=dataset.id,
        board_size=7,
        emblem_ids=emblem_ids,
        objective=objective,
        top_k=1,
        constraints={"locked_units": [locked], "banned_units": [banned]},
    )
    best = None
    for board in combinations(dataset.champions, 7):
        ids = {u.id for u in board}
        if locked not in ids or banned in ids:
            continue
        for placement in product([None] + sorted(ids), repeat=3):
            value = reference(dataset, board, emblem_ids, placement, objective)
            if value is not None:
                best = value[0] if best is None else max(best, value[0])
    output = solve(dataset, request)
    assert output["status"] == "OPTIMAL"
    candidate = output["candidates"][0]
    board = [c for c in dataset.champions if c.id in {u["id"] for u in candidate["champions"]}]
    placement = [
        next((a["champion_id"] for a in candidate["assignments"] if a["instance_index"] == i), None) for i in range(3)
    ]
    actual = reference(dataset, board, emblem_ids, placement, objective)
    assert actual is not None
    assert actual[0] == best == candidate["score"]["total"] == candidate["objective_value"]
    assert actual[1] == {t["id"]: t["count"] for t in candidate["traits"]}


@pytest.mark.parametrize("game", ["TFT", "JCC"])
def test_full_fixture_api_constraints_and_independent_counts(game):
    client = TestClient(app)
    dataset = get_catalog(game, f"fixture_{game.lower()}_v1")
    request = SolveRequest(
        game_id=game,
        ruleset_id=dataset.id,
        emblem_ids=[e.id for e in dataset.emblems[:3]],
        top_k=5,
        constraints={
            "locked_units": [dataset.champions[0].id],
            "banned_units": [dataset.champions[1].id],
            "max_unit_cost": 4,
        },
    )
    response = client.post("/api/v1/solve", json=request.model_dump())
    assert response.status_code == 200
    output = response.json()
    assert output["game_id"] == game and output["ruleset_id"] == dataset.id
    assert len(output["candidates"]) == 5
    for candidate in output["candidates"]:
        ids = {u["id"] for u in candidate["champions"]}
        assert len(ids) == 8 and dataset.champions[0].id in ids and dataset.champions[1].id not in ids
        board = [u for u in dataset.champions if u.id in ids]
        assert all(u.cost <= 4 for u in board)
        placement = [
            next((a["champion_id"] for a in candidate["assignments"] if a["instance_index"] == i), None)
            for i in range(3)
        ]
        assert len({a["instance_index"] for a in candidate["assignments"]}) == len(candidate["assignments"])
        checked = reference(dataset, board, request.emblem_ids, placement, request.objective)
        assert checked is not None and checked[0] == candidate["score"]["total"]
        assert checked[1] == {t["id"]: t["count"] for t in candidate["traits"]}


def test_solution_validator_unknown_champion_is_value_error():
    dataset = get_catalog("TFT", "fixture_tft_v1")
    request = SolveRequest(game_id="TFT", ruleset_id=dataset.id)
    selected = [u.id for u in dataset.champions[:7]] + ["jcc_unit_0"]
    with pytest.raises(ValueError, match="capacity"):
        RULES.validate_solution(dataset, request, selected, [])


def test_solver_or_when_native_equipment_permitted():
    dataset = get_catalog("TFT", "fixture_tft_v1").model_copy(deep=True)
    dataset.champions = dataset.champions[:7]
    emblem = dataset.emblems[0]
    emblem.allow_native = True
    emblem.banned_holders = [u.id for u in dataset.champions if emblem.trait_id not in u.traits]
    dataset.allow_unused_emblems = False
    request = SolveRequest(game_id="TFT", ruleset_id=dataset.id, board_size=7, emblem_ids=[emblem.id], top_k=1)
    output = solve(dataset, request)
    candidate = output["candidates"][0]
    assert len(candidate["assignments"]) == 1
    native_count = sum(emblem.trait_id in u.traits for u in dataset.champions)
    assert next(t["count"] for t in candidate["traits"] if t["id"] == emblem.trait_id) == native_count


def test_duplicate_equipment_contributes_once_when_ruleset_permits_it():
    dataset = get_catalog("TFT", "fixture_tft_v1").model_copy(deep=True)
    dataset.champions = dataset.champions[:7]
    emblem = dataset.emblems[2]
    holder = dataset.champions[0]
    assert emblem.trait_id not in holder.traits
    emblem.banned_holders = [u.id for u in dataset.champions if u.id != holder.id]
    dataset.max_same_emblem_per_holder = 3
    dataset.allow_unused_emblems = False
    request = SolveRequest(game_id="TFT", ruleset_id=dataset.id, board_size=7, emblem_ids=[emblem.id] * 3, top_k=1)
    output = solve(dataset, request)
    candidate = output["candidates"][0]
    assert len(candidate["assignments"]) == 3
    assert {a["champion_id"] for a in candidate["assignments"]} == {holder.id}
    expected = 1 + sum(emblem.trait_id in u.traits for u in dataset.champions)
    assert next(t["count"] for t in candidate["traits"] if t["id"] == emblem.trait_id) == expected
    assert all("不重复贡献" in a["explanation"] for a in candidate["assignments"])


def test_native_holder_explanation_reports_zero_added_count(monkeypatch):
    from app.api import routes

    dataset = get_catalog("TFT", "fixture_tft_v1").model_copy(deep=True)
    dataset.champions = dataset.champions[:7]
    emblem = dataset.emblems[0]
    emblem.allow_native = True
    emblem.banned_holders = [u.id for u in dataset.champions if emblem.trait_id not in u.traits]
    dataset.allow_unused_emblems = False
    monkeypatch.setattr(routes, "get_catalog", lambda game_id, ruleset_id: dataset)
    response = TestClient(app).post(
        "/api/v1/holders/rank",
        json={
            "game_id": "TFT",
            "ruleset_id": dataset.id,
            "board_size": 7,
            "emblem_ids": [emblem.id],
            "top_k": 1,
        },
    )
    assert response.status_code == 200
    holders = response.json()["rankings"][0]["holders"]
    assert holders and all("计数 +0" in h["explanation"] for h in holders)
    assert all(h["active_trait_gain"] == 0 and h["breakpoint_utility_gain"] == 0 for h in holders)
