"""Cross-worker authentication budgets; PostgreSQL is also available during Redis outages."""

import hashlib
import hmac
import logging
import math
from datetime import UTC, datetime

from fastapi import HTTPException, Request
from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from jc.config import get_settings
from jc.models import AuthRateBucket
from jc.time import utcnow

logger = logging.getLogger(__name__)


def auth_budget(db: Session, request: Request, action: str, email: str | None = None):
    settings = get_settings()
    now = utcnow()
    window = settings.auth_window_seconds
    bucket = int(now.timestamp()) // window
    expires = datetime.fromtimestamp((bucket + 1) * window, UTC)
    # Only use the ASGI peer, never caller-supplied X-Forwarded-For directly.
    peer = request.client.host if request.client else "unknown"
    limits = [(f"{action}:ip", peer, getattr(settings, f"auth_{action}_ip_limit"))]
    if action == "login" and email:
        limits.append(("login:account", email.lower(), settings.auth_login_account_limit))
    insert = pg_insert if db.get_bind().dialect.name == "postgresql" else sqlite_insert
    allowed = True
    try:
        # Ephemeral counters are not business history and expire after one window.
        db.execute(delete(AuthRateBucket).where(AuthRateBucket.expires_at <= now))
        for scope, subject, limit in limits:
            subject_hash = hmac.new(
                settings.jwt_secret.encode(), subject.encode(), hashlib.sha256
            ).hexdigest()
            statement = insert(AuthRateBucket).values(
                key=f"{scope}:{subject_hash}:{bucket}", attempts=1, expires_at=expires
            )
            returning = statement.on_conflict_do_update(
                index_elements=[AuthRateBucket.key],
                set_={"attempts": AuthRateBucket.attempts + 1},
                where=AuthRateBucket.attempts < limit,
            ).returning(AuthRateBucket.attempts)
            if db.scalar(returning) is None:
                allowed = False
                break
        db.commit()  # A later 401/409 must not roll back the consumed attempt.
    except SQLAlchemyError:
        db.rollback()
        logger.error("Authentication budget unavailable", extra={"error_code": "AUTH_BUDGET_UNAVAILABLE"})
        raise HTTPException(503, "认证服务暂不可用，请稍后重试") from None
    if not allowed:
        logger.warning(
            "Authentication request throttled",
            extra={
                "operation": action,
                "status": 429,
                "request_id": request.state.request_id,
                "error_code": "AUTH_RATE_LIMIT",
            },
        )
        raise HTTPException(
            429,
            "尝试次数过多，请稍后重试",
            headers={"Retry-After": str(max(1, math.ceil((expires - now).total_seconds())))},
        )
