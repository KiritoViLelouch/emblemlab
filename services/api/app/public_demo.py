"""Opt-in public preview restrictions; the local API retains its original behavior."""
import json
import os
from threading import BoundedSemaphore

from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from app.repositories.catalog import get_catalog
from app.schemas.domain import SolveRequest

SLOTS = BoundedSemaphore(2)
READ_PATHS = {"/health", "/api/v1/games", "/api/v1/catalog", "/api/v1/data-health"}
WEB_PATHS = {"", "/catalog", "/compare", "/data", "/about", "/guides"}
SOLVE_PATHS = {"/api/v1/solve", "/api/v1/holders/rank"}


def public_demo_enabled():
    return os.getenv("PUBLIC_DEMO", "false").lower() == "true"


async def public_preview(request: Request, call_next):
    if not public_demo_enabled() or request.method == "OPTIONS":
        return await call_next(request)
    path = request.url.path.rstrip("/")
    web_asset = os.getenv("PUBLIC_WEB_DIR") and (path in WEB_PATHS or path.startswith("/_next/"))
    if request.method == "GET" and (path in READ_PATHS or web_asset):
        return await call_next(request)
    if request.method != "POST" or path not in SOLVE_PATHS:
        return JSONResponse({"detail": "朋友测试版未开放此接口"}, status_code=403)
    raw = await request.body()
    if len(raw) > 65536:
        return JSONResponse({"detail": "请求过大"}, status_code=413)
    try:
        payload = SolveRequest.model_validate(json.loads(raw))
        dataset = get_catalog(payload.game_id, payload.ruleset_id)
        if payload.timeout_seconds > 5 or payload.top_k > 5:
            raise ValueError("朋友测试版最多求解 5 秒、返回 5 个方案")
        if not dataset.data_readiness or not dataset.data_readiness.optimization_enabled:
            raise ValueError("关键规则尚未验证，暂不开放优化")
    except (ValueError, ValidationError) as exc:
        return JSONResponse({"detail": str(exc)}, status_code=422)
    if not SLOTS.acquire(blocking=False):
        return JSONResponse({"detail": "求解服务忙，请稍后重试"}, status_code=429, headers={"Retry-After": "5"})
    try:
        return await call_next(request)
    finally:
        SLOTS.release()
