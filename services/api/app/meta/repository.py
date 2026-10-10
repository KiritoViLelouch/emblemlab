"""Immutable, reviewed export snapshots. Never fall back across a game or patch."""

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

from app.meta.providers import CsvProvider, JsonProvider, MAX_BYTES, ROOT, authorize, registry
from app.meta.schemas import Scope, Snapshot
from app.repositories.catalog import get_catalog
from app.rules.evaluator import FixtureRules
from app.schemas.domain import SolveRequest


def digest(value):
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def scope_for(dataset):
    return Scope(
        game_id=dataset.game, ruleset_id=dataset.id, patch=dataset.patch, set_id=dataset.set, mode=dataset.mode
    )


def catalog_for(scope):
    dataset = get_catalog(scope.game_id, scope.ruleset_id)
    if scope != scope_for(dataset):
        raise ValueError("Exact game/ruleset/patch/set/mode required; no version fallback")
    return dataset


def validate_export(export, dataset):
    if export.scope != scope_for(dataset):
        raise ValueError("Meta export scope does not match catalog")
    if (export.data_kind == "synthetic") != (dataset.verification_status == "synthetic"):
        raise ValueError("Synthetic meta must use synthetic catalogs; real meta cannot use fixtures")
    units, emblems = {c.id: c for c in dataset.champions}, {e.id: e for e in dataset.emblems}
    rules = FixtureRules()
    unsupported = {t.id for t in dataset.traits if not t.supported or t.special_conditions}
    for comp in export.compositions:
        if comp.reviewed_at > datetime.now(timezone.utc):
            raise ValueError("Composition review cannot be in the future")
        if not set(comp.champion_ids) <= units.keys():
            raise ValueError("Unknown or cross-game source champion")
        if any(set(units[uid].traits) & unsupported for uid in comp.champion_ids):
            raise ValueError("Source board depends on unsupported special mechanics")
        request = SolveRequest(
            game_id=dataset.game,
            ruleset_id=dataset.id,
            board_size=comp.board_size,
            emblem_ids=comp.baseline_emblem_ids,
        )
        assignments = [a.model_dump() for a in comp.baseline_assignments]
        rules.validate_solution(dataset, request, comp.champion_ids, assignments)
        if len(assignments) != len(comp.baseline_emblem_ids):
            raise ValueError("Source baseline must specify every emblem holder")
        equipped = {uid: sum(a.champion_id == uid for a in comp.baseline_assignments) for uid in comp.champion_ids}
        if any(n + equipped[uid] > units[uid].item_slots for uid, n in comp.non_emblem_item_slots.items()):
            raise ValueError("Source equipment and reservations exceed item slots")
        for pref in comp.holder_preferences:
            if (
                pref.champion_id not in units
                or pref.emblem_id not in emblems
                or not rules.legal(units[pref.champion_id], emblems[pref.emblem_id])
            ):
                raise ValueError("Source recommendation has illegal or unknown holder")
            if pref.champion_id not in comp.champion_ids:
                raise ValueError("Holder recommendation must have source-board context")


def snapshots_root():
    return Path(os.getenv("META_CATALOG_DIR", ROOT / "catalogs"))


def validate_original(export, content, filename):
    suffix = Path(filename).suffix.lower()
    if suffix not in (".json", ".csv"):
        raise ValueError("Original export must be CSV/JSON")
    provider = JsonProvider() if suffix == ".json" else CsvProvider()
    normalized = provider.normalize(content, export.model_dump(mode="json", exclude={"compositions"}))
    if normalized != export:
        raise ValueError("Normalized catalog does not match archived original export")


def read_snapshot(path, sources):
    if path.stat().st_size > MAX_BYTES:
        raise ValueError("Meta snapshot too large")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != path.parent.name:
        raise ValueError("Meta snapshot digest mismatch")
    snapshot = Snapshot.model_validate_json(raw)
    source = authorize(snapshot.export, sources)
    if digest(source.model_dump(mode="json")) != snapshot.authorization_sha256:
        raise ValueError("Meta authorization changed; reimport required")
    original = path.parent / "original.bin"
    if (
        original.stat().st_size > MAX_BYTES
        or hashlib.sha256(original.read_bytes()).hexdigest() != snapshot.original_sha256
    ):
        raise ValueError("Original meta file missing or corrupted")
    validate_original(snapshot.export, original.read_bytes(), snapshot.original_filename)
    dataset = catalog_for(snapshot.export.scope)
    if digest(dataset.model_dump(mode="json")) != snapshot.catalog_sha256:
        raise ValueError("Static catalog changed; meta reimport/review required")
    validate_export(snapshot.export, dataset)
    return snapshot, source


def available(scope, root=None):
    sources = registry()
    entries, issues = {}, []
    conflicted = set()
    for path in sorted(Path(root or snapshots_root()).glob("*/snapshot.json")):
        try:
            snapshot, source = read_snapshot(path, sources)
            if snapshot.export.scope != scope:
                continue
            for comp in snapshot.export.compositions:
                key = f"{snapshot.export.provider_id}:{comp.id}"
                if key in entries or key in conflicted:
                    conflicted.add(key)
                    entries.pop(key, None)
                    issues.append(
                        {
                            "key": key,
                            "reason": "Conflicting immutable exports; explicit operator removal/review required",
                        }
                    )
                else:
                    entries[key] = (comp, snapshot, source)
        except (OSError, ValueError, PermissionError) as exc:
            issues.append({"artifact": path.parent.name, "reason": str(exc)})
    return entries, issues


def import_export(export, content, filename, root=None, sources=None):
    if len(content) > MAX_BYTES:
        raise ValueError("Meta original exceeds 2 MiB")
    if filename != Path(filename).name or "\\" in filename:
        raise ValueError("Original filename must be a basename")
    source = authorize(export, sources)
    dataset = catalog_for(export.scope)
    validate_export(export, dataset)
    validate_original(export, content, filename)
    snapshot = Snapshot(
        schema_version=1,
        export=export,
        imported_at=datetime.now(timezone.utc),
        original_filename=filename,
        original_sha256=hashlib.sha256(content).hexdigest(),
        catalog_sha256=digest(dataset.model_dump(mode="json")),
        authorization_sha256=digest(source.model_dump(mode="json")),
    )
    root = Path(root or snapshots_root())
    root.mkdir(parents=True, exist_ok=True)
    # Repeated identical imports do not create ambiguous duplicate composition keys.
    for path in root.glob("*/snapshot.json"):
        old, _ = read_snapshot(path, sources if sources is not None else registry())
        if old.export.scope != export.scope:
            continue
        overlap = {c.id for c in old.export.compositions} & {c.id for c in export.compositions}
        if old.export.provider_id == export.provider_id and overlap:
            if (old.original_sha256, old.export, old.authorization_sha256) == (
                snapshot.original_sha256,
                export,
                snapshot.authorization_sha256,
            ):
                return path
            raise FileExistsError("Composition ID already imported; use a new reviewed source record ID")
    raw = (snapshot.model_dump_json(indent=2) + "\n").encode()
    destination = root / hashlib.sha256(raw).hexdigest()
    temporary = Path(tempfile.mkdtemp(prefix=".stage-", dir=root))
    try:
        (temporary / "snapshot.json").write_bytes(raw)
        (temporary / "original.bin").write_bytes(content)
        os.rename(temporary, destination)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return destination / "snapshot.json"
