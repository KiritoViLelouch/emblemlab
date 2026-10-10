"""Exhaustive fixed retention/order plans with real CP-SAT recourse compositions."""

from fractions import Fraction
from itertools import combinations, permutations
from time import monotonic

from app.optimizer.solver import RULES, solve
from app.reforge.rules import validate_rule

MAX_PATHS = 4096
MAX_EVALUATIONS = 128


def rational_json(value):
    if value is None:
        return None
    return {"numerator": value.numerator, "denominator": value.denominator, "value": float(value)}


def enumerate_strategies(dataset, request, rule):
    """Do not prune low-value branches or silently condition on completing a plan."""
    pools = {p.input_emblem_id: p.outcomes for p in rule.target_pools}
    known = rule.probability_status == "verified"
    n = len(request.emblem_ids)
    strategies = []
    paths_visited = 0
    for count in range(n + 1):
        for retained in combinations(range(n), count):
            targets = sorted(set(range(n)) - set(retained))
            reason = None
            if not set(request.locked_emblem_indices) <= set(retained):
                reason = "locked_emblem"
            elif len(targets) > rule.max_targets:
                reason = "target_limit"
            elif len(targets) * rule.reforgers_per_target > request.available_reforgers:
                reason = "insufficient_reforgers"
            elif any(request.emblem_ids[i] not in pools for i in targets):
                reason = "target_not_permitted"
            strategy = dict(
                retained_indices=list(retained), target_indices=targets, legal=False, reason=reason, actions=[]
            )
            strategies.append(strategy)
            if reason:
                continue
            for order in permutations(targets):
                outcomes = {}
                blocked = None

                def visit(inventory, step, mass):
                    nonlocal paths_visited, blocked
                    paths_visited += 1
                    if paths_visited > MAX_PATHS:
                        raise ValueError("Reforge scenario space exceeds 4096 nodes; use a smaller ruleset")
                    if step == len(order):
                        key = tuple(sorted(inventory))
                        if not dataset.allow_duplicate_emblems and len(set(key)) != len(key):
                            blocked = "outcome_violates_duplicate_rule"
                        outcomes[key] = outcomes.get(key, Fraction()) + mass if known else None
                        return
                    index = order[step]
                    pool = pools[request.emblem_ids[index]]
                    if rule.draw_policy == "conditional_exclude_other_instances":
                        owned = {eid for i, eid in enumerate(inventory) if i != index}
                        pool = [o for o in pool if o.emblem_id not in owned]
                    if not pool:
                        blocked = "reachable_empty_pool"
                        return
                    normalizer = sum((o.probability.fraction() for o in pool), Fraction()) if known else None
                    for outcome in pool:
                        next_inventory = inventory.copy()
                        next_inventory[index] = outcome.emblem_id
                        if not dataset.allow_duplicate_emblems and len(set(next_inventory)) != len(next_inventory):
                            blocked = "outcome_violates_duplicate_rule"
                        # Conditional normalization is part of the explicitly declared mechanic.
                        next_mass = mass * outcome.probability.fraction() / normalizer if known else None
                        visit(next_inventory, step + 1, next_mass)

                visit(request.emblem_ids.copy(), 0, Fraction(1) if known else None)
                action = dict(
                    target_order=list(order),
                    reforgers_used=len(order) * rule.reforgers_per_target,
                    legal=blocked is None,
                    reason=blocked,
                    outcomes=[]
                    if blocked
                    else [dict(emblem_ids=list(ids), mass=p) for ids, p in sorted(outcomes.items())],
                )
                strategy["actions"].append(action)
            strategy["legal"] = any(a["legal"] for a in strategy["actions"])
            if not strategy["legal"]:
                strategy["reason"] = "no_order_can_complete_all_outcomes"
    return strategies


