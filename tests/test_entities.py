from datetime import timedelta
from decimal import Decimal

from jc.config import Settings
from jc.entities import bind_team, ingest_external_match, normalize_name, score_match
from jc.models import CompetitionIdentity, Match, TeamAlias
from jc.providers.contracts import FetchedPayload, NormalizedMatch
from jc.time import utcnow
from sqlalchemy import select
from test_sporttery import fixture_payload, provider_for


def test_name_normalization_preserves_identity_qualifiers():
    assert normalize_name(" Ｍａｎ   Utd. ") == "man utd"
    assert normalize_name("Arsenal Women") != normalize_name("Arsenal")
    assert normalize_name("Arsenal U21") != normalize_name("Arsenal")


async def test_mapping_ids_review_unmatched_and_aliases(sessions):
    service, provider = provider_for(sessions, fixture_payload())
    await service.run(provider)
    with sessions() as db:
        match = db.scalar(select(Match).where(Match.sporttery_match_id == "mock-s001"))
        assert match.home_team_id and match.away_team_id
        bind_team(db, "external", "ars", match.home_team_id, "Arsenal", "MANUAL")
        bind_team(db, "external", "bay", match.away_team_id, "Bayern", "MANUAL")
        db.add(
            CompetitionIdentity(provider="external", external_id="ucl", competition_id=match.competition_id)
        )
        db.flush()
        data = FetchedPayload(
            "external", "matches", {}, "fixture://external", utcnow(), raw_id=match.raw_payload_id
        )
        item = NormalizedMatch(
            external_id="one",
            home_name="Arsenal renamed",
            away_name="Bayern",
            home_external_id="ars",
            away_external_id="bay",
            competition="UCL",
            competition_external_id="ucl",
            kickoff_at=match.kickoff_at,
        )
        mapping = ingest_external_match(db, "external", data, item, Settings())
        assert mapping.status == "AUTO_CONFIRMED" and mapping.confidence == Decimal(100)
        duplicate = ingest_external_match(
            db, "external", data, item.model_copy(update={"external_id": "two"}), Settings()
        )
        assert duplicate.status == "REVIEW"
        unknown = ingest_external_match(db, "unknown", data, item, Settings())
        assert unknown.status == "UNMATCHED"
        assert (
            score_match(
                match.home_team_id,
                match.away_team_id,
                match.competition_id,
                match.kickoff_at + timedelta(minutes=60),
                match,
            )[0]
            == 85
        )
        assert (
            score_match(
                match.away_team_id, match.home_team_id, match.competition_id, match.kickoff_at, match
            )[0]
            == 30
        )
        bind_team(db, "external", "ars", match.home_team_id, "Arsenal FC", "MANUAL")
        assert len(list(db.scalars(select(TeamAlias).where(TeamAlias.provider == "external")))) == 3
