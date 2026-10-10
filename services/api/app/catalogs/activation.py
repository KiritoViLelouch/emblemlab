"""Offline operator-reviewed, content-addressed catalogs. No HTTP activation endpoint."""

import argparse
from contextlib import contextmanager
from datetime import date, datetime, timezone
import fcntl
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import tempfile
from typing import Literal

from pydantic import Field, HttpUrl, field_validator

from app.data_validation.catalog import CORE_JCC_CHECKS, validate_catalog
from app.rules.evaluator import FixtureRules
from app.schemas.domain import Strict, Ruleset, SolveRequest, RuleCheck

ROOT = Path(__file__).resolve().parents[4] / "data"


def encode(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


def digest(content):
    return hashlib.sha256(content).hexdigest()


class Source(Strict):
    filename: str = Field(min_length=1)
    url: HttpUrl
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    category: Literal["official", "licensed_export", "manual_original"]
    license_status: Literal["original", "authorized"]
    permission_evidence: list[str] = Field(min_length=1)
    redistribution_allowed: Literal[True]
    attribution: str = Field(min_length=1)

    @field_validator("filename")
    @classmethod
    def basename(cls, value):
        if value != Path(value).name or value in (".", "..") or "\\" in value:
            raise ValueError("Source filename must be a basename")
        return value


class ExpectedCase(Strict):
    citation: str = Field(min_length=1)
    request: SolveRequest
    selected: list[str] = Field(min_length=1)
    assignments: list[dict]
    expected_trait_counts: dict[str, int]


class Approval(Strict):
    schema_version: Literal[1]
    catalog_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    decision: Literal["approve"]
    reviewer: str = Field(min_length=1)
    independent_reviewer: str = Field(min_length=1)
    reviewed_at: datetime
    source_version: str = Field(min_length=1)
    release_date: date
    scope: str = Field(min_length=1)
    unsupported_mechanics: list[str]
    rules: list[RuleCheck]
    required_champion_ids: list[str] = Field(min_length=1)
    required_trait_ids: list[str] = Field(min_length=1)
    required_emblem_ids: list[str] = Field(min_length=3)
    roster_citation: str = Field(min_length=1)
    sources: list[Source] = Field(min_length=1)
    icons: Literal["authorized_references", "text_only"]
    icon_permission_evidence: list[str]
    cases: list[ExpectedCase] = Field(min_length=3)

    @field_validator("reviewer", "independent_reviewer", "scope", "source_version", "roster_citation")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("Review fields cannot be blank")
        return value


def prepare(catalog_path, approval_path, sources_dir):
    """Validate a review bound to an exact input; never toggle an arbitrary ready flag."""
    content = Path(catalog_path).read_bytes()
    review = Approval.model_validate_json(Path(approval_path).read_bytes())
    if digest(content) != review.catalog_sha256:
        raise ValueError("Review does not match catalog bytes")
    now = datetime.now(timezone.utc)
    if review.reviewed_at.tzinfo is None or review.reviewed_at > now or review.release_date > now.date():
        raise ValueError("Review/release date must be known and not in the future")
    if review.reviewer.strip().casefold() == review.independent_reviewer.strip().casefold():
        raise ValueError("Independent reviewer required")
    raw = json.loads(content)
    dataset = Ruleset.model_validate(raw)
    if dataset.game != "JCC" or dataset.verification_status == "synthetic" or not dataset.data_readiness:
        raise ValueError("Only real JCC review drafts can be approved here")
    if dataset.license_status not in ("original", "authorized"):
        raise ValueError("Unknown source authorization")
    if dataset.data_readiness.build_version != review.source_version or review.source_version == "unreviewed":
        raise ValueError("Source build/version does not match review")
    for ids, entities in [
        (review.required_champion_ids, dataset.champions),
        (review.required_trait_ids, dataset.traits),
        (review.required_emblem_ids, dataset.emblems),
    ]:
        if len(ids) != len(set(ids)) or set(ids) != {e.id for e in entities}:
            raise ValueError("Incomplete or unexpected roster/trait/emblem records")
    rules = {r.id: r for r in review.rules}
    if len(rules) != len(review.rules) or not CORE_JCC_CHECKS <= rules.keys():
        raise ValueError("Missing essential JCC rule reviews")
    for key in CORE_JCC_CHECKS:
        rule = rules[key]
        if (
            not rule.essential
            or rule.status != "VERIFIED"
            or not all(x.strip() for x in rule.evidence)
            or not rule.evidence
        ):
            raise ValueError(f"Missing verified JCC rule evidence: {key}")
    files = {}
    if len({s.filename for s in review.sources}) != len(review.sources):
        raise ValueError("Duplicate source filenames")
    for source in review.sources:
        path = Path(sources_dir).resolve() / source.filename
        if path.is_symlink() or digest(path.read_bytes()) != source.sha256:
            raise ValueError("Missing or changed approved source")
        if not all(s.strip() for s in source.permission_evidence):
            raise ValueError("Missing source permission evidence")
        files[source.filename] = path.read_bytes()
    entities = [*dataset.champions, *dataset.traits, *dataset.emblems]
    if review.icons == "text_only" and any(e.icon_path for e in entities):
        raise ValueError("Text-only approval cannot include icons")
    if review.icons == "authorized_references" and (
        not review.icon_permission_evidence or not all(e.strip() for e in review.icon_permission_evidence)
    ):
        raise ValueError("Icon reuse evidence required")
    snapshots = dataset.data_readiness.snapshots
    if not snapshots or any(
        not any(
            s.get("sha256") == src.sha256 and s.get("filename") == src.filename and s.get("url") == str(src.url)
            for src in review.sources
        )
        for s in snapshots
    ):
        raise ValueError("Draft provenance does not match reviewed sources")
    if any(not e.verification_evidence or not all(x.strip() for x in e.verification_evidence) for e in entities):
        raise ValueError("Every entity needs independent factual evidence")
    raw["verification_status"] = "partially_verified" if review.unsupported_mechanics else "verified"
    raw["data_readiness"].update(
        optimization_enabled=True,
        rule_checks=[r.model_dump() for r in review.rules],
        last_verified_at=review.reviewed_at.isoformat(),
        build_version=review.source_version,
        scope=review.scope,
        required_champion_ids=review.required_champion_ids,
        unsupported_mechanics=review.unsupported_mechanics,
        completeness=sum(c.available for c in dataset.champions) / len(dataset.champions),
    )
    report = validate_catalog(raw)
    if not report["optimization_enabled"]:
        raise ValueError("Catalog failed activation validation: " + "; ".join(report["issues"]))
    approved = Ruleset.model_validate(raw)
    if not any(len(c.request.emblem_ids) == 3 and len(c.assignments) == 3 for c in review.cases):
        raise ValueError("A reviewed three-emblem assignment case is required")
    for case in review.cases:
        FixtureRules().validate_solution(approved, case.request, case.selected, case.assignments)
        counts = {t["id"]: t["count"] for t in FixtureRules().evaluate(approved, case.selected, case.assignments)}
        if counts != case.expected_trait_counts:
            raise ValueError("Independent expected trait counts disagree")
    return approved.model_dump(), review.model_dump(mode="json"), report, files


def _inside(root, relative):
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("Artifact path escapes data directory")
    return path


def load_entry(root, entry):
    """Runtime rechecks bytes, approval, provenance and rule gate; fail closed per entry."""
    folder = _inside(root, entry["artifact"])
    for name, key in [
        ("catalog.json", "catalog_sha256"),
        ("review.json", "review_sha256"),
        ("validation.json", "validation_sha256"),
        ("input.json", "input_sha256"),
    ]:
        if digest((folder / name).read_bytes()) != entry[key]:
            raise ValueError(f"Corrupt artifact: {name}")
    catalog, _, report, _ = prepare(folder / "input.json", folder / "review.json", folder / "sources")
    if (
        encode(catalog) != (folder / "catalog.json").read_bytes()
        or encode(report) != (folder / "validation.json").read_bytes()
    ):
        raise ValueError("Artifact review/validation disagreement")
    dataset = Ruleset.model_validate(catalog)
    if (dataset.game, dataset.id) != (entry["game"], entry["ruleset_id"]):
        raise ValueError("Registry scope mismatch")
    return dataset


def registry(root=ROOT):
    path = root / "active/index.json"
    if not path.exists():
        return {"schema_version": 1, "generation": 0, "active": [], "audit": []}
    raw = json.loads(path.read_bytes())
    if (
        not isinstance(raw, dict)
        or raw.get("schema_version") != 1
        or not isinstance(raw.get("active"), list)
        or not isinstance(raw.get("audit"), list)
        or not isinstance(raw.get("generation"), int)
    ):
        raise ValueError("Invalid active catalog registry")
    if any(not isinstance(e, dict) for e in raw["active"]):
        raise ValueError("Invalid registry entries")
    keys = [(e["game"], e["ruleset_id"]) for e in raw["active"]]
    if len(keys) != len(set(keys)) or any(game != "JCC" for game, _ in keys):
        raise ValueError("Invalid or duplicate registry scope")
    return raw


def registered(root=ROOT):
    datasets, issues = [], []
    try:
        index = registry(root)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        return [], [dict(game="JCC", issue=str(exc))]
    for entry in index["active"]:
        try:
            datasets.append(load_entry(root, entry))
        except (ValueError, OSError, KeyError, TypeError) as exc:
            issues.append(dict(game=entry.get("game", "JCC"), ruleset_id=entry.get("ruleset_id"), issue=str(exc)))
    return datasets, issues


@contextmanager
def locked(root):
    folder = root / "active"
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / ".activation.lock").open("a") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        yield


