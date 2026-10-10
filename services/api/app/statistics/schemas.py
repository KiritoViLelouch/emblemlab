from collections import Counter
from datetime import timezone
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictInt, model_validator

Text = Annotated[str, Field(min_length=1, max_length=300)]
Count = Annotated[StrictInt, Field(ge=0, le=10**12)]
Rate = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False, strict=True)]
Placement = Annotated[float, Field(ge=1, le=8, allow_inf_nan=False, strict=True)]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Scope(Strict):
    game_id: Literal["TFT", "JCC"]
    ruleset_id: Text
    patch: Text
    set_id: Text
    mode: Text


class Assignment(Strict):
    emblem_id: Text
    champion_id: Text


class Board(Strict):
    champion_ids: list[Text] = Field(min_length=1, max_length=10)
    matching_rule: Literal["exact_board", "unit_subset"]
    emblem_assignments: list[Assignment] = Field(default_factory=list, max_length=30)

    @model_validator(mode="after")
    def unique_and_normalized(self):
        if len(set(self.champion_ids)) != len(self.champion_ids):
            raise ValueError("Composition champions must be unique")
        if any(a.champion_id not in self.champion_ids for a in self.emblem_assignments):
            raise ValueError("Assignment holder must belong to composition")
        self.champion_ids.sort()
        self.emblem_assignments.sort(key=lambda a: (a.champion_id, a.emblem_id))
        return self


class HolderContext(Strict):
    kind: Literal["holder"]
    emblem_id: Text
    champion_id: Text
    composition: Board | None = None

    @model_validator(mode="after")
    def holder_in_composition(self):
        if self.composition and self.champion_id not in self.composition.champion_ids:
            raise ValueError("Holder must belong to composition context")
        if self.composition and not any(
            a.emblem_id == self.emblem_id and a.champion_id == self.champion_id
            for a in self.composition.emblem_assignments
        ):
            raise ValueError("Composition context must include the holder/emblem assignment")
        return self


class CompositionContext(Strict):
    kind: Literal["composition"]
    composition: Board


Context = Annotated[HolderContext | CompositionContext, Field(discriminator="kind")]


class Interval(Strict):
    lower: float = Field(allow_inf_nan=False, strict=True)
    upper: float = Field(allow_inf_nan=False, strict=True)
    level: float = Field(gt=0, lt=1, allow_inf_nan=False, strict=True)
    method: Text

    @model_validator(mode="after")
    def ordered(self):
        if self.lower > self.upper:
            raise ValueError("Confidence interval bounds reversed")
        return self


class ReportedConfidence(Strict):
    top_four_rate: Interval | None = None
    average_placement: Interval | None = None


class Metrics(Strict):
    # None is unknown; zero sample means no outcomes, not a zero success rate.
    sample_size: Count | None = None
    top_four_count: Count | None = None
    placement_sum: Annotated[StrictInt, Field(ge=0, le=8 * 10**12)] | None = None
    placement_counts: list[Count] | None = Field(default=None, min_length=8, max_length=8)
    top_four_rate: Rate | None = None
    average_placement: Placement | None = None
    reported_confidence: ReportedConfidence | None = None

    @model_validator(mode="after")
    def consistent(self):
        n = self.sample_size
        k, total = self.top_four_count, self.placement_sum
        if self.placement_counts is not None:
            counts = self.placement_counts
            derived = (sum(counts), sum(counts[:4]), sum(i * count for i, count in enumerate(counts, 1)))
            if any(given is not None and given != actual for given, actual in zip((n, k, total), derived)):
                raise ValueError("Histogram and supplied counts disagree")
            n, k, total = derived
            if n > 10**12:
                raise ValueError("Histogram sample size exceeds 10^12")
        if n is None and (k is not None or total is not None):
            raise ValueError("Count/sum requires sample size or complete histogram")
        if n is not None:
            if k is not None and k > n:
                raise ValueError("Top-four count exceeds sample size")
            if total is not None and not n <= total <= 8 * n:
                raise ValueError("Placement sum outside 1..8 scale")
            if n == 0:
                if self.top_four_rate is not None or self.average_placement is not None:
                    raise ValueError("Empty samples cannot report outcome metrics")
            else:
                if k is not None and self.top_four_rate is not None and abs(k / n - self.top_four_rate) > 1e-6:
                    raise ValueError("Top-four rate disagrees with counts")
                if (
                    total is not None
                    and self.average_placement is not None
                    and abs(total / n - self.average_placement) > 1e-6
                ):
                    raise ValueError("Average placement disagrees with sum")
                if k is not None and total is not None and not 5 * n - 4 * k <= total <= 8 * n - 4 * k:
                    raise ValueError("Placement sum incompatible with top-four count")
        rate = self.top_four_rate if self.top_four_rate is not None else (k / n if n and k is not None else None)
        average = (
            self.average_placement
            if self.average_placement is not None
            else (total / n if n and total is not None else None)
        )
        if rate is not None and average is not None and not 5 - 4 * rate - 1e-6 <= average <= 8 - 4 * rate + 1e-6:
            raise ValueError("Average placement incompatible with top-four rate")
        if self.reported_confidence:
            for name, point, lower, upper in [("top_four_rate", rate, 0, 1), ("average_placement", average, 1, 8)]:
                interval = getattr(self.reported_confidence, name)
                if interval and (point is None or not lower <= interval.lower <= point <= interval.upper <= upper):
                    raise ValueError("Reported interval must contain an available metric and use its scale")
        return self


