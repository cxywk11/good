import base64
import json
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from jc.api import model_dict, ok, require_match
from jc.db import get_db
from jc.models import OddsKeySnapshot, OddsSnapshot
from jc.odds import change_for, latest_rows, mapping_visibility, visible_at
from jc.providers.contracts import MARKETS, SPORTTERY_POOLS
from jc.time import as_utc, parse_time, utcnow

router = APIRouter(prefix="/api/v1/matches", tags=["Odds"])


def cutoff_value(value: datetime | None):
    try:
        return as_utc(value) if value else utcnow()
    except ValueError:
        raise HTTPException(422, "analysis_cutoff 必须包含时区") from None


@router.get("/{match_id}/sporttery-odds")
def sporttery_odds(match_id: UUID, request: Request, db: Session = Depends(get_db)):
    match = require_match(db, str(match_id))
    rows = latest_rows(db, match.id)
    markets = {
        pool: {
            **match.markets.get(pool, {"available": False, "single_allowed": None}),
            "odds": [model_dict(row) for row in rows if row.market_type == "SPORTTERY_" + pool.upper()],
        }
        for pool in SPORTTERY_POOLS
    }
    return ok(request, {"markets": markets})


@router.get("/{match_id}/odds")
def latest(
    match_id: UUID,
    request: Request,
    analysis_cutoff: datetime | None = None,
    market: str | None = None,
    db: Session = Depends(get_db),
):
    match = require_match(db, str(match_id))
    cutoff = cutoff_value(analysis_cutoff)
    if market and market not in MARKETS:
        raise HTTPException(422, "未知市场") from None
    rows = latest_rows(db, match.id, cutoff, market)
    return ok(
        request,
        {
            "items": [{**model_dict(row), "change": change_for(db, row, cutoff)} for row in rows],
            "analysis_cutoff": cutoff,
        },
    )


@router.get("/{match_id}/odds/history")
def history(
    match_id: UUID,
    request: Request,
    analysis_cutoff: datetime | None = None,
    market: str | None = None,
    provider: str | None = None,
    bookmaker: str | None = None,
    selection: str | None = None,
    line: Decimal | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    cursor: str | None = None,
    limit: int = Query(500, ge=1, le=2000),
    db: Session = Depends(get_db),
):
    match = require_match(db, str(match_id))
    cutoff = cutoff_value(analysis_cutoff)
    query = select(OddsSnapshot).where(
        OddsSnapshot.match_id == match.id, *visible_at(cutoff), mapping_visibility(db, match.id, cutoff)
    )
    if market:
        if market not in MARKETS:
            raise HTTPException(422, "未知市场") from None
        query = query.where(OddsSnapshot.market_type == market)
    for key, value in {
        "provider": provider,
        "bookmaker": bookmaker,
        "selection": selection,
        "line": line,
    }.items():
        if value is not None:
            query = query.where(getattr(OddsSnapshot, key) == value)
    if since:
        query = query.where(OddsSnapshot.collected_at >= cutoff_value(since))
    if until:
        query = query.where(OddsSnapshot.collected_at <= cutoff_value(until))
    if cursor:
        try:
            stamp, oid = json.loads(base64.urlsafe_b64decode(cursor))
            position = parse_time(stamp)
            UUID(oid)
        except Exception:
            raise HTTPException(422, "无效分页游标") from None
        query = query.where(
            or_(
                OddsSnapshot.collected_at > position,
                and_(OddsSnapshot.collected_at == position, OddsSnapshot.id > oid),
            )
        )
    rows = list(db.scalars(query.order_by(OddsSnapshot.collected_at, OddsSnapshot.id).limit(limit + 1)))
    next_cursor = None
    if len(rows) > limit:
        rows = rows[:limit]
        next_cursor = base64.urlsafe_b64encode(
            json.dumps([rows[-1].collected_at.isoformat(), rows[-1].id]).encode()
        ).decode()
    return ok(
        request,
        {"items": [model_dict(row) for row in rows], "next_cursor": next_cursor, "analysis_cutoff": cutoff},
    )


@router.get("/{match_id}/odds/key-snapshots")
def key_snapshots(match_id: UUID, request: Request, db: Session = Depends(get_db)):
    match = require_match(db, str(match_id))
    result = []
    for key, odds in db.execute(
        select(OddsKeySnapshot, OddsSnapshot)
        .join(OddsSnapshot, OddsSnapshot.id == OddsKeySnapshot.odds_snapshot_id)
        .where(
            OddsKeySnapshot.match_id == match.id,
            OddsKeySnapshot.kickoff_at == match.kickoff_at,
            mapping_visibility(db, match.id, utcnow()),
        )
    ):
        result.append(
            {
                **model_dict(key),
                "odds": model_dict(odds),
                "observation_gap_seconds": (
                    key.target_at - (key.observed_at or odds.collected_at)
                ).total_seconds(),
            }
        )
    return ok(request, result)
