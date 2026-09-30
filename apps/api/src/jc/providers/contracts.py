from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

MARKETS = (
    "1X2",
    "ASIAN_HANDICAP",
    "TOTALS",
    "CORRECT_SCORE",
    "SPORTTERY_HAD",
    "SPORTTERY_HHAD",
    "SPORTTERY_CRS",
    "SPORTTERY_TTG",
    "SPORTTERY_HAFU",
)
SPORTTERY_POOLS = ("had", "hhad", "crs", "ttg", "hafu")


@dataclass
class FetchedPayload:
    provider: str
    resource_type: str
    payload: Any
    source_url: str
    collected_at: datetime
    http_status: int | None = 200
    mock: bool = False
    external_id: str | None = None
    raw_id: str | None = None


class NormalizedMatch(BaseModel):
    external_id: str
    home_name: str = Field(min_length=1)
    away_name: str = Field(min_length=1)
    home_external_id: str | None = None
    away_external_id: str | None = None
    competition: str
    competition_external_id: str | None = None
    kickoff_at: datetime
    match_num: str | None = None
    match_date: date | None = None
    sell_date: date | None = None
    sell_status: str | None = None
    single_allowed: bool | None = None
    markets: dict = Field(default_factory=dict)
    local_timezone: str | None = None
    published_at: datetime | None = None
    effective_at: datetime | None = None

    @field_validator("kickoff_at", "published_at", "effective_at")
    @classmethod
    def timezone_required(cls, value):
        if value is not None and value.tzinfo is None:
            raise ValueError("Timezone required")
        return value


class OddsQuote(BaseModel):
    external_match_id: str
    bookmaker: str
    market_type: str
    selection: str
    line: Decimal | None = None
    raw_odds: str
    decimal_odds: Decimal = Field(gt=1, allow_inf_nan=False)
    effective_at: datetime | None = None
    published_at: datetime | None = None
    provider_open: bool = False
    provider_close: bool = False

    @model_validator(mode="after")
    def market_consistency(self):
        if self.market_type in {"ASIAN_HANDICAP", "TOTALS", "SPORTTERY_HHAD"} and self.line is None:
            raise ValueError("This market requires a line")
        if self.market_type == "TOTALS" and self.line is not None and self.line < 0:
            raise ValueError("Total must be non-negative")
        return self

    @field_validator("effective_at", "published_at")
    @classmethod
    def time_with_zone(cls, value):
        if value is not None and value.tzinfo is None:
            raise ValueError("Timezone required")
        return value

    @field_validator("market_type")
    @classmethod
    def known_market(cls, value):
        if value not in MARKETS:
            raise ValueError("Unknown market")
        return value

    @field_validator("line")
    @classmethod
    def valid_line(cls, value):
        if value is not None and (not value.is_finite() or value % Decimal("0.25") != 0):
            raise ValueError("Invalid quarter line")
        return value


class PostMatchContract(BaseModel):
    """Final regulation-time facts only; provider must supply a known finish time."""

    external_match_id: str = Field(min_length=1)
    status: Literal["FINAL"]
    period: Literal["REGULATION"]
    finished_at: datetime
    published_at: datetime | None = None
    effective_at: datetime | None = None

    @field_validator("finished_at", "published_at", "effective_at")
    @classmethod
    def zoned_time(cls, value):
        if value is not None:
            from jc.time import as_utc

            return as_utc(value)
        return value


class NormalizedResult(PostMatchContract):
    home_score: int = Field(ge=0, strict=True)
    away_score: int = Field(ge=0, strict=True)
    half_home_score: int | None = Field(None, ge=0, strict=True)
    half_away_score: int | None = Field(None, ge=0, strict=True)
    first_goal_team: Literal["HOME", "AWAY", "NONE"] | None = None
    first_goal_minute: int | None = Field(None, ge=0, strict=True)

    @model_validator(mode="after")
    def consistent_score(self):
        if self.half_home_score is not None and self.half_home_score > self.home_score:
            raise ValueError("Half-time home score exceeds final score")
        if self.half_away_score is not None and self.half_away_score > self.away_score:
            raise ValueError("Half-time away score exceeds final score")
        if self.first_goal_team == "NONE" and (
            self.home_score + self.away_score or self.first_goal_minute is not None
        ):
            raise ValueError("No-goal evidence contradicts score/minute")
        if self.first_goal_team in {"HOME", "AWAY"}:
            if (self.home_score if self.first_goal_team == "HOME" else self.away_score) == 0:
                raise ValueError("First scorer has no goals")
        if self.first_goal_minute is not None and self.first_goal_team not in {"HOME", "AWAY"}:
            raise ValueError("First goal minute requires scorer evidence")
        return self


class NormalizedTeamStats(PostMatchContract):
    external_team_id: str = Field(min_length=1)
    xg: Decimal | None = Field(None, ge=0, allow_inf_nan=False, max_digits=10, decimal_places=4)
    xga: Decimal | None = Field(None, ge=0, allow_inf_nan=False, max_digits=10, decimal_places=4)
    shots: int | None = Field(None, ge=0, strict=True)
    shots_on_target: int | None = Field(None, ge=0, strict=True)
    possession: Decimal | None = Field(None, ge=0, le=100, allow_inf_nan=False, decimal_places=4)
    corners: int | None = Field(None, ge=0, strict=True)
    red_cards: int | None = Field(None, ge=0, strict=True)

    @model_validator(mode="after")
    def consistent_shots(self):
        if self.shots is not None and self.shots_on_target is not None and self.shots_on_target > self.shots:
            raise ValueError("Shots on target exceed shots")
        return self


@dataclass
class NormalizedBatch:
    matches: list[NormalizedMatch] = field(default_factory=list)
    odds: list[OddsQuote] = field(default_factory=list)
    results: list[NormalizedResult] = field(default_factory=list)
    team_stats: list[NormalizedTeamStats] = field(default_factory=list)
