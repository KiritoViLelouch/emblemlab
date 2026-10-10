"""Local HTTP verification using an original manual scenario, never claimed as meta data.

Run from services/api: ../../.venv/bin/python ../../scripts/verify_phase1.py
Creates only temporary permissions/snapshots, starts its own loopback server and stops it.
No third-party data, external services, production deploy or default-registry mutation.
"""

from collections import Counter
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
API_DIR = ROOT / "services" / "api"
sys.path.insert(0, str(API_DIR))

from app.meta.repository import scope_for
from app.meta.schemas import Snapshot
from app.repositories.catalog import get_catalog

EXPORT = ROOT / "data/examples/meta/manual-tft18_4.json"
CATALOG = get_catalog("TFT", "tft_set18_18_4_standard")
SCOPE = scope_for(CATALOG).model_dump()
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def call(url, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    with opener.open(
        urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}), timeout=60
    ) as r:
        return r.status, json.load(r)


def check(result, input_ids):
    """Independent recount from real catalog; no production evaluator/scoring calls."""
    emblems = {e.id: e for e in CATALOG.emblems}
    units = {c.id: c for c in CATALOG.champions}
    for c in result["candidates"]:
        selected = {u["id"] for u in c["champions"]}
        baseline_counts = {t["id"]: t["count"] for t in c["source_meta_composition"]["traits"] if t["count"]}
        # Hand-checked eight-unit native relationships, independent of production evaluator code.
        assert baseline_counts == {
            "DA_18_Blossom": 3,
            "DA_18_Spellweaver": 2,
            "DA_AluneUniqueTrait18": 1,
            "DA_18_Lunar": 1,
            "DA_18_Adaptor": 2,
            "DA_18_Elderwood": 1,
            "DA_18_Defender": 2,
            "DA_18_Brawler": 1,
            "DA_18_Inferno": 1,
            "DA_DravenUniqueTrait18": 1,
            "DA_18_Caustic": 1,
            "DA_18_Invoker": 1,
        }
        assert {"DA_Draven18", "DA_18_Ornn"} <= selected
        assert not any(units[uid].exclusive_group == "DA_18_Lux" for uid in selected)
        assert len(c["champions_added"]) == len(c["champions_removed"]) == c["structural_metrics"]["replacements"]
        seen, slots, copies = set(), Counter(), Counter()
        for a in c["assignments"]:
            i, uid, eid = a["instance_index"], a["champion_id"], a["emblem_id"]
            u, e = units[uid], emblems[eid]
            assert i not in seen and input_ids[i] == eid and uid in selected
            assert u.available and e.available and not u.unlock_condition and uid not in e.banned_holders
            assert e.allow_native or e.trait_id not in u.traits
            seen.add(i)
            slots[uid] += 1
            copies[uid, eid] += 1
        assert all(n + c["occupied_item_slots"].get(uid, 0) <= units[uid].item_slots for uid, n in slots.items())
        assert all(n <= CATALOG.max_same_emblem_per_holder for n in copies.values())
        counts = {}
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
                for uid in selected
            )
            assert count == trait["count"]
            counts[trait["id"]] = count
            thresholds = next(t.thresholds for t in CATALOG.traits if t.id == trait["id"])
            reached = [b for b in thresholds if count >= b.count]
            assert trait["level"] == len(reached) and trait["utility"] == (reached[-1].utility if reached else 0)
        capacity = 8 + sum(b.slots for b in CATALOG.capacity_bonuses if counts[b.trait_id] >= b.threshold)
        assert sum(units[uid].board_slots for uid in selected) == capacity
        assert c["original_source_tier"] is c["adapted_tier"] is c["adapted_win_rate"] is None
        assert not c["statistical_evidence_available"]
    assert result["expected_value"] is result["reforge_probabilities"] is None


def summarize(result):
    return {
        **{
            k: result[k]
            for k in ("status", "scope", "search_coverage", "strategies", "pareto_frontier_ids", "elapsed_seconds")
        },
        "candidates": [
            {
                k: c[k]
                for k in (
                    "id",
                    "retained_instances",
                    "unused_instances",
                    "structural_metrics",
                    "champions_added",
                    "champions_removed",
                    "core_units_lost",
                    "solver_status",
                    "lexicographic_complete",
                    "assignments",
                    "trait_breakpoint_changes",
                    "pareto_frontier",
                    "original_source_tier",
                    "adapted_tier",
                    "adapted_win_rate",
                    "statistical_evidence_available",
                )
            }
            for c in result["candidates"]
        ],
    }


