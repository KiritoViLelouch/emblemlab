"""Transactional ingestion and exact version queries. No aggregation or solver coupling."""

import hashlib
import json
from collections import Counter
from datetime import timedelta
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from app.models.database import Session
from app.models.statistics import StatisticsRecord
from app.repositories.catalog import get_catalog
from app.rules.evaluator import FixtureRules
from app.statistics.providers import authorize, check_fields, registry, utcnow
from app.statistics.quality import summarize
from app.statistics.schemas import Observation, Scope


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def catalog_for(scope):
    catalog = get_catalog(scope.game_id, scope.ruleset_id)
    if (scope.patch, scope.set_id, scope.mode) != (catalog.patch, catalog.set, catalog.mode):
        raise ValueError("Game/ruleset/patch/set/mode must match exactly; no patch fallback")
    return catalog


def validate_context(observation, catalog):
    champions = {c.id: c for c in catalog.champions}
    emblems = {e.id: e for e in catalog.emblems}
    context = observation.context
    assignments = []
    board = context.composition
    if board:
        if not set(board.champion_ids) <= champions.keys():
            raise ValueError("Unknown or cross-game composition champion ID")
        assignments = board.emblem_assignments
    if context.kind == "holder" and not board:
        assignments = [context]
    if context.kind == "holder" and (context.champion_id not in champions or context.emblem_id not in emblems):
        raise ValueError("Unknown or cross-game holder/emblem ID")
    for assignment in assignments:
        if assignment.champion_id not in champions or assignment.emblem_id not in emblems:
            raise ValueError("Unknown or cross-game assignment ID")
        if not FixtureRules().legal(champions[assignment.champion_id], emblems[assignment.emblem_id]):
            raise ValueError("Illegal holder/emblem assignment in this ruleset")
    slots, same, copies = Counter(), Counter(), Counter()
    for assignment in assignments:
        slots[assignment.champion_id] += 1
        same[assignment.champion_id, assignment.emblem_id] += 1
        copies[assignment.emblem_id] += 1
        if slots[assignment.champion_id] > champions[assignment.champion_id].item_slots:
            raise ValueError("Composition exceeds item slots")
        if same[assignment.champion_id, assignment.emblem_id] > catalog.max_same_emblem_per_holder:
            raise ValueError("Composition exceeds same-emblem-per-holder limit")
    if not catalog.allow_duplicate_emblems and any(n > 1 for n in copies.values()):
        raise ValueError("Duplicate emblems forbidden in this ruleset")


def scope_of(row):
    return Scope(**{name: getattr(row, name) for name in Scope.model_fields})


def view(row, sources=None, fingerprint=None):
    scope = scope_of(row)
    source = authorize(row.provider_id, scope, row.data_kind, ["store", "display"], sources=sources)
    if (
        source.permission_sha256 != row.authorization["permission_sha256"]
        or source.license_id != row.authorization["license_id"]
    ):
        raise PermissionError("Stored observation license differs from active authorization")
    observation = Observation.model_validate(row.observation)
    check_fields(source, observation)
    if fingerprint is None:
        fingerprint = digest(catalog_for(scope).model_dump(mode="json"))
    if fingerprint != row.catalog_sha256:
        raise PermissionError("Catalog changed since ingestion; observation not served against changed entities")
    return dict(
        id=row.id,
        provider_id=row.provider_id,
        scope=scope.model_dump(),
        data_kind=row.data_kind,
        imported_at=row.imported_at,
        kind="statistics_observation",
        verification_status="synthetic" if row.data_kind == "synthetic" else "provider_reported",
        source=row.authorization,
        catalog_sha256=row.catalog_sha256,
        context_key=row.context_key,
        observation=row.observation,
        **summarize(observation, "derive" in source.permitted_uses, row.data_kind),
    )


