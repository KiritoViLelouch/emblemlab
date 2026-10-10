# MVP review — 2026-10-10

Scope: review and repair existing Phase 0/1 only. No Phase 2 or new product features.

## Actually executed

| Area | Execution and result |
| --- | --- |
| Startup | Started Uvicorn on 127.0.0.1:8000 and Next.js dev on 127.0.0.1:3000. Later stopped dev, built production assets, started `npm start` and verified a production browser solve. |
| Fixtures | Live HTTP loaded both independent catalogs: 14 champions, 7 traits, 7 emblems each. Game metadata matches selection; champion IDs are disjoint. Mismatched game/ruleset and cross-game emblem requests returned 422. JCC UI showed its own names and duplicate policy; game switches reset champion locks/exclusions. |
| Three emblems | Live HTTP: 5 objectives × 2 games × 5 candidates = 50 audited candidate boards. Each request locked champion 0, excluded champion 1 and capped unit cost at 4. Every best candidate in this run was OPTIMAL. |
| Counting/equipment | An independent reference recomputed unique champion/trait OR counts, highest threshold utility, score arithmetic, legal holders, slots and duplicate equipment limits. All 50 live candidates matched. Native equipment and three identical emblems on one holder under a permissive test rule both counted once. |
| Constraints | Automated and live HTTP tests covered exact 7/8/9/10 boards, locks, exclusions, maximum cost, conflicting lock/ban infeasibility, slots and unsupported unlock availability. Desktop UI confirmed all five 8-unit cards include 星灯 and exclude 暮刃 after selecting those controls. |
| Brute force | Existing 5 objective tests enumerate 9-choose-7 boards with one emblem. Added 15 independent three-emblem exhaustive cases: TFT distinct, TFT duplicates, JCC distinct × all 5 objectives. Nine-unit pools, seven-unit boards, lock/exclusion constraints and restricted slots. Oracle uses no production counting, legality or scoring function; optimum, legal assignments and counts matched CP-SAT. |
| Diversity | Every pair in each live Top-5 request replaces at least 2 champions. |
| Desktop | 1440×1000 viewport: optimization, constraints, explanations, result invalidation, sparse slots, holders and subsets. Production frontend returned five valid candidates. No horizontal document overflow measured. |
| Mobile | 390×844 and 320×780 viewport emulation: optimization returned 5 valid 8-unit boards with no horizontal overflow. At 390 pixels, comparison, Chinese/English catalog search, data-health and methodology navigation passed. These were in-app browser viewport checks, not physical devices. |
| Comparison | Saved two TFT solutions using emblem 2 then emblem 3. Both assigned the emblem to 星灯. Comparison showed 织法 → 游侠 despite the unchanged holder. Normal mobile comparison also showed champion, trait and holder differences. |
| Sparse slots | Only slot 3 populated: solve explanation said 纹章 3, holder ranking said 纹章 3 rather than 1, and locked retention displayed 保留 3 while disallowing the empty subset. |
| Empty/error states | Max cost 1 produced INFEASIBLE and zero cards; changing cost cleared that result. Intentionally stopped API: initial load showed a Chinese unavailable message and disabled solve; solve from a loaded catalog showed a clear connection error and no cards. API restarted afterward. |
| Catalog switching | Eight sequential TFT/JCC changes ended with only JCC emblem records. Obsolete-response guard is present. Artificially delayed/out-of-order responses were not injected. |
| Retention/holders | Both games: holder API returned 3 instance rankings; retained-subset API returned 8 subsets, 4 allowed with one locked instance; probabilities/EV null; actual_reforge rejected with 422. Native holder test verified explanation +0. |
| Database | Alembic migrated a new temporary SQLite database; both fixture imports produced 58 snapshot records. Temporary DB cleaned up. Automated JSON database round-trip passed. |
| Backend | `pytest -q`: **56 passed**, 1 installed Starlette/httpx TestClient deprecation warning. `ruff check app tests`: passed. |
| Frontend | `npm run typecheck`, `npm run lint`, `npm run build`: passed. All five routes generated. |
| HTTP pages | `/`, `/catalog`, `/compare`, `/data`, `/about`: HTTP 200 in dev and production smoke runs. |

