import copy
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from jc.analysis.contracts import FEATURE_VERSION
from jc.analysis.features import MatchNotVisible, build_feature_data, get_or_create_snapshot
from jc.analysis.visibility import record_visibility
from jc.models import (
    AnalysisVisibility,
    AuditLog,
    Competition,
    FeatureSnapshot,
    Match,
    MatchMapping,
    MatchResult,
    MatchVersion,
    OddsObservation,
    OddsSnapshot,
    ProviderMatch,
    RawPayload,
    Team,
    TeamMatchStats,
)
from jc.time import utcnow
from sqlalchemy import func, inspect, select, text
from sqlalchemy.exc import DatabaseError


class Timeline:
    """Known clocks at INSERT and commit; never UPDATE immutable test history."""

    def __init__(self, sessions, monkeypatch):
        self.sessions = sessions
        self.start = utcnow() - timedelta(days=3)
        self.now = self.start
        self.cutoff = self.start + timedelta(hours=2)
        monkeypatch.setattr("jc.analysis.visibility.utcnow", lambda: self.now)
        with sessions() as db:
            home = Team(canonical_name="Home", source="sporttery", created_at=self.now)
            away = Team(canonical_name="Away", source="sporttery", created_at=self.now)
            comp = Competition(canonical_name="League", source="sporttery", created_at=self.now)
            db.add_all([home, away, comp])
            db.flush()
            self.home, self.away, self.comp = home.id, away.id, comp.id
            self.match_id, self.version_id = self.match(db)
            db.commit()

    def raw(self, db, provider="sporttery", **updates):
        values = dict(
            provider=provider,
            resource_type="fixture",
            payload={"mock": True},
            source_url="fixture://features",
            payload_hash="a" * 64,
            mock=True,
            collected_at=self.now,
            created_at=self.now,
        )
        values.update(updates)
        raw = RawPayload(**values)
        db.add(raw)
        db.flush()
        return raw

    def match(self, db, kickoff=None, **state_updates):
        raw = self.raw(db)
        kickoff = kickoff or self.start + timedelta(days=7)
        state = dict(
            sporttery_match_id="mock-" + str(uuid4()),
            match_num="001",
            match_date=kickoff.date(),
            sell_date=self.start.date(),
            competition_id=self.comp,
            competition_name="League",
            home_team_id=self.home,
            away_team_id=self.away,
            home_team_name="Home",
            away_team_name="Away",
            kickoff_at=kickoff,
            sell_status="ON_SALE",
            single_allowed=True,
            markets={},
            mock=True,
            raw_payload_id=raw.id,
            collected_at=self.now,
        )
        state.update(state_updates)
        match = Match(**state, created_at=self.now)
        db.add(match)
        db.flush()
        from fastapi.encoders import jsonable_encoder

        version = MatchVersion(
            match_id=match.id,
            raw_payload_id=raw.id,
            collected_at=self.now,
            created_at=self.now,
            state=jsonable_encoder(state),
        )
        db.add(version)
        db.flush()
        return match.id, version.id

    def quote(self, db, price="2", provider="sporttery", raw_updates=None, **updates):
        raw = self.raw(db, provider, **(raw_updates or {}))
        values = dict(
            match_id=self.match_id,
            provider=provider,
            bookmaker=provider,
            market_type="1X2",
            selection="HOME",
            raw_odds=price,
            decimal_odds=Decimal(price),
            implied_probability=1 / Decimal(price),
            collected_at=self.now,
            created_at=self.now,
            effective_at=self.now,
            source=raw.source_url,
            raw_payload_id=raw.id,
            dedup_key=str(uuid4()),
            mock=True,
        )
        values.update(updates)
        row = OddsSnapshot(**values)
        db.add(row)
        db.flush()
        return row

    def external(self, db):
        raw = self.raw(db, "external")
        pm = ProviderMatch(
            provider="external",
            provider_match_id="external-1",
            home_name="Home",
            away_name="Away",
            competition="League",
            kickoff_at=self.start + timedelta(days=7),
            raw_payload_id=raw.id,
            collected_at=self.now,
            created_at=self.now,
            mock=True,
        )
        db.add(pm)
        db.flush()
        mapping = MatchMapping(
            provider_match_id=pm.id,
            match_id=self.match_id,
            provider="external",
            confidence=100,
            match_method="MANUAL",
            status="CONFIRMED",
            review_required=False,
            candidates=[],
            version=1,
            created_at=self.now,
        )
        db.add(mapping)
        db.flush()
        self.audit(db, mapping)
        return mapping

    def audit(self, db, mapping, status="CONFIRMED", version=1):
        db.add(
            AuditLog(
                entity_type="mapping",
                entity_id=mapping.id,
                operation="TEST_MAPPING",
                after={"status": status, "match_id": self.match_id, "version": version},
                created_at=self.now,
            )
        )

    def build(self, cutoff=None):
        with self.sessions() as db:
            return build_feature_data(db, self.match_id, cutoff or self.cutoff, mock=True).model_dump()


