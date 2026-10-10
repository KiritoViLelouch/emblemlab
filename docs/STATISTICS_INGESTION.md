# Phase 3 provider-neutral statistics ingestion

This API accepts aggregate observations from an authorized first-party API/export or explicitly licensed provider. It does not fetch remote data. The checked-in source registry is **empty**, and ingestion is disabled without an operator token. No real provider, credentials, verified production catalog, observed match data or provider license was supplied to this project.

Read `STATISTICS_SOURCE_AUDIT.md` for the audit performed before implementation. The optimizer, existing holder ranking, community guide importer and existing API response contracts remain unchanged. Statistics do not silently alter heuristic scores or fill a solver candidate's null statistics.

## Enable an authorized source

1. Review actual access, storage, display and derivation rights, relevant game/region policies, attribution, retention/deletion duties, and the exact permitted patch/mode/context/metrics. Record the authorization document reference and SHA-256. Public accessibility alone grants no rights. Riot/TFT authorization does not cover JCC automatically.
2. Supply a genuinely verified, versioned catalog in the existing catalog repository. Observed ingestion requires the ruleset **and every catalog entity** to have `verification_status=verified`; all game/patch/set/mode references must agree. Existing `EXAMPLE-1.0` fixtures only accept explicitly synthetic test observations. Production catalog activation remains a separate workflow.
3. Create an operator-controlled registry outside the web app. Set `STATISTICS_SOURCES_FILE` to its absolute path. The API has no source-approval or self-registration endpoint. Do not include credentials or private contract text in registry fields: authorization metadata is included in observation provenance responses.
4. Set a private `STATISTICS_INGEST_TOKEN` in the API process environment. Authorized adapters send `Authorization: Bearer <token>`. Keep this token out of frontend environment variables and source control. This is distinct from any upstream provider API key.
5. Install existing requirements and run `../../.venv/bin/alembic upgrade head` from `services/api`. Revision `0003` adds only `statistics_observations`, preserving catalog/community tables. Then start the backend as in README.

The JSON registry has `schema_version: 1` and `sources: []`. Each approved entry contains:

| Field | Meaning |
| --- | --- |
| `provider_id`, `name`, `attribution` | Stable adapter/provider identifier, display name, required credit. |
| `source_kind` | `first_party` or `licensed_provider`. |
| `access_method` | `official_api`, `licensed_api`, or `licensed_export`. Third-party providers require one of the two licensed methods. |
| `license_id`, `permission_reference`, `permission_sha256` | Actual authorization identifier, document/URL reference, and lowercase 64-character SHA-256 of evidence. These are audited operator records, not automatic legal validation. References are never dereferenced. |
| `reviewed_by`, `reviewed_at` | Operator identity and timezone-aware review timestamp. |
| `valid_from`, `valid_until`, `enabled` | Operator approval window and switch. The window must start on/after review and end after its start. This is not an inferred legal license duration. |
| `permitted_uses` | Subset of `ingest`, `store`, `display`, `derive`. Ingestion requires the first three; optional calculations require `derive`. |
| `scopes` | List of exact `{game_id,ruleset_id,patch,set_id,mode}` objects. No wildcard, latest-patch alias or prefix match. |
| `data_kinds` | `observed` and/or `synthetic`, explicitly authorized. |
| `context_kinds` | `holder` and/or `composition`. |
| `metrics` | `top_four_rate` and/or `average_placement`. Related counts/intervals require the same metric permission; full placement histograms require both. |

The registry is strictly validated, bounded to 1 MiB/100 sources, and duplicate IDs fail closed. An absent/malformed registry returns 503. Unknown, inactive, future, expired or out-of-scope sources return 403. The repository contains no enabled example permission grant: test-only invented grants live only in isolated automated/live QA fixtures.

