"""Research-only, in-memory replay of explicitly supplied historical evidence.

No online observation is asserted. Availability, selection, conflicts, cutoffs
and feature construction are all versioned together; changing them needs v2.
"""

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import asdict, dataclass, fields, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import StrEnum

from jc.analysis.contracts import FeatureData
from jc.analysis.evaluation import (
    EvaluationSample,
    evaluate_models,
    goals_evaluation_sample,
    market_evaluation_sample,
)
from jc.analysis.goals_baseline import GOALS_BASELINE_VERSION, estimate_goals_baseline
from jc.analysis.market import MARKET_MODEL_VERSION, build_market_data

RESEARCH_REPLAY_VERSION = "research-replay-v1"
EVALUATION_MODE = "RESEARCH_REPLAY"


class AvailabilityBasis(StrEnum):
    SOURCE_SNAPSHOT_AT = "SOURCE_SNAPSHOT_AT"
    PROVIDER_PUBLISHED_AT = "PROVIDER_PUBLISHED_AT"
    PROVIDER_EFFECTIVE_AT = "PROVIDER_EFFECTIVE_AT"
    VERIFIED_ARCHIVE_TIMESTAMP = "VERIFIED_ARCHIVE_TIMESTAMP"


def _identity(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a nonempty string")


def _utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Research timestamps require timezone-aware datetime")
    return value.astimezone(UTC)


@dataclass(frozen=True, kw_only=True)
class _AvailableRecord:
    # Explicit None/None retains an unavailable record without inventing a time.
    replay_available_at: datetime | None
    availability_basis: AvailabilityBasis | None
    published_at: datetime | None = None
    effective_at: datetime | None = None

    def __post_init__(self) -> None:
        for field in fields(self):
            value = getattr(self, field.name)
            if field.name.endswith("_at") and value is not None:
                object.__setattr__(self, field.name, _utc(value))
            elif field.name.endswith("_id") and value is not None:
                _identity(value, field.name)
        if (self.replay_available_at is None) != (self.availability_basis is None):
            raise ValueError("Availability requires both an explicit timestamp and verified basis")
        if self.availability_basis is not None:
            basis = AvailabilityBasis(self.availability_basis)
            object.__setattr__(self, "availability_basis", basis)
            evidence = {
                AvailabilityBasis.PROVIDER_PUBLISHED_AT: self.published_at,
                AvailabilityBasis.PROVIDER_EFFECTIVE_AT: self.effective_at,
                AvailabilityBasis.SOURCE_SNAPSHOT_AT: self.replay_available_at,
                AvailabilityBasis.VERIFIED_ARCHIVE_TIMESTAMP: self.replay_available_at,
            }[basis]
            if evidence is None or evidence != self.replay_available_at:
                raise ValueError("replay_available_at must equal the named time evidence; no inferred lag")

    @property
    def replay_status(self) -> str:
        return "REPLAY_AVAILABLE" if self.replay_available_at is not None else "REPLAY_UNAVAILABLE"


def _teams(home: str | None, away: str | None) -> None:
    if home is not None and home == away:
        raise ValueError("Canonical home and away team IDs must differ")


@dataclass(frozen=True, kw_only=True)
class ResearchMatch(_AvailableRecord):
    research_match_id: str
    sporttery_match_id: str | None
    competition_id: str | None
    home_team_id: str | None
    away_team_id: str | None
    kickoff_at: datetime
    source: str
    source_record_id: str

    def __post_init__(self) -> None:
        super().__post_init__()
        _identity(self.research_match_id, "research_match_id")
        _identity(self.source_record_id, "source_record_id")
        _identity(self.source, "source")
        object.__setattr__(self, "kickoff_at", _utc(self.kickoff_at))
        _teams(self.home_team_id, self.away_team_id)


@dataclass(frozen=True, kw_only=True)
class ResearchOddsQuote(_AvailableRecord):
    record_id: str
    research_match_id: str
    provider: str
    bookmaker: str
    market_type: str
    selection: str
    line: Decimal | None
    decimal_odds: Decimal

    def __post_init__(self) -> None:
        super().__post_init__()
        for name in ("record_id", "research_match_id", "provider", "bookmaker", "market_type", "selection"):
            _identity(getattr(self, name), name)
        for name in ("decimal_odds", "line"):
            value = getattr(self, name)
            if value is None and name == "line":
                continue
            if not isinstance(value, Decimal) or not value.is_finite():
                raise ValueError(f"{name} must be finite Decimal; no float")
        if self.decimal_odds <= 1:
            raise ValueError("decimal_odds must exceed one")


@dataclass(frozen=True, kw_only=True)
class ResearchResult(_AvailableRecord):
    record_id: str
    research_match_id: str
    home_team_id: str | None
    away_team_id: str | None
    home_score: int
    away_score: int
    finished_at: datetime
    source: str
    score_scope: str = "REGULATION"

    def __post_init__(self) -> None:
        super().__post_init__()
        for name in ("record_id", "research_match_id", "source"):
            _identity(getattr(self, name), name)
        object.__setattr__(self, "finished_at", _utc(self.finished_at))
        _teams(self.home_team_id, self.away_team_id)
        if self.score_scope != "REGULATION":
            raise ValueError("Only REGULATION results are supported")
        for score in (self.home_score, self.away_score):
            if type(score) is not int or score < 0:
                raise ValueError("Scores must be nonnegative integers")


@dataclass(frozen=True, kw_only=True)
class ResearchSource:
    source_name: str
    source_type: str
    retrieval_note: str

    def __post_init__(self) -> None:
        for field in fields(self):
            _identity(getattr(self, field.name), field.name)


@dataclass(frozen=True, kw_only=True)
class ResearchDataset:
    dataset_id: str
    dataset_version: str
    replay_version: str
    matches: tuple[ResearchMatch, ...]
    odds: tuple[ResearchOddsQuote, ...]
    results: tuple[ResearchResult, ...]
    source_manifest: tuple[ResearchSource, ...]

    def __post_init__(self) -> None:
        _identity(self.dataset_id, "dataset_id")
        _identity(self.dataset_version, "dataset_version")
        if self.replay_version != RESEARCH_REPLAY_VERSION:
            raise ValueError("Unsupported replay_version")
        for name, kind, key in (
            ("matches", ResearchMatch, "research_match_id"),
            ("odds", ResearchOddsQuote, "record_id"),
            ("results", ResearchResult, "record_id"),
            ("source_manifest", ResearchSource, "source_name"),
        ):
            rows = tuple(getattr(self, name))
            if any(not isinstance(row, kind) for row in rows):
                raise ValueError(f"{name} requires immutable research contracts")
            if len({getattr(row, key) for row in rows}) != len(rows):
                raise ValueError(f"Duplicate {name} identity")
            object.__setattr__(self, name, tuple(sorted(rows, key=lambda row: getattr(row, key))))
        sources = {s.source_name for s in self.source_manifest}
        if not sources:
            raise ValueError("source_manifest is required")
        matches = {m.research_match_id: m for m in self.matches}
        for match in self.matches:
            if match.source not in sources:
                raise ValueError("Match source missing from manifest")
        records: tuple[ResearchOddsQuote | ResearchResult, ...] = (*self.odds, *self.results)
        for record in records:
            if record.research_match_id not in matches:
                raise ValueError("Unknown research_match_id")
            source = record.provider if isinstance(record, ResearchOddsQuote) else record.source
            if source not in sources:
                raise ValueError("Record source missing from manifest")
            if isinstance(record, ResearchResult):
                match = matches[record.research_match_id]
                for name in ("home_team_id", "away_team_id"):
                    team, expected = getattr(record, name), getattr(match, name)
                    if team is not None and expected is not None and team != expected:
                        raise ValueError("Result contradicts dataset canonical team identity")


@dataclass(frozen=True)
class ReplayCutoffSpec:
    minutes: int
    kind: str = "MINUTES_BEFORE_KICKOFF"

    def __post_init__(self) -> None:
        if self.kind != "MINUTES_BEFORE_KICKOFF" or type(self.minutes) is not int or self.minutes <= 0:
            raise ValueError("Cutoff requires positive integer MINUTES_BEFORE_KICKOFF")

    def at(self, kickoff_at: datetime) -> datetime:
        return _utc(kickoff_at) - timedelta(minutes=self.minutes)


class NotReplayable(ValueError):
    status = "NOT_REPLAYABLE"


def _visible(record: _AvailableRecord, cutoff: datetime) -> bool:
    return record.replay_available_at is not None and all(
        value is None or value <= cutoff
        for value in (record.replay_available_at, record.published_at, record.effective_at)
    )


def _evidence(record: _AvailableRecord) -> dict:
    return {
        "replay_available_at": (
            record.replay_available_at.isoformat() if record.replay_available_at is not None else None
        ),
        "availability_basis": record.availability_basis.value if record.availability_basis else None,
        "published_at": record.published_at.isoformat() if record.published_at is not None else None,
        "effective_at": record.effective_at.isoformat() if record.effective_at is not None else None,
    }


def _metadata(dataset: ResearchDataset, cutoff_spec: ReplayCutoffSpec) -> dict:
    return {
        "mode": EVALUATION_MODE,
        "evaluation_mode": EVALUATION_MODE,
        "replay_version": dataset.replay_version,
        "dataset_id": dataset.dataset_id,
        "dataset_version": dataset.dataset_version,
        "cutoff_kind": cutoff_spec.kind,
        "cutoff_minutes": cutoff_spec.minutes,
        "live_visibility_proven": False,
        "canonical_identity_basis": "RESEARCH_DATASET",
        "source_manifest": [asdict(source) for source in dataset.source_manifest],
    }


def _quote_data(quote: ResearchOddsQuote) -> dict:
    return {
        "odds_snapshot_id": quote.record_id,
        "research_match_id": quote.research_match_id,
        "provider": quote.provider,
        "bookmaker": quote.bookmaker,
        "market_type": quote.market_type,
        "selection": quote.selection,
        "line": str(quote.line) if quote.line is not None else None,
        "decimal_odds": str(quote.decimal_odds),
        "mapping_id": None,
        "mapping_version": None,
        **_evidence(quote),
    }


def build_research_feature(
    dataset: ResearchDataset, research_match_id: str, cutoff_spec: ReplayCutoffSpec
) -> FeatureData:
    """Fresh FeatureData or NOT_REPLAYABLE; never mutates supplied records.

    Input IDs are type-namespaced and include previous quotes and historical
    match evidence. Target labels are unconditionally excluded before filtering.
    """
    matches = {m.research_match_id: m for m in dataset.matches}
    target = matches[research_match_id]
    cutoff = cutoff_spec.at(target.kickoff_at)
    if not _visible(target, cutoff):
        raise NotReplayable(f"NOT_REPLAYABLE: {research_match_id}: MATCH_UNAVAILABLE_AT_CUTOFF")
    series: dict[tuple, list[ResearchOddsQuote]] = defaultdict(list)
    for quote in dataset.odds:
        if quote.research_match_id == research_match_id and _visible(quote, cutoff):
            # Decimal equality canonicalizes raw lines exactly, without context rounding.
            series[(quote.provider, quote.bookmaker, quote.market_type, quote.selection, quote.line)].append(
                quote
            )
    quotes, movements = [], []
    used_odds: set[str] = set()
    for key in sorted(series, key=lambda k: (*k[:4], k[4] is not None, k[4] or Decimal(0))):
        rows = sorted(
            series[key],
            key=lambda q: (q.effective_at or q.published_at or q.replay_available_at, q.record_id),
            reverse=True,
        )
        latest, previous = rows[0], rows[1] if len(rows) > 1 else None
        quotes.append(_quote_data(latest))
        used_odds.add(latest.record_id)
        if previous is not None:
            used_odds.add(previous.record_id)
        movements.append(
            {
                "odds_snapshot_id": latest.record_id,
                "previous_snapshot_id": previous.record_id if previous is not None else None,
                "current_odds": str(latest.decimal_odds),
                "previous_odds": str(previous.decimal_odds) if previous is not None else None,
                "previous_quote": _quote_data(previous) if previous is not None else None,
            }
        )
    teams = {target.home_team_id, target.away_team_id} - {None}
    history = []
    used_matches = {research_match_id}
    for result in dataset.results:
        if result.research_match_id == research_match_id:
            continue  # Hard exclusion, independent of every supplied timestamp.
        match = matches[result.research_match_id]
        if (
            match.home_team_id is None
            or match.away_team_id is None
            or result.home_team_id is None
            or result.away_team_id is None
            or not teams.intersection((result.home_team_id, result.away_team_id))
            or not _visible(match, cutoff)
            or not _visible(result, cutoff)
            or not match.kickoff_at < result.finished_at < cutoff
        ):
            continue
        used_matches.add(match.research_match_id)
        history.append(
            {
                "record_id": result.record_id,
                "match_id": result.research_match_id,
                "home_team_id": result.home_team_id,
                "away_team_id": result.away_team_id,
                "home_score": result.home_score,
                "away_score": result.away_score,
                "finished_at": result.finished_at.isoformat(),
                "source": result.source,
                "score_scope": result.score_scope,
                **_evidence(result),
            }
        )
    research = {
        **_metadata(dataset, cutoff_spec),
        "research_match_id": research_match_id,
        "analysis_cutoff": cutoff.isoformat(),
        "input_record_ids": {
            "matches": sorted(used_matches),
            "odds": sorted(used_odds),
            "results": [row["record_id"] for row in history],
        },
        "match_records": [
            {
                "research_match_id": mid,
                "source": matches[mid].source,
                "source_record_id": matches[mid].source_record_id,
                "kickoff_at": matches[mid].kickoff_at.isoformat(),
                **_evidence(matches[mid]),
            }
            for mid in sorted(used_matches)
        ],
    }
    quality = {
        "match_available": True,
        "market_source_count": len({(q["provider"], q["bookmaker"]) for q in quotes}),
        "historical_result_count_home": sum(
            target.home_team_id in (r["home_team_id"], r["away_team_id"]) for r in history
        ),
        "historical_result_count_away": sum(
            target.away_team_id in (r["home_team_id"], r["away_team_id"]) for r in history
        ),
        "records_without_verified_availability": sum(
            row.replay_available_at is None
            for row in (*dataset.matches, *dataset.odds, *dataset.results)
            if not isinstance(row, ResearchResult) or row.research_match_id != research_match_id
        ),
    }
    return FeatureData(
        market={"quotes": quotes},
        odds_movement={"items": movements},
        team_strength={"rating": None, "past_results": history, "past_stats": []},
        schedule={
            "kickoff_at": target.kickoff_at.isoformat(),
            "seconds_to_kickoff": cutoff_spec.minutes * 60,
        },
        squad={"available": False, "players": None},
        context={
            "research": research,
            "match": {
                name: getattr(target, name)
                for name in (
                    "research_match_id",
                    "sporttery_match_id",
                    "competition_id",
                    "home_team_id",
                    "away_team_id",
                )
            },
        },
        data_quality={"research_data_quality": quality},
    )


def build_research_evaluation_samples(
    dataset: ResearchDataset, research_match_ids: Iterable[str], cutoff_spec: ReplayCutoffSpec
) -> tuple[dict[str, tuple[EvaluationSample, ...]], dict]:
    """Return immutable evaluation samples and a JSON-safe research report.

    One explicit cohort, one cutoff. Coverage denominator includes unavailable
    matches, missing/conflicting labels and either model's missing predictions.
    """
    ids = tuple(research_match_ids)
    if len(set(ids)) != len(ids):
        raise ValueError("Duplicate research target")
    matches = {m.research_match_id: m for m in dataset.matches}
    if set(ids) - matches.keys():
        raise ValueError("Unknown research target")
    market_source = f"{MARKET_MODEL_VERSION}@research-T{cutoff_spec.minutes}M"
    goals_source = f"{GOALS_BASELINE_VERSION}@research-T{cutoff_spec.minutes}M"
    groups: dict[str, list[EvaluationSample]] = {market_source: [], goals_source: []}
    diagnostics = {}
    replayable = 0
    for mid in sorted(ids):
        target = matches[mid]
        detail: dict = {
            "dataset_id": dataset.dataset_id,
            "research_match_id": mid,
            "analysis_cutoff": cutoff_spec.at(target.kickoff_at).isoformat(),
            "status": "NOT_REPLAYABLE",
            "input_record_ids": {"matches": [], "odds": [], "results": []},
            "label_record_ids": [],
            "diagnostics": [],
        }
        diagnostics[mid] = detail
        try:
            feature = build_research_feature(dataset, mid, cutoff_spec)
        except NotReplayable:
            detail["diagnostics"].append("MATCH_UNAVAILABLE_AT_CUTOFF")
            continue
        replayable += 1
        detail["status"] = "NOT_EVALUABLE"
        detail["input_record_ids"] = feature.context["research"]["input_record_ids"]
        detail["research_data_quality"] = feature.data_quality["research_data_quality"]
        labels = [r for r in dataset.results if r.research_match_id == mid]
        detail["label_record_ids"] = [r.record_id for r in labels]
        scores = {(r.home_score, r.away_score) for r in labels}
        if len(scores) > 1:
            detail["diagnostics"].append("CONFLICTING_TARGET_RESULT")
            continue
        if not labels:
            detail["diagnostics"].append("MISSING_TARGET_RESULT")
            continue
        if any(r.replay_available_at is None for r in labels):
            detail["diagnostics"].append("TARGET_RESULT_REPLAY_UNAVAILABLE")
            continue
        home, away = next(iter(scores))
        actual = "HOME" if home > away else "AWAY" if home < away else "DRAW"
        # Label times are deliberately not compared to the pre-match cutoff.
        market = build_market_data(feature)
        goals = estimate_goals_baseline(feature)
        samples = (
            (
                market_source,
                market_evaluation_sample(
                    market,
                    sample_id=f"{mid}:{market_source}",
                    match_id=mid,
                    actual_result=actual,
                    match_time=target.kickoff_at,
                ),
            ),
            (
                goals_source,
                goals_evaluation_sample(
                    goals,
                    sample_id=f"{mid}:{goals_source}",
                    match_id=mid,
                    actual_result=actual,
                    match_time=target.kickoff_at,
                ),
            ),
        )
        for source, sample in samples:
            if sample is not None:
                groups[source].append(replace(sample, prediction_source=source))
                detail["status"] = "EVALUABLE"
            else:
                detail["diagnostics"].append(f"NO_EVALUABLE_PREDICTION:{source}")
        detail["market_diagnostics"] = market["diagnostics"]
        detail["goals_diagnostics"] = goals["diagnostics"]
    report = {
        **_metadata(dataset, cutoff_spec),
        "cutoff": asdict(cutoff_spec),
        "matches_total": len(ids),
        "matches_replayable": replayable,
        "market_evaluable": len(groups[market_source]),
        "goals_evaluable": len(groups[goals_source]),
        "diagnostics": diagnostics,
    }
    return {source: tuple(rows) for source, rows in groups.items()}, report


def run_research_evaluation(
    dataset: ResearchDataset, research_match_ids: Iterable[str], cutoff_spec: ReplayCutoffSpec
) -> dict:
    """Research envelope around the unchanged evaluation-v1 frozen-sample math."""
    samples, report = build_research_evaluation_samples(dataset, research_match_ids, cutoff_spec)
    report["evaluation"] = evaluate_models(
        samples,
        baseline=f"{MARKET_MODEL_VERSION}@research-T{cutoff_spec.minutes}M",
        eligible_samples={source: report["matches_total"] for source in samples},
    )
    return report
