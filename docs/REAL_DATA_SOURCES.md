# Phase 2A — real static game data

Audited 2026-10-10. No match statistics, win rates or production reforge probabilities were imported.

## Explicit TFT target

- Game: TFT international; **Set 18, Enchanted Wilds, gameplay patch 18.4, standard mode**.
- CommunityDragon selection: `number == 18 AND mutator == TFTSet18`; never maximum numeric set ID. Snapshot also contains other sets/modes, which are not merged.
- Static resource series: CommunityDragon **16.20**, Riot Data Dragon **16.20.1**. Gameplay patch numbering is different from the resource version.
- Build: `16.20.8248524+branch.releases-16-20.content.release`.
- This is a fixed snapshot checked on the above date, not a promise of continuous live/hotfix synchronization.

Primary evidence: [Riot TFT data documentation](https://developer.riotgames.com/docs/tft), [official patch 18.4](https://teamfighttactics.leagueoflegends.com/en-us/news/game-updates/teamfight-tactics-patch-18-4/), [official Set 18 overview](https://teamfighttactics.leagueoflegends.com/en-sg/news/game-updates/enchanted-wilds-overview/), [patch schedule](https://support.riotgames.com/en-us/tft/events/patch-schedule-teamfight-tactics).

## Downloaded sources and provenance

`data/manifests/tft_set18_18_4.json` lists every exact URL, download timestamp, byte count and SHA-256. Original response metadata is also stored beside each snapshot in `data/snapshots/tft/16.20/*.meta.json`.

| Source | Imported fields | Boundary |
|---|---|---|
| Riot Data Dragon `cdn/16.20.1/data/{en_US,zh_CN}/tft-champion.json` | Canonical shop membership, names, cost/tier, icons | Official standard shop prefix only |
| Riot Data Dragon corresponding `tft-trait.json`, `tft-item.json` | Canonical IDs, translated labels, icon filenames | Traits joined by explicitly selected set IDs; items by `TFTSet18/Set18_Items/` and reviewed whitelist |
| [CommunityDragon fixed English snapshot](https://raw.communitydragon.org/16.20/cdragon/tft/en_us.json) and corresponding `zh_cn.json` | Costs, native trait references, effect activation thresholds, descriptions | Community extraction of public client static data; not Riot's official API |
| [Build metadata](https://raw.communitydragon.org/16.20/content-metadata.json) | Identifiable content build | Digest pinned |
| Riot `api/versions.json` | Initial resource version discovery | Cached discovery record; not re-fetched during reproduction |

Icons reference the official `ddragon.leagueoflegends.com/cdn/16.20.1/img/` resources. No guessed `.tex`-to-PNG URLs. An actual HTTP HEAD audit returned 200 and `image/*` for all 122 distinct URLs; evidence: `data/manifests/tft_set18_icons.json`. Art is referenced remotely, not bundled for offline viewing.

These assets remain Riot copyrighted material. Public availability does not grant a new license, endorsement or permission to third-party statistics. No DataTFT data, protected endpoint, credential, private API or scraped third-party webpage dataset is included.

## Reproduce without network

From `services/api`:

```sh
../../.venv/bin/python -m app.importers.tft_static ../../data/manifests/tft_set18_18_4.json --output ../../data/catalogs/tft/set18_18_4.json
```

The importer checks every cached file digest, build/version identity, exact shop roster, bilingual native trait relationships, costs, thresholds and reviewed emblem mapping. Changing a remote snapshot cannot silently change the active catalog. The API reads normalized local JSON; solving never downloads data.

Optional explicit downloads from the repository root:

```sh
.venv/bin/python tools/tft_snapshots.py download
.venv/bin/python tools/tft_snapshots.py icons
```

`download` uses pinned public URLs and refuses changed checksums; it does not update the manifest or re-fetch mutable discovery metadata. A new patch requires a separately reviewed manifest/catalog. The cached snapshot remains the reproducibility authority even if upstream replaces a fixed-version file.

## JCC investigation and manual workflow

The [requested DataTFT JCC reference](https://jcc.datatft.com/) was inspected as a public landing page; its retrieved page exposed no documented, authorized machine-readable export for this project. An attempt to inspect [Tencent's JCC site](https://jcc.qq.com/) timed out. This is **not proof that no legitimate interface exists**. No API credentials/license or authorized JCC dataset is configured, and no private endpoint exploration or scraping was performed.

JCC has no active real catalog. TFT entities/rules are never copied into it. `/data` provides CSV/XLSX upload, metadata editing, relation validation and a downloadable review draft. Verified rows require named reviewers, evidence and `original`/`authorized` attribution. Unknown authorization cannot yield VERIFIED rows. Uploading never activates a dataset; essential JCC rules remain UNVERIFIED and optimization remains disabled.

See the format below. Full support remains blocked on an authorized complete version/mode roster and independently reviewed rules.

## JCC CSV/XLSX format

Use `data/examples/jcc_static_template.csv` or download the empty template at `/data`. Exactly one XLSX sheet, UTF-8 CSV, <=2 MiB, <=1000 data rows, text-only cells (numeric cost cells also accepted), no formulas/macros/external workbook links. No real example rows are invented.

Exact columns, in order:

```text
entity_type,id,zh_CN,en_US,icon_url,cost,trait_ids,thresholds,trait_id,verification_status,evidence,reviewer,game,patch,set,mode,unsupported_reason
```

- Common fields: `entity_type` is `champion`, `trait`, or `emblem`; IDs and names are required; `game` must be JCC; row patch/set/mode must exactly match metadata. HTTPS icon references are validated syntactically, never fetched by the upload API.
- Champion: `cost` in 1..5; `trait_ids` is a `|`-separated list of canonical native trait IDs.
- Trait: `thresholds` is a strictly increasing `|`-separated list of positive activation counts. Utility is ordinal 1,2,..., not a combat statistic. Unsupported/nonmonotonic mechanics need `unsupported_reason`, remain disabled and may omit thresholds.
- Emblem: `trait_id` must reference a trait in the same file/version.
- Verification: VERIFIED, PARTIALLY_VERIFIED, UNVERIFIED, UNSUPPORTED. SYNTHETIC exists as a catalog state but is intentionally rejected by this real-data manual workflow. VERIFIED requires `reviewer`, nonempty `evidence` (`|` separated references), and known source authorization; these are operator attestations, not automatically authenticated proof.
- `unsupported_reason` disables the corresponding entity. Missing required roster entries, duplicates, unknown references and mixed provenance fail validation. Correct the original file/metadata and upload again; the normalized draft retains evidence/reviewer records and a file digest.

Separate metadata JSON fields:

```json
{
  "game": "JCC",
  "ruleset_id": "REPLACE_WITH_REVIEWED_ID",
  "patch": "REPLACE_WITH_PATCH",
  "set": "REPLACE_WITH_SET",
  "set_name": "REPLACE_WITH_NAME",
  "mode": "REPLACE_WITH_MODE",
  "source": "REPLACE_WITH_AUTHORIZED_SOURCE",
  "source_url": "https://REPLACE_WITH_AUTHORIZED_HOST.example/",
  "license_status": "unknown",
  "attribution": "REPLACE_WITH_ATTRIBUTION",
  "required_champion_ids": ["REPLACE_WITH_REQUIRED_CHAMPION_ID"]
}
```

These are placeholders, not game records. Multipart `POST /api/v1/data/manual/validate`: `file` plus metadata JSON string in `metadata`. JSON catalog validation: `POST /api/v1/data/validate`. Template schema: `GET /api/v1/data/manual-template`. Neither endpoint publishes data.

Offline review from `services/api`:

```sh
../../.venv/bin/python -m app.importers.game_manual /absolute/path/data.xlsx --metadata /absolute/path/metadata.json --output /absolute/path/review-draft.json
```

The draft is deliberately separate from authoritative `data/catalogs`. Rule review and activation are operator work; there is no upload-to-live shortcut.

The current adapter deliberately accepts only the audited Set 18/18.4/16.20.1 standard profile. A different set, patch, resource version or mode is rejected until its rules and manifest are reviewed; changing a patch label alone cannot relabel this dataset.

The gameplay-to-resource mapping is an explicit operator review based on the contemporaneous Riot release/patch documentation and fixed resource build. These JSON files do not independently attest that every TFT mid-patch hotfix has been applied. Full hotfix parity is unverified; the admitted static-count profile and blocked discrepancies are documented separately.
