# Phase 4 verification — 2026-10-10

All results below were actually executed locally against the current implementation. All catalogs, pools and known probabilities used here are explicitly synthetic. No production game mechanics/probability validation or live match data test is claimed.

## Commands executed

From `services/api`:

```sh
../../.venv/bin/pytest -q
../../.venv/bin/ruff check app tests
PYTHONPATH=. ../../.venv/bin/python tests/live_review.py
../../.venv/bin/python tests/live_reforge_review.py
```

- Full backend suite: **201 passed** in 5.31 seconds, including 59 new Phase 4 cases and 142 existing cases. One existing Starlette/httpx TestClient deprecation warning; no test failures.
- Ruff: passed, including the new live HTTP verification script.
- Legacy live API regression: both games, all five objectives, 50 candidate compositions independently checked, locks/exclusions/cost/counting/holders/subsets and five frontend routes passed. Evidence: `review-api-results.json`.
- New live HTTP checks: both games and both known/unknown probability laws passed; exact probability sums and EV arithmetic checked for every legal action; zero charges leave only no-op; instance locks respected; absent rule rejected. Evidence: `reforge-http-verification.json`.

From `apps/web`:

```sh
npm run typecheck
npm run lint
npm run build
```

All passed. Production Next.js server and Uvicorn API were started and used for browser/HTTP verification. No database migration or source registry changes were needed for Phase 4.

## Exhaustive synthetic reference coverage

`tests/test_reforge.py` independently enumerates all input inventories of length 0–3 from a three-symbol alphabet (duplicates allowed only for TFT), every instance-lock mask and charge budget 0–3, all retained subsets, all target orders, and all draw-choice combinations. Both declared draw policies are exercised with verified synthetic rational probabilities and unknown probabilities. The reference uses a Cartesian product of draw choices rather than the implementation's recursive traversal. Legal support and exact probability mass match.

For every reachable inventory in small nine-champion/four-emblem fixtures, an independent board/assignment oracle checks all five objective modes in both games. Candidate optimum, actual trait counts, EV, expected delta, extrema, maximum downside, expected downside and probability of loss match. The tests record real CP-SAT calls and verify each distinct inventory is solved once.

Additional executed tests cover empty inventory/no-op, duplicate instance locks, conditional action-order differences, target permission/caps/charge cost, empty pools, illegal intermediate duplicate inventories, unknown probability nulls, infeasible outcomes with no imputed score, FEASIBLE/UNKNOWN status gates, total-budget exhaustion with explicit NOT_RUN, unresolved infeasibility probability, invalid weight sums/evidence, exact version/fingerprint isolation, cross-game IDs, resource-limit rejection before solving and unchanged original optimizer/API behavior. Mocked status/clock cases test fallback reporting; they are not represented as real optimal solves.

## HTTP results

Inputs: emblem indices 0, 1, 2; board size 8; three charges; no locks; default objective.

| Synthetic game | Probability law | Retained subsets | Legal subsets | Distinct inventories | CP-SAT |
| --- | --- | ---: | ---: | ---: | --- |
| TFT | Unknown | 8 | 8 | 21 | All OPTIMAL; all EV null |
| TFT | Defined 1:2 law | 8 | 8 | 21 | All OPTIMAL; EV checked |
| JCC | Unknown | 8 | 7 | 10 | All OPTIMAL; all EV null |
| JCC | Defined 1:2 conditional law | 8 | 7 | 10 | All OPTIMAL; EV checked |

JCC's missing legal subset is explicitly illegal because reforging the first emblem while retaining the other two yields an empty pool under that synthetic law. No failure branch is removed to fabricate a successful distribution.

## Browser checks executed

Codex in-app browser using the production build and running backend:

- Three-emblem TFT unknown law: eight retained subsets, 21 inventories, optimal baseline, possible scores displayed, outcome probabilities unknown and no numeric EV.
- Selected an outcome and inspected the actual eight-champion composition, legal emblem holders and trait counts.
- Switched to known synthetic law: prior results cleared. Locked original slot 2 and set one charge: exactly three legal subsets; lock and charge rejection explanations displayed.
- Retain slots 1/2, reforge slot 3: baseline 61,093; possible scores 70,837 and 61,095, weights 1/3 and 2/3; displayed EV 64,342.333 and delta 3,249.333. This is a synthetic heuristic score, not a game statistic.
- Desktop viewport 1440×1000, mobile viewport 390×844, narrow mobile 320×780: DOM content width equalled viewport width (no horizontal page overflow); mobile outcome controls worked and the selected composition rendered.
- Game switch cleared outputs and reset emblem locks/selections; JCC's independent catalog and rule options appeared.
- JCC known law: seven legal subsets and ten inventories; opened the illegal retain-2/3 plan and confirmed the empty-pool explanation. The initially interrupted JCC action was completed in a fresh temporary browser tab.

Saved screenshots (desktop known-law and mobile composition images were also visually inspected):

- `screenshots/reforge-desktop-unknown.png`
- `screenshots/reforge-desktop-known.png`
- `screenshots/reforge-mobile-known.png`
- `screenshots/reforge-mobile-composition.png`
- `screenshots/reforge-jcc-legality.png`

Browser checks are viewport-based, not physical-device or cross-browser certification. No accessibility audit or browser stress test is claimed.

## Remaining limits

Only synthetic rule definitions ship. Production evidence review, legal first-party/licensed rule sourcing, and real-patch activation remain unconfigured. The analyzer supports fixed single-pass orders, at most three instances/charges, two explicit draw laws, 4,096 visited nodes and 128 unique inventories. Adaptive policies, repeated rerolls, non-emblem outputs, board-transition costs, gameplay execution, combat power and statistics-backed scoring are unsupported. Full reoptimization after observing an outcome is an optimistic assumption, clearly disclosed. A solver timeout can leave partial evaluations; affected point EV/ranges remain null. The analysis timeout is a soft budget with model/serialization overhead. Full contracts and assumptions: `REFORGE_ANALYSIS.md`.
