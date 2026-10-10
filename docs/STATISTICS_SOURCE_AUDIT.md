# Statistics interface audit — 2026-10-10

Audited before implementing Phase 3 ingestion.

| Existing component | Finding | Integration decision |
| --- | --- | --- |
| `schemas/domain.py` | Catalog provenance has game/patch/set/mode/source/status; no statistical schema. | Add a strict separate statistics contract. Exact catalog/version validation is mandatory. |
| `models/database.py` | `DataSource`/`StatisticsObservation` are reserved discriminator names, not validated adapters or permission checks. | Use a dedicated observations table and an operator-controlled authorization registry. Do not treat arbitrary versioned JSON as trusted statistics. |
| `repositories/catalog.py` | Reads checked-in validated JSON, with only original synthetic TFT/JCC fixtures. | No production patch mapping exists. Observed statistics must use a verified catalog; synthetic catalogs accept explicitly synthetic tests only. |
| `importers/manual.py` | Archives catalog snapshots; does not activate them. | No automatic production catalog activation in this increment. |
| `importers/community.py` | Community recommendations, source claims and human label review; no observations. | Remains separate. A guide, even reviewed, is not an authorized statistical provider. |
| `scoring/engine.py` | Rules-based score; sample/win-rate null, statistics unavailable. | Preserve behavior; ingestion does not silently replace objective weights or scores. |
| `api/routes.py` | Holder statistics null; data-health reflects the synthetic optimizer catalogs. | Add explicit statistics query endpoints; do not attach unmatched cohort data to solver candidates. |
| Existing source research | No first-party credentials, production registration or provider license supplied. | Default registry is empty. No third-party scraping or remote collection adapter is enabled. |

Primary policy pages checked: [Riot TFT developer documentation](https://developer.riotgames.com/docs/tft) and [Riot API terms](https://developer.riotgames.com/terms). The documented API is a possible upstream, not an authorization granted to this project. Applicable product registration, game-specific restrictions and permitted use must be reviewed before enabling an upstream. No terms were accepted, key requested or match data retrieved. JCC requires its own authorization; Riot permissions do not transfer automatically. Provider licenses must explicitly permit acquisition, storage, display and any requested derived metrics for the scoped data.

Chosen boundary: authorized adapters normalize legally acquired aggregate observations into the API contract. The API performs no network requests, website scraping, source URL dereferencing, account linking or player identification. Server operators approve sources outside the ingestion endpoint; payloads cannot self-authorize. Synthetic test numbers are identified as synthetic and never reported as real match statistics.
