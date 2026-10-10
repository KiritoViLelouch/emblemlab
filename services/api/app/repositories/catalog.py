import json
import os
from pathlib import Path
from app.schemas.domain import Ruleset
from app.catalogs.activation import registered

DATA = Path(__file__).resolve().parents[4] / "data" / "fixtures"
REAL = DATA.parent / "catalogs"
ACTIVE_ROOT = DATA.parent


def catalog_issues():
    return registered(ACTIVE_ROOT)[1]


def catalogs() -> list[Ruleset]:
    datasets = [
        Ruleset.model_validate(json.loads(p.read_text()))
        # JCC is available only through explicit reviewed registry promotion.
        for p in [*sorted(REAL.glob("tft/*.json")), *sorted(DATA.glob("*/*.json"))]
    ]
    approved, _ = registered(ACTIVE_ROOT)
    datasets += approved
    if os.getenv("PUBLIC_DEMO", "false").lower() == "true":
        return [d for d in datasets if d.verification_status != "synthetic"]
    return datasets


def get_catalog(game_id: str, ruleset_id: str) -> Ruleset:
    for dataset in catalogs():
        if dataset.game == game_id and dataset.id == ruleset_id:
            return dataset
    raise ValueError("所选游戏和规则集不匹配或不存在")
