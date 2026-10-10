# Phase 2 community importer verification

Executed locally on 2026-10-10. Scope is the first Phase 2 increment: CSV/XLSX community recommendations and manual label review. Broader catalog activation/statistical ingestion were not implemented.

## Automated checks actually executed

- Backend: `../../.venv/bin/pytest -q` from `services/api`: **86 passed** (56 existing optimizer/MVP tests plus 30 importer cases).
- `../../.venv/bin/ruff check app tests`: passed.
- Frontend `npm run typecheck`, `npm run lint`, `npm run build`: all passed; `/guides` included in production output.
- Alembic upgrade of the existing local SQLite database: revision `0002 (head)` confirmed. Automated test upgraded a fresh database to `0001`, seeded an existing game record, upgraded to `0002`, verified preservation, downgraded to `0001`, then upgraded again.
- Import tests executed UTF-8 BOM Chinese CSV/XLSX equivalence, sheet selection, game isolation, exact/ambiguous/unknown label matching, illegal holder detection, icon-only review, immutable raw whitespace, actual manual label changes, confirmation/draft states, correction audit/revision conflicts, catalog fingerprint changes, idempotency including four concurrent identical imports, multipart endpoints/CORS/error codes, malformed/oversized files, CSV formulas, XLSX formula/numeric/error cells, external links/macros and archive/dimension limits.
- A before/after guide-import solver comparison preserved the objective and trait output. The importer left the versioned record/statistics store empty in its isolated database; community data only entered the new tables.
- Ran `PYTHONPATH=. ../../.venv/bin/python tests/live_review.py` against the running backend and frontend: both fixture catalogs, three-emblem optimization in all five modes for each game (five candidates each), constraints, holder ranking, reforge boundary and existing page responses passed. Results remain in `docs/review-api-results.json`. The existing exhaustive small-fixture oracle tests were also rerun in the backend suite.
- CLI import executed successfully against the migrated local database; returned an attributed, versioned batch with a pending uncertain holder.

## Browser actions actually executed

Using the Codex in-app browser against local servers:

- Desktop 1440×1000: uploaded the checked-in CSV through the file chooser, saw the unresolved holder, corrected it to `tft_unit_1`, supplied reviewer/rationale and confirmed. UI showed `reviewed`, revision 2, zero pending rows, unchanged original holder text and before/after audit history.
- Switched to JCC: TFT imports disappeared and the independent JCC list was empty.
- Mobile 390×844: uploaded a generated independent OOXML JCC fixture through the file chooser. UI showed canonical JCC emblem/holder IDs with `matched` (still unverified) status and community/not-statistics labeling.
- Final production build smoke check: reopened the persisted TFT correction and expanded the correction form at 320px; reviewed status/revision survived reload and the form had no horizontal overflow.
- Measured document widths at 1440, 390 and 320 pixels: no horizontal overflow for the observed pages. Saved and visually inspected desktop and mobile screenshots.

Evidence: `docs/screenshots/community-desktop.png` and `docs/screenshots/community-mobile.png`. Browser checks are manual tool-driven checks, not a committed CI browser automation suite. The generated XLSX is a minimal test workbook, not a real community author's Excel export.

## Remaining limitations

Synthetic catalogs only; no verified current-patch community data or statistics. Icon references are opaque text, with no image fetching/OCR. Exact matching only; uncertain labels require human correction. Attribution/license and reviewer identity are self-declared. One source per file, bounded files, no list/history pagination or bulk editing. Original uploaded bytes/styles are not archived. No PostgreSQL, cross-browser matrix, full load test, real third-party workbooks, or external deployment verification was performed. The local API has no authentication and should remain bound to loopback. A Starlette/httpx TestClient deprecation warning remains; tests passed. See COMMUNITY_IMPORT.md for the full format and boundaries.

QA-owned local servers were stopped after verification. Restart with the README commands; run migrations before starting after an update.
