"""Phase 1: fictional unit fixtures prove algorithms, not real S/A meta coverage."""

from collections import Counter
import csv
import io
from itertools import combinations, product
import json

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.meta import engine, evidence, repository
from app.meta.engine import analyze, frontier, holder_audit
from app.meta.providers import CSV_FIELDS, CsvProvider, JsonProvider
from app.meta.repository import available, import_export, scope_for, validate_export
from app.meta.schemas import AdaptRequest, Export, StrategyRequest
from app.optimizer import adaptation
from app.optimizer.adaptation import AdaptationSpec, PRIORITIES
from app.optimizer.solver import RULES, solve
from app.repositories.catalog import get_catalog
from app.schemas.domain import SolveRequest


@pytest.fixture
def setup(tmp_path, monkeypatch):
    d = get_catalog("TFT", "fixture_tft_v1").model_copy(deep=True)
    d.champions = d.champions[:9]
    for e in d.emblems:
        e.banned_holders = []
    original_get = repository.get_catalog

    def get(game, ruleset):
        return d if (game, ruleset) == (d.game, d.id) else original_get(game, ruleset)

    monkeypatch.setattr(repository, "get_catalog", get)
    scope = scope_for(d)
    auth = dict(
        provider_id="unit-test",
        source_kind="manual_original",
        attribution="Fictional unit tests only",
        license_id="original-test-data",
        permission_reference="Unit-test authored fixture, not provider permission",
        permission_sha256="1" * 64,
        reviewed_by="test-author",
        reviewed_at="2020-01-01T00:00:00Z",
        valid_from="2020-01-01T00:00:00Z",
        valid_until="2100-01-01T00:00:00Z",
        enabled=True,
        scopes=[scope.model_dump()],
        data_kinds=["synthetic", "manual_scenario"],
        permitted_uses=["import", "store", "display", "adapt"],
    )
    sources = tmp_path / "sources.json"
    sources.write_text(json.dumps(dict(schema_version=1, sources=[auth])))
    monkeypatch.setenv("META_SOURCES_FILE", str(sources))
    root = tmp_path / "catalogs"
    monkeypatch.setenv("META_CATALOG_DIR", str(root))
    raw = dict(
        schema_version=1,
        provider_id="unit-test",
        source_version="fictional-v1",
        scope=scope.model_dump(),
        data_kind="synthetic",
        compositions=[
            dict(
                id="board",
                name="Fictional seven-unit board",
                champion_ids=[c.id for c in d.champions[:7]],
                board_size=7,
                core_carry_ids=[d.champions[0].id],
                core_tank_ids=[d.champions[1].id],
                source_tier="S",
                tier_citation="Fictional test tier only",
                reviewed_at="2020-01-01T00:00:00Z",
            )
        ],
    )
    return d, raw, root, sources


def install(setup, raw=None):
    _, default, _, _ = setup
    raw = raw or default
    content = json.dumps(raw).encode()
    return import_export(JsonProvider().normalize(content), content, "fictional.json")


def request(setup, **changes):
    d, _, _, _ = setup
    return StrategyRequest(
        scope=scope_for(d),
        board_size=7,
        emblem_ids=[e.id for e in d.emblems[:3]],
        include_synthetic=True,
        timeout_seconds=30,
        per_case_timeout_seconds=2,
        **changes,
    )


def independently_check(d, output, input_ids):
    units = {u.id: u for u in d.champions}
    emblems = {e.id: e for e in d.emblems}
    for c in output["candidates"]:
        ids = [u["id"] for u in c["champions"]]
        used, slots, copies = set(), Counter(), Counter()
        for a in c["assignments"]:
            i, uid, eid = a["instance_index"], a["champion_id"], a["emblem_id"]
            assert i not in used and input_ids[i] == eid and uid in ids
            used.add(i)
            unit, emblem = units[uid], emblems[eid]
            assert unit.available and emblem.available and not unit.unlock_condition
            assert uid not in emblem.banned_holders
            assert emblem.allow_native or emblem.trait_id not in unit.traits
            slots[uid] += 1
            copies[uid, eid] += 1
        assert all(n + c["occupied_item_slots"].get(uid, 0) <= units[uid].item_slots for uid, n in slots.items())
        assert all(n <= d.max_same_emblem_per_holder for n in copies.values())
        assert {i["instance_index"] for i in c["unused_instances"]} == set(range(len(input_ids))) - used
        for trait in c["traits"]:
            count = sum(
                max(
                    units[uid].trait_weights.get(trait["id"], 1) if trait["id"] in units[uid].traits else 0,
                    int(
                        any(
                            a["champion_id"] == uid and emblems[a["emblem_id"]].trait_id == trait["id"]
                            for a in c["assignments"]
                        )
                    ),
                )
                for uid in ids
            )
            thresholds = next(t.thresholds for t in d.traits if t.id == trait["id"])
            assert trait["count"] == count
            reached = [b for b in thresholds if count >= b.count]
            assert trait["level"] == len(reached)
            assert trait["utility"] == (reached[-1].utility if reached else 0)


