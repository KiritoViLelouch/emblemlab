WEIGHTS = {
    "MAX_ACTIVE_TRAITS": (10000, 10, -1, 1),
    "MAX_BREAKPOINT": (10, 100, -1, 1),
    "BALANCED": (100, 10, -2, 5),
    "LOW_COST": (10000, 1, -100, 1),
    "LATE_GAME": (100, 10, 30, 5),
}


def score(traits, champions, assignments, objective):
    values = [
        sum(t["active"] for t in traits),
        sum(t["utility"] for t in traits),
        sum(c.cost for c in champions),
        len(assignments),
    ]
    keys = ["active_traits", "breakpoint_utility", "unit_cost", "equipped_emblems"]
    components = {k: dict(value=v, weight=w, contribution=v * w) for k, v, w in zip(keys, values, WEIGHTS[objective])}
    return dict(
        total=sum(v["contribution"] for v in components.values()),
        components=components,
        kind="rules_based_estimate",
        win_rate=None,
        sample_size=None,
        ability_compatibility="unknown",
        formation="unknown",
        statistics="unavailable",
    )
