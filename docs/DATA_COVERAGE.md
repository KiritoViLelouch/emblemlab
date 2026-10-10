# Phase 2A data coverage

Fixed TFT snapshot: Set 18 / 18.4 / standard; resources 16.20.1. Catalog state: **PARTIALLY_VERIFIED**, restricted precombat trait-count profile. Complete game simulation is not supported.

| Entity | Imported | Enabled in count profile | Detail |
|---|---:|---:|---|
| Champion canonical records | 74 | 71 | 65 champion families; includes unselected Lux plus 9 origin forms. Base Lux, Kha'Zix and Rengar disabled |
| Traits | 36 | 34 | Rival and Eclipse retained for reference, disabled for optimization |
| Emblem canonical records | 21 | 20 | Flora Fatalis has two IDs with the same label; Augment variant disabled pending acquisition review |
| Distinct official icon URLs | 122 | 122 HTTP checks passed | Some canonical variants share an image |
| Rules reviewed | 14 | 8 VERIFIED in bounded profile | 3 UNVERIFIED, 3 UNSUPPORTED; no SYNTHETIC rules in real catalog |

All 74 required standard shop IDs are present (100% roster import completeness); 71/74 = 95.95% are available under the restricted profile. The UI reports **available champion coverage**, not full rules or combat completeness. 17 selected-set non-shop/PvE/armory entries were excluded with reasons. Other sets/mutators are excluded before joining entities. All records carry game, gameplay patch, set, mode, source, import date and verification. Raw synthetic fixtures remain unchanged and available through explicit development selectors/API IDs.

## Implemented mechanics and score meaning

- Canonical bilingual IDs/names, costs, native traits, reviewed emblem association, unique native/emblem contribution, physical item capacity.
- Explicit native contribution weight: chosen Lux origin contributes 2 total; Avatar contributes 1. A single Lux form may be selected; the base with no chosen origin is disabled. This exclusivity is a conservative modeled board restriction based on the documented shop transformation.
- Elder Dragon uses 2 population slots and contributes 2 total Riftbeast counts. Board size means occupied population, so an 8-population board containing it has 7 champion records.
- Trait activation counts come from selected-set effect `minUnits`, cross-checked in both locales. Supported traits use ordinal utility per breakpoint (1,2,...), never invented combat strength, win rate or placement.
- Maximum-active-trait optimization counts singleton unique traits too. This can favor expensive unique-trait units; it is a combinatorial objective, not a recommended meta composition. The old five objective formulas are preserved.

## Deliberately blocked or unverified

1. **Rival**: overlapping/nonmonotonic effects and permanently acquired traits depend on takedown history. Trait plus Kha'Zix/Rengar are disabled.
2. **Eclipse**: snapshot `minUnits` is null and activation predicate is missing. Not scored; any Lunar/Solar coexistence is conservatively forbidden, even when the game might allow some such boards.
3. **Riftbeast 10**: pre-release official overview says +1 team slot, current static effect says `TeamSize=2`. Reject count >=10 rather than select either as verified truth. Counts/tiers below 10 remain usable.
4. **Flora Fatalis Augment emblem**: association label is known, but acquisition/legal availability is not independently established. Reference-only, unavailable.
5. **Equipment exceptions**: source item `associatedTraits`, `incompatibleTraits`, and related flags are incomplete for these new records. Explicit reviewed emblem-to-trait mappings use exact official English and pinned Chinese labels. Native-holder and repeated-same-emblem equipment remain conservative search restrictions, not independently verified exhaustive equipment law. Duplicate instances on different holders are modeled; acquisition probabilities/pools are not.
6. Wisps, augments, evolving traits, board history, bench/shop contents, stars, planting/positioning, combat summons, Blackthorn sacrifice aftermath, equipment combat effects and combat/economy value are not modeled. The profile concerns precombat fielded counts only. Do not use output as battle simulation or win-rate prediction.

## Data discrepancies handled

- Selected upstream set name incorrectly reads `Set10` despite number 18/mutator TFTSet18; resolved against explicit Riot Set 18 documentation, never used as identity.
- New emblem `associatedTraits` is empty and descriptions are null. Import uses a pinned, visible review manifest and fails if official names/IDs change. No inference from an icon, old set ID or untranslated string.
- Null Eclipse threshold and overlapping Rival thresholds cannot enter the ordinary monotonic evaluator.
- Gameplay patch 18.4 and resource version 16.20.1 are distinct; both are stored, and no automatic assumption of hotfix equivalence is made.

## Verification states and gating

VERIFIED means the stated static field/count rule has evidence within the declared profile; PARTIALLY_VERIFIED means some data is usable but restrictions remain; UNVERIFIED means evidence is missing; SYNTHETIC means development-only fictional inputs; UNSUPPORTED means the evaluator cannot represent the rule. Storage keeps legacy lowercase values for API compatibility, while validation/UI expose uppercase states.

An unverified essential rule, unverified enabled entity, unsupported dependency, bad relationship or invalid/version-mismatched icon disables a real catalog. Out-of-profile unknown mechanics are blocked by explicit restrictions rather than silently scored. Legacy API defaults remain synthetic to preserve consumers; the frontend explicitly requests `include_synthetic=false`, defaults to the real TFT catalog, and provides a development opt-in. JCC's real version list is empty and its optimization controls are disabled.

JCC: **no real records imported, not fully supported**. Manual CSV/XLSX validation and draft download work; rule/roster/license review is still required. Community recommendations and statistical observations remain separate stores, unchanged by this milestone. No statistical or reforge EV work was added.

## JCC activation follow-up (2026-10-10)

JCC remains **BLOCKED: 0 real champions / 0 traits / 0 emblems / 0 approved rulesets**. The reusable import → independent review → immutable artifact → atomic registry → API → frontend integration is implemented. Public mode discovers any successfully approved real JCC registry entry; there is no longer a TFT-only hardcode. No JCC game facts have been copied from TFT or from provider tables. See [source audit](JCC_SOURCE_AUDIT.md), [coverage](JCC_RULESET_COVERAGE.md), [operator workflow](JCC_IMPORT_GUIDE.md) and [actual validation](JCC_VALIDATION_REPORT.md).

TFT catalog facts/counts are unchanged. UI now defaults to excluding Lux and offers a fixed-origin with/without comparison. Lux remains a five-cost unit; her origin count applies only when that specific form is assumed available. FEASIBLE still means a valid timeout-limited candidate, not proven optimal or reliably obtainable.
