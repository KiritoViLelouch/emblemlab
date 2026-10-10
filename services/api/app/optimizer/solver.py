from time import monotonic
from ortools.sat.python import cp_model
from app.rules.evaluator import FixtureRules
from app.scoring.engine import WEIGHTS, score
from app.optimizer.adaptation import PRIORITIES, lexicographic_solve

RULES = FixtureRules()


def solve(dataset, request, *, adaptation=None):
    adaptation_start = monotonic()
    RULES.validate(dataset, request)
    if adaptation:
        adaptation.validate(dataset)
        if request.top_k != 1:
            raise ValueError("Adaptation solves one optimum per exact neighborhood")
    model = cp_model.CpModel()
    units = dataset.champions
    emblems = {e.id: e for e in dataset.emblems}
    x = {c.id: model.new_bool_var(c.id) for c in units}
    if adaptation:
        original = set(adaptation.original_ids)
        model.add(sum(x[uid] for uid in original) == len(original) - adaptation.replacements)
        model.add(sum(x[c.id] for c in units if c.id not in original) == adaptation.replacements)
        if adaptation.preserve_core:
            for uid in adaptation.core_ids:
                model.add(x[uid] == 1)
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
        reserved = adaptation.reserved_slots.get(c.id, 0) if adaptation else 0
        model.add(sum(y[c.id, e] for e in range(len(request.emblem_ids))) <= c.item_slots - reserved)
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
    if not adaptation:
        model.maximize(
            weights[0] * sum(active)
            + weights[1] * sum(utility)
            + weights[2] * sum(c.cost * x[c.id] for c in units)
            + weights[3] * sum(y.values())
        )
    candidates = []
    start = adaptation_start if adaptation else monotonic()
    terminal = "UNKNOWN"
    lex_stages, lex_complete = [], False
    for rank in range(request.top_k):
        remaining = request.timeout_seconds - (monotonic() - start)
        if remaining <= 0:
            terminal = "UNKNOWN"
            break
        if adaptation:
            metrics = dict(equipped_emblems=sum(y.values()), core_preserved=sum(x[uid] for uid in adaptation.core_ids),
                           breakpoint_utility=sum(utility), active_traits=sum(active),
                           negative_replacements=-adaptation.replacements)
            expressions = [(key, metrics[key]) for key in PRIORITIES[adaptation.ranking]]
            if adaptation.preferred_pairs:
                pairs = set(adaptation.preferred_pairs)
                expressions.append(("source_holder_preference", sum(
                    v for (uid, eidx), v in y.items() if (request.emblem_ids[eidx], uid) in pairs
                )))
            solver, status, lex_stages, lex_complete = lexicographic_solve(model, expressions, remaining)
            if solver is None:
                terminal = "UNKNOWN"
                break
            if status == cp_model.OPTIMAL and not lex_complete:
                status = cp_model.FEASIBLE
        else:
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
        if adaptation:
            removed = set(adaptation.original_ids) - set(selected)
            added = set(selected) - set(adaptation.original_ids)
            if len(removed) != adaptation.replacements or len(added) != adaptation.replacements:
                raise RuntimeError("Post-solve replacement mismatch")
            if adaptation.preserve_core and not set(adaptation.core_ids) <= set(selected):
                raise RuntimeError("Post-solve core mismatch")
            for uid, reserved in adaptation.reserved_slots.items():
                if reserved + sum(a["champion_id"] == uid for a in assignments) > next(c.item_slots for c in units if c.id == uid):
                    raise RuntimeError("Post-solve occupied item slot mismatch")
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
                **({"lexicographic_stages": lex_stages, "lexicographic_complete": lex_complete} if adaptation else {}),
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
