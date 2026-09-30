"""Deterministic facts, no model. Every input is immutable and proven visible at cutoff."""

from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from jc.analysis.contracts import FEATURE_VERSION, FRESHNESS_SECONDS, QUALITY_VERSION, FeatureData
from jc.analysis.visibility import proven, record_visibility, temporal
from jc.entities import CONFIRMED
from jc.models import (
    AuditLog,
    FeatureSnapshot,
    MatchResult,
    MatchVersion,
    OddsObservation,
    OddsSnapshot,
    RawPayload,
    TeamMatchStats,
)
from jc.odds import SERIES, insert_ignoring_duplicate, odds_change
from jc.time import as_utc, parse_time, utcnow


class MatchNotVisible(ValueError):
    pass


def visible_versions(db: Session, cutoff: datetime, mock: bool) -> dict[str, MatchVersion]:
    rows = db.scalars(
        select(MatchVersion)
        .join(RawPayload, RawPayload.id == MatchVersion.raw_payload_id)
        .where(
            *temporal(MatchVersion, cutoff),
            *temporal(RawPayload, cutoff),
            RawPayload.provider == "sporttery",
            RawPayload.mock == mock,
        )
        .order_by(MatchVersion.collected_at.desc(), MatchVersion.created_at.desc(), MatchVersion.id.desc())
    )
    versions: dict[str, MatchVersion] = {}
    for version in rows:
        if version.state.get("mock") == mock:
            versions.setdefault(version.match_id, version)
    return versions


def mapping_evidence(db: Session, cutoff: datetime) -> dict[str, AuditLog]:
    events = db.scalars(
        select(AuditLog)
        .where(
            AuditLog.entity_type == "mapping",
            AuditLog.created_at <= cutoff,
            proven(AuditLog, cutoff),
        )
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
    )
    states: dict[str, AuditLog] = {}
    for event in events:
        states.setdefault(event.entity_id, event)
    return states


def binding_valid(row, events: dict[str, AuditLog]) -> bool:
    source = row.provider if isinstance(row, OddsSnapshot) else row.source
    if source == "sporttery":
        return row.mapping_id is None and row.mapping_version is None
    event = events.get(row.mapping_id)
    state = event.after if event else None
    return bool(
        state
        and state.get("status") in CONFIRMED
        and state.get("match_id") == row.match_id
        and state.get("version") == row.mapping_version
    )


def price_data(row: OddsSnapshot) -> dict:
    return {
        "odds_snapshot_id": row.id,
        "raw_payload_id": row.raw_payload_id,
        "provider": row.provider,
        "bookmaker": row.bookmaker,
        "market_type": row.market_type,
        "selection": row.selection,
        "line": str(row.line) if row.line is not None else None,
        "decimal_odds": str(row.decimal_odds),
        "implied_probability": str(row.implied_probability),
        "collected_at": row.collected_at.isoformat(),
        "effective_at": row.effective_at.isoformat() if row.effective_at else None,
        "published_at": row.published_at.isoformat() if row.published_at else None,
        "mapping_id": row.mapping_id,
        "mapping_version": row.mapping_version,
    }


def visible_prices(db, match_id, cutoff, mock, events):
    rows = db.scalars(
        select(OddsSnapshot)
        .join(RawPayload, RawPayload.id == OddsSnapshot.raw_payload_id)
        .where(
            OddsSnapshot.match_id == match_id,
            OddsSnapshot.mock == mock,
            RawPayload.mock == mock,
            RawPayload.provider == OddsSnapshot.provider,
            *temporal(OddsSnapshot, cutoff),
            *temporal(RawPayload, cutoff),
        )
        .order_by(
            func.coalesce(OddsSnapshot.effective_at, OddsSnapshot.collected_at).desc(),
            OddsSnapshot.collected_at.desc(),
            OddsSnapshot.created_at.desc(),
            OddsSnapshot.id.desc(),
        )
    )
    series: dict[tuple, list[OddsSnapshot]] = defaultdict(list)
    for row in rows:
        if binding_valid(row, events):
            # Movements never cross a binding version or a handicap line.
            key = tuple(str(getattr(row, key)) for key in SERIES) + (
                str(row.mapping_id),
                str(row.mapping_version),
            )
            if len(series[key]) < 2:
                series[key].append(row)
    return [series[key] for key in sorted(series)]


