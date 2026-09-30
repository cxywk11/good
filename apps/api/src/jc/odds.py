import hashlib
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import and_, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from jc.entities import CONFIRMED
from jc.models import (
    AuditLog,
    Match,
    MatchMapping,
    OddsKeySnapshot,
    OddsObservation,
    OddsSnapshot,
    ProviderMatch,
)
from jc.providers.contracts import FetchedPayload, OddsQuote
from jc.time import utcnow

SERIES = ("match_id", "provider", "bookmaker", "market_type", "selection", "line")
KEY_OFFSETS = {
    "T_24H": 1440,
    "T_6H": 360,
    "T_3H": 180,
    "T_90M": 90,
    "T_30M": 30,
    "T_15M": 15,
    "T_5M": 5,
    "LAST_PREMATCH": 0,
}


def fingerprint(values) -> str:
    def canonical(value):
        if isinstance(value, Decimal):
            return str(value.normalize())
        return str(value)

    return hashlib.sha256("|".join(canonical(value) for value in values).encode()).hexdigest()


def insert_ignoring_duplicate(db, model, values: list[dict]):
    if not values:
        return
    insert = pg_insert if db.bind.dialect.name == "postgresql" else sqlite_insert
    for start in range(0, len(values), 300):
        db.execute(insert(model).values(values[start : start + 300]).on_conflict_do_nothing())


def key_series(row: OddsSnapshot) -> str:
    return fingerprint([getattr(row, field) for field in SERIES] + [row.mapping_id, row.mapping_version])


def store_quotes(db, provider, fetched: FetchedPayload, quotes: list[OddsQuote]) -> int:
    if not quotes:
        return 0
    targets: dict[str, tuple[Match, MatchMapping | None]] = {}
    if provider.is_primary:
        for match in db.scalars(
            select(Match).where(Match.sporttery_match_id.in_({q.external_match_id for q in quotes}))
        ):
            targets[match.sporttery_match_id] = (match, None)
    else:
        rows = db.execute(
            select(ProviderMatch, MatchMapping, Match)
            .join(MatchMapping, MatchMapping.provider_match_id == ProviderMatch.id)
            .join(Match, Match.id == MatchMapping.match_id)
            .where(ProviderMatch.provider == provider.name, MatchMapping.status.in_(CONFIRMED))
        )
        for pm, mapping, match in rows:
            targets[pm.provider_match_id] = (match, mapping)
    values_by_key: dict[str, dict] = {}
    quote_by_key: dict[str, OddsQuote] = {}
    for quote in quotes:
        target = targets.get(quote.external_match_id)
        if not target:
            continue  # Provider match remains visible as UNMATCHED / REVIEW; raw odds remain replayable.
        match, mapping = target
        if match.mock != fetched.mock:
            raise ValueError("Cannot mix fixture and live odds")
        if fetched.resource_type != "history" and fetched.collected_at >= match.kickoff_at:
            continue  # Pre-match collection only. No live betting scope.
        if quote.effective_at and quote.effective_at >= match.kickoff_at:
            continue
        key = fingerprint(
            [
                match.id,
                provider.name,
                quote.bookmaker,
                quote.market_type,
                quote.selection,
                quote.line,
                quote.decimal_odds,
                quote.effective_at or fetched.collected_at,
                mapping.version if mapping else None,
            ]
        )
        values_by_key[key] = {
            "id": str(uuid4()),
            "match_id": match.id,
            "provider": provider.name,
            "bookmaker": quote.bookmaker,
            "market_type": quote.market_type,
            "selection": quote.selection,
            "line": quote.line,
            "raw_odds": quote.raw_odds,
            "decimal_odds": quote.decimal_odds,
            "implied_probability": 1 / quote.decimal_odds,
            "collected_at": fetched.collected_at,
            "effective_at": quote.effective_at,
            "published_at": quote.published_at,
            "created_at": utcnow(),
            "source": fetched.source_url,
            "raw_payload_id": fetched.raw_id,
            "mapping_id": mapping.id if mapping else None,
            "mapping_version": mapping.version if mapping else None,
            "dedup_key": key,
            "mock": fetched.mock,
        }
        quote_by_key[key] = quote
    insert_ignoring_duplicate(db, OddsSnapshot, list(values_by_key.values()))
    # Preserve observation timestamps even when a provider returns the same effective quote again.
    stored = list(db.scalars(select(OddsSnapshot).where(OddsSnapshot.dedup_key.in_(values_by_key))))
    observations = [
        {
            "id": str(uuid4()),
            "odds_snapshot_id": row.id,
            "raw_payload_id": fetched.raw_id,
            "collected_at": fetched.collected_at,
            "created_at": utcnow(),
        }
        for row in stored
    ]
    insert_ignoring_duplicate(db, OddsObservation, observations)
    for row in stored:
        match = db.get(Match, row.match_id)
        series_key = key_series(row)
        kinds = ["FIRST_OBSERVED"]
        quote = quote_by_key[row.dedup_key]
        if quote.provider_open:
            kinds.append("PROVIDER_OPEN")
        if quote.provider_close:
            kinds.append("PROVIDER_CLOSE")
        insert_ignoring_duplicate(
            db,
            OddsKeySnapshot,
            [
                {
                    "id": str(uuid4()),
                    "match_id": row.match_id,
                    "odds_snapshot_id": row.id,
                    "snapshot_type": kind,
                    "series_key": series_key,
                    "target_at": fetched.collected_at,
                    "observed_at": fetched.collected_at,
                    "kickoff_at": match.kickoff_at,
                    "created_at": utcnow(),
                }
                for kind in kinds
            ],
        )
    return len(stored)