def summarize(outcomes, evaluations, baseline, known):
    values = [evaluations[o["evaluation_id"]] for o in outcomes]
    optimal = all(v["status"] == "OPTIMAL" for v in values)
    base_score = baseline["score"] if baseline["status"] == "OPTIMAL" else None
    scores = [v["score"] for v in values] if optimal else []
    worst, best = (min(scores), max(scores)) if scores else (None, None)
    expected = (
        sum((o["mass"] * v["score"] for o, v in zip(outcomes, values)), Fraction()) if known and optimal else None
    )
    loss_probability = expected_loss = None
    if known and optimal and base_score is not None:
        loss_probability = sum((o["mass"] for o, v in zip(outcomes, values) if v["score"] < base_score), Fraction())
        expected_loss = sum((o["mass"] * max(0, base_score - v["score"]) for o, v in zip(outcomes, values)), Fraction())
    reasons = []
    if not known:
        reasons.append("probabilities_unknown")
    if not optimal:
        reasons.append("not_all_outcomes_have_proven_optimal_compositions")
    if base_score is None:
        reasons.append("baseline_not_proven_optimal")
    return dict(
        expected_value=float(expected) if expected is not None else None,
        expected_value_exact=rational_json(expected),
        expected_delta=float(expected - base_score) if expected is not None and base_score is not None else None,
        worst_case_score=worst,
        best_case_score=best,
        worst_case_delta=worst - base_score if worst is not None and base_score is not None else None,
        maximum_downside=max(0, base_score - worst) if worst is not None and base_score is not None else None,
        probability_of_loss=rational_json(loss_probability),
        expected_downside=float(expected_loss) if expected_loss is not None else None,
        infeasible_outcomes=sum(v["status"] == "INFEASIBLE" for v in values),
        infeasible_probability=rational_json(
            sum((o["mass"] for o, v in zip(outcomes, values) if v["status"] == "INFEASIBLE"), Fraction())
        )
        if known and all(v["status"] in ("OPTIMAL", "FEASIBLE", "INFEASIBLE") for v in values)
        else None,
        proven_infeasible_probability_lower_bound=rational_json(
            sum((o["mass"] for o, v in zip(outcomes, values) if v["status"] == "INFEASIBLE"), Fraction())
        )
        if known
        else None,
        unresolved_outcomes=sum(v["status"] not in ("OPTIMAL", "INFEASIBLE") for v in values),
        uncertainty=reasons,
    )


def analyze(dataset, request, rule):
    start = monotonic()
    RULES.validate(dataset, request)
    validate_rule(dataset, rule)
    if request.reforge_rule_id != rule.id:
        raise ValueError("Reforge rule ID mismatch")
    strategies = enumerate_strategies(dataset, request, rule)
    baseline_key = tuple(sorted(request.emblem_ids))
    keys = {tuple(o["emblem_ids"]) for s in strategies for a in s["actions"] for o in a["outcomes"]}
    keys.add(baseline_key)
    if len(keys) > MAX_EVALUATIONS:
        raise ValueError("Reforge scenario space exceeds 128 distinct inventories")
    ordered = [baseline_key, *sorted(keys - {baseline_key})]
    evaluations = {}
    ids = {key: f"inventory_{i}" for i, key in enumerate(ordered)}
    for i, inventory in enumerate(ordered):
        remaining = request.analysis_timeout_seconds - (monotonic() - start)
        budget = min(request.timeout_seconds, remaining / (len(ordered) - i))
        result = None
        if budget >= 0.001:
            result = solve(
                dataset,
                request.model_copy(update={"emblem_ids": list(inventory), "top_k": 1, "timeout_seconds": budget}),
            )
        candidate = result["candidates"][0] if result and result["candidates"] else None
        evaluations[ids[inventory]] = dict(
            emblem_ids=list(inventory),
            status=result["status"] if result else "NOT_RUN",
            score=candidate["score"]["total"] if candidate else None,
            result=result,
        )
    baseline = evaluations[ids[baseline_key]]
    known = rule.probability_status == "verified"
    for strategy in strategies:
        for action in strategy["actions"]:
            for outcome in action["outcomes"]:
                outcome["evaluation_id"] = ids[tuple(outcome["emblem_ids"])]
            action["summary"] = summarize(action["outcomes"], evaluations, baseline, known) if action["legal"] else None
            for outcome in action["outcomes"]:
                outcome["probability"] = rational_json(outcome.pop("mass"))
    return dict(
        analysis="versioned_reforge_scenarios",
        rule=rule.model_dump(),
        baseline_evaluation_id=ids[baseline_key],
        input_emblem_ids=request.emblem_ids,
        objective=request.objective,
        strategies=strategies,
        evaluations=evaluations,
        enumeration_complete=True,
        evaluation_complete=all(e["result"] is not None for e in evaluations.values()),
        all_compositions_proven_optimal=all(e["status"] == "OPTIMAL" for e in evaluations.values()),
        elapsed_seconds=monotonic() - start,
        value_kind="synthetic_rule_score" if rule.verification_status == "synthetic" else "rules_based_estimate",
        assumptions=[
            "Baseline is an optimized composition with all original emblems available, not a user-supplied board.",
            "Every retained subset and every fixed target order is enumerated; each target is replaced at most once.",
            "Retaining an emblem does not force equipping it; champion constraints stay fixed and holders may change.",
            "Every outcome permits full board/holder reoptimization; transition costs and combat strength are not modeled.",
            "Scores are objective-specific heuristics, not win rates or statistics; no probability is inferred from pool size.",
            "Dead-end/illegal-outcome plans are disallowed, never filtered and renormalized into successful plans.",
            "No adaptive policies, repeated rerolls, non-emblem items or live game actions are supported.",
            "Numeric EV needs verified probabilities and OPTIMAL results for every outcome; unavailable scores stay null.",
        ],
    )
