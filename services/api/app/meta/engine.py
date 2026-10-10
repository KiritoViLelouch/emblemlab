"""Retained-instance and local meta-board analysis using the existing CP-SAT engine."""

from itertools import combinations
from time import monotonic

from app.meta.evidence import load_evidence, matching_evidence, supports_holder
from app.meta.repository import available, catalog_for
from app.optimizer.adaptation import AdaptationSpec, PRIORITIES
from app.optimizer.solver import RULES, solve
from app.schemas.domain import SolveRequest


def instances(ids, indices):
    return [{"instance_index": i, "emblem_id": ids[i]} for i in indices]


def metrics(candidate, original, core):
    ids = {c["id"] for c in candidate["champions"]}
    return dict(
        equipped_emblems=len(candidate["assignments"]),
        replacements=len(set(original) - ids),
        breakpoint_utility=sum(t["utility"] for t in candidate["traits"]),
        active_traits=sum(t["active"] for t in candidate["traits"]),
        core_preserved=len(set(core) & ids),
        core_units_lost=len(set(core) - ids),
    )


def benefit_vector(candidate):
    m = candidate["structural_metrics"]
    return (
        m["equipped_emblems"],
        -m["replacements"],
        m["breakpoint_utility"],
        m["active_traits"],
        -m["core_units_lost"],
    )


def rank_value(candidate, ranking):
    m = candidate["structural_metrics"]
    values = {**m, "negative_replacements": -m["replacements"], "core_preserved": -m["core_units_lost"]}
    return tuple(values[k] for k in PRIORITIES[ranking])


def frontier(candidates, ranking):
    vectors = {c["id"]: benefit_vector(c) for c in candidates}
    for c in candidates:
        v = vectors[c["id"]]
        c["pareto_frontier"] = not any(
            all(a >= b for a, b in zip(other, v)) and any(a > b for a, b in zip(other, v))
            for key, other in vectors.items()
            if key != c["id"]
        )
    return sorted(
        candidates, key=lambda c: (not c["pareto_frontier"], tuple(-v for v in rank_value(c, ranking)), c["id"])
    )


def holder_audit(dataset, selected, assignments, preferences, records):
    after = RULES.evaluate(dataset, selected, assignments)
    audited = []
    for a in assignments:
        before = RULES.evaluate(
            dataset, selected, [other for other in assignments if other["instance_index"] != a["instance_index"]]
        )
        effect = dict(
            active_trait_gain=sum(t["active"] for t in after) - sum(t["active"] for t in before),
            breakpoint_utility_gain=sum(t["utility"] for t in after) - sum(t["utility"] for t in before),
            unique_contribution_gain=sum(t["count"] for t in after) - sum(t["count"] for t in before),
        )
        evidence = matching_evidence(records, selected, assignments, holder=a)
        supported = any(supports_holder(record) for record in evidence)
        useful = effect["active_trait_gain"] > 0 or effect["breakpoint_utility_gain"] > 0
        audited.append(
            {
                **a,
                "legality": "legal",
                "structurally_useful": useful,
                "structural_effect": effect,
                "holder_classification": "statistically_supported"
                if supported
                else "structurally_useful"
                if useful
                else "legal",
                "statistical_evidence_available": bool(evidence),
                "statistically_supported": supported,
                "statistical_support_basis": "Exact context, positive sample, provider-declared independence/deduplication and count-based confidence; observational only"
                if supported
                else None,
                "statistical_evidence": evidence,
                "source_recommendations": [
                    p.model_dump()
                    for p in preferences
                    if (p.emblem_id, p.champion_id) == (a["emblem_id"], a["champion_id"])
                ],
                "optimal_holder_claim": False,
                "explanation": "合法分配；结构作用按移除此实例后的差值计算。推荐是来源意见；统计仅描述精确上下文，不证明持有者最优。",
            }
        )
    return audited


def source_view(key, comp, snapshot, source, dataset):
    return dict(
        key=key,
        id=comp.id,
        name=comp.name,
        provider_id=snapshot.export.provider_id,
        source_tier=comp.source_tier,
        source_tier_interpretation="Source-reported classification of the original board only; not inherited by adaptations",
        tier_citation=comp.tier_citation,
        data_kind=snapshot.export.data_kind,
        source_version=snapshot.export.source_version,
        source=source.model_dump(mode="json"),
        scope=snapshot.export.scope.model_dump(),
        catalog_sha256=snapshot.catalog_sha256,
        original_sha256=snapshot.original_sha256,
        imported_at=snapshot.imported_at.isoformat(),
        reviewed_at=comp.reviewed_at.isoformat(),
        champion_ids=comp.champion_ids,
        core_carry_ids=comp.core_carry_ids,
        core_tank_ids=comp.core_tank_ids,
        non_emblem_item_slots=comp.non_emblem_item_slots,
        baseline_emblem_ids=comp.baseline_emblem_ids,
        baseline_assignments=[a.model_dump() for a in comp.baseline_assignments],
        traits=RULES.evaluate(dataset, comp.champion_ids, [a.model_dump() for a in comp.baseline_assignments]),
    )