def visible_at(cutoff: datetime):
    return (
        OddsSnapshot.collected_at <= cutoff,
        OddsSnapshot.created_at <= cutoff,
        or_(OddsSnapshot.effective_at.is_(None), OddsSnapshot.effective_at <= cutoff),
        or_(OddsSnapshot.published_at.is_(None), OddsSnapshot.published_at <= cutoff),
    )


def mapping_visibility(db, match_id: str, cutoff: datetime):
    """Resolve binding evidence as known at cutoff; earlier versions remain retrievable."""
    ids = list(
        db.scalars(
            select(OddsSnapshot.mapping_id)
            .where(OddsSnapshot.match_id == match_id, OddsSnapshot.mapping_id.is_not(None))
            .distinct()
        )
    )
    states = {}
    if ids:
        events = db.scalars(
            select(AuditLog)
            .where(
                AuditLog.entity_type == "mapping", AuditLog.entity_id.in_(ids), AuditLog.created_at <= cutoff
            )
            .order_by(AuditLog.created_at.desc())
        )
        for event in events:
            if event.entity_id not in states and event.after:
                states[event.entity_id] = event.after
    valid = [
        and_(OddsSnapshot.mapping_id == mid, OddsSnapshot.mapping_version == state["version"])
        for mid, state in states.items()
        if state.get("status") in CONFIRMED and state.get("match_id") == match_id
    ]
    return or_(OddsSnapshot.mapping_id.is_(None), *valid)


def latest_rows(db, match_id: str, cutoff: datetime | None = None, market: str | None = None):
    cutoff = cutoff or utcnow()
    rank = (
        func.row_number()
        .over(
            partition_by=[getattr(OddsSnapshot, field) for field in SERIES],
            order_by=[
                func.coalesce(OddsSnapshot.effective_at, OddsSnapshot.collected_at).desc(),
                OddsSnapshot.collected_at.desc(),
                OddsSnapshot.created_at.desc(),
                OddsSnapshot.id.desc(),
            ],
        )
        .label("rank")
    )
    query = select(OddsSnapshot.id, rank).where(
        OddsSnapshot.match_id == match_id, *visible_at(cutoff), mapping_visibility(db, match_id, cutoff)
    )
    if market:
        query = query.where(OddsSnapshot.market_type == market)
    ranked = query.subquery()
    return list(
        db.scalars(
            select(OddsSnapshot)
            .join(ranked, ranked.c.id == OddsSnapshot.id)
            .where(ranked.c.rank == 1)
            .order_by(
                OddsSnapshot.provider,
                OddsSnapshot.market_type,
                OddsSnapshot.bookmaker,
                OddsSnapshot.selection,
            )
        )
    )


