from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from jc.api import model_dict, ok
from jc.auth import admin, analyst
from jc.db import get_db
from jc.entities import CONFIRMED, bind_team, mapping_state
from jc.models import AuditLog, Match, MatchMapping, ProviderMatch, User
from jc.providers.http import ProviderError
from jc.time import utcnow

router = APIRouter(prefix="/api/v1/admin", tags=["Administration"])


@router.get("/mappings")
def mappings(
    request: Request,
    status: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=100),
    user: User = Depends(analyst),
    db: Session = Depends(get_db),
):
    query = select(MatchMapping)
    if status:
        query = query.where(
            MatchMapping.status.in_(CONFIRMED) if status == "MATCHED" else MatchMapping.status == status
        )
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    result = []
    for mapping in db.scalars(
        query.order_by(MatchMapping.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    ):
        item = model_dict(mapping)
        item["provider_match"] = model_dict(db.get(ProviderMatch, mapping.provider_match_id))
        target = db.get(Match, mapping.match_id) if mapping.match_id else None
        item["sporttery_match"] = model_dict(target) if target else None
        result.append(item)
    return ok(request, {"items": result, "total": total})


class ReviewBody(BaseModel):
    reason: str = Field(min_length=3, max_length=1000)
    version: int = Field(ge=1)
    match_id: UUID | None = None
    bind_team_ids: bool = False


@router.post("/mappings/{mapping_id}/{action}")
def review(
    mapping_id: UUID,
    action: Literal["confirm", "reject", "rebind"],
    body: ReviewBody,
    request: Request,
    user: User = Depends(admin),
    db: Session = Depends(get_db),
):
    mapping = db.scalar(select(MatchMapping).where(MatchMapping.id == str(mapping_id)).with_for_update())
    if not mapping:
        raise HTTPException(404, "映射不存在") from None
    if mapping.version != body.version:
        raise HTTPException(409, "映射已改变，请刷新后重试") from None
    before = mapping_state(mapping)
    pm = db.get(ProviderMatch, mapping.provider_match_id)
    if not pm:
        raise HTTPException(409, "供应商比赛缺失") from None
    target_id = str(body.match_id) if body.match_id else mapping.match_id
    if action != "reject":
        target = db.get(Match, target_id) if target_id else None
        if not target or target.mock != pm.mock:
            raise HTTPException(422, "必须选择同一数据环境中的体彩比赛") from None
        conflicting = db.scalar(
            select(MatchMapping).where(
                MatchMapping.provider == mapping.provider,
                MatchMapping.match_id == target.id,
                MatchMapping.status.in_(CONFIRMED),
                MatchMapping.id != mapping.id,
            )
        )
        if conflicting:
            raise HTTPException(409, "该供应商已有另一场比赛绑定此体彩比赛") from None
        if body.bind_team_ids:
            try:
                for external, team_id, name in (
                    (pm.home_provider_team_id, target.home_team_id, pm.home_name),
                    (pm.away_provider_team_id, target.away_team_id, pm.away_name),
                ):
                    if external and team_id:
                        bind_team(db, pm.provider, external, team_id, name, "MANUAL_REVIEW")
            except ProviderError as exc:
                db.rollback()
                raise HTTPException(409, str(exc)) from None
        mapping.match_id, mapping.status, mapping.confirmed_at = target.id, "CONFIRMED", utcnow()
    else:
        mapping.status, mapping.confirmed_at = "REJECTED", None
    mapping.version += 1
    mapping.review_required, mapping.match_method = False, "MANUAL_REVIEW"
    db.add(
        AuditLog(
            actor_id=user.id,
            operation=f"MAPPING_{action.upper()}",
            entity_type="mapping",
            entity_id=mapping.id,
            before=before,
            after=mapping_state(mapping),
            reason=body.reason,
            request_id=request.state.request_id,
        )
    )
    db.commit()
    return ok(request, model_dict(mapping))


@router.get("/matches/search")
def match_search(
    request: Request,
    q: str = Query("", max_length=100),
    user: User = Depends(analyst),
    db: Session = Depends(get_db),
):
    query = select(Match).order_by(Match.kickoff_at.desc()).limit(100)
    if q:
        query = query.where(
            or_(
                Match.home_team_name.contains(q, autoescape=True),
                Match.away_team_name.contains(q, autoescape=True),
                Match.match_num.contains(q, autoescape=True),
            )
        )
    return ok(request, [model_dict(row) for row in db.scalars(query)])