## Bugs fixed

1. Stale results after changing inputs: reproduced eight-unit cards under a seven-unit selection. Request-dependent results, holder ranks and subsets now clear on changes. Configuration is disabled during requests; a new solve clears the old result. Board/objective/champion-change regressions passed in the browser.
2. Sparse input slots were renumbered after filtering empties. API compact indices now map back to original visual slots for assignments, unused emblems, holders and subsets. Slot 3 regressions passed.
3. Comparison omitted a changed emblem on an unchanged holder. It now compares and displays both emblem and holder identities; exact same-holder case verified in production browser.
4. Catalog fetches could overwrite selected-game data with an obsolete response. Added active-request cancellation guard; sequential switching verified. The delayed-response race was found by inspection, not reproduced with a network interceptor.
5. Fetch failures exposed generic browser errors. Chinese API connection errors now include the endpoint; verified with backend stopped.
6. Response validator indexed unknown champion IDs before rejecting them, causing KeyError. It now raises ValueError; regression passed.
7. Explanations incorrectly claimed new trait contribution under permitted native/duplicate equipment. Assignment text now states OR semantics; holder text calculates actual count gain. Native +0 and duplicate counting regressions passed.

## Timeout observations

Actual CP-SAT runs for both games used 0.001, 0.003, 0.01 and 0.03 seconds with 3 emblems and Top-10. This run observed UNKNOWN/no candidates at 0.001 and 0.003; one OPTIMAL first candidate then UNKNOWN enumeration at 0.01; four OPTIMAL candidates then UNKNOWN enumeration at 0.03. Counts depend on timing. **No real FEASIBLE-only result was observed**, so that runtime branch is not claimed as empirically exercised.

## Remaining limitations / not verified

- Synthetic data only. Independent fixture catalogs share the same numerical trait/cost topology; IDs, names and duplicate policies differ. Verification proves fixture isolation and correctness, not current TFT/JCC game correctness.
- Scores estimate rules-based utility, not combat strength or observed win rates. Ability, formation, real statistics and verified special mechanics remain unavailable. Unsupported special traits are rejected; unknown unlock units are unavailable.
- Holders are local alternatives with other assignments fixed. Retained subsets are not actual reforges; probabilities/EV remain unknown.
- Active catalogs are checked-in JSON. SQLite archives validated snapshots; several future domain kinds are reserved in a generic store rather than full normalized tables. PostgreSQL was not run.
- Browser verification used the Codex in-app browser and viewport emulation. No physical devices, cross-browser matrix, CI browser runner, keyboard-only accessibility audit or load/concurrency benchmark executed.
- Comparison assumes valid app-written localStorage; corrupted-storage recovery is neither implemented nor tested.
- Time limits cover search/enumeration, excluding initial model construction. Later optima are conditional on diversity exclusions. FEASIBLE-only branch not observed.
- One upstream TestClient deprecation warning remains. Dependencies were not upgraded merely to hide it.

## Reproduce

From services/api:
```sh
../../.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
```
From apps/web in another terminal:
```sh
npm run dev
```
Backend checks from services/api:
```sh
../../.venv/bin/pytest -q
../../.venv/bin/ruff check app tests
PYTHONPATH=. ../../.venv/bin/python tests/live_review.py
```
Frontend checks from apps/web:
```sh
npm run typecheck
npm run lint
npm run build
npm start
```
Stop dev before building/starting production on the same port. The live script needs both servers; it writes docs/review-api-results.json. Browser checks above were executed via in-app browser tools, not a CI browser suite.

Evidence: review-api-results.json, review-live-run.log, review-desktop.png (production TFT), review-mobile.png (development JCC). QA-owned servers stopped after review.
