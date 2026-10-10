# Verification — 2026-10-10
Environment: bundled Python 3.12.14; Node 24.14.0; Next.js 15.5.27; OR-Tools 9.15.6755. Exact dependency snapshots: services/api/requirements.lock.txt and apps/web/package-lock.json.

Executed successfully:
- Python venv creation and pip installation; npm install.
- `alembic upgrade head`, manual JSON import for both fixture catalogs, and a second migration into a fresh temporary SQLite database.
- `pytest -q`: **35 passed**, including brute-force objective comparisons for all 5 modes, capacity, OR counting, equipment legality/slots, constraints, isolation, infeasibility, timeout statuses, diversity, unknown statistics/probabilities, API validation, JSON database round-trip and unsupported unlock rejection.
- `ruff check app tests`: passed. Python sources formatted with Ruff.
- `npm run typecheck`: passed; `npm run lint`: passed without warnings; `npm run build`: passed, all 5 application pages built.
- HTTP checks: health and frontend returned 200.
- In-app browser manual smoke checks: select 3 TFT emblems, solve, observe 5 OPTIMAL diverse candidates; add 2 candidates to comparison and observe champion/holder differences; view comparison at 390×844; switch to JCC and observe distinct names/duplicate policy; generate all 8 retained subsets; solve JCC and observe 5 OPTIMAL candidates. Viewport reset afterward. Screenshot: preview.png.

The sole pytest warning is a Starlette TestClient/httpx deprecation in the installed dependency combination; all tests pass. No automated full browser suite, PostgreSQL run, current-game dataset validation or external deployment was claimed. Alembic's missing app import path was fixed using prepend_sys_path before migration verification.
Preview servers were used only for local QA. Start using README commands for continued use.

## Subsequent MVP review
Fresh review: **56 backend tests passed**, frontend checks/build passed, live API auditing and desktop/mobile browser regressions passed. See [MVP_REVIEW.md](MVP_REVIEW.md) for executed cases, repaired defects and explicit untested areas. The 35-test result above belongs to the earlier implementation run.