def test_all_retention_replacements_and_core(setup):
    install(setup)
    r = request(setup, include_empty_baseline=True)
    result = analyze(r)
    assert len(result["strategies"]) == 8
    assert {tuple(s["retained_indices"]) for s in result["strategies"]} == {
        s for k in range(4) for s in combinations(range(3), k)
    }
    assert result["search_coverage"]["all_requested_cases_resolved"]
    assert len(result["candidates"]) == 24
    for s in result["strategies"]:
        assert {case["replacements"] for case in s["cases"]} == {0, 1, 2}
    for c in result["candidates"]:
        assert not c["core_units_lost"]
        assert len(c["champions_added"]) == len(c["champions_removed"]) == c["structural_metrics"]["replacements"]
        assert c["adapted_tier"] is c["adapted_win_rate"] is None
        assert c["original_source_tier"] == "S" and c["source_meta_composition"]["data_kind"] == "synthetic"
    assert result["reforge_probabilities"] is result["expected_value"] is result["reforge_action"] is None
    independently_check(setup[0], result, r.emblem_ids)


@pytest.mark.parametrize("n,expected", [(0, 1), (1, 1), (2, 3), (3, 7)])
def test_retention_cardinality_without_empty(setup, n, expected):
    install(setup)
    r = request(setup).model_copy(
        update={"emblem_ids": [e.id for e in setup[0].emblems[:n]], "replacement_counts": [0]}
    )
    assert analyze(r)["retained_strategy_count"] == expected


def test_instance_locks_duplicates_and_original_indices(setup):
    install(setup)
    r = request(setup, include_empty_baseline=True, locked_emblem_indices=[1]).model_copy(
        update={"emblem_ids": ["tft_emblem_0"] * 3, "replacement_counts": [0]}
    )
    out = analyze(r)
    assert sum(s["allowed"] for s in out["strategies"]) == 4
    assert all(not s["cases"] for s in out["strategies"] if not s["allowed"])
    only_second = next(c for c in out["candidates"] if [i["instance_index"] for i in c["retained_instances"]] == [1])
    assert only_second["assignments"][0]["instance_index"] == 1
    independently_check(setup[0], out, r.emblem_ids)


def test_unused_retained_emblems_are_legal_and_not_reforged(setup):
    d, _, _, _ = setup
    for c in d.champions:
        c.item_slots = 0
    d.allow_unused_emblems = False
    install(setup)
    r = AdaptRequest(
        **request(setup).model_dump(exclude={"include_empty_baseline", "locked_emblem_indices"}),
    )
    out = analyze(r, retain_subsets=False)
    assert out["candidates"] and all(not c["assignments"] for c in out["candidates"])
    assert all(len(c["retained_but_unused_instances"]) == 3 for c in out["candidates"])
    assert d.allow_unused_emblems is False  # no mutation of live catalog policy
    assert out["expected_value"] is None


