# JCC import, review, activation and rollback

This workflow is implemented and tested. No real JCC catalog is currently approved. It changes the checked-in catalog registry, not SQLite or a running Render filesystem. Operators commit the complete immutable artifact and registry together, then deploy a specific Git revision.

## 1. Authorized source → draft

Use the existing `app.importers.game_manual` CSV/XLSX importer. The UI at `/data` (local mode only) downloads the current header and validates drafts. Legacy 17-column files still work; the new header adds `aliases`, `board_slots`, `item_slots`, `trait_weights`, `exclusive_group`, `banned_holders`, `allow_native`.

- Pipe-delimited: aliases, native trait IDs, threshold counts, banned holder IDs, evidence citations.
- JSON object: `trait_weights`, e.g. a **reviewed** native trait ID mapped to 2. Unspecified weights default to 1 in a draft and must be explicitly reviewed before activation.
- `board_slots`: 1/2; `item_slots`: 0..3; `allow_native`: literal true/false. Empty defaults are draft defaults, not established JCC law.
- Every row retains game, patch, set, mode, Chinese/English label, verification state, factual citation and reviewer. Never invent an English translation or an official ID.
- `unsupported_reason` disables a champion/emblem or blocks ordinary trait evaluation. A row referencing a disabled trait cannot enter an enabled composition.
- Metadata additionally supports `source_version`, `release_date`, duplicate/unused-emblem policies, capacity bonuses, trait limits and incompatible pairs. These require independent evidence.
- Icons can be omitted for JCC; text fallback works. Included icons require explicit review permission.

From `services/api`:

```sh
../../.venv/bin/python -m app.importers.game_manual /path/export.csv --metadata /path/metadata.json --output /path/draft-envelope.json
```

The result remains `activated=false`. Extract `catalog` from the envelope to `/path/catalog.json`; never change a ready flag to bypass review. Correct the original rows/metadata and reimport after corrections; the new file digest invalidates old approval.

Authorized machine-readable providers may produce the same strict Ruleset draft JSON directly; no network provider or undocumented endpoint is bundled. The JSON must preserve source snapshots and per-record evidence.

## 2. Independent review

An approval JSON follows the strict `Approval` schema in `services/api/app/catalogs/activation.py`. Print the exact schema with:

```sh
../../.venv/bin/python -c 'import json; from app.catalogs.activation import Approval; print(json.dumps(Approval.model_json_schema(), ensure_ascii=False, indent=2))'
```

Required contents:

- schema_version 1, `decision: approve`, exact SHA-256 of input catalog bytes, two distinct named reviewers, timezone-aware review date, source version, release date, enabled scope, explicit unsupported mechanics.
- Complete expected champion/trait/emblem ID lists and a complete-roster citation. Each list must exactly match the imported entities. At least three emblem definitions.
- Eleven essential JCC rule reviews: version/mode, roster/cost/locales, native relationships, monotonic thresholds, emblem mapping, population/capacity, legal holders/equipment, duplicates, unique units/unlocks, special-mechanic scope, source permissions/provenance. All need VERIFIED status and evidence within the stated scope.
- Sources: original basename, HTTPS citation URL, exact SHA-256, category official/licensed_export/manual_original, original/authorized license status, permission evidence, attribution and explicit `redistribution_allowed: true`. Archive only material permitted for public redistribution. Input snapshot records must match reviewed files.
- Icon policy `text_only` (all icon fields absent) or `authorized_references` plus icon permission evidence.
- At least three independently reviewed composition cases: request, selected canonical units, assignments, and **all trait counts**. At least one must legally assign three emblem instances. Cases are checked against post-solve rules; the reviewer supplies expected facts, not optimizer-generated truth.

Approval is an operator attestation under Git/file access control, not a digital signature or automatic legal opinion. The program cannot prove a reviewer has authority or that a citation is true. Do not fill approval fields with guesses, placeholders, copied TFT assumptions or an AI pretending to be a human reviewer.

```sh
../../.venv/bin/python -m app.catalogs.activation check --catalog /path/catalog.json --approval /path/approval.json --sources-dir /path/redistributable-originals
../../.venv/bin/python -m app.catalogs.activation status
../../.venv/bin/python -m app.catalogs.activation activate --catalog /path/catalog.json --approval /path/approval.json --sources-dir /path/redistributable-originals --actor OWNER --reason 'Reviewed JCC release' --expected-revision REVISION_FROM_STATUS
```

Activation builds `data/approved/<content-hash>/` with input, catalog, approval, validation and permitted originals. It validates the artifact again, uses an exclusive operator lock, records immutable registry history, then atomically replaces `data/active/index.json`. A stale revision or changed source fails before promotion. Corrections to an already-active ruleset require a new ruleset ID.

## 3. Persist, deploy, verify

Commit the artifact directory, registry and history together. The Docker image copies all three; Render restarts do not lose approvals. The loader checks digests, source originals, review and rules on read. `/api/v1/games` lists approved JCC versions; catalog and existing solve/holder endpoints use the same CP-SAT engine. Public mode no longer hardcodes TFT. There is deliberately no public activation/upload API.

A missing/corrupt JCC artifact or registry fails closed for JCC, with `catalog_activation_issues` in `/api/v1/data-health`; TFT still loads independently. Successful synthetic workflow tests are not permission to publish synthetic records.

Run the complete backend/frontend suite, genuine approved JCC cases, browser desktop/mobile and public CORS/solver checks before declaring real JCC ready. Existing tests establish only the pipeline until real records become available.

## 4. Rollback

`status` gives the current revision. Prior exact revisions are stored in `data/active/history/<sha256>.json` and audit records reference their predecessor.

```sh
../../.venv/bin/python -m app.catalogs.activation rollback --target-revision OLD_REVIEWED_REVISION --actor OWNER --reason 'Revert JCC release' --expected-revision CURRENT_REVISION
```

Rollback validates every target artifact before atomic promotion and appends an audit event. It never deletes immutable history. Commit/deploy the rollback. For a full code rollback use the documented previous Render commit and restore the matching Pages static branch commit, without force-push.
