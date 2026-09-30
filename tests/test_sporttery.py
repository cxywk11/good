import copy
import json
from pathlib import Path

import httpx
import pytest
from jc.config import Settings
from jc.ingestion import IngestionService
from jc.models import Match, RawPayload, SyncRun
from jc.providers.contracts import FetchedPayload
from jc.providers.http import HttpTransport
from jc.providers.sporttery import SportteryProvider
from jc.time import utcnow
from sqlalchemy import func, select


def fixture_payload():
    return json.loads(Path("tests/fixtures/sporttery.json").read_text(encoding="utf-8"))


def provider_for(sessions, payload=None, status=200, timeout=False):
    service = IngestionService(sessions)

    def handler(request):
        if timeout:
            raise httpx.ReadTimeout("timeout")
        return httpx.Response(status, json=payload)

    settings = Settings(
        sporttery_base_url="https://fixture.invalid",
        sporttery_matches_path="/matches",
        provider_max_attempts=2,
    )

    async def no_wait(_):
        pass

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = SportteryProvider(settings, HttpTransport(settings, service.record_raw, client, no_wait))
    return service, provider


def test_parse_five_markets():
    service = SportteryProvider(Settings(), None)
    batch = service.normalize(
        FetchedPayload("sporttery", "matches", fixture_payload(), "fixture://test", utcnow(), mock=True)
    )
    assert len(batch.matches) == 3
    assert set(batch.matches[0].markets) == {"had", "hhad", "crs", "ttg", "hafu"}
    assert batch.matches[1].markets["crs"]["available"] is False
    assert batch.matches[0].kickoff_at.isoformat() == "2026-09-30T19:00:00+00:00"
    assert any(q.selection == "1:0" for q in batch.odds)


async def test_raw_first_and_idempotent_match(sessions):
    service, provider = provider_for(sessions, fixture_payload())
    assert (await service.run(provider))["status"] == "SUCCESS"
    assert (await service.run(provider))["status"] == "SUCCESS"
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(Match)) == 3
        assert db.scalar(select(func.count()).select_from(RawPayload)) == 2


@pytest.mark.parametrize("kind", ["timeout", "500", "empty", "schema", "odds", "duplicate", "unopened"])
async def test_bad_data_is_visible_without_dirty_matches(sessions, kind):
    payload = copy.deepcopy(fixture_payload())
    row = payload["value"]["matchInfoList"][0]["subMatchList"][0]
    if kind == "empty":
        payload["value"]["matchInfoList"] = []
    elif kind == "schema":
        payload = {"unexpected": []}
    elif kind == "odds":
        row["had"]["h"] = "NOT_ODDS"
    elif kind == "duplicate":
        other = copy.deepcopy(row)
        other["homeTeamAllName"] = "different"
        payload["value"]["matchInfoList"][0]["subMatchList"].append(other)
    elif kind == "unopened":
        for item in payload["value"]["matchInfoList"][0]["subMatchList"]:
            item["sellStatus"] = "0"
    service, provider = provider_for(sessions, payload, 500 if kind == "500" else 200, kind == "timeout")
    result = await service.run(provider)
    assert result["status"] == ("EMPTY" if kind in {"empty", "unopened"} else "FAILED")
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(Match)) == 0
        assert db.scalar(select(func.count()).select_from(RawPayload)) >= 1
        assert db.scalar(select(SyncRun)).status == result["status"]
