import copy
from datetime import date, timedelta
from decimal import Decimal

import pytest
from jc.config import get_settings
from jc.ingestion import IngestionService
from jc.models import Match, MatchResult, RawPayload, TeamMatchStats
from jc.providers.contracts import NormalizedResult, NormalizedTeamStats
from jc.providers.mock import MockSportteryProvider
from jc.providers.sporttery import SportteryProvider
from sqlalchemy import func, select


class CompletedFixture(MockSportteryProvider):
    """Keep the committed fixture's dates explicit and well before the actual test clock."""

    def __init__(self):
        super().__init__(date(2026, 9, 28))
        self.change = None

    async def fetch_results(self):
        fetched = (await super().fetch_results())[0]
        for row in fetched.payload["results"] + fetched.payload["team_stats"]:
            row["finished_at"] = "2026-09-28T21:00:00Z"
        if self.change:
            self.change(fetched)
        return [fetched]


async def test_results_raw_first_replay_and_append_corrections(sessions):
    service, provider = IngestionService(sessions), CompletedFixture()
    assert (await service.run(provider))["status"] == "SUCCESS"
    result = await service.run(provider, "results")
    assert result["status"] == "SUCCESS" and result["records"] == 2
    fetched = (await provider.fetch_results())[0]
    service.record_raw(fetched)
    with sessions() as db:
        for _ in range(2):
            service.persist_batch(db, provider, fetched, provider.normalize(fetched))
        db.commit()
        assert db.scalar(select(func.count()).select_from(MatchResult)) == 2
        stat = db.scalar(select(TeamMatchStats))
        assert stat.xg == Decimal("1.7") and stat.xga is None and stat.red_cards == 0
        assert db.get(RawPayload, stat.raw_payload_id).mock
        assert db.scalar(select(func.count()).select_from(Match)) == 3
    provider.change = lambda f: f.payload["results"][0].update(home_score=3)
    assert (await service.run(provider, "results"))["status"] == "SUCCESS"
    with sessions() as db:
        assert set(db.scalars(select(MatchResult.home_score))) == {2, 3}


async def test_external_post_match_replay_preserves_binding_versions(sessions):
    from jc.entities import bind_team
    from jc.models import MatchMapping, ProviderMatch

    service, primary = IngestionService(sessions), CompletedFixture()
    await service.run(primary)
    external = CompletedFixture()
    external.name, external.is_primary = "external_results_fixture", False
    fetched = (await external.fetch_results())[0]
    service.record_raw(fetched)
    with sessions() as db:
        match = db.scalar(select(Match).where(Match.sporttery_match_id == "mock-s001"))
        pm = ProviderMatch(
            provider=external.name,
            provider_match_id="mock-s001",
            home_name="Home",
            away_name="Away",
            competition="League",
            kickoff_at=match.kickoff_at,
            raw_payload_id=fetched.raw_id,
            collected_at=fetched.collected_at,
            mock=True,
        )
        db.add(pm)
        db.flush()
        mapping = MatchMapping(
            provider_match_id=pm.id,
            match_id=match.id,
            provider=external.name,
            confidence=100,
            match_method="MANUAL",
            status="CONFIRMED",
            review_required=False,
            candidates=[],
            version=1,
        )
        db.add(mapping)
        bind_team(db, external.name, "mock-ars", match.home_team_id, "Home", "MANUAL")
        db.commit()
        service.persist_batch(db, external, fetched, external.normalize(fetched))
        db.commit()
        mapping.version = 2
        db.commit()
        service.persist_batch(db, external, fetched, external.normalize(fetched))
        service.persist_batch(db, external, fetched, external.normalize(fetched))
        db.commit()
        assert sorted(db.scalars(select(MatchResult.mapping_version))) == [1, 2]
        assert sorted(db.scalars(select(TeamMatchStats.mapping_version))) == [1, 2]


@pytest.mark.parametrize("kind", ["score", "shots", "identity", "future_finish", "duplicate", "mock"])
async def test_invalid_post_match_batch_keeps_raw_without_partial_facts(sessions, kind):
    service, provider = IngestionService(sessions), CompletedFixture()
    await service.run(provider)

    def change(fetched):
        if kind == "score":
            fetched.payload["results"][0]["home_score"] = -1
        elif kind == "shots":
            fetched.payload["team_stats"][0]["shots_on_target"] = 99
        elif kind == "identity":
            fetched.payload["team_stats"][0]["external_team_id"] = "unregistered"
        elif kind == "future_finish":
            fetched.payload["results"][0]["finished_at"] = (
                fetched.collected_at + timedelta(hours=1)
            ).isoformat()
        elif kind == "duplicate":
            fetched.payload["results"].append(copy.deepcopy(fetched.payload["results"][0]))
        else:
            fetched.mock = False

    provider.change = change
    assert (await service.run(provider, "results"))["status"] == "FAILED"
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(RawPayload)) == 2
        assert db.scalar(select(func.count()).select_from(MatchResult)) == 0
        assert db.scalar(select(func.count()).select_from(TeamMatchStats)) == 0


async def test_mock_rejected_in_live_mode_even_with_empty_database(sessions, monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "false")
    get_settings.cache_clear()
    result = await IngestionService(sessions).run(CompletedFixture(), "results")
    assert result["status"] == "FAILED" and result["error_code"] == "MODE_CONFLICT"
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(RawPayload)) == 1
        assert not db.scalar(select(MatchResult))


async def test_unsupported_real_results_and_external_fixture_never_expand_pool(sessions):
    from jc.config import Settings

    service = IngestionService(sessions)
    real = SportteryProvider(Settings(), None)
    assert (await service.run(real, "results"))["error_code"] == "RESULTS_UNSUPPORTED"
    provider = CompletedFixture()
    provider.is_primary = False
    provider.name = "unverified_stats_fixture"
    assert (await service.run(provider, "results"))["status"] == "EMPTY"
    with sessions() as db:
        assert not db.scalar(select(Match)) and not db.scalar(select(MatchResult))


@pytest.mark.parametrize(
    "updates",
    [
        {"first_goal_team": "NONE"},
        {"first_goal_minute": 5},
        {"half_home_score": 3},
        {"status": "LIVE"},
        {"finished_at": "2026-09-28T21:00:00"},
        {"home_score": True},
    ],
)
def test_result_contract_rejects_ambiguous_or_invalid_facts(updates):
    data = dict(
        external_match_id="fixture",
        status="FINAL",
        period="REGULATION",
        finished_at="2026-09-28T21:00:00Z",
        home_score=2,
        away_score=1,
    )
    with pytest.raises(ValueError):
        NormalizedResult.model_validate({**data, **updates})


@pytest.mark.parametrize("updates", [{"xg": "NaN"}, {"possession": "101"}, {"corners": -1}])
def test_stats_contract_rejects_invalid_numbers(updates):
    with pytest.raises(ValueError):
        NormalizedTeamStats.model_validate(
            dict(
                external_match_id="fixture",
                external_team_id="team",
                status="FINAL",
                period="REGULATION",
                finished_at="2026-09-28T21:00:00Z",
                **updates,
            )
        )
