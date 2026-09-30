from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import TypeDecorator

from jc.db import Base
from jc.time import as_utc, utcnow


class UTCDateTime(TypeDecorator):
    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return as_utc(value) if value is not None else None

    def process_result_value(self, value, dialect):
        from datetime import UTC

        return value.replace(tzinfo=UTC) if value is not None and value.tzinfo is None else value


Json = JSON().with_variant(JSONB(), "postgresql")


class Identity:
    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class RawPayload(Identity, Base):
    __tablename__ = "provider_raw_payloads"
    provider: Mapped[str] = mapped_column(String(60), index=True)
    resource_type: Mapped[str] = mapped_column(String(60))
    external_id: Mapped[str | None] = mapped_column(String(200))
    payload: Mapped[Any] = mapped_column(Json)
    source_url: Mapped[str] = mapped_column(Text)
    http_status: Mapped[int | None]
    collected_at: Mapped[datetime] = mapped_column(UTCDateTime(), index=True)
    published_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    effective_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    payload_hash: Mapped[str] = mapped_column(String(64), index=True)
    mock: Mapped[bool] = mapped_column(default=False)


class Competition(Identity, Base):
    __tablename__ = "competitions"
    canonical_name: Mapped[str] = mapped_column(String(200))
    country_code: Mapped[str | None] = mapped_column(String(3))
    source: Mapped[str] = mapped_column(String(60))


class CompetitionIdentity(Identity, Base):
    __tablename__ = "competition_identities"
    competition_id: Mapped[str] = mapped_column(ForeignKey("competitions.id"))
    provider: Mapped[str] = mapped_column(String(60))
    external_id: Mapped[str] = mapped_column(String(200))
    __table_args__ = (UniqueConstraint("provider", "external_id"),)


class Team(Identity, Base):
    __tablename__ = "teams"
    canonical_name: Mapped[str] = mapped_column(String(200))
    name_zh: Mapped[str | None] = mapped_column(String(200))
    name_en: Mapped[str | None] = mapped_column(String(200))
    country_code: Mapped[str | None] = mapped_column(String(3))
    source: Mapped[str] = mapped_column(String(60))
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, onupdate=utcnow)


class TeamIdentity(Identity, Base):
    __tablename__ = "team_identities"
    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id"))
    provider: Mapped[str] = mapped_column(String(60))
    external_team_id: Mapped[str] = mapped_column(String(200))
    mapping_source: Mapped[str] = mapped_column(String(60))
    __table_args__ = (UniqueConstraint("provider", "external_team_id"),)


class TeamAlias(Identity, Base):
    __tablename__ = "team_aliases"
    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id"), index=True)
    provider: Mapped[str] = mapped_column(String(60))
    external_team_id: Mapped[str | None] = mapped_column(String(200))
    alias_name: Mapped[str] = mapped_column(String(200))
    normalized_name: Mapped[str] = mapped_column(String(200), index=True)
    language: Mapped[str | None] = mapped_column(String(10))
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    mapping_source: Mapped[str] = mapped_column(String(60))
    __table_args__ = (UniqueConstraint("provider", "external_team_id", "normalized_name"),)


class Match(Identity, Base):
    __tablename__ = "matches"
    sporttery_match_id: Mapped[str] = mapped_column(String(100), unique=True)
    source: Mapped[str] = mapped_column(String(60), default="sporttery")
    match_num: Mapped[str] = mapped_column(String(40))
    match_date: Mapped[date] = mapped_column(Date)
    sell_date: Mapped[date] = mapped_column(Date, index=True)
    competition_id: Mapped[str | None] = mapped_column(ForeignKey("competitions.id"))
    competition_name: Mapped[str] = mapped_column(String(200))
    competition_code: Mapped[str | None] = mapped_column(String(100))
    home_team_id: Mapped[str | None] = mapped_column(ForeignKey("teams.id"))
    away_team_id: Mapped[str | None] = mapped_column(ForeignKey("teams.id"))
    home_team_name: Mapped[str] = mapped_column(String(200))
    away_team_name: Mapped[str] = mapped_column(String(200))
    kickoff_at: Mapped[datetime] = mapped_column(UTCDateTime(), index=True)
    local_timezone: Mapped[str | None] = mapped_column(String(60))
    source_timezone: Mapped[str] = mapped_column(String(60), default="Asia/Shanghai")
    sell_status: Mapped[str] = mapped_column(String(30))
    single_allowed: Mapped[bool | None]
    markets: Mapped[dict] = mapped_column(Json)
    raw_payload_id: Mapped[str] = mapped_column(ForeignKey("provider_raw_payloads.id"))
    mock: Mapped[bool] = mapped_column(Boolean, default=False)
    published_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    effective_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    collected_at: Mapped[datetime] = mapped_column(UTCDateTime())
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, onupdate=utcnow)
    __table_args__ = (CheckConstraint("source = 'sporttery'", name="sporttery_only"),)


