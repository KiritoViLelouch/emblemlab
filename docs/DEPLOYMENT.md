# 朋友测试版发布

状态：**本地验证完成，尚未发布到公网**。当前没有 GitHub 发布凭据，已选择 Render 免费方案，但尚未登录托管账户。

## 结构

保留现有 Next.js + FastAPI + OR-Tools CP-SAT。GitHub Pages 只托管静态前端，Python 后端必须独立运行，不能仅上传 HTML 就宣称优化器可用。

- 前端：GitHub Pages，支持 `/仓库名/` 子路径和各页面直接打开。
- 后端：`Dockerfile.api`，Python 3.12，固定依赖，真实 TFT 规范化快照，非 root 用户，单 Uvicorn worker。
- `render.yaml` 提供可选 Render Free 后端配置；尚未创建服务或产生托管费用。免费服务闲置后休眠、首次请求有冷启动，实际内存/CPU适配仍须部署后验证。
- 不依赖本机 SQLite、原始大快照、人工上传文件或本机路径。社区导入和统计 API 不对外开放。

## 发布配置

GitHub 仓库根目录应为 **emblemlab 目录的内容**，包含 `.github/`、`apps/`、`services/` 和 `data/`。当前父目录的 Git 仓库没有 remote，不能直接将父目录全部推送。

1. 在 GitHub 建立/选定独立仓库（建议 `emblemlab`），推送本目录；保留之前的 `what-to-eat` 网站。
2. 登录选择的后端托管账户。Render 可从该仓库建立 Blueprint，使用 `render.yaml`；仅选择 Free，不开启付费升级。确认账户预算/费用设置后创建服务。
3. 设置后端 `CORS_ORIGINS=https://<GitHub用户名>.github.io`，**只有 origin，没有仓库子路径或末尾斜线**。自定义域名需使用其精确 origin。
4. 后端 `PUBLIC_DEMO=true`，启动命令单 worker，`PORT` 由托管平台注入。
5. GitHub Settings → Pages → Source 选 GitHub Actions。
6. GitHub Settings → Secrets and variables → Actions → Variables 添加 `NEXT_PUBLIC_API_URL`，值为实际后端 HTTPS origin，无末尾斜线。此地址公开，不应包含令牌。
7. 运行 `Publish friend preview` 工作流。工作流自动从 Pages 配置读取 `base_path`，构建 `apps/web/.next-export` 并发布。
8. 公网验收：分别打开首页、图鉴、数据状态；手机检查；运行一次真实三纹章优化；检查 CORS 和不可用的上传接口。成功后才向朋友提供实际 Pages 地址。

没有 API URL 时导出立即失败，防止发布仍指向朋友自己 `127.0.0.1` 的网页。前端环境变量在构建时固定；后端地址变化后须重新发布前端。回滚使用 GitHub 的旧提交重新运行工作流，后端按托管平台回滚同版本；不要混用规则版本。

## 公开测试范围

设置 `NEXT_PUBLIC_PUBLIC_DEMO=true` 显示测试说明、隐藏合成数据入口和上传/修改表单；JCC 明确未开放。

服务端 `PUBLIC_DEMO=true` 独立强制执行：

- 目录只返回真实 TFT 数据；即便 `include_synthetic=true` 也不能访问 fixture。
- 只开放 health、games、catalog、data-health 读取和 solve、holders/rank 求解。
- 导入、修改、统计和重铸接口均返回 403；无法绕过前端直接调用。
- 每次最多 5 秒、5 个候选，单进程最多两次并发求解；繁忙时返回 429 和 Retry-After。
- 请求体解析后拒绝超过 64 KiB 的求解内容。此功能并非抗 DDoS 网关；扩大公开规模前应在托管入口增加速率/请求体限制。
- 本地未设置公开模式时保留原 API、开发 fixtures 和导入行为。

## 已执行验证（2026-10-10）

- 后端完整回归：293 passed（新增公开模式19项），Ruff通过；一个上游 Starlette/httpx 弃用警告。
- 公开模式实际 CP-SAT 请求连续两次返回候选，不是 mock。
- 前端 typecheck、lint、静态导出成功；以 `/emblemlab` 子路径构建。
- 本地 HTTP 验收：6 个静态页面、页面引用的构建资源均返回 200；三枚真实纹章 CP-SAT 求解及跨 origin CORS 实测通过，见 `evidence/public_preview_http.json`。
- 浏览器视觉/点击验收：本轮浏览器导航超时，未确认通过；不能将 HTTP 资源检查当作视觉验收。
- 公网 GitHub Actions、Render 容器构建、远程 CPU/内存、HTTPS/CORS、好友访问：**未执行**。
- 本机 Docker 引擎不可用（Docker CLI info 异常退出），因此未宣称镜像构建或容器测试通过。

## 参考

- GitHub Pages 静态托管：https://docs.github.com/en/pages/getting-started-with-github-pages/what-is-github-pages
- Next 静态导出：https://nextjs.org/docs/app/guides/static-exports
- Render Free 限制：https://render.com/docs/free
- Render Blueprint：https://render.com/docs/blueprint-spec
