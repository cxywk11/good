from datetime import timedelta
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from jc.api import model_dict, ok
from jc.auth import admin, analyst
from jc.config import get_settings
from jc.db import get_db
from jc.models import AuditLog, Match, MatchMapping, ProviderState, RawPayload, SyncRun, User
from jc.providers.contracts import FetchedPayload
from jc.time import BEIJING, utcnow

router = APIRouter(prefix="/api/v1", tags=["Quality"])


@router.get("/quality")
def quality(request: Request, db: Session = Depends(get_db)):
    now = utcnow()
    day = now.astimezone(BEIJING).date()
    today_count = db.scalar(
        select(func.count())
        .select_from(Match)
        .where(Match.sell_date == day, Match.mock == get_settings().demo_mode)
    )
    mapping_counts = {
        status: count
        for status, count in db.execute(
            select(MatchMapping.status, func.count()).group_by(MatchMapping.status)
        )
    }
    runs = list(db.scalars(select(SyncRun).where(SyncRun.started_at >= now - timedelta(hours=24))))
    complete = [run for run in runs if run.status not in {"RUNNING", "QUEUED"}]
    successes = sum(run.status == "SUCCESS" for run in complete)
    errors = db.scalars(
        select(SyncRun).where(SyncRun.status == "FAILED").order_by(SyncRun.started_at.desc()).limit(20)
    )
    last = max((run.finished_at for run in runs if run.status == "SUCCESS" and run.finished_at), default=None)
    return ok(
        request,
        {
            "today_matches": today_count,
            "matched": mapping_counts.get("AUTO_CONFIRMED", 0) + mapping_counts.get("CONFIRMED", 0),
            "review": mapping_counts.get("REVIEW", 0),
            "unmatched": mapping_counts.get("UNMATCHED", 0),
            "rejected": mapping_counts.get("REJECTED", 0),
            "mapping_scope": "all stored provider matches",
            "last_sync_at": last,
            "sync_success_rate": successes / len(complete) if complete else None,
            "sync_runs_24h": len(complete),
            "recent_errors": [
                {
                    "id": r.id,
                    "provider": r.provider,
                    "operation": r.operation,
                    "error_code": r.error_code,
                    "at": r.started_at,
                }
                for r in errors
            ],
            "demo_mode": get_settings().demo_mode,
        },
    )


@router.get("/admin/sync-runs")
def sync_runs(
    request: Request, page: int = Query(1, ge=1), user: User = Depends(analyst), db: Session = Depends(get_db)
):
    total = db.scalar(select(func.count()).select_from(SyncRun))
    rows = db.scalars(select(SyncRun).order_by(SyncRun.started_at.desc()).offset((page - 1) * 30).limit(30))
    return ok(request, {"items": [model_dict(row) for row in rows], "total": total})


class SyncBody(BaseModel):
    provider: str
    operation: Literal["matches", "odds"] = "matches"


@router.post("/admin/sync", status_code=202)
def trigger_sync(
    body: SyncBody,
    request: Request,
    background: BackgroundTasks,
    user: User = Depends(admin),
    db: Session = Depends(get_db),
):
    coordinator = request.app.state.coordinator
    if body.provider not in coordinator.adapters:
        raise HTTPException(422, "该 Provider 未配置或未启用，请先检查环境变量") from None
    state = db.get(ProviderState, body.provider)
    if state and not state.enabled:
        raise HTTPException(409, "该 Provider 已禁用") from None
    pending = db.scalar(
        select(SyncRun).where(
            SyncRun.provider == body.provider,
            SyncRun.status.in_(["QUEUED", "RUNNING"]),
            SyncRun.started_at > utcnow() - timedelta(minutes=11),
        )
    )
    if pending:
        raise HTTPException(409, "该 Provider 已有排队或运行中的同步") from None
    run = SyncRun(
        provider=body.provider, operation=body.operation, request_id=request.state.request_id, status="QUEUED"
    )
    db.add(run)
    db.flush()
    db.add(
        AuditLog(
            actor_id=user.id,
            operation="SYNC_REQUESTED",
            entity_type="sync",
            entity_id=run.id,
            after={"provider": body.provider, "operation": body.operation},
            request_id=request.state.request_id,
        )
    )
    db.commit()
    background.add_task(coordinator.execute, body.provider, body.operation, request.state.request_id, run.id)
    return ok(request, {"id": run.id, "status": "QUEUED"})


class EnabledBody(BaseModel):
    enabled: bool
    reason: str = Field(min_length=3, max_length=500)


