from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any

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


@dataclass
class NormalizedBatch:
    matches: list[NormalizedMatch] = field(default_factory=list)
    odds: list[OddsQuote] = field(default_factory=list)
