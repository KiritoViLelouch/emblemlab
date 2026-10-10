"""Cached real TFT data and independent finite reference enumeration; no network in tests."""

import csv
import hashlib
import io
from itertools import combinations, product
import json
from pathlib import Path

from fastapi.testclient import TestClient
from openpyxl import Workbook
import pytest

from app.data_validation.catalog import validate_catalog
from app.importers.game_manual import COLUMNS, ManualMetadata, import_manual
from app.importers.tft_static import import_snapshot, snapshot
from app.main import app
from app.optimizer.solver import RULES, solve
from app.repositories.catalog import get_catalog
from app.schemas.domain import SolveRequest
from app.scoring.engine import WEIGHTS

ROOT = Path(__file__).resolve().parents[3]
MANIFEST = ROOT / "data/manifests/tft_set18_18_4.json"
ID = "tft_set18_18_4_standard"


@pytest.fixture(scope="module")
def data():
    return get_catalog("TFT", ID)


def request(**kwargs):
    return SolveRequest(game_id="TFT", ruleset_id=ID, top_k=1, timeout_seconds=2, **kwargs)


def test_import_reproducibility(data):
    assert import_snapshot(MANIFEST) == data
    assert (len(data.champions), len(data.traits), len(data.emblems)) == (74, 36, 21)
    assert sum(c.available for c in data.champions) == 71
    assert sum(e.available for e in data.emblems) == 20
    assert sum(t.supported for t in data.traits) == 34
    assert data.verification_status == "partially_verified"
    assert data.mode == "standard" and data.set == "18" and data.patch == "18.4"


def test_checksum_tamper_rejected(tmp_path):
    (tmp_path / "source.json").write_bytes(b'{"real":true}')
    with pytest.raises(ValueError, match="checksum"):
        snapshot(tmp_path, dict(filename="source.json", sha256=hashlib.sha256(b"other").hexdigest()))


@pytest.mark.parametrize(
    "change",
    [
        "duplicate",
        "missing_trait",
        "bad_emblem",
        "bad_threshold",
        "mixed_game",
        "mixed_patch",
        "missing_champion",
        "bad_icon",
        "wrong_icon_patch",
        "unsupported_enabled",
        "unverified_essential",
        "unverified_champion",
        "unverified_emblem",
        "missing_readiness",
    ],
)
def test_invalid_data_blocked(data, change):
    raw = data.model_dump()
    if change == "duplicate":
        raw["champions"].append(raw["champions"][0])
    elif change == "missing_trait":
        raw["champions"][0]["traits"] = ["not-a-trait"]
    elif change == "bad_emblem":
        raw["emblems"][0]["trait_id"] = "not-a-trait"
    elif change == "bad_threshold":
        raw["traits"][0]["thresholds"] = [dict(count=3, utility=2), dict(count=2, utility=1)]
    elif change == "mixed_game":
        raw["champions"][0]["game"] = "JCC"
    elif change == "mixed_patch":
        raw["emblems"][0]["patch"] = "18.3"
    elif change == "missing_champion":
        raw["champions"].pop()
    elif change == "bad_icon":
        raw["champions"][0]["icon_path"] = "javascript:invalid"
    elif change == "wrong_icon_patch":
        raw["champions"][0]["icon_path"] = raw["champions"][0]["icon_path"].replace("16.20.1", "16.19.1")
    elif change == "unsupported_enabled":
        raw["traits"][0]["special_conditions"] = "unimplemented"
    elif change == "unverified_essential":
        raw["data_readiness"]["rule_checks"][0]["status"] = "UNVERIFIED"
    elif change == "unverified_champion":
        raw["champions"][0]["verification_status"] = "unverified"
    elif change == "unverified_emblem":
        raw["emblems"][0]["verification_status"] = "unverified"
    elif change == "missing_readiness":
        raw["data_readiness"] = None
    report = validate_catalog(raw)
    assert not report["valid"] and not report["optimization_enabled"]


