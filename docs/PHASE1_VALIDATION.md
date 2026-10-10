# Phase 1 validation — 2026-10-10

Scope: the newly requested emblem-retention/meta-adaptation Phase 1 only. Implementation is on `codex/emblem-strategy-phase1`, starting from source `76df8b1730e9610456652b6de83553bd20ebc13d`. Production branch/deployments were not updated. **Phase 2 has NOT started.**

## Actual data availability

- Existing TFT 18.4 / set 18 / standard snapshot: 74 champion/form records, 36 traits, 21 emblems; enabled restricted scope remains 71/34/20. Existing assets/fixtures were not modified. Rule limitations remain those documented in DATA_COVERAGE.md.
- Authorized real S/A meta composition snapshots imported: **0**. `data/meta/sources.json` and active snapshot directory remain empty. Default requests return `MISSING_META_DATA`; invented tier lists are not silently substituted.
- Real JCC static/meta records: **0**. Existing isolated fictional JCC tests prove software behavior only. No JCC real-game acceptance claim.
- Existing observed-statistics provider registry is empty. No actual holder/composition rates or reforge probabilities were imported or fabricated.
- The supplied screenshot has no established source/version/permission contract and was **not extracted, OCR'd or imported**. Screenshot/community extraction belongs outside this milestone.

