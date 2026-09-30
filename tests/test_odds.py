from datetime import timedelta
from decimal import Decimal

import pytest
from jc.bootstrap import seed_demo
from jc.ingestion import IngestionService
from jc.models import Match, OddsKeySnapshot, OddsObservation, OddsSnapshot
from jc.odds import finalize_keys, latest_rows, odds_change
from jc.providers.mock import MockOddsProvider
from jc.time import utcnow
from sqlalchemy import func, select, text
from sqlalchemy.exc import DatabaseError


async def test_append_dedup_observations_and_point_in_time(sessions):
    before = utcnow()
    await seed_demo(sessions)
    with sessions() as db:
        match = db.scalar(select(Match).where(Match.sporttery_match_id == "mock-s001"))
        assert latest_rows(db, match.id, before) == []
        count = db.scalar(select(func.count()).select_from(OddsSnapshot))
        observation_count = db.scalar(select(func.count()).select_from(OddsObservation))
        current = latest_rows(db, match.id)
        assert {row.bookmaker for row in current} >= {
            "Sporttery",
            "Pinnacle",
            "Bet365",
            "Macau",
            "WilliamHill",
        }
        assert any(row.line == Decimal("-0.75") for row in current)
    service = IngestionService(sessions)
    provider = MockOddsProvider("pinnacle", revision=1)
    assert (await service.run(provider))["status"] == "SUCCESS"
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(OddsSnapshot)) == count
        assert db.scalar(select(func.count()).select_from(OddsObservation)) > observation_count
        with pytest.raises(DatabaseError):
            db.execute(text("UPDATE odds_snapshots SET decimal_odds=9"))
            db.commit()
        db.rollback()
        with pytest.raises(DatabaseError):
            db.execute(text("DELETE FROM odds_snapshots"))
            db.commit()
        db.rollback()
        finalize_keys(db, db.get(Match, match.id), match.kickoff_at + timedelta(seconds=1))
        db.commit()
        tags = set(db.scalars(select(OddsKeySnapshot.snapshot_type)))
        assert "FIRST_OBSERVED" in tags and "LAST_PREMATCH" in tags
        assert "PROVIDER_OPEN" not in tags and "PROVIDER_CLOSE" not in tags
        for key in db.scalars(
            select(OddsKeySnapshot).where(OddsKeySnapshot.snapshot_type == "LAST_PREMATCH")
        ):
            last_seen = db.scalar(
                select(func.max(OddsObservation.collected_at)).where(
                    OddsObservation.odds_snapshot_id == key.odds_snapshot_id,
                    OddsObservation.collected_at < match.kickoff_at,
                )
            )
            assert key.observed_at == last_seen


def test_odds_changes():
    change = odds_change(Decimal("1.82"), Decimal("1.76"))
    assert change["direction"] == "DOWN"
    assert change["absolute_change"] == Decimal("-0.06")
    assert odds_change(None, Decimal(2))["percentage_change"] is None
