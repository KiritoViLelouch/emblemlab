import json
import os
from pathlib import Path
from app.schemas.domain import Ruleset

DATA = Path(__file__).resolve().parents[4] / "data" / "fixtures"
REAL = DATA.parent / "catalogs"


def catalogs() -> list[Ruleset]:
    datasets = [
        Ruleset.model_validate(json.loads(p.read_text()))
        for p in [*sorted(REAL.glob("*/*.json")), *sorted(DATA.glob("*/*.json"))]
    ]
    if os.getenv("PUBLIC_DEMO", "false").lower() == "true":
        return [d for d in datasets if d.game == "TFT" and d.verification_status != "synthetic"]
    return datasets


def get_catalog(game_id: str, ruleset_id: str) -> Ruleset:
    for dataset in catalogs():
        if dataset.game == game_id and dataset.id == ruleset_id:
            return dataset
    raise ValueError("所选游戏和规则集不匹配或不存在")
