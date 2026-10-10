# Phase 1 meta adaptation algorithm

The existing CP-SAT model and RuleEvaluator remain the source of legality. Legacy `/solve` behavior and weighted objectives are unchanged. New internal `AdaptationSpec` controls only the new endpoints; it is not a second solver.

## Exact local neighborhoods

For original champion set B, binary selection x[u] and replacement count r in {0,1,2}:

```
sum(x[u] for u in B)     = |B| - r
sum(x[u] for u not in B) = r
```

Each replacement removes one champion and adds one. Unit cardinality stays equal to the source board; **population** still uses each unit's `board_slots` and verified capacity bonuses. Extra units from population bonuses are not automatically added outside this neighborhood. Thus some legal expanded boards may lie outside the supported neighborhood and are not searched. Source board size must match the requested base population, without patch/mode fallback.

Declared important carries and tanks are x=1 by default. Optional `preserve_core=false` explicitly relaxes that condition; core losses are returned and ranked. User locks, exclusions and maximum cost are still enforced. Units depending on unsupported traits are banned, unsupported retained emblems rejected, and source boards with unsupported mechanisms refused. Existing unavailable/unlock units, exclusive forms, incompatible traits and unverified trait-count caps continue to block affected boards.

For selected retained instance e and champion u, y[u,e] ≤ x[u]. Each retained instance may equip at most once; it may remain unused even if the ordinary `/solve` profile requires all requested emblems. This is an analysis-local copy of the equipment policy: the catalog, old endpoint and original inventory are not changed. Summed equipment is bounded by remaining item slots and same-emblem-per-holder limits. Duplicate instance IDs are never deduplicated.

Native and granted trait contribution for one unique champion is:

```
contribution[u,t] = max(native_weight[u,t] * x[u], y[u,e] for emblems e granting t)
count[t] = sum(contribution[u,t] for all champions u)
```

This preserves native double weights and prevents native/emblem or duplicate-emblem double counting. Verified ordinary threshold indicators define active traits and ordinal breakpoint utility. No nonmonotonic/conditional mechanic is guessed.

## Multi-objective optimization

For every source/subset/r cell, maximize each priority in order. Fix an earlier objective to its value **only after CP-SAT proves OPTIMAL**. Stop at the first incomplete stage. If time expires after an earlier stage was proven but later objectives remain unproven, return the legal incumbent as **FEASIBLE for the whole vector**. Only a complete lexicographic proof receives OPTIMAL. Each stage reports objective, value, status and bound.

| Ranking | Priority order (highest first) |
|---|---|
| MAX_EMBLEM_UTILIZATION | equipped instances, preserved core, breakpoint utility, active traits |
| MIN_REPLACEMENTS | fewer replacements, preserved core, equipped instances, breakpoint utility, active traits |
| MAX_BREAKPOINT_UTILITY | breakpoint utility, preserved core, equipped instances, active traits |
| BALANCED_STRUCTURAL | preserved core, breakpoint utility, equipped instances, active traits, fewer replacements |
| PRESERVE_CORE | preserved core, fewer replacements, equipped instances, breakpoint utility, active traits |

Within a cell replacement count is constant; retaining it in the vector also states the cross-cell ranking rule. Across different source boards, core preservation is compared by **units lost**, preventing a source with more declared core units from winning merely by having more labels. Hard preservation remains the default. “Balanced” is this explicit ordinal order, not a fitted combat model or an arbitrary weighted scalar.

An authorized source's applicable holder recommendations can break a final structural tie. They never outweigh a primary objective, cannot make an illegal holder legal, and are excluded from changed boards unless explicitly applicable. Missing strategic/statistical evidence produces no invented preference. Deterministic CP-SAT configuration (one worker, seed 0) resolves remaining ties without an optimal-holder claim.

## Frontier and coverage

One lexicographic optimum/incumbent is returned per source/subset/r cell. Pareto dominance compares:

- More equipped instances.
- Fewer replaced champions.
- Greater absolute breakpoint utility.
- More active traits.
- Fewer lost core units.

A dominates B only if no axis is worse and at least one is better. Equal vectors remain valid alternatives. The frontier covers **only returned candidates**; intermediate nondominated boards/assignments can be omitted by a cell's lexicographic search. This is not a complete global Pareto enumeration. Candidates on the returned frontier sort before dominated ones, then by the selected explicit priority order. Source tier and original outcome rates are not ranking axes.

More retained instances are never automatically assigned a strength bonus. Available-but-unused instances are reported. Keeping all three provides a superset of optional equipment choices under this structural model, so it can tie or dominate a smaller subset without proving it is strategically best to retain them in a real game. Unknown opportunity cost, draw probabilities, combat strength and reforge outcomes remain outside the model. No EV or actual reforge action is inferred.

All allowed subset rows are generated before solving. Replacement rounds interleave subsets so one initial strategy does not consume the entire total budget unnoticed. Up to five explicitly scoped source boards are searched. Every missing-budget cell is `NOT_RUN_BUDGET`; feasible candidates, INFEASIBLE proofs and UNKNOWN are distinguished. `all_requested_cases_resolved` means those selected cells are individually OPTIMAL/INFEASIBLE, not that every possible source/meta/Pareto board was exhausted.

## Post-solve checks and provenance

Every board passes existing RuleEvaluator validation, then explicit replacement-count, core and occupied-item checks. Assignment indices are mapped back from compact solver indices to the user's original emblem-instance indices. Baseline and adapted traits are recomputed separately. Source baseline emblems describe only the source board and do not become extra available input items.

Source authorization, exact game/set/patch/mode, static catalog hash, normalized/raw snapshot hashes and original filenames remain attached. A missing, revoked, changed or corrupted export is unavailable, never a reason to fetch/scrape a replacement or mix versions. Statistical references use the existing licensed reader and exact declared context; original source-tier classification and source-board win rates never transfer to an adapted board.

Testing uses independent exhaustive enumeration of champion subsets, legal equipment choices and manually implemented native/emblem counts for small fixtures. Fifteen cases compare five ranking profiles × three exact replacement counts. Actual TFT static-record tests and local HTTP examples separately recount holder legality, capacity, equipment and each trait. These do not establish real high-tier meta or JCC data coverage.
