"""Relationship and readiness validation, shared by importers and read-only UI."""

from urllib.parse import urlparse
import re

from app.schemas.domain import Ruleset

STATES = ["VERIFIED", "PARTIALLY_VERIFIED", "UNVERIFIED", "SYNTHETIC", "UNSUPPORTED"]
CORE_TFT_CHECKS = {
    "set_patch_mode",
    "canonical_roster_cost_locales",
    "native_trait_relationships",
    "monotonic_trait_thresholds",
    "emblem_associations",
    "source_snapshots_and_icons",
}


def validate_catalog(raw):
    issues = []
    try:
        dataset = Ruleset.model_validate(raw)
    except ValueError as exc:
        return dict(valid=False, issues=[str(exc)], optimization_enabled=False, verification_state="UNVERIFIED")
    real = dataset.verification_status != "synthetic"
    if real:
        if not dataset.data_readiness:
            issues.append("Real catalogs require readiness metadata")
        for entity in [*dataset.champions, *dataset.traits, *dataset.emblems]:
            url = urlparse(entity.icon_path or "")
            if (
                url.scheme != "https"
                or not url.netloc
                or url.username
                or url.password
                or url.fragment
                or url.query
                or ".." in url.path
            ):
                issues.append(f"Invalid icon reference: {entity.id}")
            if dataset.game == "TFT" and url.netloc != "ddragon.leagueoflegends.com":
                issues.append(f"Unapproved TFT icon source: {entity.id}")
            if (
                dataset.game == "TFT"
                and dataset.data_readiness
                and not url.path.startswith(f"/cdn/{dataset.data_readiness.resource_patch}/img/")
            ):
                issues.append(f"Mixed patch icon: {entity.id}")
        if any(t.supported and t.special_conditions for t in dataset.traits):
            issues.append("Unsupported special rules cannot be enabled")
        if dataset.data_readiness and dataset.data_readiness.optimization_enabled:
            readiness = dataset.data_readiness
            if not readiness.rule_checks or not any(r.essential for r in readiness.rule_checks):
                issues.append("Missing essential rule review")
            if any(r.essential and not r.evidence for r in readiness.rule_checks):
                issues.append("Essential rule evidence missing")
            if dataset.game == "TFT" and not CORE_TFT_CHECKS <= {r.id for r in readiness.rule_checks if r.essential}:
                issues.append("Missing essential TFT rules")
            if (
                not readiness.required_champion_ids
                or not readiness.snapshots
                or any(
                    not re.fullmatch(r"[0-9a-f]{64}", s.get("sha256", ""))
                    or not s.get("url", "").startswith("https://")
                    for s in readiness.snapshots
                )
            ):
                issues.append("Missing roster/snapshot verification")
            if dataset.verification_status not in ("verified", "partially_verified"):
                issues.append("Unverified/unsupported catalogs cannot optimize")
            if any(c.available and c.verification_status != "verified" for c in dataset.champions):
                issues.append("Unverified champions enabled")
            if any(t.supported and t.verification_status != "verified" for t in dataset.traits):
                issues.append("Unverified trait counting enabled")
            if any(e.available and e.verification_status != "verified" for e in dataset.emblems):
                issues.append("Unverified emblems enabled")
            unsupported = {t.id for t in dataset.traits if not t.supported}
            if any(c.available and set(c.traits) & unsupported for c in dataset.champions):
                issues.append("Champion depends on unsupported rules")
            if any(e.available and e.trait_id in unsupported for e in dataset.emblems):
                issues.append("Emblem depends on unsupported rules")
    enabled = not issues and (not real or bool(dataset.data_readiness and dataset.data_readiness.optimization_enabled))
    return dict(
        valid=not issues,
        issues=issues,
        optimization_enabled=enabled,
        verification_state=dataset.verification_status.upper(),
        counts=dict(champions=len(dataset.champions), traits=len(dataset.traits), emblems=len(dataset.emblems)),
        rule_counts={
            state: sum(r.status == state for r in dataset.data_readiness.rule_checks) if dataset.data_readiness else 0
            for state in STATES
        },
    )