[Riot's TFT documentation](https://developer.riotgames.com/docs/tft) describes registration/game policies; [Riot API terms](https://developer.riotgames.com/terms) govern applicable API use. These pages are references for review, not approval for this project. They were checked on 2026-10-10. Nothing here accepts terms, requests credentials, bypasses controls, or grants redistribution rights. External deployment and license-specific deletion/retention are operator responsibilities; disabling authorization hides data but does not purge stored evidence automatically.

## Endpoints

| Route | Behavior |
| --- | --- |
| `GET /api/v1/statistics/sources` | Currently active sources and their permitted scopes/uses. No credentials. Empty by default. |
| `POST /api/v1/statistics/ingest` | Token-protected JSON batch, maximum 2 MiB and 500 observations. Structural/context validation precedes transactional inserts. |
| `GET /api/v1/statistics/observations` | Exact scoped query, optional provider/context/data-kind filters, paginated records. |
| `GET /api/v1/statistics/observations/{id}` | One record with original normalized inputs, provenance, derived metrics, confidence and quality. |

POST's complete machine-readable input schema is included in `/openapi.json` and `/docs`. `app.statistics.providers.StatisticsProvider` defines the Python adapter protocol `normalize(export: bytes) -> IngestRequest`. A provider-specific authorized exporter is responsible for legally obtaining data, source-specific ID/version mapping, deduplication, and normalizing it into this contract. No concrete network adapter or raw-player/match collector is shipped.

POST example shape below is an **explicitly synthetic API example, not real statistical evidence**. It is rejected by the default empty registry; configuring a matching test-only authorization in a disposable database is required to execute it. Never label these numbers observed.

```json
{
  "schema_version": 1,
  "provider_id": "test-only-provider",
  "scope": {
    "game_id": "TFT",
    "ruleset_id": "fixture_tft_v1",
    "patch": "EXAMPLE-1.0",
    "set_id": "SYNTHETIC-EXAMPLE",
    "mode": "offline-fixture"
  },
  "data_kind": "synthetic",
  "observations": [{
    "provider_record_id": "test-export-row-1",
    "cohort_id": "synthetic-cohort",
    "cohort_definition": "Eight invented outcomes for parser verification only",
    "dataset_reference": "test-only-export-sha-or-reference",
    "sample_unit": "participant_game",
    "placement_scale": 8,
    "region": null,
    "queue_id": "synthetic-test-queue",
    "rank_band": null,
    "observed_start": "2026-10-01T00:00:00Z",
    "observed_end": "2026-10-02T00:00:00Z",
    "collected_at": "2026-10-03T00:00:00Z",
    "context": {
      "kind": "holder",
      "emblem_id": "tft_emblem_0",
      "champion_id": "tft_unit_1",
      "composition": null
    },
    "metrics": {
      "sample_size": null,
      "top_four_count": null,
      "placement_sum": null,
      "placement_counts": [1, 1, 1, 1, 1, 1, 1, 1],
      "top_four_rate": null,
      "average_placement": null
    },
    "quality": {
      "independence": "unknown",
      "deduplication": "unknown",
      "population_coverage": null,
      "notes": "Synthetic test, not actual match data"
    }
  }]
}
```

From `services/api`, send an actual normalized, licensed file:

```sh
curl http://127.0.0.1:8000/api/v1/statistics/ingest \
  -H "Authorization: Bearer ${STATISTICS_INGEST_TOKEN}" \
  -H 'Content-Type: application/json' --data-binary @authorized-statistics.json
```

GET requires **all five** scope keys. Example safe empty query for the current synthetic catalog:

```sh
curl 'http://127.0.0.1:8000/api/v1/statistics/observations?game_id=TFT&ruleset_id=fixture_tft_v1&patch=EXAMPLE-1.0&set_id=SYNTHETIC-EXAMPLE&mode=offline-fixture'
```

Optional query keys: `provider_id`, `data_kind` (default `observed`), `context_kind` (`holder`/`composition`), `context_key` (64-character canonical context SHA-256), `limit` (1–100, default 50), `offset` (nonnegative). A response returns `scope`, `data_kind`, `statistics_available`, `total`, `limit`, `offset`, `records`, and `aggregation: "none"`. An empty result is `records: []`, not zero top-four/average-placement values. `statistics_available` is true only when an authorized observed record has at least one available top-four/average-placement point metric; unknown/empty metrics do not count as available performance statistics. Synthetic results always have `statistics_available: false`. Current authorization is checked on every read: revoked/expired sources, removed scopes/metrics, changed license evidence/ID, or changed catalog fingerprints are not served. Direct reads then return 403; list queries omit those records. Historical rows are retained until the operator handles license retention/deletion requirements.

Status codes: 401 wrong/missing operator token; 403 disallowed source/use; 404 missing observation; 409 immutable provider-ID/content/catalog/license conflict; 413 body too large; 415 non-JSON; 422 schema/numeric/context/version/timestamp mismatch; 503 token unconfigured or registry unavailable. No tokens or raw export values are echoed in validation errors.

## Observation assumptions and statistical definitions

- **Outcome unit:** one eligible participant's completed game outcome (`participant_game`), not a whole lobby, unique player, holder appearance or champion copy. Provider counts must already be deduplicated to that unit. One participant-game must contribute at most once within a given cohort.
- **Placement scale:** exactly 1–8; top-four means placement ≤4. Team/double-up/other outcome scales are unsupported and rejected rather than forced onto this scale. Queue identity is explicit, not inferred from game name.
- **One denominator:** every supplied outcome metric/count in a row uses the same cohort and `sample_size`. If sources publish different denominators, export separate observations with appropriate cohort definitions. The API cannot independently prove upstream denominator definitions or completeness.
- **Patch isolation:** an entire batch is exactly one game/ruleset/patch/set/mode and observations inherit that scope. Adapters must split mixed-patch exports first. The API checks exact catalog metadata and IDs, but cannot inspect omitted raw matches to prove provider patch classification. It never infers a patch from timestamp, prefixes or "latest".
- **Time:** timezone-aware ISO-8601 only, normalized to UTC; `observed_start ≤ observed_end ≤ collected_at`. Collection may be at most five minutes ahead of server time for clock skew. Providers define whether observation-window endpoints are inclusive; cohort text must record that convention. Windows from different observations may overlap.
- **Missingness:** omitted/null metrics stay null unless exact licensed sufficient counts support an explicit derivation. Missing sample size stays unknown; a rate cannot reconstruct counts. An empty sample yields null rates/means, never zero performance. A genuine supplied zero rate with a positive sample is retained.
- **Counts:** integers only, no bools/numeric strings/fractions; sample/count cap is 10^12, placement-sum cap 8×10^12. An optional histogram has exactly eight counts ordered placement 1…8. Histograms, supplied sample/count/sum and supplied metrics must agree. Point-estimate tolerance against counts is absolute 10^-6; adapters must supply enough precision or omit rounded estimates and provide counts. Rates are fractions in [0,1], not percentages; average placement is in [1,8]. NaN/infinity, inconsistent top-four/mean combinations and impossible sums are rejected atomically.
- **Derivations:** when permission includes `derive`, histogram sum provides sample size; the first four bins provide the top-four count; weighted histogram sum provides placement sum. `top_four_rate = top_four_count / sample_size`; `average_placement = placement_sum / sample_size`. Outputs mark each metric `reported`, `derived_from_histogram`, `derived_from_counts`, or `missing`. Original normalized `observation.metrics` never gets overwritten with derived values. Without derive permission, counts remain stored but missing derived fields remain null.
- **Context:** holder rows describe an observed champion/emblem combination. `composition: null` explicitly means no board restriction, not a best-board recommendation. Composition rows (or holder rows with board context) carry unique `champion_ids`, explicit `matching_rule` (`exact_board` or `unit_subset`), and emblem assignments. Holder+board context must include its assignment. All IDs and equipment/slot/duplicate rules must be valid in the exact catalog. Lists are canonically sorted for stable identities. No implicit cross-game aliases, formation, item/star-level/rank normalization or estimates are introduced. The provider's cohort definition must explain omitted covariates and board/subset membership semantics.
- **Region/rank:** explicit values or null unknown; unknown is not "all regions"/"all ranks". `queue_id` is required. Statistics with different regions, ranks, queues, windows, cohort definitions, board rules, assignments or providers remain separate records.
- **No pooling:** no sum of overlapping windows, no averaging of averages, and no assumed independence across sources/cohorts. Replay protection does not deduplicate raw matches inside or across different provider records. Adapters must retain dataset/cohort lineage and verify sampling/deduplication.
- **Community vs statistics:** guides, recommendations and human label corrections never become samples or placements. Statistical observations live in a dedicated table; they do not alter community rows, active catalogs, solver weights or existing null statistics. No causal claims or optimal-holder claims follow from these observational cohorts.

## Confidence and quality indicators

A computed two-sided **95% Wilson score interval** for top-four rate is returned only when exact integer success/total counts are available, derivation is permitted and the provider explicitly declares independent sampling. A rounded rate times a sample size is never treated as an exact success count. The Wilson construction follows [NIST's confidence-interval reference](https://www.itl.nist.gov/div898/handbook/prc/section2/prc241.htm). Independent Bernoulli sampling is a conditional assumption, not a fact inferred from a large N: repeated players and outcomes sharing a lobby may be correlated. Unknown/clustered sampling suppresses the computed interval. Interval width is sampling uncertainty, not the probability that a holder is strong or that a recommendation is correct.

No computed average-placement interval is manufactured from a mean and sample size: variance/cluster structure is not available. Providers may supply `metrics.reported_confidence`:

```json
{
  "top_four_rate": {"lower": 0.4, "upper": 0.6, "level": 0.95, "method": "provider cluster bootstrap"},
  "average_placement": {"lower": 4.1, "upper": 4.9, "level": 0.95, "method": "provider cluster bootstrap"}
}
```

These illustrative interval fields require corresponding valid point estimates/counts in the observation; they are not defaults. Bounds must use the metric's scale and contain its point estimate; level is explicitly between 0 and 1, method is required. Provider-reported and computed confidence remain separate, and neither is labeled independently verified.

`data_quality` returns a versioned policy (`statistics-quality-v1`), provider declarations, `quality_verified: false`, observation age, and flags for unknown/empty/small sample, missing metrics/exact counts, unknown/clustered independence, unverified deduplication, unknown/partial population coverage, unknown region/rank, old observations and synthetic data. Population coverage is an optional provider-declared fraction, never invented from N. The sample threshold **100** and staleness threshold **7 days** are transparent operational warnings, not universal statistical sufficiency criteria or confidence scores. Large samples do not remove selection bias, confounding, missingness or correlated outcomes.

## Persistence and replay

Observation ID is SHA-256 of provider ID + all scope keys + data kind + provider record ID. The same ID/content/catalog/license is idempotent across batches. Different content under the same provider record ID returns 409 and rolls back the whole batch. Corrections/new provider snapshots need new upstream record IDs; old/new snapshots are never pooled. Canonical context keys and normalized payload/catalog hashes are retained with the authorization snapshot and UTC import timestamp. Changing catalog content behind the same ruleset ID blocks reads/replay until a new version is used.

Migration `0003` is additive. Downgrading to `0002` deletes statistical observations; back up first. Catalog activation, statistical objective weighting, ability compatibility, raw-match aggregation, upstream fetching/rate limiting, automatic license verification and retention/purge workflows are outside this increment. Query pagination streams stored rows and checks current permissions; exact authorized totals require scanning the scoped records. PostgreSQL, production provider exports, multi-process stress and external deployment remain unverified. Use loopback as in README.