@pytest.fixture
def timeline(sessions, monkeypatch):
    return Timeline(sessions, monkeypatch)


def test_feature_snapshot_api_deterministic_and_concurrent(client, sessions, timeline):
    with sessions() as db:
        timeline.quote(db)
        db.commit()
    params = {"analysis_cutoff": timeline.cutoff.isoformat()}
    path = f"/api/v1/matches/{timeline.match_id}/features"

    # Concurrent callers use one immutable cache identity, with database conflict handling.
    def create(_):
        with sessions() as db:
            row = get_or_create_snapshot(db, timeline.match_id, timeline.cutoff, mock=True)
            db.commit()
            return row.id

    with ThreadPoolExecutor(max_workers=4) as pool:
        ids = list(pool.map(create, range(4)))
    assert len(set(ids)) == 1
    first = client.get(path, params=params)
    assert first.status_code == 200
    data = first.json()["data"]
    assert data == client.get(path, params=params).json()["data"]
    from datetime import timezone

    same_in_beijing = timeline.cutoff.astimezone(timezone(timedelta(hours=8))).isoformat()
    assert data == client.get(path, params={"analysis_cutoff": same_in_beijing}).json()["data"]
    assert data["feature_version"] == FEATURE_VERSION
    assert data["feature_snapshot_id"] == ids[0]
    assert data["feature_data"] == timeline.build()
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(FeatureSnapshot)) == 1


@pytest.mark.parametrize(
    "entity,field",
    [
        ("odds", "collected_at"),
        ("odds", "created_at"),
        ("odds", "published_at"),
        ("odds", "effective_at"),
        ("raw", "collected_at"),
        ("raw", "created_at"),
        ("raw", "published_at"),
        ("raw", "effective_at"),
    ],
)
def test_every_odds_and_raw_time_is_checked(timeline, sessions, entity, field):
    future = timeline.cutoff + timedelta(seconds=1)
    with sessions() as db:
        timeline.quote(db, "2")
        changes = {field: future}
        timeline.quote(
            db, "9", raw_updates=changes if entity == "raw" else None, **(changes if entity == "odds" else {})
        )
        db.commit()
    data = timeline.build()
    assert [q["decimal_odds"] for q in data["market"]["quotes"]] == ["2.000000"]
    assert data["odds_movement"]["items"][0]["previous_odds"] is None


def test_backfill_and_delayed_normalization_cannot_change_history(timeline, sessions):
    with sessions() as db:
        timeline.quote(db)
        old_raw = timeline.raw(db)
        db.commit()
        snapshot = get_or_create_snapshot(db, timeline.match_id, timeline.cutoff, mock=True)
        db.commit()
        before = copy.deepcopy(snapshot.feature_data)
    timeline.now = timeline.cutoff + timedelta(hours=1)
    with sessions() as db:
        timeline.quote(db, "8", effective_at=timeline.start, collected_at=timeline.start)
        # Old Raw normalized late: even all backdated application times cannot forge commit evidence.
        timeline.quote(
            db,
            "9",
            raw_payload_id=old_raw.id,
            effective_at=timeline.start,
            collected_at=timeline.start,
            created_at=timeline.start,
        )
        db.commit()
    assert timeline.build() == before  # Rebuild bypasses the saved snapshot cache.
    with sessions() as db:
        assert (
            get_or_create_snapshot(db, timeline.match_id, timeline.cutoff, mock=True).feature_data == before
        )


def test_transaction_crossing_cutoff_is_not_visible(timeline, sessions):
    with sessions() as writer:
        row = timeline.quote(writer, "9")
        # INSERT and flush occurred before cutoff; transaction commits afterwards.
        timeline.now = timeline.cutoff + timedelta(seconds=1)
        writer.commit()
        proof = writer.get(AnalysisVisibility, ("odds_snapshots", row.id))
        assert proof.visible_at > timeline.cutoff
    assert timeline.build()["market"]["quotes"] == []


