from typing import Annotated, Literal

from pydantic import AwareDatetime, Field, StrictInt, model_validator

from app.schemas.domain import Constraints, Strict

Text = Annotated[str, Field(min_length=1, max_length=300)]
Identifier = Annotated[str, Field(pattern=r"^[A-Za-z0-9_.-]{1,100}$")]
SlotCount = Annotated[StrictInt, Field(ge=0, le=3)]
Ranking = Literal[
    "MAX_EMBLEM_UTILIZATION",
    "MIN_REPLACEMENTS",
    "MAX_BREAKPOINT_UTILITY",
    "BALANCED_STRUCTURAL",
    "PRESERVE_CORE",
]


class Scope(Strict):
    game_id: Literal["TFT", "JCC"]
    ruleset_id: Text
    patch: Text
    set_id: Text
    mode: Text


class HolderPreference(Strict):
    emblem_id: Text
    champion_id: Text
    citation: Text
    applies_to_adaptations: bool = False
    kind: Literal["source_recommendation"] = "source_recommendation"


class BaseAssignment(Strict):
    instance_index: int = Field(ge=0, le=2)
    emblem_id: Text
    champion_id: Text


class Composition(Strict):
    id: Identifier
    name: Text
    champion_ids: list[Text] = Field(min_length=1, max_length=12)
    board_size: Literal[7, 8, 9, 10]
    core_carry_ids: list[Text] = Field(default_factory=list, max_length=10)
    core_tank_ids: list[Text] = Field(default_factory=list, max_length=10)
    non_emblem_item_slots: dict[str, SlotCount] = Field(default_factory=dict, max_length=12)
    baseline_emblem_ids: list[Text] = Field(default_factory=list, max_length=3)
    baseline_assignments: list[BaseAssignment] = Field(default_factory=list, max_length=3)
    source_tier: Literal["S", "A", "B", "C"] | None = None
    tier_citation: Text | None = None
    reviewed_at: AwareDatetime
    holder_preferences: list[HolderPreference] = Field(default_factory=list, max_length=30)

    @model_validator(mode="after")
    def identities(self):
        for values in (self.champion_ids, self.core_carry_ids, self.core_tank_ids):
            if len(values) != len(set(values)):
                raise ValueError("Duplicate champion/core IDs")
        if not set(self.core_carry_ids + self.core_tank_ids) <= set(self.champion_ids):
            raise ValueError("Core units must belong to the original composition")
        if not set(self.non_emblem_item_slots) <= set(self.champion_ids):
            raise ValueError("Source item reservations must belong to original units")
        pairs = [(p.emblem_id, p.champion_id) for p in self.holder_preferences]
        if len(pairs) != len(set(pairs)):
            raise ValueError("Duplicate holder preference")
        return self


class Export(Strict):
    schema_version: Literal[1]
    provider_id: Identifier
    source_version: Text
    scope: Scope
    data_kind: Literal["meta", "manual_scenario", "synthetic"]
    compositions: list[Composition] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def tiers(self):
        if len({c.id for c in self.compositions}) != len(self.compositions):
            raise ValueError("Duplicate composition IDs")
        if self.data_kind == "meta" and any(c.source_tier is None or not c.tier_citation for c in self.compositions):
            raise ValueError("Meta exports require attributed source tiers")
        if self.data_kind == "meta" and any(not c.core_carry_ids or not c.core_tank_ids for c in self.compositions):
            raise ValueError("Meta exports must declare important carries and tanks; roles are never guessed")
        if self.data_kind == "manual_scenario" and any(c.source_tier is not None for c in self.compositions):
            raise ValueError("A manual scenario is not evidence of a meta tier")
        return self


class Authorization(Strict):
    provider_id: Identifier
    source_kind: Literal["first_party", "licensed_provider", "manual_original"]
    attribution: Text
    license_id: Text
    permission_reference: Text
    permission_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    reviewed_by: Text
    reviewed_at: AwareDatetime
    valid_from: AwareDatetime
    valid_until: AwareDatetime
    enabled: bool
    scopes: list[Scope] = Field(min_length=1, max_length=100)
    data_kinds: list[Literal["meta", "manual_scenario", "synthetic"]] = Field(min_length=1)
    permitted_uses: list[Literal["import", "store", "display", "adapt"]] = Field(min_length=1)

    @model_validator(mode="after")
    def dates(self):
        if not self.reviewed_at <= self.valid_from < self.valid_until:
            raise ValueError("Invalid permission review/validity dates")
        return self


class Registry(Strict):
    schema_version: Literal[1]
    sources: list[Authorization] = Field(max_length=100)

    @model_validator(mode="after")
    def unique(self):
        if len({s.provider_id for s in self.sources}) != len(self.sources):
            raise ValueError("Duplicate provider IDs")
        return self


class Snapshot(Strict):
    schema_version: Literal[1]
    export: Export
    imported_at: AwareDatetime
    original_filename: Text
    original_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    catalog_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    authorization_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class AdaptRequest(Strict):
    scope: Scope
    emblem_ids: list[Text] = Field(default_factory=list, max_length=3)
    composition_keys: list[Text] = Field(default_factory=list, max_length=5)
    board_size: Literal[7, 8, 9, 10] = 8
    constraints: Constraints = Field(default_factory=Constraints)
    replacement_counts: list[Literal[0, 1, 2]] = Field(default_factory=lambda: [0, 1, 2], min_length=1, max_length=3)
    ranking: Ranking = "BALANCED_STRUCTURAL"
    preserve_core: bool = True
    occupied_item_slots: dict[str, SlotCount] = Field(default_factory=dict, max_length=100)
    timeout_seconds: float = Field(default=15, ge=0.01, le=60, allow_inf_nan=False)
    per_case_timeout_seconds: float = Field(default=1, ge=0.001, le=5, allow_inf_nan=False)
    include_manual_scenarios: bool = False
    include_synthetic: bool = False
    statistics_record_ids: list[Text] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def distinct(self):
        for values in (self.composition_keys, self.replacement_counts, self.statistics_record_ids):
            if len(values) != len(set(values)):
                raise ValueError("Duplicate keys or replacement counts")
        return self


class StrategyRequest(AdaptRequest):
    include_empty_baseline: bool = False
    locked_emblem_indices: list[int] = Field(default_factory=list, max_length=3)

    @model_validator(mode="after")
    def instance_locks(self):
        if len(set(self.locked_emblem_indices)) != len(self.locked_emblem_indices) or not set(
            self.locked_emblem_indices
        ) <= set(range(len(self.emblem_ids))):
            raise ValueError("Invalid locked emblem instance")
        return self
