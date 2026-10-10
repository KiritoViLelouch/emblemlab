# Community guide import (Phase 2, first increment)

Community recommendations are editorial opinions, never match statistics or optimizer inputs. Use the **社区攻略** navigation entry (`/guides`) to upload a guide, inspect its issues, and manually correct labels. The existing solve, holder ranking, reforge and catalog APIs retain their behavior.

## Install and migrate

From the repository root, install the updated dependencies, then migrate before starting the API:

```sh
.venv/bin/pip install -r services/api/requirements.txt
cd services/api
../../.venv/bin/alembic upgrade head
```

Revision `0002` adds only `community_imports` and `community_rows`. Existing catalog snapshots and statistics records are untouched. Back up a database before downgrading: downgrading to `0001` removes the community tables.

## File format

Use UTF-8 CSV (BOM accepted) or `.xlsx`. Row 1 contains the exact English column names below, in any order. All cells must be text; format spreadsheet cells as Text before entering values. No extra title rows, merged headers, numeric/date/error cells, or formulas. Optional columns can be omitted. Unknown columns, including `win_rate`, `sample_size` and other statistical fields, cause rejection of the entire file.

| Column | Required | Meaning |
| --- | --- | --- |
| `emblem_name` | Header required | Emblem ID, Chinese/English name, or existing catalog alias. May be blank when `emblem_icon_ref` is present. |
| `emblem_icon_ref` | No | Opaque reference such as a URL, filename, or source screenshot coordinate. Saved as text; never fetched, read from disk, rendered as an image, or automatically recognized. |
| `recommended_holders` | No | Champion IDs/names/catalog aliases separated by `\|`. Each holder is an independent recommendation, not a simultaneous equipment assignment. |
| `composition_aliases` | No | Source-specific composition names separated by `\|`; does not modify catalog aliases. |
| `label_status` | No | `unverified` (default) or `uncertain`. A file cannot assert `reviewed`/`verified`. |
| `notes` | No | Free text context. |

Example (synthetic fixture IDs only):

```csv
emblem_name,emblem_icon_ref,recommended_holders,composition_aliases,label_status,notes
tft_emblem_0,guide-image.png#row-2,tft_unit_1|tft_unit_3,测试阵容|Example comp,unverified,Community opinion
,guide-image.png#row-3,未确认棋子名,待确认阵容,uncertain,Icon-only row needs manual mapping
```

A checked-in example is `data/examples/community-guide.csv`. It intentionally includes an uncertain holder for testing the review workflow. CSV quoting follows the standard CSV rules: quote cells containing commas, quotes or newlines. `|` is always a list separator; literal pipes inside names are not supported. Repeated holder/alias tokens are deduplicated in derived mappings, while the original source text is retained.

Limits: 5 MiB uploaded content; 1000 data records/worksheet rows (blank records/rows count toward the limit); 6 columns; 1000 characters per cell. XLSX additionally allows at most 200 ZIP entries and 20 MiB total declared uncompressed content. Macros and external workbook links are rejected. Only `.csv` and `.xlsx` are accepted. For a workbook with multiple sheets, supply the exact sheet name; otherwise a single sheet is selected automatically. Hidden sheets also count. CSV cannot specify a sheet. File parsing and structural validation complete before a transaction starts; malformed imports persist no rows.

## Attribution and version scope

Each import requires `game_id`, `ruleset_id`, `source_title`, `attribution` (author/credit), and `license_status` (`original`, `authorized`, or `unknown`). Optional `source_url` must be an HTTP(S) URL. These are declarations supplied by the importer, not independent license verification.

The selected catalog supplies patch, set, mode and a SHA-256 catalog fingerprint. The batch stores those fields with the source filename, file SHA-256, selected sheet, UTC import timestamp, `kind=community_recommendation`, and `verification_status=unverified`. Rows inherit this immutable provenance through their import foreign key. Source bytes and workbook styling are not archived; parsed original cell values and the file digest are retained. Original values, including whitespace, remain available in `raw`.

Matching uses exact IDs/names/catalog aliases after Unicode NFKC normalization, trimming and case folding. There is no fuzzy matching or cross-game mapping. Foreign-game IDs, unknown names, ambiguous aliases, icon-only rows and holders illegal under the selected rules remain unresolved/issues for review. This preserves uncertain source evidence without accepting it as a canonical entity. Composition aliases remain local to that row.