class Quality(Strict):
    independence: Literal["independent", "clustered", "unknown"] = "unknown"
    deduplication: Literal["verified", "not_verified", "unknown"] = "unknown"
    population_coverage: Rate | None = None
    notes: str | None = Field(default=None, max_length=2000)


class Observation(Strict):
    provider_record_id: Text
    cohort_id: Text
    cohort_definition: str = Field(min_length=1, max_length=2000)
    dataset_reference: Text
    sample_unit: Literal["participant_game"]
    placement_scale: Literal[8]
    region: Text | None = None
    queue_id: Text
    rank_band: Text | None = None
    observed_start: AwareDatetime
    observed_end: AwareDatetime
    collected_at: AwareDatetime
    context: Context
    metrics: Metrics
    quality: Quality = Field(default_factory=Quality)

    @model_validator(mode="after")
    def time_window(self):
        for name in ("observed_start", "observed_end", "collected_at"):
            setattr(self, name, getattr(self, name).astimezone(timezone.utc))
        if not self.observed_start <= self.observed_end <= self.collected_at:
            raise ValueError("Expected observed_start <= observed_end <= collected_at")
        return self


class IngestRequest(Strict):
    schema_version: Literal[1]
    provider_id: Text
    scope: Scope
    data_kind: Literal["observed", "synthetic"]
    observations: list[Observation] = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def distinct_records(self):
        if any(n > 1 for n in Counter(o.provider_record_id for o in self.observations).values()):
            raise ValueError("Duplicate provider_record_id in batch")
        return self


class SourceAuthorization(Strict):
    provider_id: Text
    name: Text
    source_kind: Literal["first_party", "licensed_provider"]
    access_method: Literal["official_api", "licensed_api", "licensed_export"]
    attribution: Text
    license_id: Text
    permission_reference: Text
    permission_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    reviewed_by: Text
    reviewed_at: AwareDatetime
    valid_from: AwareDatetime
    valid_until: AwareDatetime
    enabled: bool
    permitted_uses: list[Literal["ingest", "store", "display", "derive"]] = Field(min_length=1, max_length=4)
    scopes: list[Scope] = Field(min_length=1, max_length=100)
    data_kinds: list[Literal["observed", "synthetic"]] = Field(min_length=1, max_length=2)
    context_kinds: list[Literal["holder", "composition"]] = Field(min_length=1, max_length=2)
    metrics: list[Literal["top_four_rate", "average_placement"]] = Field(min_length=1, max_length=2)

    @model_validator(mode="after")
    def validity(self):
        if self.valid_from >= self.valid_until or self.reviewed_at > self.valid_from:
            raise ValueError("Invalid authorization validity/review window")
        if self.source_kind == "licensed_provider" and self.access_method not in ("licensed_api", "licensed_export"):
            raise ValueError("Provider ingestion requires an explicitly licensed export")
        return self


class SourceRegistry(Strict):
    schema_version: Literal[1]
    sources: list[SourceAuthorization] = Field(max_length=100)

    @model_validator(mode="after")
    def unique_sources(self):
        if len({s.provider_id for s in self.sources}) != len(self.sources):
            raise ValueError("Duplicate configured providers")
        return self