def test_reservations_illegal_holders_and_secondary_recommendation(setup):
    d, raw, _, _ = setup
    pref = dict(emblem_id="tft_emblem_0", champion_id="tft_unit_3", citation="Synthetic independent recommendation")
    raw["compositions"][0]["holder_preferences"] = [pref]
    install(setup)
    r = request(setup).model_copy(update={"emblem_ids": ["tft_emblem_0"], "replacement_counts": [0]})
    c = analyze(r)["candidates"][0]
    assert c["assignments"][0]["champion_id"] == "tft_unit_3"
    assert c["assignments"][0]["source_recommendations"]
    assert c["lexicographic_stages"][-1]["objective"] == "source_holder_preference"
    reserved = analyze(r.model_copy(update={"occupied_item_slots": {"tft_unit_3": 3}}))
    assert reserved["candidates"][0]["assignments"][0]["champion_id"] != "tft_unit_3"
    independently_check(d, reserved, r.emblem_ids)
    d.emblems[0].banned_holders = ["tft_unit_3"]
    with pytest.raises(ValueError, match="illegal"):
        validate_export(Export.model_validate(raw), d)


def test_native_double_weight_and_noncontributing_holder_label(setup):
    d, _, _, _ = setup
    d.emblems[0].allow_native = True
    d.champions[0].trait_weights = {"tft_trait_0": 2}
    assignments = [dict(instance_index=0, emblem_id="tft_emblem_0", champion_id="tft_unit_0")]
    r = SolveRequest(game_id=d.game, ruleset_id=d.id, board_size=7, emblem_ids=["tft_emblem_0"])
    ids = [c.id for c in d.champions[:7]]
    RULES.validate_solution(d, r, ids, assignments)
    assert RULES.evaluate(d, ids, assignments) == RULES.evaluate(d, ids, [])
    a = holder_audit(d, ids, assignments, [], [])[0]
    assert a["structural_effect"]["unique_contribution_gain"] == 0
    assert a["holder_classification"] == "legal" and not a["optimal_holder_claim"]


def test_infeasible_constraints_do_not_claim_optimality(setup):
    install(setup)
    r = request(setup).model_copy(
        update={
            "replacement_counts": [0],
            "constraints": request(setup).constraints.model_copy(update={"banned_units": ["tft_unit_0"]}),
        }
    )
    out = analyze(r)
    assert not out["candidates"] and all(s["status"] == "INFEASIBLE" for s in out["strategies"])
    assert out["search_coverage"]["all_requested_cases_resolved"]


def test_budget_exhaustion_is_not_infeasible(setup, monkeypatch):
    install(setup)
    times = iter([0] + [100] * 100)
    monkeypatch.setattr(engine, "monotonic", lambda: next(times))
    out = analyze(request(setup))
    assert out["search_coverage"]["attempted_cases"] == 0
    assert not out["search_coverage"]["all_requested_cases_resolved"]
    assert all(s["status"] == "INCOMPLETE_SEARCH" for s in out["strategies"])


def test_missing_meta_and_explicit_no_fallback(setup):
    assert analyze(request(setup))["status"] == "MISSING_META_DATA"
    install(setup)
    assert analyze(request(setup).model_copy(update={"include_synthetic": False}))["status"] == "MISSING_META_DATA"
    with pytest.raises(ValueError, match="Exact"):
        analyze(request(setup).model_copy(update={"scope": scope_for(setup[0]).model_copy(update={"patch": "wrong"})}))
    with pytest.raises(LookupError):
        analyze(request(setup).model_copy(update={"composition_keys": ["another-provider:board"]}))


def test_cross_game_emblems_and_duplicate_policy(setup):
    install(setup)
    with pytest.raises(ValueError, match="cross-game"):
        analyze(request(setup).model_copy(update={"emblem_ids": ["jcc_emblem_0"]}))
    setup[0].allow_duplicate_emblems = False
    with pytest.raises(ValueError, match="重复"):
        analyze(request(setup).model_copy(update={"emblem_ids": ["tft_emblem_0"] * 2}))


def test_unsupported_rules_and_unavailable_units(setup):
    d, raw, _, _ = setup
    d.traits[0].special_conditions = "unknown conditional predicate"
    with pytest.raises(ValueError, match="[Uu]nsupported"):
        install(setup)
    d.traits[0].special_conditions = None
    d.champions[0].unlock_condition = "unverified unlock"
    with pytest.raises(ValueError, match="Unavailable"):
        install(setup)
    d.champions[0].unlock_condition = None
    d.traits[0].supported = False
    with pytest.raises(ValueError, match="unsupported"):
        # Explicitly check affected retained emblem before any composition search.
        analyze(request(setup))


