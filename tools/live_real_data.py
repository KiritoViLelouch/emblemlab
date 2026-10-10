"""Actual HTTP smoke checks against the running backend; records only executed outcomes."""

import json
from pathlib import Path
from datetime import datetime, timezone
import urllib.request
import urllib.error

ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:8000"


def call(path, body=None):
    request = urllib.request.Request(
        BASE + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as exc:
        return exc.code, json.load(exc)


if __name__ == "__main__":
    rows = []
    for path in [
        "/health",
        "/api/v1/games?include_synthetic=false",
        "/api/v1/catalog?game_id=TFT&ruleset_id=tft_set18_18_4_standard",
        "/api/v1/data-health",
    ]:
        status, data = call(path)
        assert status == 200
        rows.append(dict(path=path, status=status))
    base = dict(
        game_id="TFT",
        ruleset_id="tft_set18_18_4_standard",
        board_size=8,
        top_k=1,
        timeout_seconds=3,
    )
    for emblems in [
        ["DA_18_EmblemBrawler"],
        ["DA_18_EmblemBrawler", "DA_18_EmblemBlossom", "DA_18_EmblemElderwood"],
        ["DA_18_EmblemBrawler"] * 2,
    ]:
        status, data = call("/api/v1/solve", dict(base, emblem_ids=emblems))
        assert status == 200 and data["candidates"]
        c = data["candidates"][0]
        rows.append(
            dict(
                emblems=emblems,
                status=status,
                solver_status=data["status"],
                score=c["score"]["total"],
                occupied_slots=sum(u["board_slots"] for u in c["champions"]),
                champions=[u["id"] for u in c["champions"]],
                assignments=c["assignments"],
                traits=c["traits"],
            )
        )
    for changes in [
        dict(game_id="JCC"),
        dict(emblem_ids=["tft_emblem_0"]),
        dict(emblem_ids=["DA_18_EmblemFloraFatalisAugment"]),
    ]:
        status, data = call("/api/v1/solve", dict(base, **changes))
        assert status == 422
        rows.append(dict(rejected=changes, status=status, detail=data["detail"]))
    path = ROOT / "docs/evidence/real_http.json"
    path.write_text(
        json.dumps(
            dict(executed_at=datetime.now(timezone.utc).isoformat(), results=rows),
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )
    print(
        json.dumps(
            dict(checks=len(rows), passed=True, evidence=str(path)), ensure_ascii=False
        )
    )
