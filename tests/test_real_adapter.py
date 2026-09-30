import json
from pathlib import Path

import httpx
from jc.config import Settings
from jc.ingestion import IngestionService
from jc.providers.http import HttpTransport, safe_url
from jc.providers.the_odds_api import TheOddsApiProvider


async def test_documented_live_adapter_contract_without_live_claim(sessions):
    payload = json.loads(Path("tests/fixtures/the_odds_api.json").read_text())["data"]
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=payload)

    settings = Settings(
        odds_provider_base_url="https://fixture.invalid",
        odds_provider_api_key="synthetic-key",
        odds_provider_sports="soccer_epl",
    )
    service = IngestionService(sessions)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = TheOddsApiProvider(settings, HttpTransport(settings, service.record_raw, client))
        fetched = (await provider.fetch_matches())[0]
        batch = provider.normalize(fetched)
        assert len(batch.odds) == 7
        assert batch.matches[0].home_external_id is None
        assert "synthetic-key" not in fetched.source_url
        assert requests[0].url.path == "/v4/sports/soccer_epl/odds"


def test_redact_secrets():
    assert "secret" not in safe_url("https://example.test/path?apiKey=secret&markets=h2h")
