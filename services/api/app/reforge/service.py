from itertools import combinations
from app.optimizer.solver import solve


class ReforgeRules:
    """Version-aware boundary; actual game-item mechanics have not been verified."""

    def describe(self, dataset):
        return dict(
            game_id=dataset.game,
            ruleset_id=dataset.id,
            actual_reforge_supported=False,
            probabilities=None,
            expected_value=None,
            outcome_pool=None,
            reason="重铸器数量、目标、机制及概率尚未验证；不支持实际重铸",
        )


def simulate(dataset, request):
    rules = ReforgeRules().describe(dataset)
    if request.action == "actual_reforge":
        raise ValueError(rules["reason"])
    locked = set(request.locked_emblem_indices)
    if not locked <= set(range(len(request.emblem_ids))):
        raise ValueError("Invalid locked emblem index")
    scenarios = []
    for n in range(len(request.emblem_ids) + 1):
        for subset in combinations(range(len(request.emblem_ids)), n):
            allowed = locked <= set(subset)
            result = (
                solve(
                    dataset,
                    request.model_copy(update={"emblem_ids": [request.emblem_ids[i] for i in subset], "top_k": 1}),
                )
                if allowed
                else None
            )
            scenarios.append(dict(retained_indices=list(subset), allowed=allowed, result=result))
    return dict(**rules, analysis="hypothetical_retention_only", scenarios=scenarios)