class MatchVersion(Identity, Base):
    __tablename__ = "match_versions"
    match_id: Mapped[str] = mapped_column(ForeignKey("matches.id"), index=True)
    raw_payload_id: Mapped[str] = mapped_column(ForeignKey("provider_raw_payloads.id"))
    collected_at: Mapped[datetime] = mapped_column(UTCDateTime(), index=True)
    effective_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    published_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    state: Mapped[dict] = mapped_column(Json)


class ProviderMatch(Identity, Base):
    __tablename__ = "provider_matches"
    provider: Mapped[str] = mapped_column(String(60))
    provider_match_id: Mapped[str] = mapped_column(String(200))
    home_provider_team_id: Mapped[str | None] = mapped_column(String(200))
    away_provider_team_id: Mapped[str | None] = mapped_column(String(200))
    home_name: Mapped[str] = mapped_column(String(200))
    away_name: Mapped[str] = mapped_column(String(200))
    competition: Mapped[str] = mapped_column(String(200))
    kickoff_at: Mapped[datetime] = mapped_column(UTCDateTime())
    raw_payload_id: Mapped[str] = mapped_column(ForeignKey("provider_raw_payloads.id"))
    collected_at: Mapped[datetime] = mapped_column(UTCDateTime())
    mock: Mapped[bool] = mapped_column(default=False)
    __table_args__ = (UniqueConstraint("provider", "provider_match_id"),)


class MatchMapping(Identity, Base):
    __tablename__ = "match_mapping"
    provider_match_id: Mapped[str] = mapped_column(ForeignKey("provider_matches.id"), unique=True)
    match_id: Mapped[str | None] = mapped_column(ForeignKey("matches.id"), index=True)
    provider: Mapped[str] = mapped_column(String(60))
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    match_method: Mapped[str] = mapped_column(String(60))
    status: Mapped[str] = mapped_column(String(30), index=True)
    review_required: Mapped[bool]
    candidates: Mapped[list] = mapped_column(Json)
    version: Mapped[int] = mapped_column(default=1)
    confirmed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    __table_args__ = (
        CheckConstraint("confidence >= 0 AND confidence <= 100", name="valid_confidence"),
        Index(
            "uq_confirmed_provider_target",
            "provider",
            "match_id",
            unique=True,
            postgresql_where=__import__("sqlalchemy").text("status IN ('AUTO_CONFIRMED', 'CONFIRMED')"),
            sqlite_where=__import__("sqlalchemy").text("status IN ('AUTO_CONFIRMED', 'CONFIRMED')"),
        ),
    )


class OddsSnapshot(Identity, Base):
    __tablename__ = "odds_snapshots"
    match_id: Mapped[str] = mapped_column(ForeignKey("matches.id"))
    provider: Mapped[str] = mapped_column(String(60))
    bookmaker: Mapped[str] = mapped_column(String(60))
    market_type: Mapped[str] = mapped_column(String(40))
    selection: Mapped[str] = mapped_column(String(60))
    line: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    raw_odds: Mapped[str] = mapped_column(String(80))
    decimal_odds: Mapped[Decimal] = mapped_column(Numeric(14, 6))
    implied_probability: Mapped[Decimal] = mapped_column(Numeric(16, 12))
    collected_at: Mapped[datetime] = mapped_column(UTCDateTime())
    effective_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    published_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    source: Mapped[str] = mapped_column(Text)
    raw_payload_id: Mapped[str] = mapped_column(ForeignKey("provider_raw_payloads.id"))
    mapping_id: Mapped[str | None] = mapped_column(ForeignKey("match_mapping.id"))
    mapping_version: Mapped[int | None]
    dedup_key: Mapped[str] = mapped_column(String(64), unique=True)
    mock: Mapped[bool] = mapped_column(default=False)
    __table_args__ = (
        CheckConstraint("decimal_odds > 1", name="valid_decimal_odds"),
        CheckConstraint("implied_probability > 0 AND implied_probability < 1", name="valid_probability"),
        Index("ix_odds_series", "match_id", "provider", "market_type", "collected_at"),
        Index("ix_odds_cutoff", "match_id", "collected_at", "created_at"),
    )