@router.patch("/admin/providers/{provider}")
def toggle_provider(
    provider: str,
    body: EnabledBody,
    request: Request,
    user: User = Depends(admin),
    db: Session = Depends(get_db),
):
    state = db.get(ProviderState, provider)
    if not state:
        raise HTTPException(404, "Provider 不存在") from None
    if body.enabled and provider not in request.app.state.coordinator.adapters:
        raise HTTPException(422, "请先通过环境变量配置 Provider 与凭证") from None
    before = {"enabled": state.enabled, "status": state.status}
    state.enabled, state.status = body.enabled, "DEGRADED" if body.enabled else "DISABLED"
    db.add(
        AuditLog(
            actor_id=user.id,
            operation="PROVIDER_CONFIG",
            entity_type="provider",
            entity_id=provider,
            before=before,
            after={"enabled": state.enabled, "status": state.status},
            reason=body.reason,
            request_id=request.state.request_id,
        )
    )
    db.commit()
    return ok(request, model_dict(state))


@router.get("/admin/users")
def users(
    request: Request, page: int = Query(1, ge=1), user: User = Depends(admin), db: Session = Depends(get_db)
):
    rows = db.scalars(select(User).order_by(User.created_at.desc()).offset((page - 1) * 30).limit(30))
    return ok(
        request,
        {
            "items": [
                {
                    "id": row.id,
                    "email": row.email,
                    "role": row.role,
                    "active": row.active,
                    "created_at": row.created_at,
                }
                for row in rows
            ],
            "total": db.scalar(select(func.count()).select_from(User)),
        },
    )


class UserBody(BaseModel):
    role: Literal["ADMIN", "ANALYST", "USER"]
    active: bool
    reason: str = Field(min_length=3, max_length=500)


@router.patch("/admin/users/{user_id}")
def update_user(
    user_id: UUID,
    body: UserBody,
    request: Request,
    actor: User = Depends(admin),
    db: Session = Depends(get_db),
):
    user = db.get(User, str(user_id))
    if not user:
        raise HTTPException(404, "用户不存在") from None
    if actor.id == user.id and (body.role != "ADMIN" or not body.active):
        raise HTTPException(409, "不能撤销自己的管理员权限或禁用自己的账户") from None
    before = {"role": user.role, "active": user.active}
    user.role, user.active = body.role, body.active
    db.add(
        AuditLog(
            actor_id=actor.id,
            operation="USER_UPDATED",
            entity_type="user",
            entity_id=user.id,
            before=before,
            after={"role": user.role, "active": user.active},
            reason=body.reason,
            request_id=request.state.request_id,
        )
    )
    db.commit()
    return ok(request, {"id": user.id, "role": user.role, "active": user.active})


@router.get("/admin/logs")
def logs(
    request: Request, page: int = Query(1, ge=1), user: User = Depends(analyst), db: Session = Depends(get_db)
):
    rows = db.scalars(select(AuditLog).order_by(AuditLog.created_at.desc()).offset((page - 1) * 30).limit(30))
    return ok(
        request,
        {
            "items": [model_dict(row) for row in rows],
            "total": db.scalar(select(func.count()).select_from(AuditLog)),
        },
    )


@router.get("/admin/raw/{raw_id}")
def raw_payload(raw_id: UUID, request: Request, user: User = Depends(analyst), db: Session = Depends(get_db)):
    row = db.get(RawPayload, str(raw_id))
    if not row:
        raise HTTPException(404, "Raw 不存在") from None
    return ok(request, model_dict(row))


class ReprocessBody(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


@router.post("/admin/raw/{raw_id}/reprocess")
def reprocess(
    raw_id: UUID,
    body: ReprocessBody,
    request: Request,
    user: User = Depends(admin),
    db: Session = Depends(get_db),
):
    row = db.get(RawPayload, str(raw_id))
    if not row or row.http_status != 200:
        raise HTTPException(422, "只能重处理已有的成功响应 Raw") from None
    coordinator = request.app.state.coordinator
    provider = coordinator.adapters.get(row.provider)
    if not provider or row.mock != get_settings().demo_mode:
        raise HTTPException(422, "Provider 或数据环境不匹配") from None
    fetched = FetchedPayload(
        row.provider,
        row.resource_type,
        row.payload,
        row.source_url,
        row.collected_at,
        row.http_status,
        row.mock,
        row.external_id,
        row.id,
    )
    try:
        batch = provider.normalize(fetched)
        records = coordinator.service.persist_batch(db, provider, fetched, batch)
        db.add(
            AuditLog(
                actor_id=user.id,
                operation="RAW_REPROCESSED",
                entity_type="raw",
                entity_id=row.id,
                after={"records": records},
                reason=body.reason,
                request_id=request.state.request_id,
            )
        )
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(422, "重处理失败，原始数据保留；请核查解析器与映射") from None
    return ok(request, {"records": records})
