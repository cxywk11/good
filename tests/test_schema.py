import pytest
from jc.models import RawPayload
from jc.time import utcnow
from sqlalchemy import inspect, text
from sqlalchemy.exc import DatabaseError


def test_migrations_and_raw_immutability(sessions):
    with sessions() as db:
        assert "odds_snapshots" in inspect(db.bind).get_table_names()
        raw = RawPayload(
            provider="test",
            resource_type="test",
            payload={"mock": True},
            source_url="fixture://test",
            http_status=200,
            collected_at=utcnow(),
            payload_hash="a" * 64,
        )
        db.add(raw)
        db.commit()
        with pytest.raises(DatabaseError):
            db.execute(text("UPDATE provider_raw_payloads SET provider='changed'"))
            db.commit()
        db.rollback()
        assert db.get(RawPayload, raw.id).provider == "test"
