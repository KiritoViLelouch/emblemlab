import hashlib
import json
from pathlib import Path

from app.reforge.schemas import ReforgeRule

DATA = Path(__file__).resolve().parents[4] / "data" / "reforge"


def catalog_digest(dataset):
    return hashlib.sha256(json.dumps(dataset.model_dump(), sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def validate_rule(dataset, rule):
    if rule.ruleset_id != dataset.id or any(
        getattr(rule, key) != getattr(dataset, key) for key in ("game", "patch", "set", "mode")
    ):
        raise ValueError("Reforge game/patch/set/mode/ruleset mismatch")
    if rule.catalog_sha256 != catalog_digest(dataset):
        raise ValueError("Reforge rule catalog fingerprint is stale")
    entities = [dataset, *dataset.champions, *dataset.traits, *dataset.emblems]
    if rule.verification_status != dataset.verification_status or (
        rule.verification_status == "verified" and any(e.verification_status != "verified" for e in entities)
    ):
        raise ValueError("Reforge/catalog verification mismatch")
    ids = {e.id for e in dataset.emblems}
    if any(p.input_emblem_id not in ids or any(o.emblem_id not in ids for o in p.outcomes) for p in rule.target_pools):
        raise ValueError("Unknown or cross-game reforge emblem")


def rules_for(dataset):
    rules = [ReforgeRule.model_validate_json(path.read_text()) for path in sorted(DATA.glob("*.json"))]
    if len({r.id for r in rules}) != len(rules):
        raise ValueError("Duplicate reforge rule ID")
    matches = [r for r in rules if r.game == dataset.game and r.ruleset_id == dataset.id]
    for rule in matches:
        validate_rule(dataset, rule)
    return matches


def get_rule(dataset, rule_id):
    rule = next((r for r in rules_for(dataset) if r.id == rule_id), None)
    if rule is None:
        raise ValueError("No supported reforge rule for this exact catalog/version")
    return rule
