"""Internal CP-SAT neighborhood controls, not additions to the legacy solve API."""

from dataclasses import dataclass, field
from time import monotonic

from ortools.sat.python import cp_model


PRIORITIES = {
    "MAX_EMBLEM_UTILIZATION": ["equipped_emblems", "core_preserved", "breakpoint_utility", "active_traits"],
    "MIN_REPLACEMENTS": [
        "negative_replacements",
        "core_preserved",
        "equipped_emblems",
        "breakpoint_utility",
        "active_traits",
    ],
    "MAX_BREAKPOINT_UTILITY": ["breakpoint_utility", "core_preserved", "equipped_emblems", "active_traits"],
    # Balance is an explicit order, not a calibrated combat-strength weight.
    "BALANCED_STRUCTURAL": [
        "core_preserved",
        "breakpoint_utility",
        "equipped_emblems",
        "active_traits",
        "negative_replacements",
    ],
    "PRESERVE_CORE": [
        "core_preserved",
        "negative_replacements",
        "equipped_emblems",
        "breakpoint_utility",
        "active_traits",
    ],
}


@dataclass
class AdaptationSpec:
    original_ids: list[str]
    replacements: int
    core_ids: list[str] = field(default_factory=list)
    preserve_core: bool = True
    reserved_slots: dict[str, int] = field(default_factory=dict)
    preferred_pairs: list[tuple[str, str]] = field(default_factory=list)
    ranking: str = "BALANCED_STRUCTURAL"

    def validate(self, dataset):
        units = {c.id: c for c in dataset.champions}
        if not set(self.original_ids + self.core_ids) <= units.keys() or not set(self.core_ids) <= set(
            self.original_ids
        ):
            raise ValueError("Invalid adaptation/core IDs")
        if len(set(self.original_ids)) != len(self.original_ids) or self.replacements not in (0, 1, 2):
            raise ValueError("Invalid replacement neighborhood")
        if self.ranking not in PRIORITIES:
            raise ValueError("Unknown multi-objective ranking")
        if not set(self.reserved_slots) <= units.keys() or any(
            n < 0 or n > units[uid].item_slots for uid, n in self.reserved_slots.items()
        ):
            raise ValueError("Invalid occupied item slots")


def lexicographic_solve(model, expressions, budget):
    """Only fix proven optima. A timeout never promotes a feasible incumbent to optimal."""
    start = monotonic()
    last_solver, last_status = None, cp_model.UNKNOWN
    stages = []
    for name, expression in expressions:
        remaining = budget - (monotonic() - start)
        if remaining <= 0:
            return last_solver, last_status, stages, False
        model.maximize(expression)
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = remaining
        solver.parameters.num_search_workers = 1
        solver.parameters.random_seed = 0
        status = solver.solve(model)
        stages.append(
            {
                "objective": name,
                "status": solver.status_name(status),
                "value": int(solver.value(expression)) if status in (cp_model.OPTIMAL, cp_model.FEASIBLE) else None,
                "best_bound": solver.best_objective_bound,
            }
        )
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            # Previously proven stages have a legal incumbent; keep it as FEASIBLE for the full vector.
            if last_solver is not None:
                return last_solver, cp_model.FEASIBLE, stages, False
            return solver, status, stages, False
        last_solver, last_status = solver, status
        if status != cp_model.OPTIMAL:
            return solver, status, stages, False
        model.add(expression == int(solver.value(expression)))
    return last_solver, last_status, stages, True