Source inspection used the public references [MetaTFT](https://www.metatft.com/), [DataTFT compositions](https://www.datatft.com/comps/tier/) and [JCC DataTFT](https://jcc.datatft.com/). The first/JCC returned JavaScript shells through the web tool. DataTFT exposed tier-navigation content, “Content Licensing” contact and a rights notice; no licensed complete version-matched export was supplied. No internal API, restricted endpoint, bulk data copy or scraper was implemented. These observations do not establish that licensing/export is impossible; they establish that this project currently has none. Real static sources remain the existing pinned Riot/CommunityDragon snapshots documented in REAL_DATA_SOURCES.md.

## Executed tests

Pre-change baseline, from `services/api`: `../../.venv/bin/pytest -q` → **333 passed**, 47.52s, one upstream Starlette/httpx deprecation warning.

Final executed results:

- `cd services/api && ../../.venv/bin/pytest -q` → **392 passed**, 46.71s, one upstream Starlette/httpx warning. All original 333 tests remain; 59 new Phase 1 cases pass.
- `../../.venv/bin/pytest -q tests/test_emblem_strategy.py` → **59 passed**, 2.28s in the final targeted run.
- `../../.venv/bin/ruff check app tests ../../scripts/verify_phase1.py` → passed.
- `cd apps/web && npm run typecheck && npm run lint && npm run build` → passed.
- `node --test tests/lux-policy.test.mjs` from apps/web → **5 passed**.
- `../../.venv/bin/python ../../scripts/verify_phase1.py` → actual CSV and JSON CLI imports, equivalent normalized records, both HTTP endpoints and independent result checks passed. Retention resolved all 24 cells; meta/adapt resolved all three requested neighborhoods.

Intermediate full run was 386 passed before six further cases were added. Initial targeted execution exposed a real CSV normalization bug (`board_size` remained a string for a Literal field), which was fixed by explicit integer parsing. An initial real-record test used display-name-derived IDs; it was corrected to the existing canonical `DA_Draven18`, `DA_18_MasterYi_AD` and `DA_KogMaw18_AD` IDs without modifying game records. No failed test was removed or skipped. Partial lexicographic proof handling, weak-statistics labeling and original-file linkage have dedicated regression checks.

Covered by the new tests:

- All seven nonempty/eight-with-baseline combinations, 0/1/2/3 inputs, duplicate-instance identity and original index mapping, instance locks.
- 0/1/2 exact replacements, core carry/tank preservation and explicit relaxation, added-unit locks/base-unit exclusions, population-slot accounting, unused retained emblems without mutation of legacy policy.
- Legal holders, source reservations/caller occupied slots, duplicate equipment, native/emblem nonduplication and native double weights, secondary source preferences.
- Every ranking profile versus an independent exhaustive small reference (15 cases), returned-pool Pareto tradeoffs, budget exhaustion and conditional proof status.
- Scope, cross-game/canonical references, missing metadata, S/A filter, manual opt-in, unsupported rules/unlocks, infeasibility, null reforge probabilities/EV, strict request bounds.
- CSV/JSON normalization, original-to-normalized linkage, idempotent imports, authorization revocation, changed permissions/catalogs, raw/snapshot corruption and ID conflicts.
- Fictional independent JCC import/API flow and no TFT contamination; real TFT static-board holder/population/trait recount; read-only exact-context statistical evidence and refusal to upgrade unknown quality.
- New endpoints return 403 under the public preview profile. Existing optimizer, importer, statistics, reforge, catalog activation and public-mode tests remain in the full suite.

## Actual local HTTP verification

`cd services/api && ../../.venv/bin/python ../../scripts/verify_phase1.py` starts a real temporary loopback Uvicorn backend and invokes the two new endpoints with actual CP-SAT. It imports an **original untiered manual scenario**, using temporary local-only permission records, and cleans up its temporary server/snapshots. The default repository registry is not populated.

Real-unit baseline: Ahri, Alune, Shen, Master Yi AD, Sett, Ornn, Draven, Kog'Maw AD; eight population. Draven/Ornn are protected cores. Draven reserves three ordinary item slots and Ornn two. All Lux forms are excluded. Hand-checked baseline positive native counts are asserted literally by the verification script, then every result is independently recounted from canonical static records. No production evaluator or score function is used for that recount.

Emblem A = Brawler, B = Blossom, C = Elderwood. Actual retention example with zero replacements:

| Retained | Equipped | Active traits | Breakpoint utility | Status |
|---|---:|---:|---:|---|
| ABC | 3 | 8 | 8 | OPTIMAL |
| AB | 2 | 8 | 8 | OPTIMAL |
| AC | 2 | 8 | 8 | OPTIMAL |
| BC | 2 | 7 | 7 | OPTIMAL |
| A | 1 | 8 | 8 | OPTIMAL |
| B | 1 | 7 | 7 | OPTIMAL |
| C | 1 | 7 | 7 | OPTIMAL |
| Empty | 0 | 7 | 7 | OPTIMAL |

All **24 requested cells** (eight subsets × three neighborhoods) were executed and resolved OPTIMAL in the recorded run. The returned frontier contains the three ABC alternatives with 0/1/2 replacements: active traits and ordinal utility 8/9/10 respectively. This illustrates the tradeoff between replacement count and structural utility, **not a ranking of actual combat strength or reforge value**.

Actual adaptation example (same manual board, ABC, one replacement): replace Ahri (`DA_18_Ahri`) with LeBlanc (`DA_18_LeBlanc`), preserve Draven/Ornn. Actual holders in the recorded run: Blossom → Alune, Elderwood → Alune, Brawler → Master Yi AD. The three instances are equipped legally within reservations; active traits go from seven native baseline traits to nine. Tier and win rate stay null. Equivalent assignments may change across OR-Tools/platform versions; legality and objective vectors, not these incidental ties, are the contract.

Evidence: `evidence/phase1_local_http.json` records request payloads, per-cell statuses, actual assignment annotations, changes and scores. It is a manual scenario, **not independently licensed S/A meta data**. The executable script also exercises the actual CSV and JSON CLI import paths and compares normalized records.

After verification, restarted the ordinary local backend on port 8000. Frontend:3000 and backend health returned HTTP 200; OpenAPI lists both new endpoints. An actual HTTP call against the default empty meta registry returned 200 / `MISSING_META_DATA` with eight strategy rows, and inspection confirmed zero default source authorizations and zero imported snapshots. Temporary example data was not left active.

## Files and boundaries

- `services/api/app/meta/{schemas,providers,repository,importer,engine,evidence}.py`: source contract, offline import, immutable/read-validated snapshots, strategy orchestration and evidence annotation.
- `services/api/app/optimizer/adaptation.py` and `optimizer/solver.py`: optional local-neighborhood and lexicographic CP-SAT controls. Ordinary solve path preserved.
- `services/api/app/api/meta.py`, `app/main.py`: additive local endpoints; existing public allowlist continues to deny them.
- `services/api/tests/test_emblem_strategy.py`, `scripts/verify_phase1.py`: isolated algorithm/integration tests and executable real-static HTTP verification.
- `data/meta/` is an empty operator registry/store; `data/examples/meta/` contains untiered JSON/CSV/request examples. Docker packaging includes this new empty directory for future reviewed releases.
- Required three Phase 1 documents, README and ARCHITECTURE updated. Frontend files, static catalogs and existing fixture files unchanged.

## Limitations and deployment

**NOT_DEPLOYED** for this milestone. No push/merge into the production source/static branches and no Render deployment were performed. No new production UI or browser acceptance test is claimed. API-level TestClient plus actual localhost HTTP were executed; frontend was typechecked/linted/built and existing Lux policy tests rerun. No physical-device, load, battle-strength or real-meta-provider acceptance test was performed. Local Docker build was not executed.

Missing evidence: authorized version-matched S/A base rosters/roles/equipment and tier attribution; approved real JCC static rules; optional qualified exact-context statistics. Owner/provider review remains necessary before populating the source registry. External provider API integration, screenshot extraction, community extraction, UI redesign and Phase 2 remain out of scope.

The frontier is conditional and incomplete over all legal boards; source search is capped; unsupported conditional mechanics and extra population-bonus units outside fixed-cardinality replacement neighborhoods are not searched. Missing item/star/augment/formation/availability context is not guessed. The new APIs do not implement real reforging or EV. These are deliberate explicit limits, not passing tests for unavailable data.