def test_pareto_tradeoffs_no_more_emblems_always_better():
    def candidate(id, used, replacements, utility):
        return dict(
            id=id,
            structural_metrics=dict(
                equipped_emblems=used,
                replacements=replacements,
                breakpoint_utility=utility,
                active_traits=4,
                core_preserved=2,
                core_units_lost=0,
            ),
        )

    candidates = [candidate("three", 3, 2, 10), candidate("one", 1, 0, 10), candidate("dominated", 1, 2, 8)]
    ranked = frontier(candidates, "MIN_REPLACEMENTS")
    assert ranked[0]["id"] == "one"
    assert {c["id"] for c in ranked if c["pareto_frontier"]} == {"one", "three"}


def brute_vector(d, original, core, emblem_ids, replacement, ranking):
    """Independent exhaustive count/equipment reference; no production RuleEvaluator/scoring."""
    best = None
    emblems = {e.id: e for e in d.emblems}
    for board in combinations(d.champions, 7):
        ids = {u.id for u in board}
        if len(set(original) - ids) != replacement or not set(core) <= ids:
            continue
        choices = [
            [None]
            + [
                u.id
                for u in board
                if u.item_slots
                and u.id not in emblems[eid].banned_holders
                and (emblems[eid].allow_native or emblems[eid].trait_id not in u.traits)
            ]
            for eid in emblem_ids
        ]
        for holders in product(*choices):
            slots, copies = (
                Counter(u for u in holders if u),
                Counter((uid, eid) for uid, eid in zip(holders, emblem_ids) if uid),
            )
            if any(n > next(u.item_slots for u in board if u.id == uid) for uid, n in slots.items()) or any(
                n > d.max_same_emblem_per_holder for n in copies.values()
            ):
                continue
            utility, active = 0, 0
            for t in d.traits:
                count = sum(
                    max(
                        u.trait_weights.get(t.id, 1) if t.id in u.traits else 0,
                        int(
                            any(uid == u.id and emblems[eid].trait_id == t.id for uid, eid in zip(holders, emblem_ids))
                        ),
                    )
                    for u in board
                )
                reached = [b for b in t.thresholds if count >= b.count]
                active += bool(reached)
                utility += reached[-1].utility if reached else 0
            values = dict(
                equipped_emblems=sum(u is not None for u in holders),
                negative_replacements=-replacement,
                core_preserved=len(core),
                breakpoint_utility=utility,
                active_traits=active,
            )
            vector = tuple(values[k] for k in PRIORITIES[ranking])
            if best is None or vector > best:
                best = vector
    return best


@pytest.mark.parametrize("ranking", list(PRIORITIES))
@pytest.mark.parametrize("replacement", [0, 1, 2])
def test_lexicographic_solver_against_independent_exhaustive_reference(setup, ranking, replacement):
    d, raw, _, _ = setup
    original = raw["compositions"][0]["champion_ids"]
    core = original[:2]
    r = SolveRequest(
        game_id=d.game,
        ruleset_id=d.id,
        emblem_ids=["tft_emblem_0", "tft_emblem_1"],
        board_size=7,
        top_k=1,
        timeout_seconds=3,
    )
    out = solve(d, r, adaptation=AdaptationSpec(original, replacement, core, ranking=ranking))
    c = out["candidates"][0]
    assert out["status"] == "OPTIMAL" and c["lexicographic_complete"]
    expected = brute_vector(d, original, core, r.emblem_ids, replacement, ranking)
    actual = tuple(stage["value"] for stage in c["lexicographic_stages"])
    assert actual == expected


