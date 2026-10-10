from typing import Protocol
from app.schemas.domain import Champion, Emblem, Ruleset, SolveRequest
from app.data_validation.catalog import validate_catalog


class RuleEvaluator(Protocol):
    def legal(self, champion: Champion, emblem: Emblem) -> bool: ...
    def validate(self, dataset: Ruleset, request: SolveRequest) -> None: ...


class FixtureRules:
    def legal(self, champion, emblem):
        return (
            champion.available
            and emblem.available
            and not champion.unlock_condition
            and champion.item_slots > 0
            and champion.id not in emblem.banned_holders
            and (emblem.allow_native or emblem.trait_id not in champion.traits)
        )

    def validate(self, dataset, request):
        units = {c.id for c in dataset.champions}
        emblems = {e.id for e in dataset.emblems}
        if request.game_id != dataset.game or request.ruleset_id != dataset.id:
            raise ValueError("Dataset mismatch")
        if (
            dataset.data_readiness or (dataset.verification_status != "synthetic" and dataset.mode != "offline-fixture")
        ) and not validate_catalog(dataset.model_dump())["optimization_enabled"]:
            raise ValueError("Essential rules/data are unverified; real-game optimization disabled")
        if not set(request.constraints.locked_units + request.constraints.banned_units) <= units:
            raise ValueError("Unknown or cross-game champion")
        if not set(request.emblem_ids) <= emblems:
            raise ValueError("Unknown or cross-game emblem")
        if not dataset.allow_duplicate_emblems and len(set(request.emblem_ids)) != len(request.emblem_ids):
            raise ValueError("此规则集不允许重复纹章")
        if any(t.special_conditions and t.supported for t in dataset.traits):
            raise ValueError("Unsupported special trait mechanic")
        if any(not e.available for e in dataset.emblems if e.id in request.emblem_ids):
            raise ValueError("Unsupported or unverified emblem")

    def evaluate(self, dataset, selected, assignments):
        units = {c.id: c for c in dataset.champions}
        emblems = {e.id: e for e in dataset.emblems}
        contributions = {t.id: {} for t in dataset.traits}
        for uid in selected:
            for tid in units[uid].traits:
                contributions[tid][uid] = units[uid].trait_weights.get(tid, 1)
        for a in assignments:
            tid, uid = emblems[a["emblem_id"]].trait_id, a["champion_id"]
            contributions[tid][uid] = max(contributions[tid].get(uid, 0), 1)
        result = []
        for t in dataset.traits:
            count = sum(contributions[t.id].values())
            levels = [b for b in t.thresholds if count >= b.count] if t.supported else []
            result.append(
                dict(
                    id=t.id,
                    name=t.zh_CN,
                    count=count,
                    active=bool(levels),
                    level=len(levels),
                    utility=levels[-1].utility if levels else 0,
                    thresholds=[b.count for b in t.thresholds],
                    supported=t.supported,
                )
            )
        return result

    def validate_solution(self, dataset, request, selected, assignments):
        self.validate(dataset, request)
        units = {c.id: c for c in dataset.champions}
        emblems = {e.id: e for e in dataset.emblems}
        if len(set(selected)) != len(selected) or not set(selected) <= units.keys():
            raise ValueError("Invalid board capacity")
        if not set(request.constraints.locked_units) <= set(selected) or set(request.constraints.banned_units) & set(
            selected
        ):
            raise ValueError("Invalid champion constraints")
        if any(
            not units[u].available or units[u].unlock_condition or units[u].cost > request.constraints.max_unit_cost
            for u in selected
        ):
            raise ValueError("Unavailable unit")
        seen = set()
        slots = {}
        pairs = {}
        for a in assignments:
            index = a["instance_index"]
            uid = a["champion_id"]
            eid = a["emblem_id"]
            if (
                index in seen
                or index not in range(len(request.emblem_ids))
                or request.emblem_ids[index] != eid
                or uid not in selected
                or not self.legal(units[uid], emblems[eid])
            ):
                raise ValueError("Illegal emblem holder")
            seen.add(index)
            slots[uid] = slots.get(uid, 0) + 1
            pairs[uid, eid] = pairs.get((uid, eid), 0) + 1
        if any(n > units[u].item_slots for u, n in slots.items()) or any(
            n > dataset.max_same_emblem_per_holder for n in pairs.values()
        ):
            raise ValueError("Item slots or duplicate equipment exceeded")
        if not dataset.allow_unused_emblems and len(seen) != len(request.emblem_ids):
            raise ValueError("Unused mandatory emblem")

        traits = {t["id"]: t["count"] for t in self.evaluate(dataset, selected, assignments)}
        capacity = request.board_size + sum(
            b.slots for b in dataset.capacity_bonuses if traits[b.trait_id] >= b.threshold
        )
        if sum(units[u].board_slots for u in selected) != capacity:
            raise ValueError("Invalid board capacity")
        groups = [units[u].exclusive_group for u in selected if units[u].exclusive_group]
        if len(groups) != len(set(groups)):
            raise ValueError("Exclusive champion forms")
        if any(traits[tid] > limit for tid, limit in dataset.trait_count_limits.items()):
            raise ValueError("Unverified trait breakpoint")
        if any(traits[a] and traits[b] for a, b in dataset.incompatible_trait_pairs):
            raise ValueError("Unsupported trait interaction")
