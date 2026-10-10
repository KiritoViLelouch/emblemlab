# Phase 2A — executed validation report

Executed locally on 2026-10-10. This report describes actual runs, not planned tests. Original application, optimizer, importer, statistics boundary and synthetic reforge tests were retained.

## Imported target and readiness

TFT international, **Set 18 Enchanted Wilds / gameplay patch 18.4 / standard**. Fixed Riot resources **16.20.1**, CommunityDragon **16.20**, build `16.20.8248524+branch.releases-16-20.content.release`.

74 canonical champion records (65 champion families including Lux variants), 36 traits, 21 emblem records. Available in the bounded count profile: 71 champions, 34 traits, 20 emblems. 17 non-shop entities excluded. All required official shop IDs are present; all normalized entity references and patch scopes validate. Raw source SHA-256 digests are checked during import. Canonical IDs and actual official en_US/zh_CN names are retained, including irregular IDs and duplicate display names.

Catalog **PARTIALLY_VERIFIED**. Rule review: **8 VERIFIED, 3 UNVERIFIED, 3 UNSUPPORTED**; 0 synthetic real-catalog rules. VERIFIED applies to the declared static-count profile, not the entire game. Essential profile rules must have evidence and be VERIFIED; missing reviews, unverified enabled entities or unsupported dependencies disable optimization. Native/duplicate equipment restrictions remain conservative search restrictions with incomplete independent legal evidence.

## Commands actually executed

From `services/api`:

| Command | Result |
|---|---|
| `../../.venv/bin/python -m app.importers.tft_static ../../data/manifests/tft_set18_18_4.json --output ../../data/catalogs/tft/set18_18_4.json` | Generated local catalog; valid=true; restricted optimization enabled |
| `../../.venv/bin/pytest -q` | **274 passed**, one upstream Starlette/httpx deprecation warning, 23.99 seconds on final run |
| `../../.venv/bin/ruff check app tests` | All checks passed |

From `apps/web`:

| Command | Result |
|---|---|
| `npm run typecheck` | Passed |
| `npm run lint` | Passed |
| `npm run build` | Passed; production Next.js build generated all nine routes |
| `npm start` | Started production preview at 127.0.0.1:3000 |

From repository root:

| Command | Result |
|---|---|
| `.venv/bin/python tools/tft_snapshots.py icons` | 122 distinct icon URLs checked with HTTP HEAD; all 200 and image content types |
| `.venv/bin/python tools/live_real_data.py` | 10 actual HTTP checks passed against running backend; evidence saved |
| `.venv/bin/ruff check --config services/api/pyproject.toml tools` | All checks passed |

Backend started with `../../.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000` from `services/api`. Both production frontend and backend were restarted after relevant application changes. The optional new snapshot re-download command was not re-executed; original source downloads succeeded and every cached file was subsequently hash-checked by the importer.

The existing 201-test suite passed unchanged. Phase 2A adds 73 tests (including parameterized cases) for real static import, solver constraints, independent enumeration, validation, manual drafts and reviewed version boundaries.

## Real-data solver checks

| Case | Actual execution and result |
|---|---|
| One real emblem | Brawler emblem: CP-SAT returned a composition with legal non-native holder; mandatory-equipment test passed |
| Three distinct real emblems | Brawler, Blossom, Elderwood: all three assigned in mandatory-equipment test; UI also returned all three assignments |
| Two identical real emblems | Two Brawler instances assigned to different holders; duplicate-on-one-holder limit respected |
| Native-trait holder | Kobuko + Brawler emblem rejected by conservative equipment policy; direct counting still contributes only once |
| Breakpoints | Blossom native counts 1..7 and Lux contribution reaching 9 independently checked; Coven 3/4/5/7, Elderwood 3/5/7/9/11, Riftbeast 3/5/7/10 matched documented static breakpoints |
| Board constraints | Real solves at 7/8/9/10 population with locked Elder Dragon: exactly the requested occupied population, one fewer champion record due to its 2-slot cost |
| Illegal/unsupported boards | Multiple Lux forms, Lunar+Solar coexistence, Rival units, and Riftbeast count >=10 infeasible under the explicit bounded profile |
| Version isolation | Wrong game/ruleset, fixture emblem in real catalog, and disabled Augment emblem rejected; unaudited importer set/patch/mutator/resource/mode changes rejected |
| Missing/invalid data | Duplicate normalized and source champion IDs, absent traits/champions, bad emblem associations, bad thresholds, mixed provenance, invalid/version-mismatched icons, missing rule evidence/reviews and enabled unsupported data blocked |
| Brute-force comparison | **15 independently enumerated restricted real-roster cases**, across all 5 objectives and 0/1/2 identical emblems, exactly matched CP-SAT OPTIMAL scores. Includes Lux weights and Elder Dragon population costs. Reference does not call production RuleEvaluator or score(). An additional finite synthetic check covers optional capacity bonuses |

