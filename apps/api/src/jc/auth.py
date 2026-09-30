import hashlib
import secrets
from datetime import timedelta

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pwdlib import PasswordHash
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from jc.api import ok
from jc.auth_limits import auth_budget
from jc.config import get_settings
from jc.db import get_db
from jc.models import AuditLog, AuthSession, RefreshToken, User
from jc.time import utcnow

router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])
passwords = PasswordHash.recommended()
dummy_hash = passwords.hash(secrets.token_urlsafe(32))
bearer = HTTPBearer(auto_error=False)


class Credentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)


class RefreshBody(BaseModel):
    refresh_token: str = Field(min_length=20, max_length=200)


def jwt_key():
    key = get_settings().jwt_secret
    if len(key) < 32:
        raise HTTPException(503, "请先配置 JWT_SECRET（至少 32 字符）") from None
    return key


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def issue_tokens(db: Session, user: User, session: AuthSession):
    now = utcnow()
    access = jwt.encode(
        {"sub": user.id, "sid": session.id, "type": "access", "iat": now, "exp": now + timedelta(minutes=15)},
        jwt_key(),
        algorithm="HS256",
    )
    refresh = secrets.token_urlsafe(48)
    db.add(
        RefreshToken(
            user_id=user.id, family_id=session.id, token_hash=digest(refresh), expires_at=session.expires_at
        )
    )
    return {
        "access_token": access,
        "refresh_token": refresh,
        "token_type": "bearer",
        "expires_in": 900,
        "user": {"id": user.id, "email": user.email, "role": user.role},
    }


def current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)
) -> User:
    if not credentials:
        raise HTTPException(401, "请先登录") from None
    try:
        claims = jwt.decode(
            credentials.credentials,
            jwt_key(),
            algorithms=["HS256"],
            options={"require": ["exp", "iat", "sub", "sid", "type"]},
        )
        if claims["type"] != "access":
            raise ValueError("Wrong token type")
        session = db.get(AuthSession, claims["sid"])
        user = db.get(User, claims["sub"])
        if not session or session.revoked_at or session.expires_at <= utcnow() or not user or not user.active:
            raise ValueError("Session ended")
        if session.user_id != user.id:
            raise ValueError("Wrong session")
        return user
    except (jwt.PyJWTError, ValueError, KeyError):
        raise HTTPException(401, "登录已过期或已退出") from None


def admin(user: User = Depends(current_user)) -> User:
    if user.role != "ADMIN":
        raise HTTPException(403, "需要管理员权限") from None
    return user


def analyst(user: User = Depends(current_user)) -> User:
    if user.role not in {"ADMIN", "ANALYST"}:
        raise HTTPException(403, "需要研究员或管理员权限") from None
    return user


@router.post("/register", status_code=201)
def register(body: Credentials, request: Request, db: Session = Depends(get_db)):
    jwt_key()
    auth_budget(db, request, "register")
    user = User(email=str(body.email).lower(), password_hash=passwords.hash(body.password), role="USER")
    db.add(user)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "该邮箱已注册") from None
    db.add(
        AuditLog(
            actor_id=user.id,
            operation="REGISTER",
            entity_type="user",
            entity_id=user.id,
            request_id=request.state.request_id,
        )
    )
    db.commit()
    return ok(request, {"id": user.id, "email": user.email, "role": user.role})


@router.post("/login")
def login(body: Credentials, request: Request, db: Session = Depends(get_db)):
    jwt_key()
    auth_budget(db, request, "login", str(body.email))
    user = db.scalar(select(User).where(User.email == str(body.email).lower()))
    valid = passwords.verify(body.password, user.password_hash if user else dummy_hash)
    if not user or not valid or not user.active:
        raise HTTPException(401, "邮箱或密码错误") from None
    session = AuthSession(user_id=user.id, expires_at=utcnow() + timedelta(days=7))
    db.add(session)
    db.flush()
    tokens = issue_tokens(db, user, session)
    db.add(
        AuditLog(
            actor_id=user.id,
            operation="LOGIN",
            entity_type="user",
            entity_id=user.id,
            request_id=request.state.request_id,
        )
    )
    db.commit()
    return ok(request, tokens)


@router.post("/refresh")
def refresh(body: RefreshBody, request: Request, db: Session = Depends(get_db)):
    jwt_key()
    auth_budget(db, request, "refresh")
    token = db.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == digest(body.refresh_token)).with_for_update()
    )
    if not token:
        raise HTTPException(401, "无效刷新令牌") from None
    session = db.get(AuthSession, token.family_id)
    if token.revoked_at:
        if session:
            session.revoked_at = utcnow()
            db.execute(
                update(RefreshToken)
                .where(RefreshToken.family_id == token.family_id)
                .values(revoked_at=utcnow())
            )
            db.commit()
        raise HTTPException(401, "检测到刷新令牌重用，当前会话已撤销") from None
    user = db.get(User, token.user_id)
    if not session or session.revoked_at or not user or not user.active or token.expires_at <= utcnow():
        raise HTTPException(401, "刷新令牌已失效") from None
    token.revoked_at = utcnow()
    tokens = issue_tokens(db, user, session)
    db.commit()
    return ok(request, tokens)


@router.post("/logout")
def logout(
    request: Request,
    user: User = Depends(current_user),
    credentials: HTTPAuthorizationCredentials = Depends(bearer),
    db: Session = Depends(get_db),
):
    claims = jwt.decode(credentials.credentials, jwt_key(), algorithms=["HS256"])
    session = db.get(AuthSession, claims["sid"])
    if not session:
        raise HTTPException(401, "会话不存在") from None
    session.revoked_at = utcnow()
    db.execute(update(RefreshToken).where(RefreshToken.family_id == session.id).values(revoked_at=utcnow()))
    db.add(
        AuditLog(
            actor_id=user.id,
            operation="LOGOUT",
            entity_type="user",
            entity_id=user.id,
            request_id=request.state.request_id,
        )
    )
    db.commit()
    return ok(request, {"logged_out": True})


@router.get("/me")
def me(request: Request, user: User = Depends(current_user)):
    return ok(request, {"id": user.id, "email": user.email, "role": user.role})
