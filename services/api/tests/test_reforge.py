"""Synthetic laws. Independent exhaustive draws, boards, assignments and EV oracle."""

from collections import defaultdict
from fractions import Fraction
from itertools import combinations, permutations, product

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.reforge import analyzer, rules
from app.reforge.analyzer import analyze, enumerate_strategies
from app.reforge.rules import catalog_digest, get_rule
from app.reforge.schemas import AnalysisRequest, ReforgeRule
from app.repositories.catalog import get_catalog
from test_mvp_review import OBJECTIVES, reference


def fixture(game="TFT", known=True):
    d = get_catalog(game, f"fixture_{game.lower()}_v1").model_copy(deep=True)
    d.champions, d.emblems = d.champions[:9], d.emblems[:4]
    for i, c in enumerate(d.champions):
        c.item_slots = 1 if i < 3 else 0
    for e in d.emblems:
        e.banned_holders = []
    rule = get_rule(get_catalog(game, d.id), f"synthetic_{game.lower()}_{'known' if known else 'unknown'}_v1")
    raw = rule.model_dump()
    raw["catalog_sha256"] = catalog_digest(d)
    raw["target_pools"] = [
        dict(
            input_emblem_id=e.id,
            outcomes=[
                dict(
                    emblem_id=d.emblems[(i + j) % 4].id, probability=dict(numerator=w, denominator=3) if known else None
                )
                for j, w in [(1, 1), (2, 2)]
            ],
        )
        for i, e in enumerate(d.emblems)
    ]
    return d, ReforgeRule.model_validate(raw)


def request(d, rule, **updates):
    raw = dict(
        game_id=d.game,
        ruleset_id=d.id,
        reforge_rule_id=rule.id,
        emblem_ids=[e.id for e in d.emblems[:3]],
        board_size=7,
        available_reforgers=3,
        constraints=dict(locked_units=[d.champions[0].id], banned_units=[d.champions[-1].id]),
    )
    return AnalysisRequest.model_validate(raw | updates)


def draw_oracle(d, rule, inventory, order):
    pools = {p.input_emblem_id: p.outcomes for p in rule.target_pools}
    masses, possible = defaultdict(Fraction), set()
    for choices in product(*(pools[inventory[i]] for i in order)):
        current, mass, reachable = list(inventory), Fraction(1), True
        for index, chosen in zip(order, choices):
            options = pools[inventory[index]]
            if rule.draw_policy == "conditional_exclude_other_instances":
                options = [o for o in options if o.emblem_id not in current[:index] + current[index + 1 :]]
            if not options:
                return None
            if chosen not in options:
                reachable = False
                break
            if rule.probability_status == "verified":
                weights = [Fraction(o.probability.numerator, o.probability.denominator) for o in options]
                mass *= Fraction(chosen.probability.numerator, chosen.probability.denominator) / sum(weights)
            current[index] = chosen.emblem_id
            if not d.allow_duplicate_emblems and len(set(current)) != len(current):
                return None
        if reachable:
            key = tuple(sorted(current))
            possible.add(key)
            masses[key] += mass
    return {key: masses[key] if rule.probability_status == "verified" else None for key in possible}


