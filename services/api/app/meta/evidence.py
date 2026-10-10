"""Read-only exact-context evidence. Never transfer source-board outcome rates."""

from collections import Counter

from sqlalchemy.exc import SQLAlchemyError

from app.statistics.service import observation_by_id


def load_evidence(ids, scope):
    records, issues = [], []
    for record_id in ids:
        try:
            record = observation_by_id(record_id)
        except (LookupError, PermissionError, RuntimeError, SQLAlchemyError, ValueError):
            issues.append({"id": record_id, "status": "unavailable_or_not_authorized"})
            continue
        if record["scope"] != scope.model_dump():
            raise ValueError("Statistics evidence belongs to another game/patch/mode")
        records.append(record)
    return records, issues


def matching_evidence(records, champions, assignments, holder=None):
    pairs = Counter((a["emblem_id"], a["champion_id"]) for a in assignments)
    matches = []
    for record in records:
        metrics = record["metrics"]
        if (
            record["data_kind"] != "observed"
            or not metrics["sample_size"]
            or not any(metrics.get(k) is not None for k in ("top_four_rate", "average_placement"))
        ):
            continue
        context = record["observation"]["context"]
        board = context.get("composition")
        if not board or board["matching_rule"] != "exact_board" or set(board["champion_ids"]) != set(champions):
            continue
        if Counter((a["emblem_id"], a["champion_id"]) for a in board["emblem_assignments"]) != pairs:
            continue
        if holder is not None and (
            context["kind"] != "holder"
            or (context["emblem_id"], context["champion_id"]) != (holder["emblem_id"], holder["champion_id"])
        ):
            continue
        if holder is None and context["kind"] != "composition":
            continue
        matches.append(
            {key: record[key] for key in ("id", "provider_id", "metrics", "confidence", "data_quality", "source")}
        )
    return matches


def supports_holder(record):
    """Conditional descriptive support, never a causal or optimal-holder claim.

    Weak/unknown quality remains visible without upgrading the holder label.
    No invented universal sample-size cutoff is used.
    """
    declared = record["data_quality"].get("provider_declared", {})
    confidence = record["confidence"].get("computed_top_four_rate")
    return (
        declared.get("independence") == "independent"
        and declared.get("deduplication") == "verified"
        and bool(confidence)
        and confidence.get("method") == "wilson_score"
    )
