import copy
from datetime import timedelta
from decimal import Decimal

import httpx
import pytest
from jc.bootstrap import seed_demo
from jc.config import Settings
from jc.ingestion import IngestionService
from jc.jobs import Coordinator
from jc.models import AuditLog, Match, MatchMapping, RawPayload
from jc.odds import latest_rows, store_quotes
from jc.providers.contracts import OddsQuote
from jc.providers.http import HttpTransport, ProviderError
from jc.providers.mock import MockOddsProvider, MockSportteryProvider
from jc.time import utcnow
from sqlalchemy import func, select


def make_admin(client, sessions):
    from jc.models import User

    credentials = {"email": "review@example.com", "password": "review-password-123"}
    assert client.post("/api/v1/auth/register", json=credentials).status_code == 201
    with sessions() as db:
        user = db.scalar(select(User).where(User.email == credentials["email"]))
        user.role = "ADMIN"
        db.commit()
    result = client.post("/api/v1/auth/login", json=credentials).json()["data"]
    return {"Authorization": "Bearer " + result["access_token"]}


async def test_full_mock_api_history_quality_and_review(client, sessions):
    await seed_demo(sessions)
    coordinator = Coordinator(Settings(), sessions)
    coordinator.initialize_states()
    client.app.state.coordinator = coordinator
    public = client.get("/api/v1/matches/today").json()["data"]
    assert public["total"] == 3
    first = next(m for m in public["items"] if m["sporttery_match_id"] == "mock-s001")
    mid = first["id"]
    pools = client.get(f"/api/v1/matches/{mid}/sporttery-odds").json()["data"]["markets"]
    assert len(pools) == 5 and all(pool["odds"] for pool in pools.values())
    prices = client.get(f"/api/v1/matches/{mid}/odds").json()["data"]["items"]
    assert {row["provider"] for row in prices} == {"sporttery", "pinnacle", "bet365", "macau", "williamhill"}
    page = client.get(f"/api/v1/matches/{mid}/odds/history?limit=3").json()["data"]
    second = client.get(
        f"/api/v1/matches/{mid}/odds/history", params={"limit": 3, "cursor": page["next_cursor"]}
    ).json()["data"]
    assert not {row["id"] for row in page["items"]} & {row["id"] for row in second["items"]}
    assert (
        client.get(f"/api/v1/matches/{mid}/odds", params={"analysis_cutoff": "2020-01-01T00:00:00Z"}).json()[
            "data"
        ]["items"]
        == []
    )
    assert (
        client.get(
            f"/api/v1/matches/{mid}/odds", params={"analysis_cutoff": "2026-09-30T18:00:00"}
        ).status_code
        == 422
    )
    assert client.get("/api/v1/matches/not-a-uuid").status_code == 422
    quality = client.get("/api/v1/quality").json()["data"]
    assert (quality["matched"], quality["review"], quality["unmatched"]) == (8, 4, 4)
    assert client.get("/api/v1/admin/mappings").status_code == 401
    headers = make_admin(client, sessions)
    mappings = client.get("/api/v1/admin/mappings?status=REVIEW", headers=headers).json()["data"]["items"]
    row = mappings[0]
    body = {"version": row["version"], "reason": "核实球队身份和时间偏差", "match_id": row["match_id"]}
    result = client.post(f"/api/v1/admin/mappings/{row['id']}/confirm", json=body, headers=headers)
    assert result.status_code == 200 and result.json()["data"]["status"] == "CONFIRMED"
    assert (
        client.post(f"/api/v1/admin/mappings/{row['id']}/confirm", json=body, headers=headers).status_code
        == 409
    )
    raw_id = row["provider_match"]["raw_payload_id"]
    replay = client.post(
        f"/api/v1/admin/raw/{raw_id}/reprocess", headers=headers, json={"reason": "确认映射后重处理"}
    )
    assert replay.status_code == 200
    with sessions() as db:
        assert (
            db.scalar(
                select(func.count()).select_from(AuditLog).where(AuditLog.operation == "MAPPING_CONFIRM")
            )
            == 1
        )
        assert db.scalar(select(func.count()).select_from(Match)) == 3
    assert client.get("/api/v1/admin/users", headers=headers).status_code == 200
    assert "password_hash" not in client.get("/api/v1/admin/users", headers=headers).text
    assert client.get("/api/v1/admin/logs", headers=headers).status_code == 200
    assert (
        client.patch(
            "/api/v1/admin/providers/pinnacle",
            headers=headers,
            json={"enabled": False, "reason": "测试暂停采集"},
        ).status_code
        == 200
    )
    assert (
        client.post("/api/v1/admin/sync", headers=headers, json={"provider": "pinnacle"}).status_code == 409
    )
    await coordinator.close()


