# Phase 1: emblem strategy engine

This milestone implements **only the newly requested Phase 1**. The repository's older community/statistics/reforge phases remain intact; no new Phase 2 work, OCR, screenshot extraction, redesign or production deployment was performed.

Software scope: internal/API-level retained-emblem and local composition adaptation. **Real S/A meta coverage is BLOCKED by missing authorized exports.** The default meta source registry and snapshot directory are empty. Real TFT static data remains the restricted fixed 18.4 profile; real JCC data remains unavailable. A hand-picked real-unit example is explicitly `manual_scenario`, with no tier or win rate, and requires opt-in. Fictional unit fixtures never establish real meta validity.

## Interfaces

- `POST /api/v1/emblem-strategy/analyze`: all nonempty instance subsets; optional empty baseline. For three inputs: ABC, AB, AC, BC, A, B, C, optionally empty. Duplicate IDs remain separate indices. `locked_emblem_indices` prevents discarding specified instances; it does **not** require equipping them.
- `POST /api/v1/meta/adapt`: only the supplied retained inventory, searching the same 0/1/2-replacement neighborhoods.
- Offline `python -m app.meta.importer`: authorized CSV/JSON normalization and immutable snapshot import. There is no public import/activation endpoint.

Both endpoints share `scope`, `emblem_ids` (0–3), `board_size` (7/8/9/10), existing `constraints`, optional `composition_keys`, `replacement_counts`, `ranking`, `preserve_core`, `occupied_item_slots`, and search budgets. `include_manual_scenarios` and `include_synthetic` are false by default. Strategy adds `include_empty_baseline` (false) and instance locks. Unknown fields, including probabilities, are rejected.

Search is capped at five scoped base boards, three neighborhoods and eight subsets. Default total budget is 15 seconds; allowed maximum is 60. Default per-case budget is one second; maximum is five. Every requested cell is reported even when budget prevents executing it. `NOT_RUN_BUDGET`/`UNKNOWN` are not infeasibility proofs. Only S/A source classifications are eligible in ordinary `meta` mode. A B/C source record is archived but excluded from search. Omitted keys beyond five are explicitly returned; callers can select up to five exact `provider_id:composition_id` keys.

## Response contract

The response contains source records/versions/permissions, static-game data scope, all retained strategies, per-source/per-replacement solver status, ranked candidates and a frontier over **returned candidates only**. Each candidate includes:

- Original-instance retained, unused and retained-but-unused lists. `proposed_to_reforge_instances` is a hypothetical list of unused instances, **not an action or a prediction**. `reforge_action`, probabilities and EV are null.
- Source board, attributed original tier, original emblem assignments and native/baseline traits; adapted champion records and exact added/removed IDs.
- Actual optimized assignments, legal/structural/statistical annotations, core losses, item reservations, full traits, activated traits and before/after breakpoint changes.
- Structural metric vector, ranking explanation, conditional CP-SAT status and each lexicographic proof stage. No aggregate weighted combat score is created. `objective_value`/`best_bound` refer only to the last completed stage, as labeled by `objective_value_kind`.
- `adapted_tier` and `adapted_win_rate` stay null. Explicit exact-context observed records may appear separately, without transferring original-board rates or pooling providers.

`MISSING_META_DATA` is a normal, explicit empty result. A requested unknown/unauthorized/version-mismatched composition key returns 404. Invalid scope/rules/constraints return 422. Missing or malformed operator registry returns 503; unusable individual artifacts are omitted with source issues. The existing `PUBLIC_DEMO` allowlist returns 403 for both new routes. They have not been deployed or added to the production UI.

## Holder accuracy

Existing RuleEvaluator legality, unique native/emblem contribution, duplicate-equipment limits and game/version restrictions are reused. Added occupied-slot constraints reserve ordinary items before assigning emblems. Source `non_emblem_item_slots` and caller `occupied_item_slots` are total ordinary-item counts; merge takes the maximum, not the sum. The caller cannot erase source reservations by supplying a smaller count. Unspecified equipment is assumed empty; stars, formation and item effects are not modeled.

`legal` means all modeled assignment restrictions passed. `structurally_useful` means removing that instance reduces an activated trait or breakpoint utility; subthreshold contribution is reported separately and does not automatically get this label. A source recommendation is an opinion, retained with its citation. It is a final tiebreak only after every primary structural objective is proven equal. It applies to changed boards only when the source explicitly declares `applies_to_adaptations=true`.

Statistics are optional references to the **existing authorized statistics store**, requested by `statistics_record_ids`. The reader rechecks permission, catalog fingerprint and exact scope. Matching requires exact champion set and emblem/holder multiset, not a unit subset or the original meta board. Records with unknown/zero sample or no outcome metric do not qualify. `statistically_supported` additionally requires provider-declared independence, verified deduplication and the existing count-based Wilson confidence calculation. Weak observations may be visible without upgrading the label. This is conditional observational support, **not causal evidence or an optimal-holder claim**; quality/confidence remain attached. Normal item/star/augment context is not present in that statistics contract and is not inferred. No observations are supplied by this milestone.

## Authorized export workflow