def test_exact_context_statistical_evidence_only(setup, monkeypatch):
    d, raw, _, _ = setup
    ids = raw["compositions"][0]["champion_ids"]
    assignments = [dict(instance_index=0, emblem_id="tft_emblem_0", champion_id="tft_unit_3")]
    board = dict(
        champion_ids=ids,
        matching_rule="exact_board",
        emblem_assignments=[{"emblem_id": "tft_emblem_0", "champion_id": "tft_unit_3"}],
    )
    record = dict(
        id="test-statistics",
        scope=scope_for(d).model_dump(),
        data_kind="observed",
        provider_id="fictional",
        observation=dict(
            context=dict(kind="holder", champion_id="tft_unit_3", emblem_id="tft_emblem_0", composition=board)
        ),
        metrics=dict(sample_size=10, top_four_rate=0.5, average_placement=4.5),
        confidence={},
        data_quality={},
        source={},
    )
    # Inject a trusted reader response to test exact matching, not a real provider observation.
    monkeypatch.setattr(evidence, "observation_by_id", lambda _: record)
    records, _ = evidence.load_evidence(["test-statistics"], scope_for(d))
    audited = holder_audit(d, ids, assignments, [], records)
    assert audited[0]["statistical_evidence_available"] and not audited[0]["statistically_supported"]
    assert audited[0]["holder_classification"] != "statistically_supported"
    record["confidence"] = {"computed_top_four_rate": {"method": "wilson_score"}}
    record["data_quality"] = {"provider_declared": {"independence": "independent", "deduplication": "verified"}}
    audited = holder_audit(d, ids, assignments, [], records)
    assert audited[0]["holder_classification"] == "statistically_supported"
    assert not audited[0]["optimal_holder_claim"]
    assert not evidence.matching_evidence(records, ids[1:] + ["tft_unit_7"], assignments, holder=assignments[0])
    board["matching_rule"] = "unit_subset"
    assert not evidence.matching_evidence(records, ids, assignments, holder=assignments[0])
    record["scope"]["game_id"] = "JCC"
    with pytest.raises(ValueError, match="another game"):
        evidence.load_evidence(["test-statistics"], scope_for(d))


def test_meta_api_and_public_gate(setup, monkeypatch):
    install(setup)
    client = TestClient(app)
    payload = request(setup).model_dump(mode="json")
    payload["replacement_counts"] = [0]
    response = client.post("/api/v1/emblem-strategy/analyze", json=payload)
    assert response.status_code == 200 and len(response.json()["strategies"]) == 7
    payload.pop("locked_emblem_indices")
    payload.pop("include_empty_baseline")
    response = client.post("/api/v1/meta/adapt", json=payload)
    assert response.status_code == 200 and len(response.json()["strategies"]) == 1
    monkeypatch.setenv("PUBLIC_DEMO", "true")
    assert client.post("/api/v1/meta/adapt", json=payload).status_code == 403
    assert client.post("/api/v1/emblem-strategy/analyze", json=payload).status_code == 403


@pytest.mark.parametrize(
    "bad",
    [
        {"replacement_counts": [3]},
        {"locked_emblem_indices": [3]},
        {"reforge_probabilities": [0.5]},
        {"statistics_record_ids": ["a"] * 21},
        {"occupied_item_slots": {"tft_unit_0": 4}},
        {"timeout_seconds": float("inf")},
        {"replacement_counts": [1, 1]},
    ],
)
def test_request_validation(setup, bad):
    payload = request(setup).model_dump()
    with pytest.raises(ValueError):
        StrategyRequest.model_validate({**payload, **bad})


def test_csv_json_idempotence_and_sources(setup):
    _, raw, _, sources_path = setup
    export = Export.model_validate(raw)
    output = io.StringIO()
    writer = csv.DictWriter(output, CSV_FIELDS)
    writer.writeheader()
    row = export.compositions[0].model_dump(mode="json")
    for key in ("champion_ids", "core_carry_ids", "core_tank_ids", "baseline_emblem_ids"):
        row[key] = "|".join(row[key])
    for key in ("non_emblem_item_slots", "baseline_assignments", "holder_preferences"):
        row[key] = json.dumps(row[key])
    writer.writerow(row)
    csv_export = CsvProvider().normalize(
        output.getvalue().encode(), {k: v for k, v in raw.items() if k != "compositions"}
    )
    assert csv_export == export
    path = install(setup)
    assert install(setup) == path
    assert len(available(export.scope)[0]) == 1
    sources = json.loads(sources_path.read_text())
    sources["sources"][0]["enabled"] = False
    sources_path.write_text(json.dumps(sources))
    entries, issues = available(export.scope)
    assert not entries and issues
    with pytest.raises(PermissionError):
        install(setup)