def _write_once(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != content:
            raise ValueError("Immutable artifact collision")
    else:
        with path.open("xb") as file:
            file.write(content)
            file.flush()
            os.fsync(file.fileno())


def _promote(root, entries, actor, reason, expected):
    current = registry(root)
    previous = digest(encode(current))
    if previous != expected:
        raise ValueError("Registry changed; review latest revision before promotion")
    for entry in entries:
        load_entry(root, entry)
    _write_once(root / "active/history" / (previous + ".json"), encode(current))
    new = dict(
        schema_version=1,
        generation=current["generation"] + 1,
        active=entries,
        audit=[
            *current["audit"],
            dict(actor=actor, reason=reason, previous_sha256=previous, at=datetime.now(timezone.utc).isoformat()),
        ],
    )
    content = encode(new)
    _write_once(root / "active/history" / (digest(content) + ".json"), content)
    fd, path = tempfile.mkstemp(dir=root / "active", prefix=".index-")
    try:
        with os.fdopen(fd, "wb") as file:
            file.write(content)
            file.flush()
            os.fsync(file.fileno())
        os.replace(path, root / "active/index.json")
    finally:
        if os.path.exists(path):
            os.unlink(path)
    return new


def activate(catalog_path, approval_path, sources_dir, *, actor, reason, expected_revision, root=ROOT):
    if not actor.strip() or not reason.strip():
        raise ValueError("Operator actor and reason required")
    catalog, review, report, sources = prepare(catalog_path, approval_path, sources_dir)
    catalog_bytes, review_bytes, report_bytes = encode(catalog), encode(review), encode(report)
    artifact = "approved/" + digest(catalog_bytes + review_bytes)
    entry = dict(
        game="JCC",
        ruleset_id=catalog["id"],
        artifact=artifact,
        catalog_sha256=digest(catalog_bytes),
        review_sha256=digest(review_bytes),
        validation_sha256=digest(report_bytes),
        input_sha256=digest(Path(catalog_path).read_bytes()),
    )
    with locked(root):
        index = registry(root)
        if digest(encode(index)) != expected_revision:
            raise ValueError("Registry changed; review latest revision before promotion")
        existing = [e for e in index["active"] if e["ruleset_id"] == entry["ruleset_id"]]
        if existing and existing[0] != entry:
            raise ValueError("Ruleset ID already active; use a new version ID for corrections")
        stage = Path(tempfile.mkdtemp(dir=root, prefix=".approval-"))
        try:
            for name, content in [
                ("catalog.json", catalog_bytes),
                ("review.json", review_bytes),
                ("validation.json", report_bytes),
                ("input.json", Path(catalog_path).read_bytes()),
            ]:
                _write_once(stage / name, content)
            for name, content in sources.items():
                _write_once(stage / "sources" / name, content)
            destination = root / artifact
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists():
                load_entry(root, entry)
            else:
                os.rename(stage, destination)
            entries = [e for e in index["active"] if e["ruleset_id"] != entry["ruleset_id"]] + [entry]
            return _promote(root, entries, actor, reason, expected_revision)
        finally:
            if stage.exists():
                shutil.rmtree(stage)


def rollback(target_revision, *, actor, reason, expected_revision, root=ROOT):
    if not actor.strip() or not reason.strip() or not re.fullmatch(r"[0-9a-f]{64}", target_revision):
        raise ValueError("Valid target revision, operator and reason required")
    with locked(root):
        target = json.loads((root / "active/history" / (target_revision + ".json")).read_bytes())
        if digest(encode(target)) != target_revision:
            raise ValueError("Corrupted rollback history")
        return _promote(root, target["active"], actor, reason, expected_revision)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=ROOT)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status")
    review = commands.add_parser("check")
    promote = commands.add_parser("activate")
    for command in (review, promote):
        command.add_argument("--catalog", required=True)
        command.add_argument("--approval", required=True)
        command.add_argument("--sources-dir", required=True)
    revert = commands.add_parser("rollback")
    revert.add_argument("--target-revision", required=True)
    for command in (promote, revert):
        command.add_argument("--actor", required=True)
        command.add_argument("--reason", required=True)
        command.add_argument("--expected-revision", required=True)
    args = vars(parser.parse_args())
    command, root = args.pop("command"), args.pop("data_root")
    if command == "status":
        index = registry(root)
        datasets, issues = registered(root)
        result = dict(
            revision=digest(encode(index)),
            generation=index["generation"],
            active=[d.id for d in datasets],
            issues=issues,
        )
    elif command == "check":
        _, _, result, _ = prepare(args["catalog"], args["approval"], args["sources_dir"])
    elif command == "activate":
        result = activate(args.pop("catalog"), args.pop("approval"), args.pop("sources_dir"), root=root, **args)
    else:
        result = rollback(args.pop("target_revision"), root=root, **args)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
