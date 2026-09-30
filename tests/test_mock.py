from jc.bootstrap import seed_demo
from jc.models import Match, MatchMapping, ProviderMatch, RawPayload
from jc.providers.base import OddsProvider
from jc.providers.mock import MockOddsProvider, MockSportteryProvider
from sqlalchemy import func, select


async def test_all_mock_providers_flow_and_main_pool_is_primary_only(sessions):
    await seed_demo(sessions)
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(Match)) == 3
        assert db.scalar(select(func.count()).select_from(ProviderMatch)) == 16
        states = set(db.scalars(select(MatchMapping.status)))
        assert states == {"AUTO_CONFIRMED", "REVIEW", "UNMATCHED"}
        assert all(raw.mock for raw in db.scalars(select(RawPayload)))
    for provider in [
        MockSportteryProvider(),
        *[MockOddsProvider(p) for p in ("pinnacle", "bet365", "macau", "williamhill")],
    ]:
        assert isinstance(provider, OddsProvider)
        assert (await provider.health_check())["status"] == "HEALTHY"