async def test_older_effective_backfill_cannot_replace_latest_or_leak(sessions):
    await seed_demo(sessions)
    service = IngestionService(sessions)
    provider = MockOddsProvider("pinnacle", revision=1)
    fetched = (await provider.fetch_odds())[0]
    fetched.resource_type = "history"
    quote = provider.normalize(fetched).odds[0]
    before = utcnow()
    quote = quote.model_copy(
        update={"decimal_odds": Decimal("9.99"), "effective_at": quote.effective_at - timedelta(days=1)}
    )
    service.record_raw(fetched)
    with sessions() as db:
        store_quotes(db, provider, fetched, [quote])
        db.commit()
        match = db.scalar(select(Match).where(Match.sporttery_match_id == "mock-s001"))
        current = [
            row
            for row in latest_rows(db, match.id)
            if row.provider == "pinnacle" and row.selection == "HOME" and row.market_type == "1X2"
        ]
        assert current[0].decimal_odds != Decimal("9.99")
        visible_before = latest_rows(db, match.id, before)
        assert not any(row.decimal_odds == Decimal("9.99") for row in visible_before)


async def test_kickoff_change_invalidates_and_old_raw_does_not_revert(sessions):
    await seed_demo(sessions)
    service = IngestionService(sessions)
    source = MockSportteryProvider()
    older = (await source.fetch_matches())[0]
    service.record_raw(older)
    newer = copy.deepcopy(older)
    newer.raw_id = None
    newer.collected_at = utcnow()
    row = newer.payload["value"]["matchInfoList"][0]["subMatchList"][0]
    row["matchTime"] = "04:00:00"
    service.record_raw(newer)
    cutoff_before_change = utcnow()
    with sessions() as db:
        service.persist_batch(db, source, newer, source.normalize(newer))
        db.commit()
        match = db.scalar(select(Match).where(Match.sporttery_match_id == "mock-s001"))
        new_time = match.kickoff_at
        assert set(db.scalars(select(MatchMapping.status).where(MatchMapping.match_id == match.id))) == {
            "REVIEW"
        }
        assert all(row.provider == "sporttery" for row in latest_rows(db, match.id))
        assert any(row.provider == "pinnacle" for row in latest_rows(db, match.id, cutoff_before_change))
        service.persist_batch(db, source, older, source.normalize(older))
        db.commit()
        assert db.get(Match, match.id).kickoff_at == new_time


async def test_retry_after_retains_raw_and_defers_without_hammering(sessions):
    service = IngestionService(sessions)
    calls = []
    cooldowns = []

    async def cooldown(provider, seconds):
        cooldowns.append(seconds)

    def handler(request):
        calls.append(request)
        return httpx.Response(429, json={"error": "quota"}, headers={"Retry-After": "3600"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        transport = HttpTransport(Settings(), service.record_raw, client)
        transport.on_rate_limit = cooldown
        with pytest.raises(ProviderError) as error:
            await transport.fetch("test", "odds", "https://fixture.invalid")
        assert error.value.raw_id and error.value.code == "RATE_LIMITED"
    assert len(calls) == 1 and cooldowns[0] >= 3600
    with sessions() as db:
        assert db.scalar(select(RawPayload)).http_status == 429


def test_missing_line_rejected():
    with pytest.raises(ValueError):
        OddsQuote(
            external_match_id="test",
            bookmaker="test",
            market_type="ASIAN_HANDICAP",
            selection="HOME",
            raw_odds="1.9",
            decimal_odds=Decimal("1.9"),
        )