@pytest.mark.parametrize("field", ["patch", "game_id", "mode"])
def test_export_version_isolation(setup, field):
    _, raw, _, _ = setup
    raw["scope"][field] = "JCC" if field == "game_id" else "other"
    with pytest.raises((PermissionError, ValueError)):
        install(setup)


@pytest.mark.parametrize("corruption", ["snapshot", "raw", "catalog", "permission"])
def test_corrupted_or_stale_exports_are_not_used(setup, corruption):
    d, raw, _, sources = setup
    path = install(setup)
    if corruption == "snapshot":
        path.write_text(path.read_text() + " ")
    elif corruption == "raw":
        (path.parent / "original.bin").unlink()
    elif corruption == "catalog":
        d.champions[0].cost = 2
    else:
        registry = json.loads(sources.read_text())
        registry["sources"][0]["permission_sha256"] = "2" * 64
        sources.write_text(json.dumps(registry))
    entries, issues = available(scope_for(d))
    assert not entries and issues
    assert analyze(request(setup))["status"] == "MISSING_META_DATA"


def test_missing_registry_is_clear_service_failure(setup):
    setup[3].unlink()
    response = TestClient(app).post("/api/v1/emblem-strategy/analyze", json=request(setup).model_dump(mode="json"))
    assert response.status_code == 503


def test_import_conflict_and_unsupported_source_meta(setup):
    install(setup)
    raw = setup[1]
    raw["compositions"][0]["name"] = "Changed but same immutable ID"
    with pytest.raises(FileExistsError):
        install(setup)
    raw["compositions"][0]["champion_ids"][-1] = "jcc_unit_0"
    with pytest.raises(ValueError, match="cross-game"):
        install(setup)


def test_real_tft_static_example_is_manual_not_meta(tmp_path, monkeypatch):
    """Real reviewed static records; hand-picked board is NOT a verified high-tier comp."""
    d = get_catalog("TFT", "tft_set18_18_4_standard")
    ids = [
        "DA_18_Ahri",
        "DA_18_Alune",
        "DA_18_Shen",
        "DA_18_MasterYi_AD",
        "DA_18_Sett",
        "DA_18_Ornn",
        "DA_Draven18",
        "DA_KogMaw18_AD",
    ]
    assert set(ids) <= {u.id for u in d.champions}
    raw = dict(
        schema_version=1,
        provider_id="review-example",
        source_version="local-static-check-18.4",
        scope=scope_for(d).model_dump(),
        data_kind="manual_scenario",
        compositions=[
            dict(
                id="structural-example",
                name="Real static records; not meta-tier evidence",
                champion_ids=ids,
                board_size=8,
                core_carry_ids=["DA_Draven18"],
                core_tank_ids=["DA_18_Ornn"],
                reviewed_at="2026-10-10T00:00:00Z",
            )
        ],
    )
    validate_export(Export.model_validate(raw), d)
    for keep in (["DA_18_EmblemBrawler"], ["DA_18_EmblemBrawler", "DA_18_EmblemBlossom", "DA_18_EmblemElderwood"]):
        r = SolveRequest(
            game_id=d.game,
            ruleset_id=d.id,
            board_size=8,
            emblem_ids=keep,
            top_k=1,
            timeout_seconds=3,
            constraints={"banned_units": [u.id for u in d.champions if u.exclusive_group == "DA_18_Lux"]},
        )
        c = solve(
            d.model_copy(update={"allow_unused_emblems": True}),
            r,
            adaptation=AdaptationSpec(ids, 1, ["DA_Draven18", "DA_18_Ornn"]),
        )["candidates"][0]
        assert {"DA_Draven18", "DA_18_Ornn"} <= {u["id"] for u in c["champions"]}
        # Full independent trait count and equipment checks above use actual catalog values.
        c["occupied_item_slots"] = {}
        c["unused_instances"] = [{"instance_index": i} for i in range(len(keep)) if i in c["unused_emblem_indices"]]
        independently_check(d, {"candidates": [c]}, keep)


