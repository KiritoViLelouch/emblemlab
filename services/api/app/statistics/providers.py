"""Trusted local authorization registry; adapters cannot grant themselves permission."""

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol
from pydantic import ValidationError
from app.statistics.schemas import IngestRequest, SourceAuthorization, SourceRegistry

DEFAULT_REGISTRY = Path(__file__).resolve().parents[4] / "data/statistics/sources.json"


class StatisticsProvider(Protocol):
    """A provider-specific authorized exporter returns the common ingestion schema.

    Credentials, HTTP requests, rate limits and export rights belong to the upstream
    adapter. This package ships no remote adapters and calls no provider websites.
    """

    def normalize(self, export: bytes) -> IngestRequest: ...


def utcnow():
    return datetime.now(timezone.utc)


def registry():
    path = Path(os.getenv("STATISTICS_SOURCES_FILE", str(DEFAULT_REGISTRY)))
    try:
        with path.open("rb") as file:
            content = file.read(1024 * 1024 + 1)
        if len(content) > 1024 * 1024:
            raise ValueError("Registry too large")
        return SourceRegistry.model_validate_json(content).sources
    except (OSError, ValueError, ValidationError) as exc:
        raise RuntimeError("Statistics source registry invalid or unavailable; ingestion disabled") from exc


def active(source):
    return source.enabled and source.valid_from <= utcnow() < source.valid_until


def authorize(provider_id, scope, data_kind, uses, sources=None):
    source = next((s for s in (registry() if sources is None else sources) if s.provider_id == provider_id), None)
    if source is None or not active(source):
        raise PermissionError("Provider is not approved, disabled or authorization expired")
    if scope not in source.scopes or data_kind not in source.data_kinds or not set(uses) <= set(source.permitted_uses):
        raise PermissionError("Provider authorization does not cover this exact scope, data kind or use")
    return source


def check_fields(source: SourceAuthorization, observation):
    if observation.context.kind not in source.context_kinds:
        raise PermissionError("Context not covered by provider authorization")
    metrics = observation.metrics
    uses_top_four = metrics.top_four_rate is not None or metrics.top_four_count is not None
    uses_average = metrics.average_placement is not None or metrics.placement_sum is not None
    if metrics.placement_counts is not None:
        uses_top_four = uses_average = True
    if metrics.reported_confidence:
        uses_top_four |= metrics.reported_confidence.top_four_rate is not None
        uses_average |= metrics.reported_confidence.average_placement is not None
    if (uses_top_four and "top_four_rate" not in source.metrics) or (
        uses_average and "average_placement" not in source.metrics
    ):
        raise PermissionError("Metric/counts not covered by provider authorization")
