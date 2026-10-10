"""Transparent derivations from actual sufficient counts; unknowns remain None."""

import math
from app.statistics.providers import utcnow


QUALITY_POLICY = "statistics-quality-v1"


def summarize(observation, allow_derivation, data_kind):
    original = observation.metrics
    n, k, total = original.sample_size, original.top_four_count, original.placement_sum
    origins = {
        name: "reported" if getattr(original, name) is not None else "missing"
        for name in ("sample_size", "top_four_rate", "average_placement")
    }
    if original.placement_counts is not None and allow_derivation:
        counts = original.placement_counts
        if n is None:
            n = sum(counts)
            origins["sample_size"] = "derived_from_histogram"
        k = sum(counts[:4])
        total = sum(i * count for i, count in enumerate(counts, 1))
    rate, average = original.top_four_rate, original.average_placement
    if allow_derivation and n:
        if rate is None and k is not None:
            rate = k / n
            origins["top_four_rate"] = "derived_from_counts"
        if average is None and total is not None:
            average = total / n
            origins["average_placement"] = "derived_from_counts"
    computed = None
    # An arbitrary rounded rate is never converted into a fabricated success count.
    if allow_derivation and n and k is not None and observation.quality.independence == "independent":
        z = 1.959963984540054
        p, z2 = k / n, z * z
        denominator = 1 + z2 / n
        center = (p + z2 / (2 * n)) / denominator
        margin = z * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n)) / denominator
        computed = dict(
            lower=max(0.0, center - margin),
            upper=min(1.0, center + margin),
            level=0.95,
            method="wilson_score",
            basis="exact_counts_and_provider_declared_independence",
        )
    flags = []
    if n is None:
        flags.append("sample_size_unknown")
    elif n == 0:
        flags.append("empty_sample")
    elif n < 100:
        flags.append("sample_below_100")
    if rate is None:
        flags.append("top_four_rate_missing")
    if average is None:
        flags.append("average_placement_missing")
    if k is None:
        flags.append("exact_top_four_count_missing")
    if observation.quality.independence != "independent":
        flags.append("independence_" + observation.quality.independence)
    if observation.quality.deduplication != "verified":
        flags.append("deduplication_" + observation.quality.deduplication)
    coverage = observation.quality.population_coverage
    if coverage is None:
        flags.append("population_coverage_unknown")
    elif coverage < 1:
        flags.append("partial_population_coverage")
    age_days = max(0.0, (utcnow() - observation.observed_end).total_seconds() / 86400)
    if age_days > 7:
        flags.append("observation_window_older_than_7_days")
    if observation.region is None:
        flags.append("region_unknown")
    if observation.rank_band is None:
        flags.append("rank_band_unknown")
    if data_kind == "synthetic":
        flags.append("synthetic_not_match_evidence")
    return dict(
        metrics=dict(sample_size=n, top_four_rate=rate, average_placement=average, origins=origins),
        confidence=dict(
            computed_top_four_rate=computed,
            computed_average_placement=None,
            provider_reported=original.reported_confidence.model_dump() if original.reported_confidence else None,
            interpretation="Conditional sampling uncertainty only; not evidence of causal holder strength",
        ),
        data_quality=dict(
            policy=QUALITY_POLICY,
            flags=flags,
            observation_age_days=age_days,
            provider_declared=observation.quality.model_dump(),
            quality_verified=False,
            sample_warning_threshold=100,
            stale_warning_days=7,
        ),
    )
