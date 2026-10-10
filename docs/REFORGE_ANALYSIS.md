# Phase 4: versioned reforge scenario analysis

This analyzer evaluates offline, fixed, single-pass plans. It never interacts with a game client. All bundled catalogs and reforge laws are **original synthetic definitions, not actual TFT/JCC mechanics or probabilities**. No current game rules were researched or verified in this milestone. Community advice and statistical observations do not supply probabilities or change optimizer scores.

## Interface audit and compatibility

Before Phase 4, `app/reforge/service.py` implemented only hypothetical retained subsets: remove some input emblems from the solver inventory, respecting instance locks. The `ReforgeRules.describe` boundary had no mechanics, pools or probabilities. `/api/v1/reforge/simulate` continues to return its original retention-only shape, with null probabilities/EV; its `actual_reforge` action still returns 422. Discarding or leaving an emblem unused is not a reforge.

New modules `reforge/schemas.py`, `rules.py`, and `analyzer.py` define, load, enumerate and evaluate finite versioned laws. The existing CP-SAT solver, rule evaluator, scoring coefficients, catalog fixtures, community API, statistics API and database schema are unchanged. The new analyzer calls the real `solve` function with Top 1 for each distinct outcome inventory; there is no proxy scoring model.

## API

- `GET /api/v1/reforge/rules?game_id=TFT&ruleset_id=fixture_tft_v1`: complete server-controlled rule definitions matching the requested catalog, or an empty list when no definition exists.
- `POST /api/v1/reforge/analyze`: extends the solve request with a required `reforge_rule_id`, `available_reforgers` (integer 0–3, default 0), `locked_emblem_indices` (unique zero-based input instance indices), and `analysis_timeout_seconds` (0.001–60, default 20).

Example with unknown probabilities:

```json
{
  "game_id": "TFT",
  "ruleset_id": "fixture_tft_v1",
  "reforge_rule_id": "synthetic_tft_unknown_v1",
  "emblem_ids": ["tft_emblem_0", "tft_emblem_1", "tft_emblem_2"],
  "board_size": 8,
  "objective": "MAX_ACTIVE_TRAITS",
  "constraints": {"locked_units": [], "banned_units": [], "max_unit_cost": 5},
  "available_reforgers": 2,
  "locked_emblem_indices": [1],
  "timeout_seconds": 3,
  "analysis_timeout_seconds": 20
}
```

`top_k` and `min_champion_distance` remain accepted inherited fields, but analysis always uses one composition per inventory. `timeout_seconds` caps each CP-SAT solve; the analyzer shares the remaining analysis budget fairly across pending inventories. Enumeration/model construction/serialization add overhead, so this is a soft execution budget, not a hard HTTP deadline. If insufficient time remains, results are explicitly `NOT_RUN`; they have no fabricated score or solver result.

Response sections:

- `rule`: full version, provenance, mechanics, pool law, verification and evidence metadata.
- `baseline_evaluation_id`: points to an optimized composition with **all original emblems available**. It is not a valuation of an externally supplied current board.
- `strategies`: all `2^N` original-instance retained subsets, including illegal ones and reasons. The complement is reforged. Each strategy has every fixed permutation of its target indices and the charge cost, legality, outcomes and summary for each order. Retaining all emblems is the no-op action.
- `outcomes`: each distinct resulting emblem multiset, its probability (or null), and `evaluation_id`. Different paths to the same multiset are merged by adding exact probability mass, not by equal weighting.
- `evaluations`: shared actual CP-SAT results, inventory, status, and score. Every canonical inventory is solved at most once per request, including the baseline. Assignment instance indices refer to that evaluation's sorted `emblem_ids`; they are not original UI slots. Retention locks and target order always refer to original request instances, so duplicate instances remain distinguishable.
- `enumeration_complete`: true on a successful response; oversized spaces fail with 422 rather than silently truncating.
- `evaluation_complete`: all distinct inventories were passed to CP-SAT; does **not** mean they were solved optimally. `all_compositions_proven_optimal` separately reports that fact. Full solver status, best bound and candidate assignments remain available.

Malformed requests, missing/mismatched rules, stale catalogs, unsupported mechanics, invalid pools and oversized spaces return 422. No fallback to another game, patch, set, mode or rule ID occurs. The response's `value_kind` distinguishes synthetic rule scores from production heuristic estimates.

## Rule format and activation

Definitions are operator-controlled JSON files under `data/reforge/*.json`. HTTP clients select an ID; they cannot submit mechanics or assert verified probabilities. The Pydantic `ReforgeRule` schema is authoritative. See the four complete checked-in examples.

Each definition includes:

| Field | Contract |
| --- | --- |
| `schema_version`, `id`, `name` | Version 1; unique rule ID; human-readable name |
| `game`, `patch`, `set`, `mode`, `ruleset_id` | Exact catalog scope |
| `catalog_sha256` | SHA-256 of UTF-8 `json.dumps(dataset.model_dump(), sort_keys=True, separators=(",", ":"))`; includes rules, names and provenance |
| `source`, `imported_at`, `verification_status` | Provenance; only `synthetic` or `verified` mechanics may activate |
| `mechanics_evidence` | `kind`, nonempty `reference`, `reviewed_by`, `reviewed_at` |
| `mechanic` | Only `replace_each_target_once` supported |
| `draw_policy` | `independent` or `conditional_exclude_other_instances` |
| `reforgers_per_target`, `max_targets` | Integers 1–3 |
| `target_pools` | 1–100 entries, unique `input_emblem_id`, 1–12 unique output emblem IDs each; all IDs in this exact catalog |
| `probability_status` | `unknown` or `verified` |
| `probability_evidence` | Required for verified distributions; must be null for unknown |