The deterministic import ID includes file content hash, filename, attribution metadata, selected sheet and catalog fingerprint. Repeating the same import returns the existing record, including corrections. Different metadata or content creates a separate batch. Duplicate source rows are preserved as separate rows. Imported recommendations never write `StatisticsObservation` records, change active fixture catalogs, or affect scoring/optimization.

## Review and corrections

- `matched`: all supplied labels uniquely match and holders satisfy current equip rules; still unverified community opinion.
- `needs_review`: unresolved/ambiguous labels, illegal holders or explicit `uncertain` source status.
- `reviewed`: a human explicitly confirmed valid mappings. This is label/rule verification, not a strength, probability or statistical claim.

Open a row's **人工校正标签与推荐** disclosure. Correct the name/ID, icon reference, holders, aliases or notes. Supply reviewer and correction rationale. Saving without confirmation leaves uncertain source labels pending; checking confirmation permits `reviewed` only when all labels resolve and holders are legal. The source `label_status` is retained for provenance even after confirmation.

Each save increments `revision` and appends before/after snapshots, reviewer, rationale and UTC timestamp. Original `raw` values are immutable. `expected_revision` guards against lost edits; stale revisions return 409 and the UI asks you to reopen the import. Review also returns 409 if the selected catalog content changed since import; publish/select a new ruleset and reimport. An edit to a previously reviewed row requires explicit confirmation again to remain reviewed.

## API

All routes are additive. Existing API request/response schemas are unchanged.

```sh
curl http://127.0.0.1:8000/api/v1/guides/import \
  -F file=@../../data/examples/community-guide.csv \
  -F game_id=TFT -F ruleset_id=fixture_tft_v1 \
  -F source_title='Example community guide' \
  -F attribution='EmblemLab synthetic example' -F license_status=original
```

Run the example from `services/api`. Add `-F source_url=https://example.org/guide` or `-F sheet=Guides` as needed.

| Route | Behavior |
| --- | --- |
| `POST /api/v1/guides/import` | Multipart fields above; returns batch metadata and rows. |
| `GET /api/v1/guides?game_id=TFT&ruleset_id=fixture_tft_v1` | Lists metadata for the exact game/version. |
| `GET /api/v1/guides/{import_id}` | Full batch, original values, current mappings and history. |
| `PATCH /api/v1/guides/{import_id}/rows/{row_id}` | Saves a correction and returns the updated batch. |

PATCH body (all editable fields replace the current values; omitted optional editable fields become empty):

```json
{
  "expected_revision": 1,
  "emblem_name": "tft_emblem_0",
  "emblem_icon_ref": "guide-image.png#row-2",
  "recommended_holders": "tft_unit_1",
  "composition_aliases": "测试阵容|Example comp",
  "notes": "Corrected the original uncertain holder",
  "reviewer": "Local reviewer",
  "correction_note": "Checked against selected synthetic catalog",
  "confirm": true
}
```

Invalid uploads/confirmation requests return 422, missing imports/rows 404, stale revision/catalog changes 409. Import and correction writes are transactional. Upload parsing/database work runs in a worker thread after the bounded content read.

## CLI

From `services/api`, after migration:

```sh
../../.venv/bin/python -m app.importers.community ../../data/examples/community-guide.csv \
  --game TFT --ruleset fixture_tft_v1 \
  --source-title 'Example community guide' \
  --attribution 'EmblemLab synthetic example' --license-status original
```

Optional `--source-url` and `--sheet` match the API. The CLI prints the resulting batch JSON. Manual review uses the UI or PATCH API.

## Current limits

Offline, manually supplied files only. No OCR, icon downloads, embedded-image extraction, automatic authorization verification, fuzzy correction, bulk review, activation of imported game catalogs, or statistics ingestion. One attribution applies to the whole file; split mixed-source guides into separate imports. No authentication or reviewer identity verification: this remains a loopback-only local tool. Import lists/full histories are not paginated; large long-lived collections need a separate scaling step. The file size limit is enforced on parsed uploaded content; an externally exposed deployment would also need a server/proxy request-body limit. PostgreSQL and real third-party community workbooks have not been exercised.