1. Obtain permission covering import, storage, display and adaptation for the exact game/set/patch/mode. Keep the actual permission evidence. Public access, a screenshot, or a code repository license does not authorize third-party tier/statistics reuse.
2. Review a separate operator registry (`META_SOURCES_FILE`, default `data/meta/sources.json`). Its strict `Authorization` fields are `provider_id`, `source_kind` (`first_party`, `licensed_provider`, `manual_original`), `attribution`, `license_id`, `permission_reference`, `permission_sha256`, `reviewed_by`, `reviewed_at`, `valid_from`, `valid_until`, `enabled`, `scopes`, `data_kinds`, `permitted_uses`. Dates are timezone-aware. Required uses are `import`, `store`, `display`, `adapt`. The import file cannot grant itself permission. This is operator attestation under filesystem/Git access, not cryptographic proof of legal rights or source-tier accuracy.
3. Prepare JSON `Export` (schema below) or CSV plus JSON batch metadata. Canonical IDs only; no fuzzy name matching, extraction or web requests.
4. Validate and import offline. Original board legality, population, equipment, declared cores, complete baseline assignments and source preferences are checked before a snapshot is written.
5. Commit reviewed artifacts/registry through normal review if later release is authorized. Runtime rereads permissions and refuses changed catalogs, changed authorizations, corrupt/missing originals and conflicting composition IDs. Changed records require a new source record ID; no implicit latest-version selection. Old artifacts can be moved out of the configured directory under operator review; this importer does not mutate game-catalog activation.

From `services/api`, with a **real reviewed registry** configured:

```sh
META_SOURCES_FILE=/absolute/path/reviewed-sources.json \
META_CATALOG_DIR=/absolute/path/meta-catalogs \
../../.venv/bin/python -m app.meta.importer /absolute/path/export.json

META_SOURCES_FILE=/absolute/path/reviewed-sources.json \
META_CATALOG_DIR=/absolute/path/meta-catalogs \
../../.venv/bin/python -m app.meta.importer /absolute/path/export.csv \
  --metadata /absolute/path/export.metadata.json
```

Run the backend with those same environment variables. Input is limited to 2 MiB and 100 compositions per export. No new dependency or database migration is required. Provider protocol `MetaCompositionProvider.normalize` produces the common `Export`; JSON/CSV adapters ship, remote adapters do not.

JSON batch fields: `schema_version:1`, `provider_id`, `source_version`, exact `scope` (`game_id`, `ruleset_id`, `patch`, `set_id`, `mode`), `data_kind`, `compositions`.

Composition fields: unique `id`, `name`, unique `champion_ids`, `board_size`, `core_carry_ids`, `core_tank_ids`, `non_emblem_item_slots`, `baseline_emblem_ids`, `baseline_assignments`, `source_tier`, `tier_citation`, `reviewed_at`, `holder_preferences`. Meta records require tier/citation and explicitly declared carries/tanks. `manual_scenario` records forbid a tier. `synthetic` records require a synthetic static catalog and explicit API opt-in. Real records cannot use fixture catalogs. Preference fields are `emblem_id`, `champion_id`, `citation`, optional `applies_to_adaptations:false`, `kind:"source_recommendation"`. Statistical metrics are not accepted in this format.

CSV uses this **exact ordered header**:

```csv
id,name,champion_ids,board_size,core_carry_ids,core_tank_ids,non_emblem_item_slots,baseline_emblem_ids,baseline_assignments,source_tier,tier_citation,reviewed_at,holder_preferences
```

ID lists are pipe-separated. Reservation/assignment/preference cells are JSON objects/arrays with ordinary CSV escaping. Empty tier/citation becomes null; blank JSON cells become `{}`/`[]`. UTF-8/BOM is accepted. Companion metadata contains the JSON batch fields except compositions. Stored normalized metadata plus the archived CSV reproduce the export; the companion file itself is not separately archived. Example JSON, CSV and metadata are under `data/examples/meta/` and describe the same **untiered manual scenario**.

Artifacts are `data/meta/catalogs/<snapshot-sha256>/snapshot.json` plus `original.bin` (or `META_CATALOG_DIR`). The snapshot records normalized export, exact catalog hash, authorization hash, import date, original filename and original SHA-256. A fully written directory is renamed into place. Loading rehashes both files and reruns normalization/validation. Concurrent conflicting imports fail closed at discovery rather than silently picking one. Permissions and artifact history must be maintained in the repository or another operator-controlled persistent store, not ephemeral runtime writes.

## API examples and executable local check

After an authorized example import, from repository root:

```sh
curl -X POST http://127.0.0.1:8000/api/v1/emblem-strategy/analyze \
  -H 'Content-Type: application/json' --data-binary @data/examples/meta/analyze-request.json
curl -X POST http://127.0.0.1:8000/api/v1/meta/adapt \
  -H 'Content-Type: application/json' --data-binary @data/examples/meta/adapt-request.json
```

These example requests opt into manual scenarios and exclude all Lux forms; they require an imported source and are not a shortcut around authorization. With the shipped empty registry, omit `composition_keys` to receive `MISSING_META_DATA` rather than querying a nonexistent example key.

Reproduce the executed internal example without changing the default registry:

```sh
cd services/api
../../.venv/bin/python ../../scripts/verify_phase1.py
```

It creates temporary permissions **only for the original local manual scenario**, tests CSV/JSON CLI imports, starts its own loopback Uvicorn server, calls both endpoints, independently recounts results, stops the server and removes temporary artifacts. Output evidence is `docs/evidence/phase1_local_http.json`. It does not import any provider tier list, authorize third-party reuse, test real JCC or deploy anything.
