from time import monotonic
from ortools.sat.python import cp_model
from app.rules.evaluator import FixtureRules
from app.scoring.engine import WEIGHTS, score

RULES = FixtureRules()


def solve(dataset, request):
    RULES.validate(dataset, request)
    model = cp_model.CpModel()
    units = dataset.champions
    emblems = {e.id: e for e in dataset.emblems}
    x = {c.id: model.new_bool_var(c.id) for c in units}
    for group in {c.exclusive_group for c in units if c.exclusive_group}:
        model.add(sum(x[c.id] for c in units if c.exclusive_group == group) <= 1)
    for c in units:
        if c.id in request.constraints.locked_units:
            model.add(x[c.id] == 1)
        if (
            c.id in request.constraints.banned_units
            or c.cost > request.constraints.max_unit_cost
            or not c.available
            or c.unlock_condition
        ):
            model.add(x[c.id] == 0)
    y = {}
    for eidx, eid in enumerate(request.emblem_ids):
        for c in units:
            v = model.new_bool_var(f"e{eidx}_{c.id}")
            y[c.id, eidx] = v
            model.add(v <= x[c.id])
            if not RULES.legal(c, emblems[eid]):
                model.add(v == 0)
        equipped = sum(y[c.id, eidx] for c in units)
        if dataset.allow_unused_emblems:
            model.add(equipped <= 1)
        else:
            model.add(equipped == 1)
    for c in units:
        model.add(sum(y[c.id, e] for e in range(len(request.emblem_ids))) <= c.item_slots)
        for eid in set(request.emblem_ids):
            model.add(
                sum(y[c.id, e] for e, v in enumerate(request.emblem_ids) if v == eid)
                <= dataset.max_same_emblem_per_holder
            )
    active = []
    utility = []
    trait_counts = {}
    for t in dataset.traits:
        contributors = []
        for c in units:
            weight = c.trait_weights.get(t.id, 1)
            sources = [weight * x[c.id]] if t.id in c.traits else []
            sources += [y[c.id, e] for e, eid in enumerate(request.emblem_ids) if emblems[eid].trait_id == t.id]
            v = model.new_int_var(0, max(1, weight), f"{c.id}_{t.id}")
            if sources:
                model.add_max_equality(v, sources)
            else:
                model.add(v == 0)
            contributors.append(v)
        count = sum(contributors)
        trait_counts[t.id] = count
        if t.id in dataset.trait_count_limits:
            model.add(count <= dataset.trait_count_limits[t.id])
        previous = 0
        for index, b in enumerate(t.thresholds if t.supported else []):
            reached = model.new_bool_var(f"{t.id}_{b.count}")
            model.add(count >= b.count).only_enforce_if(reached)
            model.add(count < b.count).only_enforce_if(reached.Not())
            if index == 0:
                active.append(reached)
            utility.append((b.utility - previous) * reached)
            previous = b.utility
    bonuses = []
    for i, bonus in enumerate(dataset.capacity_bonuses):
        reached = model.new_bool_var(f"capacity_{i}")
        model.add(trait_counts[bonus.trait_id] >= bonus.threshold).only_enforce_if(reached)
        model.add(trait_counts[bonus.trait_id] < bonus.threshold).only_enforce_if(reached.Not())
        bonuses.append(bonus.slots * reached)
    model.add(sum(c.board_slots * x[c.id] for c in units) == request.board_size + sum(bonuses))
    for i, (a, b) in enumerate(dataset.incompatible_trait_pairs):
        absent = model.new_bool_var(f"incompatible_{i}")
        model.add(trait_counts[a] == 0).only_enforce_if(absent)
        model.add(trait_counts[b] == 0).only_enforce_if(absent.Not())
    weights = WEIGHTS[request.objective]
    model.maximize(
        weights[0] * sum(active)
        + weights[1] * sum(utility)
        + weights[2] * sum(c.cost * x[c.id] for c in units)
        + weights[3] * sum(y.values())
    )
    candidates = []
    start = monotonic()
    terminal = "UNKNOWN"
    for rank in range(request.top_k):
        remaining = request.timeout_seconds - (monotonic() - start)
        if remaining <= 0:
            terminal = "UNKNOWN"
            break
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = remaining
        solver.parameters.num_search_workers = 1
        solver.parameters.random_seed = 0
        status = solver.solve(model)
        terminal = solver.status_name(status)
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            break
        selected = [c.id for c in units if solver.value(x[c.id])]
        assignments = [
            dict(
                instance_index=e,
                emblem_id=request.emblem_ids[e],
                champion_id=c.id,
                explanation="符合当前保守装备限制；原生与纹章取最大贡献，不重复贡献；特殊棋子权重来自版本规则；技能适配未知",
            )
            for c in units
            for e in range(len(request.emblem_ids))
            if solver.value(y[c.id, e])
        ]
        RULES.validate_solution(dataset, request, selected, assignments)
        traits = RULES.evaluate(dataset, selected, assignments)
        champions = [c for c in units if c.id in selected]
        candidates.append(
            dict(
                id=f"candidate_{rank + 1}",
                champions=[c.model_dump() for c in champions],
                assignments=assignments,
                unused_emblem_indices=[
                    e for e in range(len(request.emblem_ids)) if not any(a["instance_index"] == e for a in assignments)
                ],
                traits=traits,
                score=score(traits, champions, assignments, request.objective),
                solver_status=terminal,
                objective_value=solver.objective_value,
                best_bound=solver.best_objective_bound,
            )
        )
        model.add(sum(x[u] for u in selected) <= len(selected) - request.min_champion_distance)
    return dict(
        game_id=dataset.game,
        ruleset_id=dataset.id,
        status=candidates[0]["solver_status"] if candidates else terminal,
        enumeration_status=terminal,
        candidates=candidates,
        elapsed_seconds=monotonic() - start,
        assumptions=[
            "Exact occupied board slots; unique eligible champions with explicit native trait weights",
            "Unlock/special mechanics unsupported and blocked",
            "Each subsequent optimum is conditional on diversity exclusions",
            "Scores are ordinal trait-count heuristics; actual win-rate unavailable",
            *([dataset.data_readiness.scope] if dataset.data_readiness else []),
        ],
        data_quality=dict(
            verification_status=dataset.verification_status,
            source=dataset.source,
            patch=dataset.patch,
            set=dataset.set,
            mode=dataset.mode,
            imported_at=dataset.imported_at,
            license_status=dataset.license_status,
        ),
    )
