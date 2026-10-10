# EmblemLab conventions
- Scope: Phase 0/1, Phase 2 community guide import, Phase 3 provider-neutral statistics ingestion API, and the user-authorized Phase 4 versioned reforge analyzer. Phase 2A real static-data integration is user-authorized. Offline hypothetical training and review; no live client integrations or game automation.
- Python >=3.12, Next.js/TypeScript; Chinese first, English names kept in versioned catalogs.
- Run from services/api: `../../.venv/bin/pytest -q` and `../../.venv/bin/ruff check app tests`.
- Run from apps/web: `npm run typecheck`, `npm run lint`, `npm run build`.
- Solver has no FastAPI imports. Dataset rules belong in RuleEvaluator and validated schemas.
- Every game record carries game, patch, set, mode, source, import timestamp and verification.
- Reject cross-game IDs. Never fabricate current game data, statistics, probabilities, assets or licenses.
- No scraping third-party sites, private APIs, authentication bypass, memory reads, packets, client modifications or gameplay automation.
- Document architecture choices in docs/ARCHITECTURE.md. Keep fixture changes covered by solver/reference tests.
