"""Server-controlled finite, single-pass reforge mechanics; never inferred from game names."""

from fractions import Fraction
from typing import Literal

from pydantic import Field, StrictInt, model_validator

from app.schemas.domain import Provenance, SolveRequest, Strict


class Probability(Strict):
    numerator: StrictInt = Field(gt=0, le=10**9)
    denominator: StrictInt = Field(gt=0, le=10**9)

    def fraction(self):
        return Fraction(self.numerator, self.denominator)


class PoolOutcome(Strict):
    emblem_id: str = Field(min_length=1)
    probability: Probability | None = None


class TargetPool(Strict):
    input_emblem_id: str = Field(min_length=1)
    outcomes: list[PoolOutcome] = Field(min_length=1, max_length=12)


class Evidence(Strict):
    kind: Literal["synthetic_definition", "first_party", "licensed_provider"]
    reference: str = Field(min_length=1)
    reviewed_by: str = Field(min_length=1)
    reviewed_at: str = Field(min_length=1)


class ReforgeRule(Provenance):
    schema_version: Literal[1] = 1
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    ruleset_id: str
    catalog_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    mechanic: Literal["replace_each_target_once"]
    draw_policy: Literal["independent", "conditional_exclude_other_instances"]
    reforgers_per_target: StrictInt = Field(ge=1, le=3)
    max_targets: StrictInt = Field(ge=1, le=3)
    target_pools: list[TargetPool] = Field(min_length=1, max_length=100)
    mechanics_evidence: Evidence
    probability_status: Literal["unknown", "verified"]
    probability_evidence: Evidence | None = None

    @model_validator(mode="after")
    def validate_laws(self):
        if self.verification_status == "unverified":
            raise ValueError("Unverified reforge mechanics cannot be activated")
        expected_kind = self.verification_status == "synthetic"
        evidence = [self.mechanics_evidence]
        if self.probability_status == "verified":
            if self.probability_evidence is None:
                raise ValueError("Verified probabilities require evidence")
            evidence.append(self.probability_evidence)
        elif self.probability_evidence is not None:
            raise ValueError("Unknown probabilities cannot claim evidence")
        if any((e.kind == "synthetic_definition") != expected_kind for e in evidence):
            raise ValueError("Evidence kind must match synthetic/verified mechanics")
        sources = [p.input_emblem_id for p in self.target_pools]
        if len(sources) != len(set(sources)):
            raise ValueError("Duplicate target pool")
        for pool in self.target_pools:
            ids = [o.emblem_id for o in pool.outcomes]
            if len(ids) != len(set(ids)):
                raise ValueError("Duplicate pool outcome")
            if self.probability_status == "unknown":
                if any(o.probability is not None for o in pool.outcomes):
                    raise ValueError("Unknown probabilities must be null")
            elif (
                any(o.probability is None for o in pool.outcomes)
                or sum((o.probability.fraction() for o in pool.outcomes), Fraction()) != 1
            ):
                raise ValueError("Verified pool probabilities must sum exactly to one")
        return self


class AnalysisRequest(SolveRequest):
    reforge_rule_id: str = Field(min_length=1)
    available_reforgers: StrictInt = Field(default=0, ge=0, le=3)
    locked_emblem_indices: list[StrictInt] = Field(default_factory=list, max_length=3)
    analysis_timeout_seconds: float = Field(default=20, ge=0.001, le=60, allow_inf_nan=False)

    @model_validator(mode="after")
    def valid_indices(self):
        if len(set(self.locked_emblem_indices)) != len(self.locked_emblem_indices) or any(
            i < 0 or i >= len(self.emblem_ids) for i in self.locked_emblem_indices
        ):
            raise ValueError("Invalid or duplicate locked emblem index")
        return self
