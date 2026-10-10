# EmblemLab · 纹章实验室
Runnable local offline strategy optimizer. Phase 0/1 optimizer plus community guide import, the Phase 3 statistics ingestion API, and the Phase 4 versioned reforge analyzer.
**Phase 2A now includes a fixed real TFT Set 18 / patch 18.4 / standard snapshot (Riot resources 16.20.1 + CommunityDragon 16.20). The catalog is PARTIALLY_VERIFIED with explicit restricted counting rules. JCC has no enabled real dataset. Original synthetic fixtures remain available through development opt-in.**

Source/import format: [REAL_DATA_SOURCES.md](docs/REAL_DATA_SOURCES.md). Coverage and restrictions: [DATA_COVERAGE.md](docs/DATA_COVERAGE.md). Executed checks: [VALIDATION_REPORT.md](docs/VALIDATION_REPORT.md).

## Requirements
Python 3.12+ and Node.js 20.9+ / npm. No keys or external services. Initial package installation needs internet; runtime solving is local. The workspace's bundled Python 3.12 was used during verification because system `python3` is 3.9.

## Start locally
Terminal 1, from this repository's `emblemlab` directory:
```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r services/api/requirements.txt
cd services/api
../../.venv/bin/alembic upgrade head
../../.venv/bin/python -m app.importers.manual ../../data/fixtures/tft/v1.json
../../.venv/bin/python -m app.importers.manual ../../data/fixtures/jcc/v1.json
../../.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
```
Terminal 2, from `emblemlab`:
```sh
cd apps/web
npm ci
npm run dev
```
Open http://127.0.0.1:3000. API docs: http://127.0.0.1:8000/docs.
After updating, install the updated requirements and run `alembic upgrade head` before starting the backend.

Optional configuration: `.env.example` describes variables. Export backend variables in its shell; copy the frontend variable to `apps/web/.env.local`. Default URLs work without configuration. `DATABASE_URL` may point to PostgreSQL with an installed matching SQLAlchemy driver; PostgreSQL has not been run in this milestone.

## Verify
```sh
cd services/api
../../.venv/bin/pytest -q
../../.venv/bin/ruff check app tests
cd ../../apps/web
npm run typecheck
npm run lint
npm run build
```
Production frontend: `npm run build` then `npm start`. Python dependencies are range constrained in requirements.txt; the exact verified environment is in requirements.lock.txt. `npm ci` uses package-lock.json.

## Features
- Real TFT: 74 canonical champion records (including Lux forms), 36 traits and 21 emblem records, bilingual names and official icon references. Enabled under the restricted profile: 71/34/20. TFT/JCC development fixtures remain separate (14/7/7 each).
- Up to three emblem instances; TFT example allows duplicates, JCC example disallows them.
- Exact 7/8/9/10 champion board, locks, exclusions, maximum unit cost, legal equipment and item slots.
- Real OR-Tools CP-SAT; five objective modes, diverse Top-K, transparent status, bounds, estimates and assignments.
- Catalog, same-ruleset two-composition comparison in localStorage, version/data-health and methodology pages.
- Holder ranking under candidate equipment constraints; hypothetical retained subsets with instance locks; version-aware reforge scenario analysis with actual CP-SAT outcomes, unknown-probability scenarios and conditional expected rule scores.
- Versioned SQLAlchemy JSON entity store, Alembic migration, validated manual fixture JSON import/export, human-confirmed icon-label metadata without guessed mappings.

- CSV/XLSX community guide upload, attribution, per-version label resolution and audited manual correction at `/guides`; separate from statistics and solver inputs.

- Provider-neutral, permission-gated statistical observations with exact patch isolation, sample counts, top-four rate, average placement, holder/composition context, confidence and quality flags. Default source registry is empty; no live data is bundled. See [statistics contract and assumptions](docs/STATISTICS_INGESTION.md).