Documentation cross-checks use Riot's [Set 18 overview](https://teamfighttactics.leagueoflegends.com/en-sg/news/game-updates/enchanted-wilds-overview/) and the cached bilingual static snapshots. The chosen-origin double contribution, Elder Dragon's two slots/two Riftbeast contributions, and origin thresholds are independently asserted rather than inferred from solver output.

Full real-roster HTTP solves used 3-second limits and returned **FEASIBLE**, not proven global optima. Recorded rule scores: one Brawler 130105; three distinct 120097; two Brawlers 140116. These are heuristic objective values, not win rates or comparable optimal guarantees across timeout-limited requests. The desktop UI used its 5-second total budget and returned one FEASIBLE candidate (120105, 12 active traits), with enumeration_status UNKNOWN. Top 5 was requested but the remaining budget did not produce five candidates; this is displayed honestly.

## Running UI checks

Performed through the actual in-app browser against the production frontend:

- Default selection loaded real TFT Set 18/18.4, PARTIALLY_VERIFIED badge, source, last review date, available-champion coverage, and unsupported mechanics.
- Selected Brawler/Blossom/Elderwood and clicked optimize; saw a real returned candidate and three holder labels.
- Desktop width 1280: document scrollWidth 1280. Mobile width 390: scrollWidth 390; result remained present with a single-column workspace. No horizontal overflow in checked states.
- JCC with development mode off showed no audited real version and disabled optimization.
- Opted into development data and selected EXAMPLE-1.0: visible SYNTHETIC banner and fixture names; selected a real emblem and locked Akali, then switched patch and observed empty emblem slots and zero locked units (see version_reset.json).
- Uploaded a clearly labeled **test-only synthetic CSV** through the manual review UI; displayed valid draft with `activated=false`, `optimization_enabled=false`, file digest and reviewer/evidence. No test entity was installed into active catalogs. Backend tests additionally exercised XLSX and invalid manual rows. A real licensed JCC workbook was not available and was not claimed tested.
- Initial browser pass saw some transient remote image failures despite successful HEAD checks. Added text fallback; final screenshot shows loaded first-party portraits and final DOM inspection found zero broken images. Remote asset availability still depends on network/CDN access; all-device rendering was not tested.

Evidence: `docs/evidence/real_http.json`, `real_ui.json`, `real_desktop.jpg`, `real_mobile.jpg`, `synthetic_opt_in.jpg`, `manual_review.jpg`, `version_reset.json`; HTTP icon audit in `data/manifests/tft_set18_icons.json`.

## Fixed issues and recorded discrepancies

1. Synthetic-only catalog loading and hard-coded fixture selectors replaced with additive real catalog loading and explicit development opt-in. Legacy API catalog defaults and fixture IDs retained.
2. Original boolean-only contribution and one-unit-one-slot model corrected for verified native double counts, physical population cost and exclusive forms; independent post-validation agrees with CP-SAT.
3. Unsupported Rival/Eclipse data cannot enter monotonic trait scoring; unverified Riftbeast capstone and Lunar/Solar interaction are explicitly blocked.
4. Source `Set10` display-name anomaly resolved via explicit number/mutator plus Riot documentation. Empty emblem association fields replaced by a visible reviewed ID/official-label mapping, never an icon guess. Flora Fatalis Augment variant remains disabled.
5. Real optimization now rejects missing readiness, missing essential review/evidence, unverified enabled entities and unsupported dependencies. Post-validation rejects unknown assignment IDs before deriving traits, avoiding an unchecked lookup error.
6. Version-dependent selections are cleared on game/patch/ruleset changes; unavailable units/emblems are disabled in selectors. Real TFT reforge rules are not invented or enabled.
7. Snapshot `TeamSize=2` at Riftbeast 10 conflicts with overview's +1. Recorded as UNVERIFIED and blocked. Native/duplicate equipment exception law remains independently unverified and conservatively restricted.
8. Additive catalog schema fields changed catalog serialization. Synthetic reforge fixture fingerprints were regenerated; existing archived community/statistics records still enforce stale-catalog fingerprint protection and may need reimport.

## Remaining blockers / not executed

- JCC: no authorized complete real dataset or independent version/mode rules configured. Manual draft workflow is available; **full JCC support is not claimed**. No protected endpoint was scraped or bypassed. Tencent reference retrieval timed out; DataTFT permission was not granted.
- TFT: unresolved capstone/conditional/evolving rules and equipment exceptions listed in DATA_COVERAGE.md; all such branches are blocked or excluded. Future patches/modes need a new reviewed adapter profile. Gameplay-to-resource mapping uses contemporaneous Riot release documentation and pinned resource build, not an embedded server attestation of every TFT hotfix. Full hotfix parity and live-client behavior were not tested.
- No combat simulation, star/economy/augmentation history, plant positioning, exhaustive summon interactions, acquisition probability, win-rate dataset or real reforge EV was implemented or tested.
- Only 1280px desktop and 390px mobile layouts were checked; no physical mobile device or all-browser certification. Icons are remote references, not a fully offline art bundle.
- No production deployment, PostgreSQL run, game-client automation or externally authorized JCC provider integration was performed. The backend remains a loopback development service; catalog JSON remains authoritative.
