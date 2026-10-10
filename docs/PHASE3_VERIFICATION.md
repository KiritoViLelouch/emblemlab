# Phase 3 statistics verification — 2026-10-10

Implemented scope: audit of existing source interfaces; provider-neutral aggregate statistics ingestion/read APIs; permission registry/token boundary; exact patch/catalog/context isolation; sample/placement metrics and conditional confidence/quality indicators. No real upstream data or approval was supplied or invented. No third-party website scraping or remote collection was performed.

## Checks actually executed

- Backend: `../../.venv/bin/pytest -q` from `services/api`: **142 passed** (86 prior cases + 56 statistical ingestion cases).
- Ruff: `../../.venv/bin/ruff check app tests`: passed.
- Frontend: `npm run typecheck`, `npm run lint`, `npm run build`: passed. Frontend code was not changed in this increment; these are regression checks.
- Local SQLite migration upgraded from `0002` to `0003 (head)` successfully. Automated migration test seeded a community import under `0002`, upgraded and verified preservation, downgraded to `0002`, then upgraded again. Existing migration/optimizer/community tests also passed.
- Actual HTTP smoke checks against a separate loopback API process and disposable SQLite database: explicitly synthetic histogram ingestion (200), exact count derivations (N=8, top-four=0.5, average=4.5), unchanged replay, synthetic-only scoped retrieval, no observed rows, wrong-patch rejection (422), missing-token rejection (401), source revocation blocking direct read (403) and hiding list entries. Test grants and numbers are inventions clearly labeled synthetic; they are not real permissions or match evidence.
- Actual HTTP checks against the normal backend: default source list empty, ingestion disabled (503), observed result empty and unavailable. No synthetic statistics were inserted into the normal database.
- Re-ran `PYTHONPATH=. ../../.venv/bin/python tests/live_review.py` against the normal backend and production frontend: independent TFT/JCC fixtures, three-emblem solves in all five modes (five candidates per mode/game), legal constraints/trait/assignment checks, holder ranking, reforge boundaries and existing page statuses passed. Existing exhaustive brute-force reference cases were rerun in pytest.

HTTP evidence: `docs/statistics-http-verification.json`. Legacy API evidence: `docs/review-api-results.json`. No new browser interaction/layout assertions are claimed for this backend-only increment.

## Statistical test coverage actually executed

Strict numeric/finite validation; no booleans/string/fractional counts; unknown/empty samples; real zero counts and Wilson boundary cases; missing point values remain null; no counts reconstructed from rounded rates; histogram/sample/count/sum consistency; placement/top-four feasibility; provider-reported intervals and range/level/method checks; known Wilson reference values; suppression for clustered/unknown independence and absent derive permission; operational low-N/stale/coverage flags; timezone and collection-time validation; empty observed metric records do not claim available performance statistics.

Exact game/ruleset/patch/set/mode isolation; both TFT/JCC ingestion with first-party source-kind tests; separate providers and patch IDs; holder/composition/subset context and canonical ordering; foreign/unknown IDs; illegal equipment/slot limits; absent, malformed, expired, disabled, disallowed or changed licenses; registry/token gate; immutable ID replay/conflict and rollback; four concurrent identical ingestions; pagination/context filtering; revocation on read; catalog fingerprint changes; body/record bounds; machine-readable OpenAPI input schema; preservation of optimizer scores/null statistics and separation from community records.

Tests exercising `observed` paths deliberately use a simulated verified catalog and invented authorization inside isolated test databases. They test validation logic, not actual source approval or current-patch validity.

## Remaining limitations / not verified

No real licensed provider export, first-party API credentials, production registration, verified production catalog, actual observed statistics, live fetch adapter, raw-match aggregation or statistical scoring integration. No PostgreSQL, browser matrix, external deployment, multi-process stress or production performance test. Source permission and sampling claims require operator/provider review; the software does not authenticate a contract or independently prove sampling/deduplication/patch membership. Authorization revocation hides data but does not automate license-specific purging. Scoped authorized totals scan matching rows. A Starlette/httpx TestClient deprecation warning remains; tests passed.

All test-owned API/frontend processes were stopped after verification. The normal database retains the additive schema migration; test statistics remain isolated in disposable QA databases. Restart using README and configure only genuinely authorized sources as documented in STATISTICS_INGESTION.md.
