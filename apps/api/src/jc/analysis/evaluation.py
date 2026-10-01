"""evaluation-v1: deterministic mathematics over frozen samples, without I/O.

This module neither establishes historical visibility nor selects a winning model.
Formula, precision, clipping, bins, outcome and sample rules are versioned together.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import (
    ROUND_HALF_EVEN,
    Context,
    Decimal,
    DecimalException,
    DivisionByZero,
    InvalidOperation,
    Overflow,
    Underflow,
    localcontext,
)
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Literal, TypedDict

if TYPE_CHECKING:
    from jc.analysis.goals_baseline import GoalsBaselineResult

EVALUATION_VERSION = "evaluation-v1"
EVALUATION_MODE: Literal["FROZEN_SAMPLE_SET"] = "FROZEN_SAMPLE_SET"
LOG_EPSILON = Decimal("1e-15")
PROBABILITY_SUM_TOLERANCE = Decimal("1e-23")  # Includes market-v1's 24-place output.
DECIMAL_PRECISION = 50
OUTCOMES = ("HOME", "DRAW", "AWAY")  # Also the accuracy tie priority.
BIN_EDGES = tuple(Decimal(f"0.{i}") for i in range(10)) + (Decimal("1.0"),)
ZERO, ONE = Decimal(0), Decimal(1)
_CONTEXT = Context(
    prec=DECIMAL_PRECISION,
    rounding=ROUND_HALF_EVEN,
    Emin=-999999,
    Emax=999999,
    capitals=1,
    clamp=0,
    flags=[],
    traps=[InvalidOperation, DivisionByZero, Overflow, Underflow],
)


def _identity(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a nonempty string")
    return value


def _utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("match_time and cutoff_date require timezone-aware datetime values")
    return value.astimezone(UTC)


def _probabilities(values: Mapping[str, Decimal | str]) -> Mapping[str, Decimal]:
    if not isinstance(values, Mapping) or set(values) != set(OUTCOMES):
        raise ValueError("probabilities require exactly HOME, DRAW, AWAY")
    with localcontext(_CONTEXT):
        parsed = {}
        for outcome in OUTCOMES:
            value = values[outcome]
            if not isinstance(value, (Decimal, str)):
                raise ValueError("probabilities must be Decimal or Decimal strings; no float")
            try:
                probability = Decimal(value)
            except DecimalException as exc:
                raise ValueError("Invalid Decimal probability") from exc
            if not probability.is_finite() or not ZERO <= probability <= ONE:
                raise ValueError("probabilities must be finite and within [0, 1]")
            parsed[outcome] = probability
        # Validate the exact supplied sum, including digits beyond the metric context.
        # All nonzero values are <= 1; two guard digits suffice for summing three terms.
        with localcontext(_CONTEXT) as validation:
            validation.prec = max(
                DECIMAL_PRECISION,
                max((-int(p.as_tuple().exponent) for p in parsed.values() if p), default=0) + 2,
            )
            if abs(sum(parsed.values(), ZERO) - ONE) > PROBABILITY_SUM_TOLERANCE:
                raise ValueError("probability sum outside evaluation-v1 tolerance")
    return MappingProxyType(parsed)


@dataclass(frozen=True, init=False)
class EvaluationSample:
    sample_id: str
    match_id: str
    prediction_source: str
    probabilities: Mapping[str, Decimal]
    actual_result: str
    match_time: datetime | None

    def __init__(
        self,
        sample_id: str,
        match_id: str,
        prediction_source: str,
        probabilities: Mapping[str, Decimal | str],
        actual_result: str,
        *,
        match_time: datetime | None = None,
    ) -> None:
        if not isinstance(actual_result, str) or actual_result not in OUTCOMES:
            raise ValueError("actual_result must be HOME, DRAW or AWAY")
        object.__setattr__(self, "sample_id", _identity(sample_id, "sample_id"))
        object.__setattr__(self, "match_id", _identity(match_id, "match_id"))
        object.__setattr__(self, "prediction_source", _identity(prediction_source, "prediction_source"))
        object.__setattr__(self, "probabilities", _probabilities(probabilities))
        object.__setattr__(self, "actual_result", actual_result)
        object.__setattr__(self, "match_time", _utc(match_time) if match_time is not None else None)


class CalibrationBin(TypedDict):
    lower_bound: str
    upper_bound: str
    upper_inclusive: bool
    count: int
    mean_predicted_probability: str | None
    actual_frequency: str | None
    calibration_error: str | None


class EvaluationResult(TypedDict):
    evaluation_version: str
    evaluation_mode: Literal["FROZEN_SAMPLE_SET"]
    prediction_source: str | None
    sample_size: int
    eligible_samples: int | None
    evaluated_samples: int
    coverage: str | None
    log_loss: str | None
    brier_score: str | None
    accuracy: str | None
    clipping_count: int
    calibration: dict[str, list[CalibrationBin]]
    ece: dict[str, str | None]  # HOME, DRAW, AWAY and macro.


class PairedComparison(TypedDict):
    baseline: str
    candidate: str
    direction: str
    negative_means: str
    common_sample_size: int
    mean_log_loss_difference: str | None
    mean_brier_difference: str | None


class ModelEvaluations(TypedDict):
    evaluation_version: str
    evaluation_mode: Literal["FROZEN_SAMPLE_SET"]
    models: dict[str, EvaluationResult]
    paired_comparisons: list[PairedComparison]


def _prepare(samples: Iterable[EvaluationSample]) -> tuple[EvaluationSample, ...]:
    rows = tuple(samples)
    seen: set[tuple[str, str]] = set()
    actuals: dict[str, str] = {}
    for sample in rows:
        if not isinstance(sample, EvaluationSample):
            raise ValueError("Expected immutable EvaluationSample")
        key = (sample.prediction_source, sample.match_id)
        if key in seen:
            raise ValueError("Duplicate prediction_source + match_id")
        seen.add(key)
        if actuals.setdefault(sample.match_id, sample.actual_result) != sample.actual_result:
            raise ValueError("Conflicting actual_result for the same match_id")
    return tuple(sorted(rows, key=lambda s: (s.match_id, s.prediction_source, s.sample_id)))


def _losses(sample: EvaluationSample) -> tuple[Decimal, Decimal]:
    log_loss = -max(sample.probabilities[sample.actual_result], LOG_EPSILON).ln()
    brier = sum(((sample.probabilities[k] - int(k == sample.actual_result)) ** 2 for k in OUTCOMES), ZERO)
    return log_loss, brier


def _encoded(value: Decimal) -> str:
    return str(value if value else ZERO)  # Canonical zero, never "-0".


def _calibration(
    samples: tuple[EvaluationSample, ...],
) -> tuple[dict[str, list[CalibrationBin]], dict[str, str | None]]:
    calibration, ece = {}, {}
    ece_values = []
    for outcome in OUTCOMES:
        counts = [0] * 10
        totals = [ZERO] * 10
        positives = [0] * 10
        for sample in samples:
            p = sample.probabilities[outcome]
            # Direct comparisons preserve exact boundaries even beyond 50 digits.
            index = next((i for i in range(9) if p < BIN_EDGES[i + 1]), 9)
            counts[index] += 1
            totals[index] += p
            positives[index] += int(sample.actual_result == outcome)
        bins = []
        weighted_error = ZERO
        for i, count in enumerate(counts):
            mean = totals[i] / count if count else None
            frequency = Decimal(positives[i]) / count if count else None
            error = abs(mean - frequency) if mean is not None and frequency is not None else None
            bins.append(
                CalibrationBin(
                    lower_bound=str(BIN_EDGES[i]),
                    upper_bound=str(BIN_EDGES[i + 1]),
                    upper_inclusive=i == 9,
                    count=count,
                    mean_predicted_probability=_encoded(mean) if mean is not None else None,
                    actual_frequency=_encoded(frequency) if frequency is not None else None,
                    calibration_error=_encoded(error) if error is not None else None,
                )
            )
            if error is not None:
                weighted_error += (Decimal(count) / len(samples)) * error
        calibration[outcome] = bins
        ece[outcome] = _encoded(weighted_error) if samples else None
        ece_values.append(weighted_error)
    ece["macro"] = _encoded(sum(ece_values, ZERO) / 3) if samples else None
    return calibration, ece


def evaluate(samples: Iterable[EvaluationSample], *, eligible_samples: int | None = None) -> EvaluationResult:
    """Equal-weight metrics for one source; invalid/duplicate samples fail the run.

    Unknown or zero eligible denominator yields coverage=None. Never normalize or
    mutate predictions. FROZEN_SAMPLE_SET does not certify live as-of provenance.
    """
    rows = _prepare(samples)
    sources = {s.prediction_source for s in rows}
    if len(sources) > 1:
        raise ValueError("evaluate requires one prediction_source; use evaluate_models")
    n = len(rows)
    if eligible_samples is not None and (type(eligible_samples) is not int or eligible_samples < n):
        raise ValueError("eligible_samples must be an integer >= evaluated_samples")
    with localcontext(_CONTEXT):
        log_total = brier_total = ZERO
        correct = clipped = 0
        for sample in rows:
            log_loss, brier = _losses(sample)
            log_total += log_loss
            brier_total += brier
            predicted = max(OUTCOMES, key=lambda k: sample.probabilities[k])
            correct += int(predicted == sample.actual_result)
            clipped += int(sample.probabilities[sample.actual_result] < LOG_EPSILON)
        calibration, ece = _calibration(rows)
        return EvaluationResult(
            evaluation_version=EVALUATION_VERSION,
            evaluation_mode=EVALUATION_MODE,
            prediction_source=rows[0].prediction_source if rows else None,
            sample_size=n,
            eligible_samples=eligible_samples,
            evaluated_samples=n,
            coverage=_encoded(Decimal(n) / eligible_samples) if eligible_samples else None,
            log_loss=_encoded(log_total / n) if n else None,
            brier_score=_encoded(brier_total / n) if n else None,
            accuracy=_encoded(Decimal(correct) / n) if n else None,
            clipping_count=clipped,
            calibration=calibration,
            ece=ece,
        )


def evaluate_models(
    samples: Mapping[str, Iterable[EvaluationSample]],
    *,
    baseline: str,
    eligible_samples: Mapping[str, int] | None = None,
) -> ModelEvaluations:
    """Compare each named candidate to an explicitly named baseline on common matches.

    Each model also retains metrics over its full own sample set and own coverage.
    No ranking, winner, significance estimate or coverage denominator is inferred.
    """
    for source in samples:
        _identity(source, "prediction_source")
    if baseline not in samples:
        raise ValueError("baseline must name a supplied model")
    if eligible_samples is not None and set(eligible_samples) - set(samples):
        raise ValueError("Unknown model in eligible_samples")
    groups = {source: _prepare(samples[source]) for source in sorted(samples)}
    _prepare(sample for rows in groups.values() for sample in rows)
    models = {}
    for source, rows in groups.items():
        if any(s.prediction_source != source for s in rows):
            raise ValueError("Model key must equal sample prediction_source")
        result = evaluate(rows, eligible_samples=eligible_samples.get(source) if eligible_samples else None)
        result["prediction_source"] = source  # Includes explicitly supplied empty models.
        models[source] = result
    pairs = []
    base = {s.match_id: s for s in groups[baseline]}
    with localcontext(_CONTEXT):
        for source, rows in groups.items():
            if source == baseline:
                continue
            common = [s for s in rows if s.match_id in base]
            log_delta = brier_delta = ZERO
            for sample in common:
                candidate_log, candidate_brier = _losses(sample)
                baseline_log, baseline_brier = _losses(base[sample.match_id])
                log_delta += candidate_log - baseline_log
                brier_delta += candidate_brier - baseline_brier
            pairs.append(
                PairedComparison(
                    baseline=baseline,
                    candidate=source,
                    direction="candidate - baseline",
                    negative_means="candidate loss is lower",
                    common_sample_size=len(common),
                    mean_log_loss_difference=_encoded(log_delta / len(common)) if common else None,
                    mean_brier_difference=_encoded(brier_delta / len(common)) if common else None,
                )
            )
    return ModelEvaluations(
        evaluation_version=EVALUATION_VERSION,
        evaluation_mode=EVALUATION_MODE,
        models=models,
        paired_comparisons=pairs,
    )


def market_evaluation_sample(
    market_data: Mapping[str, Any],
    *,
    sample_id: str,
    match_id: str,
    actual_result: str,
    match_time: datetime | None = None,
) -> EvaluationSample | None:
    """Read frozen external_consensus.p_market only; None means not evaluable."""
    probabilities = market_data["external_consensus"]["p_market"]
    if probabilities is None:
        return None
    return EvaluationSample(
        sample_id, match_id, market_data["version"], probabilities, actual_result, match_time=match_time
    )


def goals_evaluation_sample(
    result: "GoalsBaselineResult",
    *,
    sample_id: str,
    match_id: str,
    actual_result: str,
    match_time: datetime | None = None,
) -> EvaluationSample | None:
    """Read a frozen OK result's score.one_x_two, without rerunning the model."""
    if result["status"] not in {"OK", "INSUFFICIENT_DATA", "OUT_OF_RANGE"}:
        raise ValueError("Unknown Goals Baseline status")
    if result["status"] != "OK" or result["score"] is None:
        return None
    return EvaluationSample(
        sample_id,
        match_id,
        result["version"],
        result["score"]["one_x_two"],
        actual_result,
        match_time=match_time,
    )


def temporal_split(
    samples: Iterable[EvaluationSample], cutoff_date: datetime
) -> tuple[tuple[EvaluationSample, ...], tuple[EvaluationSample, ...]]:
    """Explicit match_time < cutoff versus >= cutoff, ordered oldest first in UTC.

    This partitions samples only; it neither trains nor proves historical visibility.
    Missing timestamps are rejected, never inferred from IDs or sample order.
    """
    cutoff = _utc(cutoff_date)
    rows = _prepare(samples)
    times: dict[str, datetime] = {}
    for sample in rows:
        if sample.match_time is None:
            raise ValueError("temporal_split requires match_time on every sample")
        if times.setdefault(sample.match_id, sample.match_time) != sample.match_time:
            raise ValueError("Conflicting match_time for the same match_id")
    ordered = sorted(rows, key=lambda s: (times[s.match_id], s.match_id, s.prediction_source, s.sample_id))
    return (
        tuple(s for s in ordered if times[s.match_id] < cutoff),
        tuple(s for s in ordered if times[s.match_id] >= cutoff),
    )
