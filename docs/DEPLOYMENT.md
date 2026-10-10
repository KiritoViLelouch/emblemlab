# 朋友测试版发布

发布于 2026-10-10，保留现有 Next.js、FastAPI 和 OR-Tools CP-SAT 架构。

- 分享入口：[GitHub Pages](https://kiritovilelouch.github.io/emblemlab/)。
- 同源备用入口：[Render](https://emblemlab.onrender.com/)，网页与求解 API 一起运行。
- 源码：[KiritoViLelouch/emblemlab](https://github.com/KiritoViLelouch/emblemlab)，默认分支 `codex/friend-preview`。
- 只开放固定 TFT 数据集 `tft_set18_18_4_standard`（18.4），74 个棋子实体、36 个羁绊、21 个纹章。该集合包含不同形态实体，74 不是可同时上场的独立英雄数量。目录为 PARTIALLY_VERIFIED，保守禁用尚未支持的规则；不宣称完整游戏模拟或当前实时版本。
- JCC 未开放；不显示合成 fixtures 为实服数据。评分是静态羁绊启发式，不是胜率。

## 实际托管配置

Render 服务 `srv-db52m1bbc2fs73e3s4cg`，Singapore，Docker，**Free**，一个实例、一个 Uvicorn worker；不依赖用户电脑在线。根目录 Dockerfile 先构建 Next 静态网页，再复制到 Python 镜像，由 FastAPI 在 API 路由之后挂载。

- `PUBLIC_DEMO=true`
- `PUBLIC_WEB_DIR=/srv/emblemlab/public`
- `CORS_ORIGINS=https://kiritovilelouch.github.io`（只有 origin，没有仓库路径）
- Docker 前端构建：`STATIC_EXPORT=true NEXT_PUBLIC_PUBLIC_DEMO=true NEXT_PUBLIC_API_URL=same-origin`
- `/health` 为平台健康检查；`PORT` 由平台注入。
- 服务构建过滤忽略 `docs/**`。本次使用 Render CLI 创建、明确提交部署；没有通过仓库集成验证自动部署，源码更新后应检查并显式触发部署。
- `render.yaml` 是可选 Blueprint 模板；现有服务由 CLI 创建，名称、地区和分支以本节为准，勿重复创建服务。

免费实例闲置会休眠，首次求解可能等待冷启动。测试版每次最多求解 5 秒、返回 5 个候选，单进程最多两次并发；忙时返回 429。请求体解析后拒绝超过 64 KiB 的求解内容，并非入口抗 DDoS 限制。CPU、内存和并发压力测试未执行；仅适合少量朋友试用。

## GitHub Pages 发布方式

账号 GitHub Actions 构建曾返回：`The job was not started because your account is locked due to a billing issue.` 因此本次改为**本地构建后发布独立静态分支**，未开通付费服务。

Pages 当前配置为 `build_type=legacy`，来源 `codex/pages-static` 根目录，包含 `.nojekyll`；GitHub Pages 构建 API 确认 `built`，随后实际 HTTPS 页面及资源检查通过。静态发布提交 `aa86ca82521f2ad27070429713ddc417fcaafd8b`；它是独立生成产物，不要合并进源码分支。

更新前端：在 `apps/web` 执行 `npm ci`、`npm run typecheck`、`npm run lint`，再用以下环境构建：

```sh
STATIC_EXPORT=true NEXT_PUBLIC_PUBLIC_DEMO=true NEXT_PUBLIC_BASE_PATH=/emblemlab NEXT_PUBLIC_API_URL=https://emblemlab.onrender.com npm run build
```

将 **`apps/web/.next-export/`** 的内容更新到独立静态分支，保留 `.nojekyll`，推送后检查 Pages 构建和公网资源。不要上传 `.next/`、源码、凭据或数据库。构建变量固定在 JS 中；后端地址变化后必须重新发布前端。

`.github/workflows/pages.yml` 保留供未来 Actions 恢复使用；启用前须将 Pages source 改回 GitHub Actions。`NEXT_PUBLIC_API_URL` 仓库变量已设置为实际 Render 地址。当前 Pages 使用静态分支，不依赖此工作流成功。

更新后端：推送源码分支，用 `render deploys create srv-db52m1bbc2fs73e3s4cg --commit <完整提交SHA> --confirm`，检查部署为 live，并重新执行公网求解验证。回滚同样明确指定旧提交，前后端规则版本保持一致。

## 公开模式边界

前端显示测试说明，隐藏合成数据入口、上传与修改表单、未开放的重铸分析；JCC 明确标为尚未开放。

服务端独立执行限制，无法绕过前端访问：

- 只提供已审核且通过激活校验的真实目录；目前只有 TFT。即使 `include_synthetic=true` 也不返回 fixture。
- 开放 health、games、catalog、data-health 读取和 solve、holders/rank 求解。
- 目录关键规则未验证时拒绝优化；限制超时及候选数量。
- 导入、修改、统计、重铸和 API 文档接口返回 403。
- 固定网页及 `/_next/` 资源可 GET/HEAD；HEAD 不开放管理 API。
- 本地不设置公开模式时保留原 API、开发 fixtures 和导入行为。

## 已执行验证

详见 `evidence/public_cloud_preview_http.json`（公网）及 `evidence/same_origin_preview_http.json`、`evidence/public_preview_http.json`（本地）。公开测试从实际 HTTPS 地址请求，没有 mock 求解器。

- 后端完整回归：`cd services/api && ../../.venv/bin/pytest -q`；294 passed，一个上游 Starlette/httpx 弃用警告。
- `../../.venv/bin/ruff check app tests` 通过。
- HEAD 修复定向回归：公开模式 20 项通过，包括静态页面/资源 HEAD 及管理 API 仍关闭。
- 前端 `npm run typecheck`、`npm run lint`、`npm run build` 通过；另已成功构建 Pages 子路径及 Render 同源静态版本。
- Render 实际云端 Docker 镜像构建成功，健康检查正常。
- GitHub Pages 与 Render 各六个页面、各 14 个页面引用资源 HTTPS 200；构建 JS 未包含本机 API 地址。
- 公网一枚及三枚真实纹章实际 CP-SAT 返回 FEASIBLE 候选。下载同版本目录后独立调用规则校验，复核上场容量、纹章持有者和完整羁绊计数。
- GitHub origin 的实际 POST CORS 响应与 OPTIONS 预检通过。
- 公网合成版本、无效纹章、JCC 请求被拒绝；管理、导入、重铸接口关闭。

**未执行：**本轮浏览器视觉/点击验收（浏览器控制持续超时）、真机手机测试、朋友设备访问、负载测试。HTTP 检查不等于这些测试通过。本机 Docker 引擎不可用，未执行本机容器运行；实际 Render 云端构建已执行。

## 参考

- [GitHub Pages](https://docs.github.com/en/pages/getting-started-with-github-pages/what-is-github-pages)
- [Next 静态导出](https://nextjs.org/docs/app/guides/static-exports)
- [Render Free 限制](https://render.com/docs/free)
- [Render Blueprint](https://render.com/docs/blueprint-spec)

## JCC registry / Lux release follow-up

Feature branch `codex/jcc-catalog-activation` starts at `ade8717`; pre-change Render commit is `43f448d0fee19c8de3d701aa593acc04aadde822`, pre-change Pages artifact commit `aa86ca82521f2ad27070429713ddc417fcaafd8b`. `docs/evidence/jcc_prechange_baseline.json` records the actual public TFT three-emblem response before changes. Source TFT JSON and fixtures were not edited.

The image now includes `data/active/` and `data/approved/`. Promote JCC only offline after explicit review; commit artifacts, registry and history together. No runtime SQLite activation or ephemeral Render write is required. JCC stays unavailable while the registry is empty. Public mode permits approved games and continues to reject imports/admin/statistics/reforge.

Code rollback: explicitly deploy Render commit `43f448d0fee19c8de3d701aa593acc04aadde822`. Pages rollback: restore files from `aa86ca82521f2ad27070429713ddc417fcaafd8b` into a **new** `codex/pages-static` commit and push normally (do not reset or force-push history). Registry-only rollback uses the offline command in JCC_IMPORT_GUIDE.md followed by a normal source commit/deploy.


### 2026-10-10 JCC workflow / Lux update — deployed

Source `b22dd3ac58a6b5297c87122fc80c078ae3a6391f` was pushed by normal fast-forward to `codex/friend-preview`. Render deployment `dep-db5376942hec73fib810` is **live**. Prebuilt Pages artifact `9c3082fdcc42f034e7a227baf39edfdac9f27f4a` on `codex/pages-static` is **built**. GitHub Actions billing lock was not changed; static branch publication remains the release path.

New actual verification: 333 backend tests, Ruff, frontend typecheck/lint/build, 5 Lux policy tests, same-origin and Pages exports passed. Local browser clicked real three-emblem paired Lux solves, saved comparison, and checked desktop/390/412px layouts. Public HTTPS suite checked both sites' six pages/fourteen assets, two real constrained Lux solves, independent trait recount, CORS, data registry and public-mode boundaries. See `evidence/jcc_release_public_http.json` and `JCC_VALIDATION_REPORT.md`.

Public browser control timed out, so public click/visual acceptance remains **not executed**. Genuine JCC data remains **BLOCKED**, zero active JCC records; no synthetic catalog was activated. TFT remains a reviewed restricted 18.4 snapshot, not a claim of current live-patch or every mechanic support. The rollback revisions above remain valid.