@pytest.mark.parametrize("game", ["TFT", "JCC"])
@pytest.mark.parametrize("known", [False, True])
def test_exhaustive_inventories_locks_budgets_orders(game, known):
    d, rule = fixture(game, known)
    alphabet = [e.id for e in d.emblems[:3]]
    for n in range(4):
        for inventory in product(alphabet, repeat=n):
            if not d.allow_duplicate_emblems and len(set(inventory)) != n:
                continue
            for mask in range(2**n):
                locks = [i for i in range(n) if mask & (1 << i)]
                for budget in range(4):
                    req = request(
                        d, rule, emblem_ids=list(inventory), locked_emblem_indices=locks, available_reforgers=budget
                    )
                    strategies = enumerate_strategies(d, req, rule)
                    assert len(strategies) == len({tuple(s["retained_indices"]) for s in strategies}) == 2**n
                    for s in strategies:
                        retained = set(s["retained_indices"])
                        targets = set(range(n)) - retained
                        if not set(locks) <= retained or len(targets) > budget:
                            assert not s["legal"] and not s["actions"]
                            continue
                        assert {tuple(a["target_order"]) for a in s["actions"]} == set(permutations(sorted(targets)))
                        for a in s["actions"]:
                            expected = draw_oracle(d, rule, inventory, a["target_order"])
                            assert a["legal"] == (expected is not None)
                            assert a["reforgers_used"] == len(targets)
                            if expected is not None:
                                assert {tuple(o["emblem_ids"]): o["mass"] for o in a["outcomes"]} == expected
                                if known:
                                    assert sum(expected.values()) == 1
                            else:
                                assert not a["outcomes"]


def board_oracle(d, req, inventory):
    best = None
    for board in combinations(d.champions, req.board_size):
        ids = {u.id for u in board}
        if not set(req.constraints.locked_units) <= ids or set(req.constraints.banned_units) & ids:
            continue
        if any(not u.available or u.unlock_condition or u.cost > req.constraints.max_unit_cost for u in board):
            continue
        options = []
        for eid in inventory:
            e = next(e for e in d.emblems if e.id == eid)
            options.append(
                [None]
                + [
                    u.id
                    for u in board
                    if u.item_slots and u.id not in e.banned_holders and (e.allow_native or e.trait_id not in u.traits)
                ]
            )
        for placement in product(*options):
            answer = reference(d, board, inventory, placement, req.objective)
            if answer is not None:
                best = answer[0] if best is None else max(answer[0], best)
    return best


@pytest.mark.parametrize("objective", list(OBJECTIVES))
@pytest.mark.parametrize("game", ["TFT", "JCC"])
def test_every_cpsat_outcome_matches_exhaustive_boards_ev_and_risk(game, objective, monkeypatch):
    d, rule = fixture(game)
    req = request(d, rule, objective=objective)
    real_solve, calls = analyzer.solve, []

    def recorded(dataset, solve_request):
        calls.append(tuple(solve_request.emblem_ids))
        return real_solve(dataset, solve_request)

    monkeypatch.setattr(analyzer, "solve", recorded)
    out = analyze(d, req, rule)
    assert out["enumeration_complete"] and out["evaluation_complete"] and out["all_compositions_proven_optimal"]
    assert len(calls) == len(set(calls)) == len(out["evaluations"])
    scores = {}
    for eid, v in out["evaluations"].items():
        best = board_oracle(d, req, v["emblem_ids"])
        assert v["status"] == "OPTIMAL" and v["score"] == best
        c = v["result"]["candidates"][0]
        board = [u for u in d.champions if u.id in {u["id"] for u in c["champions"]}]
        placement = [
            next((a["champion_id"] for a in c["assignments"] if a["instance_index"] == i), None)
            for i in range(len(v["emblem_ids"]))
        ]
        actual = reference(d, board, v["emblem_ids"], placement, objective)
        assert actual[0] == best and actual[1] == {t["id"]: t["count"] for t in c["traits"]}
        scores[eid] = best
    baseline = scores[out["baseline_evaluation_id"]]
    for s in out["strategies"]:
        for a in s["actions"]:
            if not a["legal"]:
                continue
            ps = [Fraction(o["probability"]["numerator"], o["probability"]["denominator"]) for o in a["outcomes"]]
            vs = [scores[o["evaluation_id"]] for o in a["outcomes"]]
            ev = sum(p * v for p, v in zip(ps, vs))
            stats = a["summary"]
            assert stats["expected_value"] == float(ev) and stats["expected_delta"] == float(ev - baseline)
            assert stats["worst_case_score"] == min(vs) and stats["best_case_score"] == max(vs)
            assert stats["maximum_downside"] == max(0, baseline - min(vs))
            assert stats["expected_downside"] == float(sum(p * max(0, baseline - v) for p, v in zip(ps, vs)))
            assert stats["probability_of_loss"]["value"] == float(sum(p for p, v in zip(ps, vs) if v < baseline))
            assert not stats["uncertainty"]