class OddsKeySnapshot(Identity, Base):
    __tablename__ = "odds_key_snapshots"
    match_id: Mapped[str] = mapped_column(ForeignKey("matches.id"))
    odds_snapshot_id: Mapped[str] = mapped_column(ForeignKey("odds_snapshots.id"))
    snapshot_type: Mapped[str] = mapped_column(String(40))
    target_at: Mapped[datetime] = mapped_column(UTCDateTime())
    observed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    series_key: Mapped[str] = mapped_column(String(64))
    kickoff_at: Mapped[datetime] = mapped_column(UTCDateTime())
    __table_args__ = (UniqueConstraint("series_key", "snapshot_type", "kickoff_at"),)


class OddsObservation(Identity, Base):
    __tablename__ = "odds_observations"
    odds_snapshot_id: Mapped[str] = mapped_column(ForeignKey("odds_snapshots.id"), index=True)
    raw_payload_id: Mapped[str] = mapped_column(ForeignKey("provider_raw_payloads.id"))
    collected_at: Mapped[datetime] = mapped_column(UTCDateTime(), index=True)
    __table_args__ = (UniqueConstraint("odds_snapshot_id", "raw_payload_id"),)


class AuditLog(Identity, Base):
    __tablename__ = "audit_logs"
    actor_id: Mapped[str | None] = mapped_column(String(100))
    operation: Mapped[str] = mapped_column(String(100), index=True)
    entity_type: Mapped[str] = mapped_column(String(60))
    entity_id: Mapped[str] = mapped_column(String(200))
    before: Mapped[dict | None] = mapped_column(Json)
    after: Mapped[dict | None] = mapped_column(Json)
    reason: Mapped[str | None] = mapped_column(Text)
    request_id: Mapped[str | None] = mapped_column(String(100))
    __table_args__ = (Index("ix_audit_entity_time", "entity_type", "entity_id", "created_at"),)


class SyncRun(Identity, Base):
    __tablename__ = "sync_runs"
    provider: Mapped[str] = mapped_column(String(60), index=True)
    operation: Mapped[str] = mapped_column(String(60))
    request_id: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(30))
    started_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    duration_ms: Mapped[int | None]
    records: Mapped[int] = mapped_column(default=0)
    error_code: Mapped[str | None] = mapped_column(String(100))
    error_message: Mapped[str | None] = mapped_column(Text)
    raw_payload_id: Mapped[str | None] = mapped_column(ForeignKey("provider_raw_payloads.id"))


class ProviderState(Base):
    __tablename__ = "provider_states"
    provider: Mapped[str] = mapped_column(String(60), primary_key=True)
    enabled: Mapped[bool] = mapped_column(default=True)
    status: Mapped[str] = mapped_column(String(30), default="DEGRADED")
    last_success_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    last_failure_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    latency: Mapped[int | None]
    consecutive_failures: Mapped[int] = mapped_column(default=0)
    rate_limit_status: Mapped[str] = mapped_column(String(60), default="AVAILABLE")
    next_allowed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())


class User(Identity, Base):
    __tablename__ = "users"
    email: Mapped[str] = mapped_column(String(320), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(20), default="USER")
    active: Mapped[bool] = mapped_column(default=True)
    __table_args__ = (CheckConstraint("role IN ('ADMIN', 'ANALYST', 'USER')", name="valid_role"),)


class RefreshToken(Identity, Base):
    __tablename__ = "refresh_tokens"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    family_id: Mapped[str] = mapped_column(String(36), index=True)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime())
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime())


class AuthSession(Identity, Base):
    __tablename__ = "auth_sessions"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime())
