import os
import secrets
from typing import Annotated, Literal
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool
from app.statistics import service
from app.statistics.providers import active, registry
from app.statistics.schemas import IngestRequest, Scope

router = APIRouter(prefix="/api/v1/statistics", tags=["authorized statistics"])
MAX_REQUEST_BYTES = 2 * 1024 * 1024


def guarded(fn):
    try:
        return fn()
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    except FileExistsError as exc:
        raise HTTPException(409, str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc


def ingestion_access(authorization: Annotated[str | None, Header()] = None):
    token = os.getenv("STATISTICS_INGEST_TOKEN")
    if not token:
        raise HTTPException(503, "Statistics ingestion disabled: configure operator token and approved sources")
    if authorization is None or not secrets.compare_digest(authorization.encode(), ("Bearer " + token).encode()):
        raise HTTPException(
            401, "Statistics ingestion requires the operator bearer token", headers={"WWW-Authenticate": "Bearer"}
        )


def ingestion_schema():
    """Inline definitions for a self-contained OpenAPI body schema (streaming route)."""
    schema = IngestRequest.model_json_schema()
    definitions = schema.pop("$defs", {})

    def expand(value):
        if isinstance(value, list):
            return [expand(item) for item in value]
        if isinstance(value, dict):
            if "$ref" in value:
                return expand(definitions[value["$ref"].rsplit("/", 1)[1]])
            return {
                key: ({"propertyName": item["propertyName"]} if key == "discriminator" else expand(item))
                for key, item in value.items()
            }
        return value

    return expand(schema)


@router.post(
    "/ingest",
    dependencies=[Depends(ingestion_access)],
    openapi_extra={"requestBody": {"required": True, "content": {"application/json": {"schema": ingestion_schema()}}}},
)
async def ingest(request: Request):
    if request.headers.get("content-type", "").split(";")[0].strip().lower() != "application/json":
        raise HTTPException(415, "Expected application/json")
    content = bytearray()
    async for chunk in request.stream():
        if len(content) + len(chunk) > MAX_REQUEST_BYTES:
            raise HTTPException(413, "Statistics batch exceeds 2 MiB")
        content.extend(chunk)
    try:
        body = IngestRequest.model_validate_json(bytes(content))
    except ValidationError as exc:
        # Do not echo untrusted input or private export contents in errors.
        raise HTTPException(422, exc.errors(include_input=False, include_context=False)) from exc
    return await run_in_threadpool(guarded, lambda: service.ingest(body))


@router.get("/sources")
def sources():
    def read():
        return [
            dict(
                provider_id=s.provider_id,
                name=s.name,
                source_kind=s.source_kind,
                attribution=s.attribution,
                license_id=s.license_id,
                scopes=[v.model_dump() for v in s.scopes],
                data_kinds=s.data_kinds,
                context_kinds=s.context_kinds,
                metrics=s.metrics,
                valid_until=s.valid_until.isoformat(),
                permitted_uses=s.permitted_uses,
            )
            for s in registry()
            if active(s) and {"store", "display"} <= set(s.permitted_uses)
        ]

    return guarded(read)


@router.get("/observations")
def observations(
    game_id: Literal["TFT", "JCC"],
    ruleset_id: str,
    patch: str,
    set_id: str,
    mode: str,
    provider_id: str | None = None,
    data_kind: Literal["observed", "synthetic"] = "observed",
    context_kind: Literal["holder", "composition"] | None = None,
    context_key: Annotated[str | None, Query(pattern=r"^[a-f0-9]{64}$")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    return guarded(
        lambda: service.observations(
            Scope(game_id=game_id, ruleset_id=ruleset_id, patch=patch, set_id=set_id, mode=mode),
            provider_id,
            data_kind,
            context_kind,
            context_key,
            limit,
            offset,
        )
    )


@router.get("/observations/{record_id}")
def observation(record_id: str):
    return guarded(lambda: service.observation_by_id(record_id))