def test_unknown_has_scenario_range_but_never_numeric_ev_or_probability():
    d, rule = fixture(known=False)
    out = analyze(d, request(d, rule), rule)
    assert out["all_compositions_proven_optimal"]
    for s in out["strategies"]:
        for a in s["actions"]:
            if not a["legal"]:
                continue
            assert all(o["probability"] is None for o in a["outcomes"])
            for key in [
                "expected_value",
                "expected_value_exact",
                "expected_delta",
                "probability_of_loss",
                "expected_downside",
                "infeasible_probability",
            ]:
                assert a["summary"][key] is None
            assert a["summary"]["worst_case_score"] is not None
            assert a["summary"]["uncertainty"] == ["probabilities_unknown"]


def test_infeasible_outcomes_not_zero_or_renormalized():
    d, rule = fixture()
    d.allow_unused_emblems = False
    d.emblems[3].banned_holders = [u.id for u in d.champions]
    rule.catalog_sha256 = catalog_digest(d)
    out = analyze(d, request(d, rule, emblem_ids=[d.emblems[1].id]), rule)
    a = out["strategies"][0]["actions"][0]
    assert a["summary"]["infeasible_outcomes"] == 1
    assert a["summary"]["infeasible_probability"]["value"] == pytest.approx(2 / 3)
    assert a["summary"]["expected_value"] is None and a["summary"]["worst_case_score"] is None
    impossible = [v for v in out["evaluations"].values() if v["status"] == "INFEASIBLE"]
    assert len(impossible) == 1 and impossible[0]["score"] is None


@pytest.mark.parametrize("status", ["FEASIBLE", "UNKNOWN", "INFEASIBLE"])
def test_no_ev_when_compositions_not_optimal(monkeypatch, status):
    d, rule = fixture()
    result = analyzer.solve(d, request(d, rule))
    result["status"] = status
    if status != "FEASIBLE":
        result["candidates"] = []
    else:
        result["candidates"][0]["solver_status"] = status
    monkeypatch.setattr(analyzer, "solve", lambda *args: result)
    out = analyze(d, request(d, rule), rule)
    assert out["evaluation_complete"] and not out["all_compositions_proven_optimal"]
    assert all(
        a["summary"]["expected_value"] is None and a["summary"]["maximum_downside"] is None
        for s in out["strategies"]
        for a in s["actions"]
        if a["legal"]
    )


def test_total_budget_reports_unexecuted_results(monkeypatch):
    d, rule = fixture()
    times = iter([0, 0, *([100] * 150)])
    monkeypatch.setattr(analyzer, "monotonic", lambda: next(times))
    out = analyze(d, request(d, rule), rule)
    assert out["evaluations"][out["baseline_evaluation_id"]]["result"] is not None
    assert not out["evaluation_complete"]
    skipped = [v for v in out["evaluations"].values() if v["status"] == "NOT_RUN"]
    assert skipped and all(v["result"] is None and v["score"] is None for v in skipped)
    assert all(
        a["summary"]["expected_value"] is None
        for s in out["strategies"]
        for a in s["actions"]
        if a["target_order"] and a["legal"]
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("game", "JCC"),
        ("patch", "NEW"),
        ("set", "other"),
        ("mode", "ranked"),
        ("ruleset_id", "other"),
        ("catalog_sha256", "0" * 64),
    ],
)
def test_exact_version_fingerprint(field, value):
    d, rule = fixture()
    setattr(rule, field, value)
    with pytest.raises(ValueError, match="mismatch|stale"):
        analyze(d, request(d, rule), rule)


