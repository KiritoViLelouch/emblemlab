from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Provenance(Strict):
    game: Literal["TFT", "JCC"]
    patch: str
    set: str
    mode: str
    source: str
    imported_at: str
    verification_status: Literal["synthetic", "verified", "partially_verified", "unverified", "unsupported"]

    @field_validator("verification_status", mode="before")
    @classmethod
    def normalize_verification(cls, value):
        return value.lower() if isinstance(value, str) else value


class Entity(Provenance):
    id: str
    zh_CN: str
    en_US: str
    icon_path: str | None = None
    aliases: list[str] = Field(default_factory=list)
    description: str | None = None
    verification_evidence: list[str] = Field(default_factory=list)


class Threshold(Strict):
    count: int = Field(ge=1)
    utility: int = Field(ge=0)


class Trait(Entity):
    thresholds: list[Threshold]
    counting_rule: Literal["unique_eligible"] = "unique_eligible"
    special_conditions: str | None = None
    supported: bool = True


class Champion(Entity):
    cost: int = Field(ge=1, le=5)
    traits: list[str]
    item_slots: int = Field(default=3, ge=0, le=3)
    available: bool = True
    unlock_condition: str | None = None
    board_slots: int = Field(default=1, ge=1, le=2)
    trait_weights: dict[str, int] = Field(default_factory=dict)
    exclusive_group: str | None = None


class Emblem(Entity):
    trait_id: str
    banned_holders: list[str] = Field(default_factory=list)
    allow_native: bool = False
    available: bool = True


class RuleCheck(Strict):
    id: str
    status: Literal["VERIFIED", "PARTIALLY_VERIFIED", "UNVERIFIED", "SYNTHETIC", "UNSUPPORTED"]
    essential: bool
    evidence: list[str]
    notes: str = ""


class DataReadiness(Strict):
    source_kind: Literal["riot_and_communitydragon", "manual_review"]
    set_name: str
    resource_patch: str
    build_version: str
    last_verified_at: str | None
    live_as_of: str | None
    optimization_enabled: bool
    scope: str
    completeness: float = Field(ge=0, le=1)
    required_champion_ids: list[str]
    snapshots: list[dict]
    rule_checks: list[RuleCheck]
    unsupported_mechanics: list[str]
    excluded_entities: list[dict] = Field(default_factory=list)


class CapacityBonus(Strict):
    trait_id: str
    threshold: int = Field(ge=1)
    slots: int = Field(ge=1, le=2)


class Ruleset(Entity):
    allow_duplicate_emblems: bool
    allow_unused_emblems: bool
    max_same_emblem_per_holder: int = Field(default=1, ge=1)
    champions: list[Champion]
    traits: list[Trait]
    emblems: list[Emblem]
    license_status: str
    data_readiness: DataReadiness | None = None
    capacity_bonuses: list[CapacityBonus] = Field(default_factory=list)
    trait_count_limits: dict[str, int] = Field(default_factory=dict)
    incompatible_trait_pairs: list[tuple[str, str]] = Field(default_factory=list)

    @model_validator(mode="after")
    def isolated(self):
        entities = self.champions + self.traits + self.emblems
        if len({e.id for e in entities}) != len(entities):
            raise ValueError("Duplicate entity IDs")
        for entity in entities:
            if any(getattr(entity, key) != getattr(self, key) for key in ["game", "patch", "set", "mode"]):
                raise ValueError("Cross-game/version entity reference")
        traits = {t.id for t in self.traits}
        champions = {c.id for c in self.champions}
        for c in self.champions:
            if len(set(c.traits)) != len(c.traits) or not set(c.traits) <= traits:
                raise ValueError("Unknown native trait")
            if not set(c.trait_weights) <= set(c.traits) or any(w not in (1, 2) for w in c.trait_weights.values()):
                raise ValueError("Invalid native trait weight")
        for t in self.traits:
            counts = [b.count for b in t.thresholds]
            utilities = [b.utility for b in t.thresholds]
            if (not counts and t.supported) or counts != sorted(set(counts)) or utilities != sorted(utilities):
                raise ValueError("Invalid thresholds")
        for e in self.emblems:
            if e.trait_id not in traits or not set(e.banned_holders) <= champions:
                raise ValueError("Unknown emblem reference")
        for bonus in self.capacity_bonuses:
            if bonus.trait_id not in traits:
                raise ValueError("Unknown capacity trait")
        if not set(self.trait_count_limits) <= traits or any(v < 0 for v in self.trait_count_limits.values()):
            raise ValueError("Invalid trait count limit")
        if any(a not in traits or b not in traits or a == b for a, b in self.incompatible_trait_pairs):
            raise ValueError("Invalid incompatible traits")
        if self.data_readiness:
            rule_ids = [r.id for r in self.data_readiness.rule_checks]
            if len(rule_ids) != len(set(rule_ids)):
                raise ValueError("Duplicate rule review IDs")
            required = self.data_readiness.required_champion_ids
            if len(required) != len(set(required)) or not set(required) <= champions:
                raise ValueError("Missing required champions")
            if self.data_readiness.optimization_enabled and any(
                r.essential and r.status != "VERIFIED" for r in self.data_readiness.rule_checks
            ):
                raise ValueError("Essential rules are not verified")
        return self


class Constraints(Strict):
    locked_units: list[str] = Field(default_factory=list)
    banned_units: list[str] = Field(default_factory=list)
    max_unit_cost: int = Field(default=5, ge=1, le=5)


class SolveRequest(Strict):
    game_id: Literal["TFT", "JCC"]
    ruleset_id: str
    emblem_ids: list[str] = Field(default_factory=list, max_length=3)
    board_size: Literal[7, 8, 9, 10] = 8
    objective: Literal["MAX_ACTIVE_TRAITS", "MAX_BREAKPOINT", "BALANCED", "LOW_COST", "LATE_GAME"] = "MAX_ACTIVE_TRAITS"
    constraints: Constraints = Field(default_factory=Constraints)
    top_k: int = Field(default=5, ge=1, le=10)
    timeout_seconds: float = Field(default=3, ge=0.001, le=15)
    min_champion_distance: int = Field(default=2, ge=1, le=10)


class ReforgeRequest(SolveRequest):
    locked_emblem_indices: list[int] = Field(default_factory=list)
    action: Literal["retained_subsets", "actual_reforge"] = "retained_subsets"
