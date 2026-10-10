"""Actual reviewed TFT records; availability scenarios do not assert draw probabilities."""

import pytest
from app.repositories.catalog import get_catalog
from app.schemas.domain import SolveRequest
from app.optimizer.solver import solve, RULES


@pytest.mark.parametrize("population", [7, 8, 9, 10])
def test_real_lux_with_and_without_are_distinct_legal_boards(population):
    d = get_catalog("TFT", "tft_set18_18_4_standard")
    forms = [c for c in d.champions if c.exclusive_group == "DA_18_Lux"]
    chosen = "DA_Lux18_Blossom"
    assert next(c for c in forms if c.id == chosen).cost == 5
    for with_lux in [False, True]:
        r = SolveRequest(
            game_id=d.game,
            ruleset_id=d.id,
            board_size=population,
            top_k=1,
            timeout_seconds=2,
            emblem_ids=["DA_18_EmblemBrawler", "DA_18_EmblemBlossom", "DA_18_EmblemElderwood"],
            constraints=dict(
                locked_units=[chosen] if with_lux else [],
                banned_units=[c.id for c in forms if not with_lux or c.id != chosen],
            ),
        )
        result = solve(d, r)
        assert result["candidates"], result["status"]
        c = result["candidates"][0]
        ids = [u["id"] for u in c["champions"]]
        assert (chosen in ids) == with_lux and sum(u["board_slots"] for u in c["champions"]) == population
        assert sum(u["exclusive_group"] == "DA_18_Lux" for u in c["champions"]) == int(with_lux)
        RULES.validate_solution(d, r, ids, c["assignments"])
        # Independent native/emblem maximum per unique entity, including Lux's verified double contribution.
        for trait in c["traits"]:
            count = 0
            for u in c["champions"]:
                native = u["trait_weights"].get(trait["id"], 1) if trait["id"] in u["traits"] else 0
                granted = int(
                    any(
                        a["champion_id"] == u["id"]
                        and next(e for e in d.emblems if e.id == a["emblem_id"]).trait_id == trait["id"]
                        for a in c["assignments"]
                    )
                )
                count += max(native, granted)
            assert count == trait["count"]