@pytest.mark.parametrize(
    "emblems",
    [
        ["DA_18_EmblemBrawler"],
        ["DA_18_EmblemBrawler", "DA_18_EmblemBlossom", "DA_18_EmblemElderwood"],
        ["DA_18_EmblemBrawler"] * 2,
    ],
)
def test_real_emblem_solve(data, emblems):
    d = data.model_copy(deep=True)
    d.allow_unused_emblems = False
    r = request(emblem_ids=emblems)
    result = solve(d, r)
    assert result["status"] in ["OPTIMAL", "FEASIBLE"]
    c = result["candidates"][0]
    assert len(c["assignments"]) == len(emblems)
    RULES.validate_solution(d, r, [u["id"] for u in c["champions"]], c["assignments"])
    if len(set(emblems)) == 1:
        assert len({a["champion_id"] for a in c["assignments"]}) == len(emblems)
    for a in c["assignments"]:
        unit = next(u for u in d.champions if u.id == a["champion_id"])
        emblem = next(e for e in d.emblems if e.id == a["emblem_id"])
        assert emblem.trait_id not in unit.traits


def test_native_holder_and_breakpoints(data):
    unit = next(c for c in data.champions if c.id == "DA_18_Kobuko")
    emblem = next(e for e in data.emblems if e.id == "DA_18_EmblemBrawler")
    assert not RULES.legal(unit, emblem)
    a = dict(instance_index=0, emblem_id=emblem.id, champion_id=unit.id)
    assert RULES.evaluate(data, [unit.id], [a]) == RULES.evaluate(data, [unit.id], [])
    selected = [
        "DA_18_Kobuko",
        "DA_18_Alistar",
        "DA_18_Yorick",
        "DA_18_Xayah",
        "DA_18_Ornn",
        "DA_18_Ahri",
        "DA_18_Sett",
    ]
    with pytest.raises(ValueError, match="Illegal emblem"):
        RULES.validate_solution(data, request(board_size=7, emblem_ids=[emblem.id]), selected, [a])
    native = [
        "DA_Karma18",
        "DA_18_Yorick",
        "DA_18_Yunara",
        "DA_18_MasterYi_AD",
        "DA_18_Ahri",
        "DA_18_Sett",
        "DA_18_Ashe",
    ]
    trait = next(t for t in data.traits if t.id == "DA_18_Blossom")
    assert [b.count for b in trait.thresholds] == [3, 5, 7, 9, 11]
    for count in range(1, 8):
        row = next(t for t in RULES.evaluate(data, native[:count], []) if t["id"] == trait.id)
        assert row["count"] == count and row["level"] == sum(count >= v for v in [3, 5, 7, 9, 11])
    row = next(t for t in RULES.evaluate(data, native + ["DA_Lux18_Blossom"], []) if t["id"] == trait.id)
    assert row["count"] == 9 and row["level"] == 4


@pytest.mark.parametrize("size", [7, 8, 9, 10])
def test_real_board_slots(data, size):
    r = request(
        board_size=size, constraints={"locked_units": ["DA_18_ElderDragon"], "banned_units": [], "max_unit_cost": 5}
    )
    c = solve(data, r)["candidates"][0]
    assert sum(u["board_slots"] for u in c["champions"]) == size and len(c["champions"]) == size - 1
    native = sum(
        ("DA_Riftbeast18" in u["traits"]) * (2 if u["id"] == "DA_18_ElderDragon" else 1) for u in c["champions"]
    )
    assert next(t["count"] for t in c["traits"] if t["id"] == "DA_Riftbeast18") == native


@pytest.mark.parametrize(
    "locked", [["DA_Lux18_Blossom", "DA_18_Lux_Coven"], ["DA_18_Leona", "DA_18_Aphelios"], ["DA_18_KhaZix"]]
)
def test_unsupported_combinations(data, locked):
    assert (
        solve(data, request(constraints={"locked_units": locked, "banned_units": [], "max_unit_cost": 5}))["status"]
        == "INFEASIBLE"
    )