Evidence kinds: `synthetic_definition` only for synthetic laws; `first_party` or `licensed_provider` for verified production laws. Production laws require a verified catalog and verified entities. Evidence is an operator review record, not automatic proof of authenticity or permission. Before adding production laws, an operator must obtain authoritative or explicitly licensed mechanics/probabilities and validate the applicability and rights. The loader neither fetches evidence URLs nor scrapes websites. It rejects any catalog hash change, requiring a freshly reviewed definition.

Each output has `emblem_id` and a `probability` that is null when unknown, or an exact rational `{ "numerator": 1, "denominator": 3 }`. Positive integer components are limited to 1e9. All entries have positive support; omit impossible/zero-probability outcomes. Verified base pools must sum **exactly** to one. Mixed known/unknown weights, duplicate entries and numeric probabilities labelled unknown are rejected. Neither a uniform distribution nor independence is inferred from pool membership.

Under `independent`, each target draws from its source pool independently. Under `conditional_exclude_other_instances`, each step excludes all IDs held by the other current instances, including locked/retained instances and future targets, then conditions the explicitly specified base distribution on the remaining set. This normalization is part of that declared law. Unknown pools are filtered the same way but remain unweighted. Action order can therefore change the distribution or legality. Original-ID return is permitted only if explicitly present in the source pool. Each original target can be used once; drawn replacements are never rerolled.

A fixed plan is legal only if it respects locks, target permissions, target cap, charges and catalog duplicate restrictions at **every step**, and every possible branch can complete. A reachable empty pool or illegal duplicate makes that whole order illegal. Failure branches are not removed to produce an artificially successful distribution. Unsupported rules such as changing charge costs, non-emblem results, adaptive stopping or repeated rerolls require an explicit future schema/mechanic; they cannot be approximated by this one.

## Values, probabilities and downside

The baseline and every outcome preserve the same board size, champion locks, exclusions, cost cap and objective. Each outcome can fully reselect the board and legal holders. A retained emblem need not be equipped when the catalog allows unused emblems. There are no gold, bench, ownership, transition or reforger opportunity costs. This is the value of a reoptimized composition under a transparent heuristic objective, not combat power, top-four rate, win rate or a financial value.

For each legal action, if every outcome has an `OPTIMAL` composition, `worst_case_score` and `best_case_score` describe the full possible score range. They are scenarios, not probability claims. If the baseline is also `OPTIMAL`, maximum downside is `max(0, baseline − worst)` and the worst delta is `worst − baseline`.

Only verified probabilities **and** optimal compositions for all outcomes permit numeric `expected_value = Σ p(outcome) × score(outcome)`. `expected_value_exact` retains numerator/denominator as well as a float for clients. A proven baseline additionally permits `expected_delta`, `probability_of_loss = Σ p(score < baseline)`, and `expected_downside = Σ p × max(0, baseline − score)`.

All these probability-dependent fields are null when probabilities are unknown, including for a no-op or a singleton pool. No averaging or assumed equal weights is used. A missing or infeasible composition has no numeric penalty substituted. `FEASIBLE` scores and solver bounds can be inspected, but point EV and full ranges are withheld if any outcome lacks an optimal composition. Infeasible and unresolved outcome counts are separate. Known probability mass of proven infeasible outcomes is reported as a lower bound; exact `infeasible_probability` is null if any outcome still has unknown feasibility. No confidence interval is fabricated for an unverified probability law.

## Synthetic laws

There are four original demonstration definitions: known and unknown variants for each of TFT and JCC, scoped to `EXAMPLE-1.0`, `SYNTHETIC-EXAMPLE`, `offline-fixture` and the matching catalog fingerprint.

For emblem `i` among seven symbols, the pool is `(i+1) mod 7` and `(i+2) mod 7`. The known variant defines exact base probabilities 1/3 and 2/3; those numbers are a mathematical toy law, **not estimates from matches or actual game rules**. The unknown variant deliberately supplies no probabilities. TFT uses independent draws; JCC excludes other currently owned symbols before each draw. A target consumes one reforger, at most three targets. Both known and unknown variants enumerate the same possible support under their mechanic.

## Exhaustiveness, limits and verification

The analyzer enumerates every subset and every fixed target order, then every allowed draw path without score pruning. For three instances this means eight subsets and at most sixteen ordered plans including no-op. All legal terminal inventories are submitted to the existing CP-SAT solver. Shared canonical inventory results are valid because original instance locks constrain reforge actions, not holders, and all other solver inputs are identical.

Limits: three input emblems/charges, 4,096 visited draw-tree nodes per analysis, and 128 unique evaluation inventories. A limit breach fails before solving. Large real catalogs may time out; unfinished CP-SAT searches and unexecuted evaluations are explicit. No persistent reforge cache or database migration is needed.

Tests exhaust every input inventory of length 0–3 from a three-symbol alphabet, every lock mask and charge budget 0–3, each retention subset, all target orders and draw paths for both supported mechanics and known/unknown laws. A second independent oracle exhausts small board combinations and legal equipment placements, comparing every resulting inventory's optimum, trait counts, EV and risk for all five objectives. Additional cases cover incomplete search, infeasibility, dead ends, duplicate locks, version fingerprints, target restrictions, invalid weights, resource bounds and old API compatibility. See PHASE4_VERIFICATION.md for commands actually run and browser checks.