def odds_change(previous: Decimal | None, current: Decimal) -> dict:
    if previous is None:
        return {
            "previous_odds": None,
            "current_odds": current,
            "absolute_change": None,
            "percentage_change": None,
            "direction": "UNKNOWN",
        }
    delta = current - previous
    return {
        "previous_odds": previous,
        "current_odds": current,
        "absolute_change": delta,
        "percentage_change": delta / previous * 100,
        "direction": "UP" if delta > 0 else "DOWN" if delta < 0 else "FLAT",
    }


def change_for(db, row: OddsSnapshot, cutoff: datetime):
    constraints = [getattr(OddsSnapshot, key) == getattr(row, key) for key in SERIES]
    ordered = list(
        db.scalars(
            select(OddsSnapshot)
            .where(*constraints, *visible_at(cutoff), mapping_visibility(db, row.match_id, cutoff))
            .order_by(
                func.coalesce(OddsSnapshot.effective_at, OddsSnapshot.collected_at).desc(),
                OddsSnapshot.collected_at.desc(),
                OddsSnapshot.created_at.desc(),
                OddsSnapshot.id.desc(),
            )
            .limit(2)
        )
    )
    return odds_change(ordered[1].decimal_odds if len(ordered) > 1 else None, row.decimal_odds)


def finalize_keys(db, match: Match, now: datetime | None = None):
    now = now or utcnow()
    for kind, minutes in KEY_OFFSETS.items():
        target = match.kickoff_at - timedelta(minutes=minutes)
        if now < target:
            continue
        # Do not manufacture a missed threshold from a later scrape or retrospective import.
        rank = (
            func.row_number()
            .over(
                partition_by=[getattr(OddsSnapshot, key) for key in SERIES],
                order_by=[
                    OddsObservation.collected_at.desc(),
                    OddsSnapshot.effective_at.desc(),
                    OddsObservation.created_at.desc(),
                ],
            )
            .label("rank")
        )
        ranked = (
            select(
                OddsSnapshot.id.label("snapshot_id"), OddsObservation.collected_at.label("observed_at"), rank
            )
            .join(OddsObservation, OddsObservation.odds_snapshot_id == OddsSnapshot.id)
            .where(
                OddsSnapshot.match_id == match.id,
                OddsObservation.collected_at <= target,
                OddsObservation.collected_at < match.kickoff_at,
                OddsObservation.created_at <= now,
                *visible_at(now),
                mapping_visibility(db, match.id, now),
                or_(OddsSnapshot.effective_at.is_(None), OddsSnapshot.effective_at <= target),
                or_(OddsSnapshot.published_at.is_(None), OddsSnapshot.published_at <= target),
            )
            .subquery()
        )
        rows = db.execute(
            select(OddsSnapshot, ranked.c.observed_at)
            .join(ranked, ranked.c.snapshot_id == OddsSnapshot.id)
            .where(ranked.c.rank == 1)
        )
        insert_ignoring_duplicate(
            db,
            OddsKeySnapshot,
            [
                {
                    "id": str(uuid4()),
                    "match_id": match.id,
                    "odds_snapshot_id": row.id,
                    "snapshot_type": kind,
                    "target_at": target,
                    "observed_at": observed_at,
                    "series_key": key_series(row),
                    "kickoff_at": match.kickoff_at,
                    "created_at": now,
                }
                for row, observed_at in rows
            ],
        )