@pytest.mark.parametrize(
    "mutation",
    [
        "unknown_numeric",
        "bad_sum",
        "no_evidence",
        "wrong_evidence",
        "duplicate_outcome",
        "duplicate_pool",
        "unverified",
        "unsupported_mechanic",
        "unsupported_draw",
        "negative",
        "zero",
        "bool_weight",
    ],
)
def test_invalid_law_contracts(mutation):
    _, rule = fixture()
    raw = rule.model_dump()
    if mutation == "unknown_numeric":
        raw["probability_status"] = "unknown"
        raw["probability_evidence"] = None
    elif mutation == "bad_sum":
        raw["target_pools"][0]["outcomes"][0]["probability"]["numerator"] = 2
    elif mutation == "no_evidence":
        raw["probability_evidence"] = None
    elif mutation == "wrong_evidence":
        raw["mechanics_evidence"]["kind"] = "first_party"
    elif mutation == "duplicate_outcome":
        raw["target_pools"][0]["outcomes"] *= 2
    elif mutation == "duplicate_pool":
        raw["target_pools"] *= 2
    elif mutation == "unverified":
        raw["verification_status"] = "unverified"
    elif mutation == "unsupported_mechanic":
        raw["mechanic"] = "reroll_until_win"
    elif mutation == "unsupported_draw":
        raw["draw_policy"] = "assume_uniform"
    elif mutation == "negative":
        raw["target_pools"][0]["outcomes"][0]["probability"]["numerator"] = -1
    elif mutation == "zero":
        raw["target_pools"][0]["outcomes"][0]["probability"]["denominator"] = 0
    elif mutation == "bool_weight":
        raw["target_pools"][0]["outcomes"][0]["probability"]["numerator"] = True
    with pytest.raises(ValueError):
        ReforgeRule.model_validate(raw)


def test_target_limits_consumption_and_permissions():
    d, rule = fixture()
    rule.max_targets = 1
    rule.reforgers_per_target = 2
    rule.target_pools = rule.target_pools[1:]
    out = enumerate_strategies(d, request(d, rule), rule)
    assert sum(s["legal"] for s in out) == 3
    assert {s["reason"] for s in out if not s["legal"]} == {"target_limit", "target_not_permitted"}
    out = enumerate_strategies(d, request(d, rule, available_reforgers=1), rule)
    assert sum(s["legal"] for s in out) == 1


def test_intermediate_duplicate_cannot_be_repaired_later():
    d, rule = fixture("JCC")
    rule.draw_policy = "independent"
    out = enumerate_strategies(d, request(d, rule), rule)
    assert any(a["reason"] == "outcome_violates_duplicate_rule" for s in out for a in s["actions"])


@pytest.mark.parametrize("bound", ["MAX_PATHS", "MAX_EVALUATIONS"])
def test_space_limits_fail_before_solving(monkeypatch, bound):
    d, rule = fixture()
    monkeypatch.setattr(analyzer, bound, 1)

    def forbidden(*args):
        pytest.fail("Oversized space must fail before CP-SAT")

    monkeypatch.setattr(analyzer, "solve", forbidden)
    with pytest.raises(ValueError, match="scenario space"):
        analyze(d, request(d, rule), rule)


def test_foreign_emblems_and_changed_catalog_rejected():
    d, rule = fixture()
    rule.target_pools[0].outcomes[0].emblem_id = "jcc_emblem_0"
    with pytest.raises(ValueError, match="cross-game"):
        analyze(d, request(d, rule), rule)
    d, rule = fixture()
    d.champions[0].cost = 5
    with pytest.raises(ValueError, match="stale"):
        analyze(d, request(d, rule), rule)