def test_unverified_breakpoint_and_version_isolation(data):
    ids = [c.id for c in data.champions if "DA_Riftbeast18" in c.traits]
    assert len(ids) == 10
    assert (
        solve(
            data, request(board_size=10, constraints={"locked_units": ids[:-1], "banned_units": [], "max_unit_cost": 5})
        )["status"]
        == "INFEASIBLE"
    )
    for update in [dict(game_id="JCC"), dict(ruleset_id="fixture_tft_v1"), dict(emblem_ids=["tft_emblem_0"])]:
        with pytest.raises(ValueError):
            solve(data, request().model_copy(update=update))


# Independent reference: never uses RuleEvaluator, score(), or CP-SAT.
def brute(data, units, emblem_ids, size, objective):
    emblems = {e.id: e for e in data.emblems}
    best = None
    for n in range(1, len(units) + 1):
        for board in combinations(units, n):
            if sum(c.board_slots for c in board) != size:
                continue
            groups = [c.exclusive_group for c in board if c.exclusive_group]
            if len(groups) != len(set(groups)):
                continue
            choices = [[c for c in board if emblems[e].trait_id not in c.traits] for e in emblem_ids]
            for holders in product(*choices):
                pairs = [(c.id, e) for c, e in zip(holders, emblem_ids)]
                if len(set(pairs)) != len(pairs):
                    continue
                counts = {
                    t.id: sum(c.trait_weights.get(t.id, 1) for c in board if t.id in c.traits) for t in data.traits
                }
                for c, e in zip(holders, emblem_ids):
                    counts[emblems[e].trait_id] += 1
                if any(counts[t] > limit for t, limit in data.trait_count_limits.items()):
                    continue
                if any(counts[a] and counts[b] for a, b in data.incompatible_trait_pairs):
                    continue
                active = sum(t.supported and any(counts[t.id] >= b.count for b in t.thresholds) for t in data.traits)
                utility = sum(
                    max([b.utility for b in t.thresholds if counts[t.id] >= b.count] + [0])
                    for t in data.traits
                    if t.supported
                )
                w = WEIGHTS[objective]
                value = w[0] * active + w[1] * utility + w[2] * sum(c.cost for c in board) + w[3] * len(emblem_ids)
                best = value if best is None else max(best, value)
    return best


@pytest.mark.parametrize("objective", ["MAX_ACTIVE_TRAITS", "MAX_BREAKPOINT", "BALANCED", "LOW_COST", "LATE_GAME"])
@pytest.mark.parametrize("emblems", [[], ["DA_18_EmblemBrawler"], ["DA_18_EmblemBrawler"] * 2])
def test_bruteforce_reference(data, objective, emblems):
    ids = [
        "DA_18_Kobuko",
        "DA_18_Yorick",
        "DA_18_Xayah",
        "DA_18_Ornn",
        "DA_18_Ahri",
        "DA_18_Sett",
        "DA_18_ElderDragon",
        "DA_Lux18_Blossom",
        "DA_18_Alistar",
    ]
    units = [c for c in data.champions if c.id in ids]
    d = data.model_copy(deep=True)
    d.allow_unused_emblems = False
    r = request(
        board_size=7,
        emblem_ids=emblems,
        objective=objective,
        constraints={"banned_units": [c.id for c in data.champions if c.id not in ids]},
    )
    result = solve(d, r)
    assert result["status"] == "OPTIMAL"
    assert result["candidates"][0]["score"]["total"] == brute(d, units, emblems, 7, objective)


def manual_csv(rows):
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(COLUMNS)
    for row in rows:
        writer.writerow([row.get(key, "") for key in COLUMNS])
    return buf.getvalue().encode()