def test_missing_commit_proof_fails_closed_and_is_never_backdated(timeline, sessions):
    with sessions() as db:
        engine = db.get_bind()
    # Core writers do not run ORM events; lazy proof recovery must use actual read time.
    raw_id, oid = str(uuid4()), str(uuid4())
    with engine.begin() as conn:
        conn.execute(
            RawPayload.__table__.insert().values(
                id=raw_id,
                provider="sporttery",
                resource_type="odds",
                payload={},
                source_url="fixture://core",
                collected_at=timeline.start,
                created_at=timeline.start,
                payload_hash="b" * 64,
                mock=True,
            )
        )
        conn.execute(
            OddsSnapshot.__table__.insert().values(
                id=oid,
                match_id=timeline.match_id,
                provider="sporttery",
                bookmaker="sporttery",
                market_type="1X2",
                selection="HOME",
                raw_odds="9",
                decimal_odds=9,
                implied_probability=Decimal("0.111111"),
                collected_at=timeline.start,
                created_at=timeline.start,
                source="fixture://core",
                raw_payload_id=raw_id,
                dedup_key=str(uuid4()),
                mock=True,
            )
        )
    timeline.now = timeline.cutoff + timedelta(seconds=1)
    assert timeline.build()["market"]["quotes"] == []
    record_visibility(engine)
    assert timeline.build()["market"]["quotes"] == []
    assert timeline.build(timeline.now + timedelta(seconds=1))["market"]["quotes"]


@pytest.mark.parametrize(
    "future_field", ["collected_at", "created_at", "published_at", "effective_at", "raw"]
)
def test_match_version_and_raw_future_times(timeline, sessions, future_field):
    before = timeline.build()
    with sessions() as db:
        old = db.get(MatchVersion, timeline.version_id)
        raw = timeline.raw(
            db, **({"published_at": timeline.cutoff + timedelta(seconds=1)} if future_field == "raw" else {})
        )
        state = {**old.state, "kickoff_at": (timeline.start + timedelta(days=8)).isoformat()}
        args = dict(
            match_id=timeline.match_id,
            raw_payload_id=raw.id,
            state=state,
            collected_at=timeline.start + timedelta(minutes=1),
            created_at=timeline.now,
        )
        if future_field != "raw":
            args[future_field] = timeline.cutoff + timedelta(seconds=1)
        db.add(MatchVersion(**args))
        db.commit()
    assert timeline.build() == before


def test_kickoff_change_and_mutable_entities_do_not_leak(timeline, sessions):
    before = timeline.build()
    timeline.now = timeline.cutoff + timedelta(seconds=1)
    with sessions() as db:
        current = db.get(Match, timeline.match_id)
        current.kickoff_at += timedelta(days=1)
        current.home_team_name = "Future rename"
        db.get(Team, timeline.home).canonical_name = "Future name"
        old = db.get(MatchVersion, timeline.version_id)
        raw = timeline.raw(db)
        db.add(
            MatchVersion(
                match_id=current.id,
                raw_payload_id=raw.id,
                collected_at=timeline.now,
                created_at=timeline.now,
                state={**old.state, "kickoff_at": current.kickoff_at.isoformat()},
            )
        )
        db.commit()
    assert timeline.build() == before
    later = timeline.build(timeline.now + timedelta(seconds=1))
    assert later["schedule"]["kickoff_at"] != before["schedule"]["kickoff_at"]


def test_missing_data_is_explicit_and_quality_decreases(timeline, sessions):
    empty = timeline.build()
    assert empty["team_strength"] == {"rating": None, "past_results": [], "past_stats": []}
    assert empty["squad"]["players"] is None and empty["context"]["evidence"] is None
    assert empty["data_quality"]["score"] == 20
    timeline.now = timeline.cutoff - timedelta(minutes=10)
    with sessions() as db:
        timeline.quote(db)
        mapping = timeline.external(db)
        timeline.quote(db, provider="external", mapping_id=mapping.id, mapping_version=1)
        old = db.get(MatchVersion, timeline.version_id)
        raw = timeline.raw(db)
        db.add(
            MatchVersion(
                match_id=timeline.match_id,
                raw_payload_id=raw.id,
                collected_at=timeline.now,
                created_at=timeline.now,
                state=old.state,
            )
        )
        db.commit()
    full = timeline.build()
    assert full["data_quality"]["score"] == 100
    assert timeline.build(timeline.cutoff + timedelta(hours=2))["data_quality"]["score"] == 80
    timeline.now = timeline.cutoff + timedelta(minutes=1)
    with sessions() as db:
        timeline.audit(db, mapping, "REVIEW", 2)
        db.commit()
    assert timeline.build() == full
    later = timeline.build(timeline.now + timedelta(seconds=1))
    assert later["data_quality"]["score"] == 60
    assert all(q["provider"] == "sporttery" for q in later["market"]["quotes"])


