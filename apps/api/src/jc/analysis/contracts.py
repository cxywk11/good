"""Versioned, JSON-safe feature output; Decimal values are encoded as strings."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

FEATURE_VERSION = "p4-features-v1"
QUALITY_VERSION = "availability-v1"
FRESHNESS_SECONDS = 3600


class FeatureData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    market: dict[str, Any]
    odds_movement: dict[str, Any]
    team_strength: dict[str, Any]
    schedule: dict[str, Any]
    squad: dict[str, Any]
    context: dict[str, Any]
    data_quality: dict[str, Any]


class FeatureSnapshotOutput(BaseModel):
    feature_snapshot_id: str
    match_id: str
    analysis_cutoff: datetime
    feature_version: str
    feature_data: FeatureData
    data_quality_score: int = Field(ge=0, le=100)


class MarketSnapshotOutput(BaseModel):
    market_snapshot_id: str
    feature_snapshot_id: str
    match_id: str
    analysis_cutoff: datetime
    market_model_version: str
    normalization_method: str
    market_data: dict[str, Any]
    mock: bool