@pytest.fixture
def manual_case():
    meta = ManualMetadata(
        game="JCC",
        ruleset_id="manual-test",
        patch="TEST_ONLY",
        set="TEST_ONLY",
        set_name="Synthetic test input for manual workflow",
        mode="test-only",
        source="Tests, not game data",
        source_url="https://example.com/test",
        license_status="original",
        attribution="Test author",
        required_champion_ids=["test-unit"],
    )
    base = dict(
        game="JCC",
        patch="TEST_ONLY",
        set="TEST_ONLY",
        mode="test-only",
        verification_status="VERIFIED",
        evidence="test:synthetic-not-game-data",
        reviewer="test",
        icon_url="https://example.com/test.png",
    )
    rows = [
        dict(base, entity_type="trait", id="test-trait", zh_CN="测试羁绊", en_US="Test trait", thresholds="2|4"),
        dict(
            base,
            entity_type="champion",
            id="test-unit",
            zh_CN="测试棋子",
            en_US="Test unit",
            cost="1",
            trait_ids="test-trait",
        ),
        dict(
            base, entity_type="emblem", id="test-emblem", zh_CN="测试纹章", en_US="Test emblem", trait_id="test-trait"
        ),
    ]
    return meta, rows


@pytest.mark.parametrize("extension", ["csv", "xlsx"])
def test_manual_review_draft(manual_case, extension):
    meta, rows = manual_case
    content = manual_csv(rows)
    if extension == "xlsx":
        book = Workbook()
        sheet = book.active
        sheet.append(COLUMNS)
        for row in rows:
            sheet.append([row.get(key, "") for key in COLUMNS])
        buf = io.BytesIO()
        book.save(buf)
        content = buf.getvalue()
    result = import_manual(content, "test." + extension, meta)
    assert (
        result["validation"]["valid"] and not result["activated"] and not result["validation"]["optimization_enabled"]
    )
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/data/manual/validate",
            files={"file": ("test." + extension, content)},
            data={"metadata": meta.model_dump_json()},
        )
        assert response.status_code == 200 and not response.json()["activated"]


@pytest.mark.parametrize(
    "bad",
    [
        "duplicate",
        "cross_game",
        "missing_evidence",
        "unknown_license",
        "bad_threshold",
        "missing_required",
        "unknown_trait",
        "formula",
    ],
)
def test_manual_bad_input(manual_case, bad):
    meta, rows = manual_case
    if bad == "duplicate":
        rows.append(rows[1])
    elif bad == "cross_game":
        rows[0]["game"] = "TFT"
    elif bad == "missing_evidence":
        rows[0]["evidence"] = ""
    elif bad == "unknown_license":
        meta.license_status = "unknown"
    elif bad == "bad_threshold":
        rows[0]["thresholds"] = "4|2"
    elif bad == "missing_required":
        rows.pop(1)
    elif bad == "unknown_trait":
        rows[1]["trait_ids"] = "absent"
    elif bad == "formula":
        rows[0]["zh_CN"] = "=1+1"
    with pytest.raises(ValueError):
        import_manual(manual_csv(rows), "test.csv", meta)


def test_live_selector_and_disabled_emblem():
    with TestClient(app) as client:
        games = client.get("/api/v1/games?include_synthetic=false").json()
        assert games[0]["versions"][0]["ruleset_id"] == ID
        assert all(v["verification_state"] != "SYNTHETIC" for g in games for v in g["versions"])
        assert games[1]["versions"] == []
        assert client.get("/api/v1/catalog").json()["id"] == "fixture_tft_v1"
        assert (
            client.post(
                "/api/v1/solve", json=request(emblem_ids=["DA_18_EmblemFloraFatalisAugment"]).model_dump()
            ).status_code
            == 422
        )


def test_actual_icon_audit(data):
    report = json.loads((ROOT / "data/manifests/tft_set18_icons.json").read_text())
    urls = {e.icon_path for e in [*data.champions, *data.traits, *data.emblems]}
    assert urls == {r["url"] for r in report["results"]}
    assert all(r["status"] == 200 and r["content_type"].startswith("image/") for r in report["results"])


@pytest.mark.parametrize("field", ["all_rules", "one_rule", "rule_evidence", "snapshots", "roster", "duplicate_rule"])
def test_missing_review_blocks_optimization(data, field):
    raw = data.model_dump()
    d = raw["data_readiness"]
    if field == "all_rules":
        d["rule_checks"] = []
    elif field == "one_rule":
        d["rule_checks"] = d["rule_checks"][1:]
    elif field == "rule_evidence":
        d["rule_checks"][0]["evidence"] = []
    elif field == "snapshots":
        d["snapshots"] = []
    elif field == "roster":
        d["required_champion_ids"] = []
    elif field == "duplicate_rule":
        d["rule_checks"].append(d["rule_checks"][0])
    assert not validate_catalog(raw)["optimization_enabled"]


