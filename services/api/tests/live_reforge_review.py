"""Run against the local API; writes compact evidence, never mutates stored data."""

import json
from fractions import Fraction
from pathlib import Path

import httpx


def main():
    report = dict(scope="synthetic_only", checks=[])
    with httpx.Client(base_url="http://127.0.0.1:8000", timeout=60) as client:
        for game in ["TFT", "JCC"]:
            base = dict(
                game_id=game,
                ruleset_id=f"fixture_{game.lower()}_v1",
                emblem_ids=[f"{game.lower()}_emblem_{i}" for i in range(3)],
                available_reforgers=3,
            )
            for known in [False, True]:
                body = base | dict(reforge_rule_id=f"synthetic_{game.lower()}_{'known' if known else 'unknown'}_v1")
                response = client.post("/api/v1/reforge/analyze", json=body)
                response.raise_for_status()
                out = response.json()
                assert (
                    len(out["strategies"]) == 8
                    and out["evaluation_complete"]
                    and out["all_compositions_proven_optimal"]
                )
                for strategy in out["strategies"]:
                    for action in strategy["actions"]:
                        if not action["legal"]:
                            continue
                        if known:
                            ps = [
                                Fraction(o["probability"]["numerator"], o["probability"]["denominator"])
                                for o in action["outcomes"]
                            ]
                            assert sum(ps) == 1
                            scores = [out["evaluations"][o["evaluation_id"]]["score"] for o in action["outcomes"]]
                            assert action["summary"]["expected_value"] == float(sum(p * s for p, s in zip(ps, scores)))
                        else:
                            assert action["summary"]["expected_value"] is None
                            assert all(o["probability"] is None for o in action["outcomes"])
                report["checks"].append(
                    dict(
                        game=game,
                        probability_status=out["rule"]["probability_status"],
                        strategies=len(out["strategies"]),
                        legal_strategies=sum(s["legal"] for s in out["strategies"]),
                        inventories=len(out["evaluations"]),
                        all_optimal=True,
                        ev_checked=known,
                        unknown_ev_null=not known,
                    )
                )
            no_charge = client.post("/api/v1/reforge/analyze", json=body | dict(available_reforgers=0)).json()
            assert sum(s["legal"] for s in no_charge["strategies"]) == 1
            locked = client.post("/api/v1/reforge/analyze", json=body | dict(locked_emblem_indices=[1])).json()
            assert all(1 in s["retained_indices"] for s in locked["strategies"] if s["legal"])
            assert (
                client.post("/api/v1/reforge/analyze", json=body | dict(reforge_rule_id="missing")).status_code == 422
            )
            report[game] = dict(zero_charge_no_op_only=True, instance_lock_respected=True, missing_rule_rejected=True)
    path = Path(__file__).resolve().parents[3] / "docs" / "reforge-http-verification.json"
    path.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