def main():
    report = dict(
        executed_at=datetime.now(timezone.utc).isoformat(),
        kind="local_actual_http_and_cp_sat",
        data_kind="manual_scenario",
        real_meta_tier_evidence=False,
        real_jcc_test=False,
        static_source=CATALOG.source,
        snapshot_verification=CATALOG.verification_status,
        example_sha256=hashlib.sha256(EXPORT.read_bytes()).hexdigest(),
    )
    with tempfile.TemporaryDirectory(prefix="emblemlab-phase1-") as directory:
        temporary = Path(directory)
        now = datetime.now(timezone.utc)
        permission = "Original hand-picked structural scenario, authored for local EmblemLab Phase 1 testing; no third-party meta tier or statistics."
        source = dict(
            provider_id="emblemlab-local-example",
            source_kind="manual_original",
            attribution=permission,
            license_id="original-scenario-local-testing",
            permission_reference=permission,
            permission_sha256=hashlib.sha256(permission.encode()).hexdigest(),
            reviewed_by="EmblemLab local Phase 1 review",
            reviewed_at=now.isoformat(),
            valid_from=now.isoformat(),
            valid_until=(now + timedelta(days=1)).isoformat(),
            enabled=True,
            scopes=[SCOPE],
            data_kinds=["manual_scenario"],
            permitted_uses=["import", "store", "display", "adapt"],
        )
        registry = temporary / "sources.json"
        registry.write_text(json.dumps(dict(schema_version=1, sources=[source])))
        env = {
            **os.environ,
            "META_SOURCES_FILE": str(registry),
            "META_CATALOG_DIR": str(temporary / "catalogs"),
            "PUBLIC_DEMO": "false",
            "PYTHONPATH": str(API_DIR),
        }
        imported = subprocess.run(
            [sys.executable, "-m", "app.meta.importer", str(EXPORT)],
            cwd=API_DIR,
            env=env,
            check=True,
            capture_output=True,
        )
        csv_import = subprocess.run(
            [
                sys.executable,
                "-m",
                "app.meta.importer",
                str(EXPORT.with_suffix(".csv")),
                "--metadata",
                str(EXPORT.with_suffix(".metadata.json")),
                "--output-dir",
                str(temporary / "csv-catalogs"),
            ],
            cwd=API_DIR,
            env=env,
            check=True,
            capture_output=True,
        )
        json_snapshot = Snapshot.model_validate_json(Path(imported.stdout.decode().strip()).read_bytes())
        csv_snapshot = Snapshot.model_validate_json(Path(csv_import.stdout.decode().strip()).read_bytes())
        assert json_snapshot.export == csv_snapshot.export
        report["csv_and_json_cli_imports"] = "passed; equivalent normalized records, separately archived originals"
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        url = f"http://127.0.0.1:{port}"
        process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)],
            cwd=API_DIR,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            for _ in range(100):
                try:
                    call(url + "/health")
                    break
                except OSError:
                    if process.poll() is not None:
                        raise RuntimeError("Local verification API failed to start")
                    time.sleep(0.1)
            else:
                raise RuntimeError("Local verification startup timed out")
            payload = dict(
                scope=SCOPE,
                board_size=8,
                emblem_ids=["DA_18_EmblemBrawler", "DA_18_EmblemBlossom", "DA_18_EmblemElderwood"],
                composition_keys=["emblemlab-local-example:structural-example"],
                include_manual_scenarios=True,
                replacement_counts=[0, 1, 2],
                timeout_seconds=30,
                per_case_timeout_seconds=1,
                constraints={"banned_units": [u.id for u in CATALOG.champions if u.exclusive_group == "DA_18_Lux"]},
            )
            code, retention = call(url + "/api/v1/emblem-strategy/analyze", {**payload, "include_empty_baseline": True})
            assert code == 200 and len(retention["strategies"]) == 8 and retention["candidates"]
            check(retention, payload["emblem_ids"])
            report["retention"] = dict(
                http=code, request={**payload, "include_empty_baseline": True}, response=summarize(retention)
            )
            code, adapted = call(url + "/api/v1/meta/adapt", payload)
            assert code == 200 and len(adapted["strategies"]) == 1 and adapted["candidates"]
            check(adapted, payload["emblem_ids"])
            report["adaptation"] = dict(http=code, request=payload, response=summarize(adapted))
            report["independent_legality_population_items_and_trait_recount"] = "passed"
        finally:
            process.terminate()
            process.wait(timeout=10)
    out = ROOT / "docs/evidence/phase1_local_http.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print("Actual local HTTP checks passed:", out)
    for candidate in report["retention"]["response"]["candidates"]:
        print(candidate["id"], candidate["solver_status"], candidate["structural_metrics"])


if __name__ == "__main__":
    main()
