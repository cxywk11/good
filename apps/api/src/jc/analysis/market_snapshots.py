"""Persistence boundary: one frozen feature, no historical/current source queries."""

from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from jc.analysis.contracts import FeatureData
from jc.analysis.market import MARKET_MODEL_VERSION, NORMALIZATION_METHOD, build_market_data
from jc.models import FeatureSnapshot, MarketModelSnapshot
from jc.odds import insert_ignoring_duplicate
from jc.time import utcnow


class FeatureNotFound(ValueError):
    pass


def get_or_create_market_snapshot(
    db: Session,
    feature_snapshot_id: str,
    market_model_version: str = MARKET_MODEL_VERSION,
    *,
    mock: bool,
) -> MarketModelSnapshot:
    if market_model_version != MARKET_MODEL_VERSION:
        raise ValueError("Unsupported market_model_version")
    feature = db.scalar(
        select(FeatureSnapshot).where(
            FeatureSnapshot.id == feature_snapshot_id,
            FeatureSnapshot.mock == mock,
        )
    )
    if feature is None:
        raise FeatureNotFound("Feature snapshot not found in this data mode")
    # This is market-v1's fixed input contract, not the moving current Feature version.
    if feature.feature_version != "p4-features-v1":
        raise ValueError("Unsupported feature_version for market-v1")
    query = select(MarketModelSnapshot).where(
        MarketModelSnapshot.feature_snapshot_id == feature_snapshot_id,
        MarketModelSnapshot.market_model_version == market_model_version,
        MarketModelSnapshot.mock == mock,
    )
    existing = db.scalar(query)
    if existing:
        return existing
    data = build_market_data(FeatureData.model_validate(feature.feature_data))
    insert_ignoring_duplicate(
        db,
        MarketModelSnapshot,
        [
            dict(
                id=str(uuid4()),
                match_id=feature.match_id,
                feature_snapshot_id=feature.id,
                analysis_cutoff=feature.analysis_cutoff,
                market_model_version=market_model_version,
                normalization_method=NORMALIZATION_METHOD,
                market_data=data,
                mock=feature.mock,
                created_at=utcnow(),
            )
        ],
    )
    row = db.scalar(query)
    assert row is not None
    return row
