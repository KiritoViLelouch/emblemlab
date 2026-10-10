"""Offline export adapters. No network fetching, scraping or self-granted permission."""

import csv
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
from typing import Protocol

from app.meta.schemas import Export, Registry

ROOT = Path(__file__).resolve().parents[4] / "data" / "meta"
MAX_BYTES = 2 * 1024 * 1024


class MetaCompositionProvider(Protocol):
    def normalize(self, content: bytes, metadata: dict | None = None) -> Export: ...


class JsonProvider:
    def normalize(self, content, metadata=None):
        if len(content) > MAX_BYTES:
            raise ValueError("Meta export exceeds 2 MiB")
        return Export.model_validate_json(content)


CSV_FIELDS = [
    "id",
    "name",
    "champion_ids",
    "board_size",
    "core_carry_ids",
    "core_tank_ids",
    "non_emblem_item_slots",
    "baseline_emblem_ids",
    "baseline_assignments",
    "source_tier",
    "tier_citation",
    "reviewed_at",
    "holder_preferences",
]


class CsvProvider:
    def normalize(self, content, metadata=None):
        if len(content) > MAX_BYTES:
            raise ValueError("Meta export exceeds 2 MiB")
        reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")))
        if reader.fieldnames != CSV_FIELDS:
            raise ValueError("CSV headers must exactly match the documented meta format")
        rows = []
        for row in reader:
            if len(rows) >= 100 or None in row or any(v is None for v in row.values()):
                raise ValueError("Invalid CSV width or more than 100 compositions")
            row["board_size"] = int(row["board_size"])
            for key in ("champion_ids", "core_carry_ids", "core_tank_ids", "baseline_emblem_ids"):
                row[key] = [v.strip() for v in row[key].split("|") if v.strip()]
            for key, default in (
                ("non_emblem_item_slots", {}),
                ("baseline_assignments", []),
                ("holder_preferences", []),
            ):
                row[key] = json.loads(row[key]) if row[key].strip() else default
            for key in ("source_tier", "tier_citation"):
                row[key] = row[key] or None
            rows.append(row)
        return Export.model_validate({**(metadata or {}), "compositions": rows})


def registry(path=None):
    path = Path(path or os.getenv("META_SOURCES_FILE", ROOT / "sources.json"))
    try:
        if path.stat().st_size > MAX_BYTES:
            raise ValueError("Registry too large")
        return Registry.model_validate_json(path.read_bytes()).sources
    except (OSError, ValueError) as exc:
        raise RuntimeError("Meta source registry invalid or unavailable") from exc


def authorize(export, sources=None):
    source = next(
        (s for s in (registry() if sources is None else sources) if s.provider_id == export.provider_id), None
    )
    now = datetime.now(timezone.utc)
    if source is None or not source.enabled or not source.valid_from <= now < source.valid_until:
        raise PermissionError("Meta provider is not approved or permission expired")
    if (
        export.scope not in source.scopes
        or export.data_kind not in source.data_kinds
        or not {"import", "store", "display", "adapt"} <= set(source.permitted_uses)
    ):
        raise PermissionError("Meta permission does not cover scope, kind and all required uses")
    return source