def test_future_mapping_confirmation_cannot_authorize_old_quote(timeline, sessions):
    timeline.now = timeline.cutoff + timedelta(seconds=1)
    with sessions() as db:
        mapping = timeline.external(db)
        timeline.quote(
            db,
            provider="external",
            mapping_id=mapping.id,
            mapping_version=1,
            created_at=timeline.start,
            collected_at=timeline.start,
            effective_at=timeline.start,
        )
        db.commit()
    assert timeline.build()["market"]["quotes"] == []


def test_future_observation_cannot_make_source_fresh(timeline, sessions):
    with sessions() as db:
        quote = timeline.quote(db)
        db.commit()
    before = timeline.build()
    timeline.now = timeline.cutoff + timedelta(seconds=1)
    with sessions() as db:
        raw = timeline.raw(db)
        db.add(
            OddsObservation(
                odds_snapshot_id=quote.id,
                raw_payload_id=raw.id,
                collected_at=timeline.cutoff - timedelta(seconds=1),
                created_at=timeline.start,
            )
        )
        db.commit()
    assert timeline.build() == before


def test_api_time_errors_and_mock_isolation(client, timeline, sessions):
    path = f"/api/v1/matches/{timeline.match_id}/features"
    for cutoff in ("2026-09-01T12:00:00", (utcnow() + timedelta(days=1)).isoformat()):
        assert client.get(path, params={"analysis_cutoff": cutoff}).status_code == 422
    assert client.get(path).status_code == 422
    assert (
        client.get(
            path, params={"analysis_cutoff": (timeline.start - timedelta(seconds=1)).isoformat()}
        ).status_code
        == 404
    )
    with sessions() as db, pytest.raises(MatchNotVisible):
        build_feature_data(db, timeline.match_id, timeline.cutoff, mock=False)
    with sessions() as db:
        timeline.quote(db, "9", mock=False)
        db.commit()
    assert timeline.build()["market"]["quotes"] == []


@pytest.mark.parametrize(
    "table", ["feature_snapshots", "analysis_visibility", "match_results", "team_match_stats"]
)
@pytest.mark.parametrize("operation", ["UPDATE", "DELETE"])
def test_new_tables_are_database_immutable(timeline, sessions, table, operation):
    with sessions() as db:
        raw = timeline.raw(db)
        evidence = dict(
            dedup_key=str(uuid4()),
            match_id=timeline.match_id,
            match_version_id=timeline.version_id,
            source="sporttery",
            raw_payload_id=raw.id,
            observed_at=timeline.now,
            finished_at=timeline.now,
            created_at=timeline.now,
            mock=True,
        )
        db.add(MatchResult(**evidence, home_score=0, away_score=0))
        db.add(TeamMatchStats(**evidence, team_id=timeline.home))
        get_or_create_snapshot(db, timeline.match_id, timeline.cutoff, mock=True)
        db.commit()
        field = "entity_type" if table == "analysis_visibility" else "id"
        sql = f"UPDATE {table} SET {field}={field}" if operation == "UPDATE" else f"DELETE FROM {table}"
        with pytest.raises(DatabaseError, match="append-only"):
            db.execute(text(sql))
            db.commit()
        db.rollback()


def test_migration_upgrade_check_downgrade_preserves_old_history(sessions, timeline):
    config = Config("alembic.ini")
    command.check(config)
    command.downgrade(config, "006_auth_rate_buckets")
    with sessions() as db:
        assert db.get(Match, timeline.match_id)
        assert "feature_snapshots" not in inspect(db.bind).get_table_names()
        with pytest.raises(DatabaseError):
            db.execute(text("DELETE FROM match_versions"))
        db.rollback()
    command.upgrade(config, "head")
    command.check(config)


def add_past_facts(timeline, db, mid, vid, *, xg="1.5", **overrides):
    raw = timeline.raw(db)
    values = dict(
        dedup_key=str(uuid4()),
        match_id=mid,
        match_version_id=vid,
        source="sporttery",
        raw_payload_id=raw.id,
        observed_at=timeline.now,
        created_at=timeline.now,
        mock=True,
        finished_at=timeline.start - timedelta(hours=1),
    )
    values.update(overrides)
    db.add(MatchResult(**values, home_score=2, away_score=0))
    db.add(TeamMatchStats(**values, team_id=timeline.home, xg=Decimal(xg)))