## API
`GET /health`, `GET /api/v1/games`, `GET /api/v1/catalog?game_id=TFT&ruleset_id=fixture_tft_v1`, `POST /api/v1/solve`, `POST /api/v1/holders/rank`, `POST /api/v1/reforge/simulate`, `GET /api/v1/data-health`.
```sh
curl -X POST http://127.0.0.1:8000/api/v1/solve -H 'Content-Type: application/json' -d '{"game_id":"TFT","ruleset_id":"fixture_tft_v1","emblem_ids":["tft_emblem_0","tft_emblem_1","tft_emblem_2"],"board_size":8,"objective":"MAX_ACTIVE_TRAITS","top_k":3}'
```
Reforge request extends solve with `locked_emblem_indices: [0]`, `action: "retained_subsets"`. Three inputs always enumerate eight subsets, marking lock-incompatible ones disallowed. Probabilities and EV are null. `actual_reforge` returns 422.
JSON export example (from services/api):
```sh
../../.venv/bin/python -c "from app.importers.manual import export_json; export_json('TFT','fixture_tft_v1','export.json')"
```
The API intentionally reads validated checked-in real catalog and fixture JSON, while SQLite stores imported snapshots. Database-backed catalog activation remains deferred; importing a snapshot does not change the active catalog.

## Limitations
Fixed real TFT static data is available for a restricted precombat count profile; complete game rules, live statistics, special unlock evaluation, formation modeling and ability compatibility remain unavailable. Artwork uses remote official references with text fallback. Unknown/special trait mechanics are blocked; locked unavailable units make the model infeasible. Cost is a simple theoretical-ceiling proxy, not combat strength. Holder recommendations are local alternatives with other candidate assignments fixed. Total solve budget applies across Top-K; subset analysis has a separate bounded solve per allowed subset. Runtime schemas reject invalid input; returned compositions are independently validated by the rule evaluator. Community CSV/XLSX recommendations are available separately; OCR, verified production reforge rules and adaptive reforge policies remain deferred.

Phase 2 added community guide imports. Phase 3 adds the statistics ingestion boundary; see [source audit](docs/STATISTICS_SOURCE_AUDIT.md) and [Phase 3 verification](docs/PHASE3_VERIFICATION.md). See [import format and review workflow](docs/COMMUNITY_IMPORT.md) and [executed verification](docs/PHASE2_VERIFICATION.md). Database-driven catalog activation remains deferred. Real static catalog generation is documented in Phase 2A.

Phase 4 adds `GET /api/v1/reforge/rules` and `POST /api/v1/reforge/analyze`, plus a scenario panel on the optimizer page. The legacy simulate API is preserved. Only synthetic laws ship; unknown probabilities never receive numeric EV. See [reforge contract and assumptions](docs/REFORGE_ANALYSIS.md) and [Phase 4 verification](docs/PHASE4_VERIFICATION.md).

## 分享给朋友测试

已上线：[GitHub 测试网站](https://kiritovilelouch.github.io/emblemlab/)，[Render 备用入口](https://emblemlab.onrender.com/)。Python 求解器独立运行于 Render Free，电脑关机后仍可访问；闲置后的第一次请求可能需要等待冷启动。当前仅开放固定版本 TFT，金铲铲尚未开放。发布方式、实际测试和限制见 [部署说明](docs/DEPLOYMENT.md)。

## JCC 审核启用与拉克丝对照

JCC 当前状态 **BLOCKED**：尚无获得公开发布授权的完整真实版本数据，实际导入为 **0 棋子 / 0 羁绊 / 0 纹章**。已实现 CSV/XLSX/规范化 JSON → 独立审核 → 固定快照 → 原子启用/回滚 → 目录/API/前端的完整软件流程；不能把合成测试通过视为 JCC 已上线。来源核查见 [JCC_SOURCE_AUDIT.md](docs/JCC_SOURCE_AUDIT.md)，操作见 [JCC_IMPORT_GUIDE.md](docs/JCC_IMPORT_GUIDE.md)，结果见 [JCC_VALIDATION_REPORT.md](docs/JCC_VALIDATION_REPORT.md)。

TFT 页面默认“不带拉克丝”；可选择已获得的指定羁绊形态，或点击“计算不带 / 带指定拉克丝两版”。两版各用真实 CP-SAT 求解并可加入对比。五费卡及指定形态不保证可获得，结果是各自假设下的规则估分；不计算 D 牌概率。