@pytest.mark.parametrize("game", ["TFT", "JCC"])
def test_additive_api_optimizer_unchanged(game):
    client = TestClient(app)
    d = get_catalog(game, f"fixture_{game.lower()}_v1")
    base = dict(game_id=game, ruleset_id=d.id, emblem_ids=[e.id for e in d.emblems[:3]], top_k=1)
    before = client.post("/api/v1/solve", json=base).json()
    listed = client.get("/api/v1/reforge/rules", params=dict(game_id=game, ruleset_id=d.id))
    assert listed.status_code == 200 and len(listed.json()) == 2
    for known in [False, True]:
        response = client.post(
            "/api/v1/reforge/analyze",
            json=dict(
                **base,
                reforge_rule_id=f"synthetic_{game.lower()}_{'known' if known else 'unknown'}_v1",
                available_reforgers=3,
            ),
        )
        assert response.status_code == 200
        out = response.json()
        assert (
            len(out["strategies"]) == 8
            and out["all_compositions_proven_optimal"]
            and out["value_kind"] == "synthetic_rule_score"
        )
    assert before["candidates"] == client.post("/api/v1/solve", json=base).json()["candidates"]
    legacy = client.post("/api/v1/reforge/simulate", json=base)
    assert legacy.status_code == 200 and legacy.json()["expected_value"] is None
    assert client.post("/api/v1/reforge/simulate", json=dict(**base, action="actual_reforge")).status_code == 422


@pytest.mark.parametrize(
    "change",
    [
        {"locked_emblem_indices": [-1]},
        {"locked_emblem_indices": [3]},
        {"locked_emblem_indices": [0, 0]},
        {"locked_emblem_indices": [True]},
        {"available_reforgers": -1},
        {"available_reforgers": 4},
        {"available_reforgers": True},
        {"reforge_rule_id": "synthetic_jcc_known_v1"},
        {"reforge_rule_id": "missing"},
        {"probability_status": "verified"},
    ],
)
def test_api_invalid_requests(change):
    body = (
        dict(
            game_id="TFT",
            ruleset_id="fixture_tft_v1",
            emblem_ids=["tft_emblem_0"] * 3,
            reforge_rule_id="synthetic_tft_known_v1",
        )
        | change
    )
    assert TestClient(app).post("/api/v1/reforge/analyze", json=body).status_code == 422


def test_missing_rules_no_version_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr(rules, "DATA", tmp_path)
    d = get_catalog("TFT", "fixture_tft_v1")
    assert rules.rules_for(d) == []
    with pytest.raises(ValueError, match="exact catalog"):
        rules.get_rule(d, "missing")


def test_unresolved_feasibility_does_not_claim_zero_infeasibility_probability(monkeypatch):
    d, rule = fixture()
    monkeypatch.setattr(analyzer, "solve", lambda *args: dict(status="UNKNOWN", candidates=[]))
    out = analyze(d, request(d, rule), rule)
    for s in out["strategies"]:
        for a in s["actions"]:
            if a["legal"]:
                assert a["summary"]["infeasible_probability"] is None
                assert a["summary"]["proven_infeasible_probability_lower_bound"]["value"] == 0


def test_action_order_changes_conditional_distribution():
    d, rule = fixture("JCC")
    req = request(d, rule, emblem_ids=[e.id for e in d.emblems[:2]])
    actions = enumerate_strategies(d, req, rule)[0]["actions"]
    assert len(actions) == 2 and all(a["legal"] for a in actions)
    assert actions[0]["outcomes"] != actions[1]["outcomes"]


def test_duplicate_instance_lock_preserves_the_locked_original_index():
    d, rule = fixture()
    req = request(d, rule, emblem_ids=[d.emblems[0].id] * 3, locked_emblem_indices=[1])
    out = analyze(d, req, rule)
    assert sum(s["legal"] for s in out["strategies"]) == 4
    for s in out["strategies"]:
        if s["legal"]:
            assert 1 in s["retained_indices"]
            assert all(1 not in a["target_order"] for a in s["actions"])
            assert all(d.emblems[0].id in o["emblem_ids"] for a in s["actions"] for o in a["outcomes"])