def test_past_stats_corrections_and_target_labels_are_isolated(timeline, sessions):
    with sessions() as db:
        mid, vid = timeline.match(db, kickoff=timeline.start - timedelta(hours=3))
        add_past_facts(timeline, db, mid, vid)
        # Corrupt/direct-import target labels cannot become target input features.
        add_past_facts(timeline, db, timeline.match_id, timeline.version_id, xg="99")
        db.commit()
    before = timeline.build()
    strength = before["team_strength"]
    assert len(strength["past_results"]) == len(strength["past_stats"]) == 1
    assert strength["past_stats"][0]["xg"] == "1.5000"
    assert strength["past_stats"][0]["xga"] is None and strength["past_stats"][0]["shots"] is None
    timeline.now = timeline.cutoff + timedelta(seconds=1)
    with sessions() as db:
        add_past_facts(timeline, db, mid, vid, xg="9", observed_at=timeline.start, created_at=timeline.start)
        db.commit()
    assert timeline.build() == before
    # A normal later correction uses its new observation time and wins only after it is visible.
    timeline.now += timedelta(seconds=1)
    with sessions() as db:
        add_past_facts(timeline, db, mid, vid, xg="3")
        old = db.get(MatchVersion, vid)
        raw = timeline.raw(db)
        db.add(
            MatchVersion(
                match_id=mid,
                raw_payload_id=raw.id,
                state=old.state,
                collected_at=timeline.now,
                created_at=timeline.now,
            )
        )
        db.commit()
    later = timeline.build(timeline.now + timedelta(seconds=1))
    assert later["team_strength"]["past_stats"][0]["xg"] == "3.0000"
    assert timeline.build() == before


@pytest.mark.parametrize(
    "entity,field",
    [
        ("stats", "observed_at"),
        ("stats", "created_at"),
        ("stats", "published_at"),
        ("stats", "effective_at"),
        ("stats", "finished_at"),
        ("raw", "published_at"),
        ("raw", "effective_at"),
        ("raw", "created_at"),
    ],
)
def test_future_stats_and_raw_cannot_enter_past_team_facts(timeline, sessions, entity, field):
    future = timeline.cutoff + timedelta(seconds=1)
    with sessions() as db:
        mid, vid = timeline.match(db, kickoff=timeline.start - timedelta(hours=3))
        kwargs = {field: future} if entity == "stats" else {}
        if field == "finished_at":
            kwargs["observed_at"] = future  # Valid DB chronology, still unavailable at cutoff.
        if entity == "raw":
            raw = timeline.raw(db, **{field: future})
            kwargs["raw_payload_id"] = raw.id
        add_past_facts(timeline, db, mid, vid, **kwargs)
        db.commit()
    assert timeline.build()["team_strength"]["past_stats"] == []
    assert timeline.build()["team_strength"]["past_results"] == []


def test_visible_mapping_change_splits_odds_movement(timeline, sessions):
    with sessions() as db:
        mapping = timeline.external(db)
        timeline.quote(db, "2", provider="external", mapping_id=mapping.id, mapping_version=1)
        db.commit()
    timeline.now += timedelta(minutes=1)
    with sessions() as db:
        timeline.audit(db, mapping, version=2)
        timeline.quote(db, "3", provider="external", mapping_id=mapping.id, mapping_version=2)
        db.commit()
    data = timeline.build()
    assert len(data["market"]["quotes"]) == 1
    assert data["odds_movement"]["items"][0]["previous_snapshot_id"] is None


def test_unknown_team_ids_remain_unknown_and_score_zero(timeline, sessions):
    timeline.now += timedelta(minutes=1)
    with sessions() as db:
        old = db.get(MatchVersion, timeline.version_id)
        raw = timeline.raw(db)
        db.add(
            MatchVersion(
                match_id=timeline.match_id,
                raw_payload_id=raw.id,
                state={**old.state, "home_team_id": None, "away_team_id": None},
                collected_at=timeline.now,
                created_at=timeline.now,
            )
        )
        db.commit()
    data = timeline.build()
    assert data["context"]["match"]["home_team_id"] is None
    assert data["data_quality"]["score"] == 0


def test_feature_v1_rejects_postkickoff_cutoff(timeline, sessions):
    with sessions() as db:
        mid, _ = timeline.match(db, kickoff=timeline.start + timedelta(hours=1))
        db.commit()
        with pytest.raises(ValueError, match="pre-match"):
            build_feature_data(db, mid, timeline.cutoff, mock=True)