def test_independent_jcc_fixture_import_api_and_no_tft_contamination(setup, monkeypatch):
    """This is fictional JCC workflow coverage, never real JCC validation."""
    install(setup)
    jcc = get_catalog("JCC", "fixture_jcc_v1")
    source_path = setup[3]
    registry = json.loads(source_path.read_text())
    registry["sources"][0]["scopes"].append(scope_for(jcc).model_dump())
    source_path.write_text(json.dumps(registry))
    # The permission changed, so the previous TFT artifact is intentionally stale.
    raw = {
        **setup[1],
        "scope": scope_for(jcc).model_dump(),
        "compositions": [
            dict(
                id="jcc-board",
                name="Fictional JCC board",
                champion_ids=[u.id for u in jcc.champions[:7]],
                board_size=7,
                core_carry_ids=[jcc.champions[0].id],
                core_tank_ids=[jcc.champions[1].id],
                source_tier="A",
                tier_citation="Fictional tier",
                reviewed_at="2020-01-01T00:00:00Z",
            )
        ],
    }
    content = json.dumps(raw).encode()
    # Import into a separate scope store to keep stale-source operator conflicts explicit.
    root = setup[2] / "jcc"
    import_export(Export.model_validate(raw), content, "jcc-fictional.json", root=root)
    entries, issues = available(scope_for(jcc), root=root)
    assert list(entries) == ["unit-test:jcc-board"] and not issues
    assert available(scope_for(setup[0]), root=root)[0] == {}
    monkeypatch.setenv("META_CATALOG_DIR", str(root))
    r = StrategyRequest(
        scope=scope_for(jcc),
        board_size=7,
        emblem_ids=[e.id for e in jcc.emblems[:3]],
        include_synthetic=True,
        replacement_counts=[0],
        timeout_seconds=10,
    )
    response = TestClient(app).post("/api/v1/emblem-strategy/analyze", json=r.model_dump(mode="json"))
    assert response.status_code == 200 and response.json()["candidates"]
    for c in response.json()["candidates"]:
        assert all(u["game"] == "JCC" for u in c["champions"])
    independently_check(jcc, response.json(), r.emblem_ids)


def test_population_slots_and_optional_core_relaxation(setup):
    d, raw, _, _ = setup
    d.champions[0].board_slots = 2
    raw["compositions"][0]["champion_ids"] = [u.id for u in d.champions[:6]]
    install(setup)
    out = analyze(request(setup).model_copy(update={"replacement_counts": [0, 1, 2]}))
    assert out["candidates"]
    for c in out["candidates"]:
        assert sum(u["board_slots"] for u in c["champions"]) == 7 and len(c["champions"]) == 6
    # A banned core makes hard preservation infeasible, but explicit relaxation may replace it.
    constraints = request(setup).constraints.model_copy(update={"banned_units": ["tft_unit_1"]})
    r = request(setup).model_copy(update={"constraints": constraints, "replacement_counts": [1]})
    assert not analyze(r)["candidates"]
    relaxed = analyze(r.model_copy(update={"preserve_core": False}))
    assert relaxed["candidates"] and all("tft_unit_1" in c["core_units_lost"] for c in relaxed["candidates"])


def test_csv_input_bounds_and_immutable_original_link(setup):
    with pytest.raises(ValueError):
        CsvProvider().normalize(b"unknown,header\nx,y\n", {})
    with pytest.raises(ValueError):
        JsonProvider().normalize(b" " * (2 * 1024 * 1024 + 1))
    original = json.dumps(setup[1]).encode()
    export = Export.model_validate(setup[1])
    with pytest.raises(ValueError, match="does not match"):
        import_export(export, original.replace(b"Fictional seven-unit board", b"Different raw board"), "raw.json")


def test_partial_lexicographic_proof_is_reported_feasible(setup, monkeypatch):
    d, raw, _, _ = setup
    clock = iter([0, 0, 100])
    monkeypatch.setattr(adaptation, "monotonic", lambda: next(clock))
    r = SolveRequest(game_id=d.game, ruleset_id=d.id, board_size=7, emblem_ids=["tft_emblem_0"], top_k=1)
    result = solve(d, r, adaptation=AdaptationSpec(raw["compositions"][0]["champion_ids"], 0))
    assert result["status"] == "FEASIBLE"
    candidate = result["candidates"][0]
    assert not candidate["lexicographic_complete"] and len(candidate["lexicographic_stages"]) == 1
    assert candidate["lexicographic_stages"][0]["status"] == "OPTIMAL"


