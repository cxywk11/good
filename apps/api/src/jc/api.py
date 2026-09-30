from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from jc.config import get_settings
from jc.db import get_db
from jc.models import Match, MatchMapping, MatchVersion, ProviderState
from jc.time import BEIJING, as_utc, utcnow

router = APIRouter(prefix="/api/v1")


def ok(request: Request, data):
    return {
        "success": True,
        "data": jsonable_encoder(data, custom_encoder={Decimal: str}),
        "request_id": request.state.request_id,
    }


def model_dict(row):
    return {column.key: getattr(row, column.key) for column in row.__table__.columns}


def match_data(db: Session, match: Match):
    result = model_dict(match)
    result["kickoff_beijing"] = match.kickoff_at.astimezone(BEIJING).isoformat()
    result["sporttery_sp"] = {}
    from jc.odds import latest_rows

    rows = latest_rows(db, match.id, market="SPORTTERY_HAD")
    for row in rows:
        result["sporttery_sp"].setdefault(row.selection, str(row.decimal_odds))
    result["provider_coverage"] = list(
        db.scalars(
            select(MatchMapping.provider).where(
                MatchMapping.match_id == match.id, MatchMapping.status.in_(["AUTO_CONFIRMED", "CONFIRMED"])
            )
        )
    )
    return result


@router.get("/matches/today")
def today(
    request: Request,
    sell_date: date | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=100),
    db: Session = Depends(get_db),
):
    day = sell_date or utcnow().astimezone(BEIJING).date()
    filters = (Match.sell_date == day, Match.mock == get_settings().demo_mode)
    total = db.scalar(select(func.count()).select_from(Match).where(*filters))
    rows = db.scalars(
        select(Match)
        .where(*filters)
        .order_by(Match.kickoff_at, Match.match_num)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return ok(
        request,
        {
            "items": [match_data(db, match) for match in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
            "sell_date": day,
            "demo_mode": get_settings().demo_mode,
        },
    )


def require_match(db: Session, match_id: str) -> Match:
    match = db.get(Match, match_id)
    if not match or match.mock != get_settings().demo_mode:
        raise HTTPException(404, "比赛不存在")
    return match


@router.get("/matches/{match_id}")
def detail(
    match_id: UUID, request: Request, analysis_cutoff: datetime | None = None, db: Session = Depends(get_db)
):
    match = require_match(db, str(match_id))
    if analysis_cutoff:
        try:
            cutoff = as_utc(analysis_cutoff)
        except ValueError:
            raise HTTPException(422, "analysis_cutoff 必须包含时区") from None
        version = db.scalar(
            select(MatchVersion)
            .where(
                MatchVersion.match_id == match.id,
                MatchVersion.collected_at <= cutoff,
                MatchVersion.created_at <= cutoff,
            )
            .order_by(MatchVersion.collected_at.desc(), MatchVersion.created_at.desc())
            .limit(1)
        )
        if not version:
            raise HTTPException(404, "该时刻尚无可见比赛数据")
        return ok(request, {"id": match.id, **version.state, "analysis_cutoff": cutoff})
    return ok(request, match_data(db, match))


@router.get("/providers/status")
def providers(request: Request, db: Session = Depends(get_db)):
    return ok(request, [model_dict(state) for state in db.scalars(select(ProviderState))])