def last_observations(db, prices, cutoff, mock):
    observations: dict[str, OddsObservation] = {}
    if prices:
        rows = db.execute(
            select(OddsObservation, OddsSnapshot.provider)
            .join(
                RawPayload,
                RawPayload.id == OddsObservation.raw_payload_id,
            )
            .join(OddsSnapshot, OddsSnapshot.id == OddsObservation.odds_snapshot_id)
            .where(
                OddsObservation.odds_snapshot_id.in_([rows[0].id for rows in prices]),
                *temporal(OddsObservation, cutoff),
                *temporal(RawPayload, cutoff),
                RawPayload.mock == mock,
                RawPayload.provider == OddsSnapshot.provider,
            )
            .order_by(
                OddsObservation.collected_at.desc(),
                OddsObservation.created_at.desc(),
                OddsObservation.id.desc(),
            )
        )
        for row, _ in rows:
            observations.setdefault(row.odds_snapshot_id, row)
    return observations


def past_facts(db, target_id, target_state, versions, events, cutoff, mock):
    """Expose source-specific observations, not fabricated strength ratings or averages."""
    teams = {target_state.get("home_team_id"), target_state.get("away_team_id")} - {None}
    target_kickoff = parse_time(target_state["kickoff_at"])
    output: dict[str, list] = {"results": [], "stats": []}
    for model, name, fields in (
        (
            MatchResult,
            "results",
            (
                "home_score",
                "away_score",
                "half_home_score",
                "half_away_score",
                "first_goal_team",
                "first_goal_minute",
            ),
        ),
        (
            TeamMatchStats,
            "stats",
            ("team_id", "xg", "xga", "shots", "shots_on_target", "possession", "corners", "red_cards"),
        ),
    ):
        query = (
            select(model)
            .join(RawPayload, RawPayload.id == model.raw_payload_id)
            .where(
                model.match_id != target_id,
                model.mock == mock,
                RawPayload.mock == mock,
                RawPayload.provider == model.source,
                *temporal(model, cutoff, "observed_at"),
                *temporal(RawPayload, cutoff),
                model.finished_at < cutoff,
                model.finished_at < target_kickoff,
            )
            .order_by(model.observed_at.desc(), model.created_at.desc(), model.id.desc())
        )
        latest = set()
        for row in db.scalars(query):
            version = versions.get(row.match_id)
            if not version or not binding_valid(row, events):
                continue
            bound_version = db.scalar(
                select(MatchVersion)
                .join(RawPayload, RawPayload.id == MatchVersion.raw_payload_id)
                .where(
                    MatchVersion.id == row.match_version_id,
                    MatchVersion.match_id == row.match_id,
                    *temporal(MatchVersion, cutoff),
                    *temporal(RawPayload, cutoff),
                    RawPayload.mock == mock,
                    RawPayload.provider == "sporttery",
                )
            )
            if not bound_version or any(
                bound_version.state.get(key) != version.state.get(key)
                for key in ("home_team_id", "away_team_id", "kickoff_at")
            ):
                continue
            participants = {version.state.get("home_team_id"), version.state.get("away_team_id")} - {None}
            if (
                not participants & teams
                or (model is TeamMatchStats and row.team_id not in participants & teams)
                or row.finished_at <= parse_time(version.state["kickoff_at"])
            ):
                continue
            key = (row.match_id, row.source, getattr(row, "team_id", None))
            if key in latest:
                continue
            latest.add(key)
            values = {field: getattr(row, field) for field in fields}
            values = {
                key: str(value) if isinstance(value, Decimal) else value for key, value in values.items()
            }
            output[name].append(
                {
                    **values,
                    "id": row.id,
                    "match_id": row.match_id,
                    "match_version_id": row.match_version_id,
                    "home_team_id": version.state.get("home_team_id"),
                    "away_team_id": version.state.get("away_team_id"),
                    "source": row.source,
                    "raw_payload_id": row.raw_payload_id,
                    "finished_at": row.finished_at.isoformat(),
                    "observed_at": row.observed_at.isoformat(),
                    "mapping_evidence_id": events[row.mapping_id].id if row.mapping_id else None,
                }
            )
        output[name].sort(key=lambda item: (item["match_id"], item["source"], item.get("team_id", "")))
    return output