def test_meta_schema_needs_source_tier_and_declared_roles(setup):
    raw = setup[1]
    raw["data_kind"] = "meta"
    raw["compositions"][0]["tier_citation"] = None
    with pytest.raises(ValueError, match="attributed"):
        Export.model_validate(raw)
    raw["compositions"][0]["tier_citation"] = "Test citation only"
    raw["compositions"][0]["core_tank_ids"] = []
    with pytest.raises(ValueError, match="carries and tanks"):
        Export.model_validate(raw)
    raw["data_kind"] = "manual_scenario"
    with pytest.raises(ValueError, match="not evidence"):
        Export.model_validate(raw)


def test_manual_scenario_requires_explicit_opt_in_and_cannot_use_fixture(setup):
    raw = setup[1]
    raw["data_kind"] = "manual_scenario"
    raw["compositions"][0]["source_tier"] = None
    raw["compositions"][0]["tier_citation"] = None
    with pytest.raises(ValueError, match="real meta cannot use fixtures"):
        install(setup)


def test_source_baseline_emblem_is_not_added_to_retained_inventory(setup):
    raw = setup[1]
    comp = raw["compositions"][0]
    comp["baseline_emblem_ids"] = ["tft_emblem_0"]
    comp["baseline_assignments"] = [dict(instance_index=0, emblem_id="tft_emblem_0", champion_id="tft_unit_3")]
    install(setup)
    r = request(setup).model_copy(update={"emblem_ids": [], "replacement_counts": [0]})
    c = analyze(r)["candidates"][0]
    assert c["source_meta_composition"]["baseline_assignments"]
    assert c["assignments"] == [] and c["trait_breakpoint_changes"]


def test_locked_added_unit_and_excluded_base_unit_respect_neighborhood(setup):
    install(setup)
    constraints = request(setup).constraints.model_copy(
        update={"locked_units": ["tft_unit_8"], "banned_units": ["tft_unit_2"]}
    )
    r = request(setup).model_copy(update={"constraints": constraints})
    result = analyze(r)
    assert result["candidates"]
    assert all(
        case["status"] == "INFEASIBLE" for s in result["strategies"] for case in s["cases"] if case["replacements"] == 0
    )
    for c in result["candidates"]:
        ids = {u["id"] for u in c["champions"]}
        assert "tft_unit_8" in ids and "tft_unit_2" not in ids
        assert c["structural_metrics"]["replacements"] >= 1


def test_s_a_selection_and_manual_opt_in_on_real_static_scope(setup):
    """Fictional source tiers in temp files test filters; NOT real meta-tier evidence."""
    from pathlib import Path

    real = get_catalog("TFT", "tft_set18_18_4_standard")
    example = Path(__file__).resolve().parents[3] / "data/examples/meta/manual-tft18_4.json"
    manual = json.loads(example.read_text())
    manual["provider_id"] = "unit-test"
    registry = json.loads(setup[3].read_text())
    registry["sources"][0]["scopes"].append(scope_for(real).model_dump())
    registry["sources"][0]["data_kinds"].append("meta")
    setup[3].write_text(json.dumps(registry))
    content = json.dumps(manual).encode()
    import_export(Export.model_validate(manual), content, "manual.json")
    r = StrategyRequest(scope=scope_for(real), board_size=8, replacement_counts=[0], timeout_seconds=3)
    assert analyze(r)["status"] == "MISSING_META_DATA"
    assert analyze(r.model_copy(update={"include_manual_scenarios": True}))["candidates"]
    meta = {**manual, "data_kind": "meta", "compositions": []}
    for tier in ("S", "A", "B"):
        meta["compositions"].append(
            {
                **manual["compositions"][0],
                "id": f"fictional-tier-{tier}",
                "source_tier": tier,
                "tier_citation": "Fictional filtering test, not real tier evidence",
            }
        )
    content = json.dumps(meta).encode()
    import_export(Export.model_validate(meta), content, "fictional-tiers.json")
    result = analyze(r)
    assert {c["original_source_tier"] for c in result["candidates"]} == {"S", "A"}
    assert all(c["adapted_tier"] is None for c in result["candidates"])
