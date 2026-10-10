# JCC follow-up validation — 2026-10-10

**JCC status: BLOCKED.** Real JCC set/patch/mode selected: none. Genuine imported counts: 0 champions, 0 traits, 0 emblems. No claim of “JCC REAL STATIC OPTIMIZER READY” is made. See JCC_SOURCE_AUDIT.md for source/permission findings and JCC_RULESET_COVERAGE.md for exact missing facts.

## Baseline and changes

Confirmed source branch `codex/friend-preview` at `ade8717`; Render live revision `43f448d0fee19c8de3d701aa593acc04aadde822`. Created `codex/jcc-catalog-activation`. Pre-change suite: 294 passed. Actual production health, catalog discovery and real TFT three-emblem solve passed before editing (jcc_prechange_baseline.json).

Implemented extended manual fields; strict review-to-activation CLI; immutable normalized catalog/input/review/validation/raw-source artifacts; atomic version registry and audited rollback; per-artifact failure isolation; API discovery and mode metadata; data-driven frontend gating. Existing solver, statistics and reforge contracts retained. Public import/mutation/reforge remain closed. No real JCC data or unknown game rules fabricated.

User-requested TFT Lux scenarios are included: default without Lux, chosen-origin forced Lux, two separate actual solves with per-scenario statuses and saved comparison. They do not model draw probabilities or rename a heuristic score as observed win rate.

## Automated execution

- From `services/api`: `../../.venv/bin/pytest -q` → **333 passed**, 47.90s; one upstream Starlette/httpx deprecation warning.
- `../../.venv/bin/ruff check app tests` → passed.
- From `apps/web`: `npm run typecheck`, `npm run lint`, `npm run build` → passed; public same-origin static export also passed.
- From repository root: `node --test apps/web/tests/lux-policy.test.mjs` → **5 passed** (uses installed TypeScript and actual reviewed TFT catalog).
- A preliminary full run invoked from repository root passed 328 and failed two existing Alembic tests because their config path requires `services/api` as cwd. Re-executed from the documented cwd: all 330 passed. No test was removed or skipped to hide that failure.

35 new activation tests use **explicitly fictional temporary records**, proving software behavior only: import provenance/digests, legacy CSV, bilingual aliases, source permission and independent-review requirements, version/mode, completeness, manual count cases, arbitrary-flag rejection, stale promotion, corruption/missing originals/approvals/reports, independent TFT/JCC discovery, actual three-emblem CP-SAT and holder API, locks/exclusions, population, duplicates, native non-duplication, unsupported mechanics, five-objective exhaustive reference agreement, and rollback. No temporary test dataset was installed in the repository registry.

Four new real TFT tests each solve with and without Lux at population 7/8/9/10, and independently recount native weights/emblem contributions. These establish TFT behavior, not real JCC validity. Original statistics/reforge tests remain in the full suite.

## Actual local browser checks

Browser control recovered this turn. Used the supported browser Playwright interface against the real production build at localhost:3000 and backend:8000:

- Loaded real TFT 18.4; default Lux policy was without Lux.
- Selected Brawler/Blossom/Elderwood and Blossom Lux, clicked paired solve. Both responses rendered FEASIBLE; first board excluded Lux, second contained the requested five-cost Blossom Lux; three assignments rendered in each. Real HTTP CP-SAT, no mock.
- Saved both cards and navigated to comparison; saw board, trait and assignment differences with scenario labels.
- Desktop 1280px: scrollWidth 1280. iPhone-sized 390px: scrollWidth 390 and both cards present. Android-sized 412px: scrollWidth 412. Saved desktop and mobile screenshots; examined mobile card layout.
- No captured console error at local comparison inspection.
- Switched to JCC: no approved version, solve disabled. Switched back to TFT: emblem selections cleared and default Lux policy present.

Evidence: `evidence/jcc_local_browser.json`, `evidence/lux_compare_desktop.png`, `evidence/lux_compare_mobile.png`. This is viewport emulation, not physical-device certification.

## Not established

Genuine JCC three-emblem, actual-JCC expected counts, legal-holder correctness, genuine roster completeness and real JCC browser E2E are **BLOCKED**, since authorized real records and independent reviews are unavailable. Fictional test cases do not establish these conditions. No statistical rates, production reforge probabilities, OCR or game-client integration were added.

Owner next action: obtain a versioned, redistribution-authorized JCC static export (DataTFT content-authorization contact or another legitimate provider), including the missing rules listed in JCC_RULESET_COVERAGE.md; supply source/version/permission evidence and arrange independent review. Then run the implemented import/check/activate workflow, genuine-data integration/browser tests, commit artifacts and deploy. Do not remove the JCC unavailable warning merely to appear finished.

## Public release verification — executed 2026-10-10

Status: software workflow and Lux changes **DEPLOYED**, real JCC **BLOCKED**, TFT fixed-version scope **RESTRICTED**. Render reports deployment `dep-db5376942hec73fib810` live at source commit `b22dd3ac58a6b5297c87122fc80c078ae3a6391f`; GitHub Pages reports artifact `9c3082fdcc42f034e7a227baf39edfdac9f27f4a` built.

Actual HTTPS checks passed on https://kiritovilelouch.github.io/emblemlab/ and https://emblemlab.onrender.com/: six pages and fourteen referenced assets per site; bundled JavaScript contains no localhost API URL. The current backend returns the new empty `catalog_activation_issues` list, real TFT 18.4 catalog 74/36/21, and no approved JCC versions even with `include_synthetic=true`.

Two actual Render CP-SAT POST requests used three genuine TFT emblems (Brawler, Blossom, Elderwood), population 8. Both returned **FEASIBLE**, not OPTIMAL. The first banned all Lux forms; the second locked Blossom Lux and banned alternatives. Each returned the appropriate board. Independently recounted each trait from native weights and emblem assignments, checked population and complete assignments, and ran RuleEvaluator legality checks. GitHub-origin POST CORS and OPTIONS preflight passed. Public invalid/cross-game/synthetic requests returned 422; imports/admin/reforge remained 403; public page HEAD was 200 and private API HEAD 403.

Evidence: `evidence/jcc_release_public_http.json` contains actual requests, responses and statuses. This HTTP suite does not prove public frontend click-through. Existing Pages-tab reload and DOM inspection and a fresh same-browser Render-tab attempt timed out. **Public browser click/visual acceptance was not completed**. The local browser results above remain the only executed visual/mobile acceptance. No true-device, friend-device or load testing was performed. No real JCC acceptance test was possible.

After static publication, restored a standard local production build, restarted frontend/backend, and checked localhost:3000, backend health and registry health returned HTTP 200 with no activation issues. No approved JCC artifact was installed. Activation CLI uses POSIX file locking and was tested locally on macOS; its module loads in the Linux deployment. Linux promotion locking and Windows operator execution have not been separately tested.