def ingest(request):
    source = authorize(request.provider_id, request.scope, request.data_kind, ["ingest", "store", "display"])
    catalog = catalog_for(request.scope)
    entities = [catalog, *catalog.champions, *catalog.traits, *catalog.emblems]
    if request.data_kind == "observed" and any(e.verification_status != "verified" for e in entities):
        raise ValueError("Observed statistics require a verified catalog; synthetic fixtures are not observed data")
    if request.data_kind == "synthetic" and catalog.verification_status != "synthetic":
        raise ValueError("Synthetic statistics require an explicitly synthetic catalog")
    fingerprint = digest(catalog.model_dump(mode="json"))
    prepared = []
    for observation in request.observations:
        check_fields(source, observation)
        validate_context(observation, catalog)
        if observation.collected_at > utcnow() + timedelta(minutes=5):
            raise ValueError("Collected timestamp is in the future (maximum clock skew 5 minutes)")
        payload = observation.model_dump(mode="json")
        identity = digest(
            [request.provider_id, request.scope.model_dump(), request.data_kind, observation.provider_record_id]
        )
        prepared.append(
            dict(
                id=identity,
                provider_id=request.provider_id,
                provider_record_id=observation.provider_record_id,
                **request.scope.model_dump(),
                data_kind=request.data_kind,
                context_kind=observation.context.kind,
                context_key=digest(payload["context"]),
                payload_sha256=digest(payload),
                catalog_sha256=fingerprint,
                imported_at=utcnow().isoformat(),
                authorization=source.model_dump(mode="json"),
                observation=payload,
            )
        )
    inserted = 0
    # Unique IDs prevent replay across batches; differing immutable content is a conflict.
    for attempt in range(2):
        try:
            with Session.begin() as session:
                inserted = 0
                for candidate in prepared:
                    existing = session.get(StatisticsRecord, candidate["id"])
                    if existing:
                        if (
                            existing.payload_sha256 != candidate["payload_sha256"]
                            or existing.catalog_sha256 != candidate["catalog_sha256"]
                            or existing.authorization["permission_sha256"] != source.permission_sha256
                            or existing.authorization["license_id"] != source.license_id
                        ):
                            raise FileExistsError(
                                "Provider record ID already exists with different content/catalog/license"
                            )
                    else:
                        session.add(StatisticsRecord(**candidate))
                        inserted += 1
        except IntegrityError:
            if attempt == 1:
                raise FileExistsError("Concurrent ingestion conflict; retry the same batch")
            continue
        break
    sources = registry()
    current_fingerprint = digest(catalog_for(request.scope).model_dump(mode="json"))
    with Session() as session:
        rows = [
            view(session.get(StatisticsRecord, candidate["id"]), sources, current_fingerprint) for candidate in prepared
        ]
    return dict(inserted=inserted, unchanged=len(prepared) - inserted, records=rows)


def observations(
    scope, provider_id=None, data_kind="observed", context_kind=None, context_key=None, limit=50, offset=0
):
    fingerprint = digest(catalog_for(scope).model_dump(mode="json"))
    # Permission and catalog snapshots are consistent within this query.
    sources = registry()
    query = select(StatisticsRecord).where(
        *(getattr(StatisticsRecord, k) == v for k, v in scope.model_dump().items()),
        StatisticsRecord.data_kind == data_kind,
    )
    if provider_id:
        query = query.where(StatisticsRecord.provider_id == provider_id)
    if context_kind:
        query = query.where(StatisticsRecord.context_kind == context_kind)
    if context_key:
        query = query.where(StatisticsRecord.context_key == context_key)
    results = []
    total = 0
    has_metrics = False
    # Page only after filtering current permissions. No cross-provider pooling or fallback.
    with Session() as session:
        for row in session.scalars(query.order_by(StatisticsRecord.id)).yield_per(100):
            try:
                record = view(row, sources, fingerprint)
                has_metrics |= any(record["metrics"][key] is not None for key in ("top_four_rate", "average_placement"))
                if offset <= total < offset + limit:
                    results.append(record)
                total += 1
            except PermissionError:
                continue
    return dict(
        scope=scope.model_dump(),
        data_kind=data_kind,
        statistics_available=data_kind == "observed" and has_metrics,
        total=total,
        limit=limit,
        offset=offset,
        records=results,
        aggregation="none",
    )


def observation_by_id(record_id):
    with Session() as session:
        row = session.get(StatisticsRecord, record_id)
        if row is None:
            raise LookupError("Statistics observation not found")
        return view(row)
