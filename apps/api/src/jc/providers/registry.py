from jc.config import Settings
from jc.providers.base import OddsProvider
from jc.providers.http import HttpTransport
from jc.providers.mock import MockOddsProvider, MockSportteryProvider
from jc.providers.sporttery import SportteryProvider
from jc.providers.the_odds_api import TheOddsApiProvider


def providers(settings: Settings, record_raw, client=None, before_request=None) -> dict[str, OddsProvider]:
    transport = HttpTransport(settings, record_raw, client)
    if before_request:
        transport.before_request = before_request
    if settings.demo_mode:
        return {
            p.name: p
            for p in [
                MockSportteryProvider(),
                *[MockOddsProvider(name) for name in ("pinnacle", "bet365", "macau", "williamhill")],
            ]
        }
    result: dict[str, OddsProvider] = {}
    if settings.sporttery_enabled:
        result["sporttery"] = SportteryProvider(settings, transport)
    if settings.odds_provider_enabled:
        result["the_odds_api"] = TheOddsApiProvider(settings, transport)
    return result