def test_postvalidation_rejects_unknown_assignment_ids(data):
    selected = [
        "DA_18_Kobuko",
        "DA_18_Alistar",
        "DA_18_Yorick",
        "DA_18_Xayah",
        "DA_18_Ornn",
        "DA_18_Ahri",
        "DA_18_Sett",
    ]
    for eid, holder in [("not-an-emblem", selected[0]), ("DA_18_EmblemBrawler", "not-a-holder")]:
        with pytest.raises(ValueError, match="Illegal emblem"):
            RULES.validate_solution(
                data,
                request(board_size=7, emblem_ids=["DA_18_EmblemBrawler"]),
                selected,
                [dict(instance_index=0, emblem_id=eid, champion_id=holder)],
            )


def test_missing_real_readiness_rejected_at_solve(data):
    broken = data.model_copy(deep=True)
    broken.data_readiness = None
    with pytest.raises(ValueError, match="unverified"):
        solve(broken, request())


def test_generic_capacity_bonus_matches_finite_reference():
    from app.schemas.domain import CapacityBonus

    d = get_catalog("TFT", "fixture_tft_v1").model_copy(deep=True)
    d.champions = d.champions[:9]
    tid = d.traits[0].id
    d.capacity_bonuses = [CapacityBonus(trait_id=tid, threshold=3, slots=1)]
    d.champions[0].board_slots = 2
    r = SolveRequest(game_id="TFT", ruleset_id=d.id, board_size=7, top_k=1)
    result = solve(d, r)
    reference = []
    for n in range(1, 10):
        for board in combinations(d.champions, n):
            counts = {t.id: sum(t.id in c.traits for c in board) for t in d.traits}
            if sum(c.board_slots for c in board) != 7 + int(counts[tid] >= 3):
                continue
            active = sum(any(counts[t.id] >= b.count for b in t.thresholds) for t in d.traits)
            utility = sum(max([b.utility for b in t.thresholds if counts[t.id] >= b.count] + [0]) for t in d.traits)
            w = WEIGHTS[r.objective]
            reference.append(w[0] * active + w[1] * utility + w[2] * sum(c.cost for c in board))
    assert result["status"] == "OPTIMAL" and result["candidates"][0]["score"]["total"] == max(reference)


@pytest.mark.parametrize(
    "key,value",
    [
        ("patch", "18.3"),
        ("set_number", 17),
        ("mutator", "TFTSet18_DoubleUp"),
        ("resource_patch", "16.19.1"),
        ("mode", "double-up"),
    ],
)
def test_import_refuses_unreviewed_version_profile(tmp_path, key, value):
    manifest = json.loads(MANIFEST.read_text())
    manifest[key] = value
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError):
        import_snapshot(path)


def test_import_rejects_duplicate_source_units(monkeypatch):
    import app.importers.tft_static as importer

    original = importer.snapshot

    def duplicate(folder, entry):
        blob = original(folder, entry)
        if entry["filename"] == "en_us.json":
            s = next(s for s in blob["setData"] if s["number"] == 18 and s["mutator"] == "TFTSet18")
            s["champions"].append(s["champions"][0])
        return blob

    monkeypatch.setattr(importer, "snapshot", duplicate)
    with pytest.raises(ValueError, match="Duplicate source champion"):
        importer.import_snapshot(MANIFEST)


@pytest.mark.parametrize(
    "trait_id,counts",
    [("DA_18_Coven", [3, 4, 5, 7]), ("DA_18_Elderwood", [3, 5, 7, 9, 11]), ("DA_Riftbeast18", [3, 5, 7, 10])],
)
def test_documented_origin_breakpoints(data, trait_id, counts):
    assert [b.count for b in next(t for t in data.traits if t.id == trait_id).thresholds] == counts
