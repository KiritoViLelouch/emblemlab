import json
from itertools import combinations
from pathlib import Path
import httpx
from tests.test_mvp_review import reference
from app.repositories.catalog import get_catalog

client = httpx.Client(base_url="http://127.0.0.1:8000", timeout=30)
report = {"health": client.get("/health").json(), "games": client.get("/api/v1/games").json(), "checks": []}
assert report["health"]["status"] == "ok"
assert {g["id"] for g in report["games"]} == {"TFT", "JCC"}
for game in ["TFT", "JCC"]:
    dataset = get_catalog(game, f"fixture_{game.lower()}_v1")
    catalog = client.get("/api/v1/catalog", params={"game_id": game, "ruleset_id": dataset.id})
    assert catalog.status_code == 200
    assert all(c["game"] == game for key in ["champions", "traits", "emblems"] for c in catalog.json()[key])
    body = dict(
        game_id=game,
        ruleset_id=dataset.id,
        emblem_ids=[e.id for e in dataset.emblems[:3]],
        board_size=8,
        constraints={
            "locked_units": [dataset.champions[0].id],
            "banned_units": [dataset.champions[1].id],
            "max_unit_cost": 4,
        },
        top_k=5,
        timeout_seconds=5,
    )
    for mode in ["MAX_ACTIVE_TRAITS", "MAX_BREAKPOINT", "BALANCED", "LOW_COST", "LATE_GAME"]:
        response = client.post("/api/v1/solve", json={**body, "objective": mode})
        assert response.status_code == 200
        result = response.json()
        assert len(result["candidates"]) == 5
        for c in result["candidates"]:
            ids = {u["id"] for u in c["champions"]}
            assert len(ids) == 8 and dataset.champions[0].id in ids and dataset.champions[1].id not in ids
            board = [u for u in dataset.champions if u.id in ids]
            assert all(u.cost <= 4 for u in board)
            placement = [
                next((a["champion_id"] for a in c["assignments"] if a["instance_index"] == i), None) for i in range(3)
            ]
            actual = reference(dataset, board, body["emblem_ids"], placement, mode)
            assert actual is not None and actual[0] == c["score"]["total"]
            assert actual[1] == {t["id"]: t["count"] for t in c["traits"]}
            assert c["score"]["win_rate"] is None and c["score"]["sample_size"] is None
        for a, b in combinations(result["candidates"], 2):
            assert len({c["id"] for c in a["champions"]} - {c["id"] for c in b["champions"]}) >= 2
        report["checks"].append(
            dict(
                game=game,
                objective=mode,
                status=result["status"],
                candidates=len(result["candidates"]),
                best_score=result["candidates"][0]["score"]["total"],
            )
        )
    for n in [7, 8, 9, 10]:
        r = client.post("/api/v1/solve", json={**body, "board_size": n, "constraints": {}, "top_k": 1}).json()
        assert len(r["candidates"][0]["champions"]) == n
    conflict = client.post(
        "/api/v1/solve",
        json={
            **body,
            "constraints": {"locked_units": [dataset.champions[0].id], "banned_units": [dataset.champions[0].id]},
        },
    )
    assert conflict.json()["status"] == "INFEASIBLE" and not conflict.json()["candidates"]
    mismatched = "JCC" if game == "TFT" else "TFT"
    assert client.get("/api/v1/catalog", params={"game_id": mismatched, "ruleset_id": dataset.id}).status_code == 422
    assert (
        client.post("/api/v1/solve", json={**body, "emblem_ids": [f"{mismatched.lower()}_emblem_0"]}).status_code == 422
    )
    holders = client.post("/api/v1/holders/rank", json=body)
    assert holders.status_code == 200 and len(holders.json()["rankings"]) == 3
    subset = client.post("/api/v1/reforge/simulate", json={**body, "locked_emblem_indices": [1], "timeout_seconds": 1})
    assert subset.status_code == 200
    subsets = subset.json()
    assert len(subsets["scenarios"]) == 8 and sum(s["allowed"] for s in subsets["scenarios"]) == 4
    assert subsets["probabilities"] is None and subsets["expected_value"] is None
    assert client.post("/api/v1/reforge/simulate", json={**body, "action": "actual_reforge"}).status_code == 422
report["fixture_ids_disjoint"] = not (
    {u.id for u in get_catalog("TFT", "fixture_tft_v1").champions}
    & {u.id for u in get_catalog("JCC", "fixture_jcc_v1").champions}
)
assert report["fixture_ids_disjoint"]
web = httpx.Client(base_url="http://127.0.0.1:3000", timeout=30)
report["page_statuses"] = {p: web.get(p).status_code for p in ["/", "/catalog", "/compare", "/data", "/about"]}
assert all(v == 200 for v in report["page_statuses"].values())
Path("../../docs/review-api-results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
print(json.dumps(report, ensure_ascii=False, indent=2))