def data_quality(state, prices, observations, version, cutoff, events):
    """V1: five equally weighted binary availability checks, 20 points each.

    Unknown is zero points, never a guessed value. Counts and ages remain explicit.
    This measures input availability only; it is neither confidence nor a recommendation gate.
    """
    external = sorted({rows[0].provider for rows in prices if rows[0].provider != "sporttery"})
    sporttery = any(rows[0].provider == "sporttery" for rows in prices)
    match_available = all(
        state.get(key) is not None
        for key in (
            "kickoff_at",
            "home_team_id",
            "away_team_id",
            "competition_id",
            "sell_status",
        )
    )
    ages = {"match": (cutoff - version.collected_at).total_seconds()}
    for rows in prices:
        row = rows[0]
        seen = observations.get(row.id)
        ages["odds:" + row.id] = (cutoff - (seen.collected_at if seen else row.collected_at)).total_seconds()
    fresh = bool(prices) and all(0 <= age <= FRESHNESS_SECONDS for age in ages.values())
    mapping_ok = bool(state.get("home_team_id") and state.get("away_team_id") and external)
    checks = {
        "match_data_available": match_available,
        "sporttery_odds_available": sporttery,
        "external_odds_coverage": bool(external),
        "entity_mapping_quality": mapping_ok,
        "source_freshness": fresh,
    }
    score = 20 * sum(checks.values())
    return {
        "algorithm": QUALITY_VERSION,
        "checks": checks,
        "points_per_check": 20,
        "external_provider_count": len(external),
        "external_providers": external,
        "entity_mapping_status": "CONFIRMED" if mapping_ok else "UNKNOWN",
        "mapping_evidence_ids": sorted(
            {events[rows[0].mapping_id].id for rows in prices if rows[0].mapping_id}
        ),
        "source_age_seconds": ages,
        "freshness_threshold_seconds": FRESHNESS_SECONDS,
        "missing_sections": ["squad", "context.evidence", "team_strength.rating"],
        "score": score,
    }


def build_feature_data(db: Session, match_id: str, cutoff: datetime, *, mock: bool) -> FeatureData:
    cutoff = as_utc(cutoff)
    if cutoff > utcnow():
        raise ValueError("analysis_cutoff cannot be in the future")
    # Finish/probe committed evidence receipts before reading; concurrent receipt INSERTs
    # are resolved by the unique key, including receipts pending at the requested cutoff.
    record_visibility(db.get_bind().engine)
    versions = visible_versions(db, cutoff, mock)
    version = versions.get(match_id)
    if version is None:
        raise MatchNotVisible("No proven match version was visible at analysis_cutoff")
    state = version.state
    if cutoff >= parse_time(state["kickoff_at"]):
        raise ValueError("Feature v1 requires a pre-match analysis_cutoff")
    events = mapping_evidence(db, cutoff)
    prices = visible_prices(db, match_id, cutoff, mock, events)
    observations = last_observations(db, prices, cutoff, mock)
    quality = data_quality(state, prices, observations, version, cutoff, events)
    facts = past_facts(db, match_id, state, versions, events, cutoff, mock)
    movements = []
    for rows in prices:
        latest, previous = rows[0], rows[1] if len(rows) > 1 else None
        change = odds_change(previous.decimal_odds if previous else None, latest.decimal_odds)
        movements.append(
            {
                "odds_snapshot_id": latest.id,
                "previous_snapshot_id": previous.id if previous else None,
                **{key: str(value) if isinstance(value, Decimal) else value for key, value in change.items()},
            }
        )
    return FeatureData(
        market={
            "quotes": [
                dict(
                    price_data(rows[0]),
                    observation_id=observations[rows[0].id].id if rows[0].id in observations else None,
                )
                for rows in prices
            ]
        },
        odds_movement={"items": movements},
        team_strength={"rating": None, "past_results": facts["results"], "past_stats": facts["stats"]},
        schedule={
            "kickoff_at": state["kickoff_at"],
            "seconds_to_kickoff": (parse_time(state["kickoff_at"]) - cutoff).total_seconds(),
            "rest_days": None,
        },
        squad={"available": False, "players": None},
        context={
            "mock": mock,
            "match_version_id": version.id,
            "raw_payload_id": version.raw_payload_id,
            "match": {
                key: state.get(key)
                for key in (
                    "sporttery_match_id",
                    "competition_id",
                    "competition_name",
                    "home_team_id",
                    "away_team_id",
                    "home_team_name",
                    "away_team_name",
                    "sell_status",
                    "markets",
                    "local_timezone",
                )
            },
            "evidence": None,
        },
        data_quality=quality,
    )


def get_or_create_snapshot(db: Session, match_id: str, cutoff: datetime, *, mock: bool) -> FeatureSnapshot:
    cutoff = as_utc(cutoff)
    query = select(FeatureSnapshot).where(
        FeatureSnapshot.match_id == match_id,
        FeatureSnapshot.analysis_cutoff == cutoff,
        FeatureSnapshot.feature_version == FEATURE_VERSION,
        FeatureSnapshot.mock == mock,
    )
    existing = db.scalar(query)
    if existing:
        return existing
    data = build_feature_data(db, match_id, cutoff, mock=mock)
    insert_ignoring_duplicate(
        db,
        FeatureSnapshot,
        [
            {
                "id": str(uuid4()),
                "match_id": match_id,
                "analysis_cutoff": cutoff,
                "feature_version": FEATURE_VERSION,
                "feature_data": data.model_dump(mode="json"),
                "data_quality_score": data.data_quality["score"],
                "mock": mock,
                "created_at": utcnow(),
            }
        ],
    )
    row = db.scalar(query)
    assert row is not None
    return row