def analyze(request, *, retain_subsets=True):
    start = monotonic()
    dataset = catalog_for(request.scope)
    validation_request = SolveRequest(
        game_id=dataset.game,
        ruleset_id=dataset.id,
        emblem_ids=request.emblem_ids,
        board_size=request.board_size,
        constraints=request.constraints,
        top_k=1,
    )
    RULES.validate(dataset, validation_request)
    units = {c.id: c for c in dataset.champions}
    if not set(request.occupied_item_slots) <= units.keys() or any(
        n > units[uid].item_slots for uid, n in request.occupied_item_slots.items()
    ):
        raise ValueError("Unknown/cross-game unit or invalid occupied item slots")
    unsupported_traits = {t.id for t in dataset.traits if not t.supported or t.special_conditions}
    if any(e.id in request.emblem_ids and e.trait_id in unsupported_traits for e in dataset.emblems):
        raise ValueError("Emblem depends on unsupported special trait mechanics")
    entries, source_issues = available(request.scope)
    if request.composition_keys and not set(request.composition_keys) <= entries.keys():
        raise LookupError("Requested composition is missing, unauthorized or from another exact version")
    entries = {
        key: value
        for key, value in entries.items()
        if (not request.composition_keys or key in request.composition_keys)
        and value[0].board_size == request.board_size
        and (
            (value[1].export.data_kind == "meta" and value[0].source_tier in ("S", "A"))
            or (value[1].export.data_kind == "manual_scenario" and request.include_manual_scenarios)
            or (value[1].export.data_kind == "synthetic" and request.include_synthetic)
        )
    }
    omitted_keys = sorted(entries)[5:]
    entries = {key: entries[key] for key in sorted(entries)[:5]}
    records, evidence_issues = load_evidence(request.statistics_record_ids, request.scope)
    n = len(request.emblem_ids)
    if retain_subsets:
        subsets = [
            list(s)
            for k in range(n, -1, -1)
            for s in combinations(range(n), k)
            if k or request.include_empty_baseline or n == 0
        ]
    else:
        subsets = [list(range(n))]
    strategies = []
    for subset in subsets:
        allowed = not retain_subsets or set(request.locked_emblem_indices) <= set(subset)
        strategies.append(
            dict(
                retained_indices=subset,
                retained_instances=instances(request.emblem_ids, subset),
                not_retained_instances=instances(request.emblem_ids, [i for i in range(n) if i not in subset]),
                allowed=allowed,
                cases=[],
                status="PENDING" if allowed else "DISALLOWED_BY_INSTANCE_LOCK",
            )
        )
    sources = {key: source_view(key, *value, dataset) for key, value in entries.items()}
    candidates = []
    # Round-robin across subsets first: a large initial case cannot silently hide later strategies.
    for replacement in request.replacement_counts:
        for key, (comp, snapshot, source) in entries.items():
            core = list(dict.fromkeys(comp.core_carry_ids + comp.core_tank_ids))
            reserved = {
                uid: max(comp.non_emblem_item_slots.get(uid, 0), request.occupied_item_slots.get(uid, 0))
                for uid in set(comp.non_emblem_item_slots) | set(request.occupied_item_slots)
            }
            if any(n > units[uid].item_slots for uid, n in reserved.items()):
                raise ValueError("Occupied slots exceed current champion item slots")
            for strategy in strategies:
                if not strategy["allowed"]:
                    continue
                subset = strategy["retained_indices"]
                case = dict(source_key=key, replacements=replacement, status="NOT_RUN_BUDGET", candidate_id=None)
                strategy["cases"].append(case)
                remaining = request.timeout_seconds - (monotonic() - start)
                if remaining < 0.001:
                    continue
                # Retained means available, not mandatory equipment. The original catalog is never changed.
                local_dataset = dataset.model_copy(update={"allow_unused_emblems": True})
                banned = set(request.constraints.banned_units) | {
                    c.id for c in dataset.champions if set(c.traits) & unsupported_traits
                }
                constraints = request.constraints.model_copy(update={"banned_units": sorted(banned)})
                local = validation_request.model_copy(
                    update={
                        "emblem_ids": [request.emblem_ids[i] for i in subset],
                        "constraints": constraints,
                        "timeout_seconds": min(remaining, request.per_case_timeout_seconds),
                    }
                )
                preferences = [p for p in comp.holder_preferences if not replacement or p.applies_to_adaptations]
                specification = AdaptationSpec(
                    comp.champion_ids,
                    replacement,
                    core,
                    request.preserve_core,
                    reserved,
                    [(p.emblem_id, p.champion_id) for p in preferences],
                    request.ranking,
                )
                result = solve(local_dataset, local, adaptation=specification)
                case.update(status=result["status"], elapsed_seconds=result["elapsed_seconds"])
                if not result["candidates"]:
                    continue
                c = result["candidates"][0]
                selected = [u["id"] for u in c["champions"]]
                c["assignments"] = holder_audit(local_dataset, selected, c["assignments"], preferences, records)
                statistical_evidence = matching_evidence(records, selected, c["assignments"])
                for a in c["assignments"]:
                    a["solver_instance_index"] = a["instance_index"]
                    a["instance_index"] = subset[a["instance_index"]]
                used = {a["instance_index"] for a in c["assignments"]}
                unused = [i for i in range(n) if i not in used]
                original_traits = {t["id"]: t for t in sources[key]["traits"]}
                changes = [
                    {
                        "trait_id": t["id"],
                        "before": original_traits[t["id"]],
                        "after": t,
                        "count_delta": t["count"] - original_traits[t["id"]]["count"],
                        "level_delta": t["level"] - original_traits[t["id"]]["level"],
                        "utility_delta": t["utility"] - original_traits[t["id"]]["utility"],
                    }
                    for t in c["traits"]
                    if t != original_traits[t["id"]]
                ]
                identifier = f"{key}/keep-{''.join(map(str, subset)) or 'none'}/replace-{replacement}"
                # The legacy weighted score is not the optimization objective of this new engine.
                c.pop("score")
                c.pop("unused_emblem_indices")
                c.update(
                    id=identifier,
                    source_meta_composition=sources[key],
                    original_source_tier=comp.source_tier,
                    retained_instances=strategy["retained_instances"],
                    unused_instances=instances(request.emblem_ids, unused),
                    retained_but_unused_instances=instances(request.emblem_ids, [i for i in subset if i not in used]),
                    proposed_to_reforge_instances=instances(request.emblem_ids, unused),
                    champions_added=sorted(set(selected) - set(comp.champion_ids)),
                    champions_removed=sorted(set(comp.champion_ids) - set(selected)),
                    core_units_lost=sorted(set(core) - set(selected)),
                    occupied_item_slots=reserved,
                    activated_traits=[t for t in c["traits"] if t["active"]],
                    trait_breakpoint_changes=changes,
                    structural_metrics=metrics(c, comp.champion_ids, core),
                    adapted_tier=None,
                    adapted_win_rate=None,
                    objective_value_kind="last_completed_lexicographic_stage_only",
                    statistical_evidence_available=bool(statistical_evidence),
                    statistical_evidence=statistical_evidence,
                    explanation="来源等级仅适用于原阵容。按明确的多目标顺序优化局部结构，不预测实战胜率；未用纹章仅列为可能处理的实例，不代表已重铸。",
                )
                case["candidate_id"] = identifier
                candidates.append(c)
    for strategy in strategies:
        if not strategy["allowed"]:
            continue
        cases = strategy["cases"]
        if not entries:
            strategy["status"] = "MISSING_META_DATA"
        elif any(c["candidate_id"] for c in cases):
            strategy["status"] = "CANDIDATES_FOUND"
        elif all(c["status"] == "INFEASIBLE" for c in cases):
            strategy["status"] = "INFEASIBLE"
        else:
            strategy["status"] = "INCOMPLETE_SEARCH"
    ranked = frontier(candidates, request.ranking)
    cases = [c for s in strategies for c in s["cases"]]
    return dict(
        scope=request.scope.model_dump(),
        analysis="hypothetical_emblem_retention_and_local_adaptation",
        static_game_data=dict(
            source=dataset.source,
            imported_at=dataset.imported_at,
            verification_status=dataset.verification_status,
            license_status=dataset.license_status,
            unsupported_mechanics=dataset.data_readiness.unsupported_mechanics if dataset.data_readiness else [],
        ),
        status="MISSING_META_DATA" if not entries else "CANDIDATES_FOUND" if candidates else "NO_CANDIDATE",
        retained_strategy_count=len(strategies),
        strategies=strategies,
        candidates=ranked,
        pareto_frontier_ids=[c["id"] for c in ranked if c["pareto_frontier"]],
        ranking=request.ranking,
        ranking_priorities=PRIORITIES[request.ranking],
        source_compositions=list(sources.values()),
        ranking_metric_interpretation={
            "core_preserved": "Within a source: maximize preserved core count; across sources: minimize core units lost"
        },
        omitted_composition_keys=omitted_keys,
        source_issues=source_issues,
        statistics_issues=evidence_issues,
        elapsed_seconds=monotonic() - start,
        search_coverage=dict(
            requested_cases=len(cases),
            attempted_cases=sum(c["status"] != "NOT_RUN_BUDGET" for c in cases),
            all_requested_cases_resolved=bool(cases) and all(c["status"] in ("OPTIMAL", "INFEASIBLE") for c in cases),
        ),
        reforge_action=None,
        reforge_probabilities=None,
        expected_value=None,
        limitations=[
            "Pareto frontier covers returned candidates, not every legal composition or assignment",
            "OPTIMAL is conditional on exact source board, replacement count and stated lexicographic priorities",
            "No inheritance of source tier or win rate; static trait utility is not combat strength",
            "Only supplied equipment reservations are known; unspecified equipment is assumed empty",
            "Champion availability, including Lux forms, must be specified with locks/exclusions; no draw probability is modeled",
            "Not using an emblem does not physically reforge it; probabilities and EV remain unknown",
            "Core preservation is hard by default; disabling it is an explicit hypothetical relaxation",
            *([dataset.data_readiness.scope] if dataset.data_readiness else []),
        ],
    )
