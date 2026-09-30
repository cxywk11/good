from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

from fastapi import HTTPException
from jc.auth_limits import auth_budget
from jc.config import get_settings
from jc.models import AuthRateBucket
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from starlette.requests import Request


def configure(monkeypatch, **settings):
    for key, value in settings.items():
        monkeypatch.setenv(key.upper(), str(value))
    get_settings.cache_clear()


def request(peer="127.0.0.1"):
    result = Request({"type": "http", "client": (peer, 1234), "headers": []})
    result.state.request_id = "budget-test"
    return result


def test_login_budget_survives_rejected_requests_and_expires(client, sessions, monkeypatch):
    configure(monkeypatch, auth_login_account_limit=2, auth_window_seconds=60)
    moment = datetime(2026, 9, 30, 1, 0, 10, tzinfo=UTC)
    monkeypatch.setattr("jc.auth_limits.utcnow", lambda: moment)
    credentials = {"email": "absent@example.com", "password": "a-wrong-password"}
    assert client.post("/api/v1/auth/login", json=credentials).status_code == 401
    assert client.post("/api/v1/auth/login", json=credentials).status_code == 401
    blocked = client.post("/api/v1/auth/login", json=credentials)
    assert blocked.status_code == 429
    assert blocked.headers["Retry-After"] == "50"
    assert blocked.json()["request_id"] and not blocked.json()["success"]
    with sessions() as db:
        keys = list(db.scalars(select(AuthRateBucket.key)))
        assert all("absent" not in key and "testclient" not in key for key in keys)
    moment += timedelta(minutes=1)
    assert client.post("/api/v1/auth/login", json=credentials).status_code == 401
    with sessions() as db:
        assert len(list(db.scalars(select(AuthRateBucket)))) == 2


def test_ip_budget_cannot_be_bypassed_with_email_or_forwarded_headers(client, monkeypatch):
    configure(monkeypatch, auth_login_ip_limit=2)
    for index in range(2):
        assert (
            client.post(
                "/api/v1/auth/login",
                json={"email": f"absent{index}@example.com", "password": "a-wrong-password"},
            ).status_code
            == 401
        )
    blocked = client.post(
        "/api/v1/auth/login",
        headers={"X-Forwarded-For": "198.51.100.123"},
        json={"email": "another@example.com", "password": "a-wrong-password"},
    )
    assert blocked.status_code == 429


def test_shared_account_budget_across_peers_and_case(sessions, monkeypatch):
    configure(monkeypatch, auth_login_account_limit=1)
    with sessions() as db:
        auth_budget(db, request("192.0.2.1"), "login", "PERSON@example.com")
    with sessions() as db:
        try:
            auth_budget(db, request("192.0.2.2"), "login", "person@example.com")
        except HTTPException as exc:
            assert exc.status_code == 429
        else:
            raise AssertionError("Account budget was bypassed")


def test_atomic_budget_under_concurrent_workers(sessions, monkeypatch):
    configure(monkeypatch, auth_login_account_limit=4)

    def attempt(index):
        with sessions() as db:
            try:
                auth_budget(db, request(f"192.0.2.{index + 1}"), "login", "race@example.com")
                return 200
            except HTTPException as exc:
                return exc.status_code

    with ThreadPoolExecutor(max_workers=8) as pool:
        statuses = list(pool.map(attempt, range(16)))
    assert statuses.count(200) == 4
    assert statuses.count(429) == 12


def test_registration_and_refresh_have_separate_budgets(client, monkeypatch):
    configure(monkeypatch, auth_register_ip_limit=1, auth_refresh_ip_limit=1)
    credentials = {"email": "person@example.com", "password": "a-strong-test-password"}
    assert client.post("/api/v1/auth/register", json=credentials).status_code == 201
    assert client.post("/api/v1/auth/register", json=credentials).status_code == 429
    token = client.post("/api/v1/auth/login", json=credentials).json()["data"]
    assert (
        client.post("/api/v1/auth/refresh", json={"refresh_token": token["refresh_token"]}).status_code == 200
    )
    assert (
        client.post("/api/v1/auth/refresh", json={"refresh_token": token["refresh_token"]}).status_code == 429
    )


def test_budget_database_failure_does_not_allow_authentication(sessions, monkeypatch):
    with sessions() as db:
        monkeypatch.setattr(db, "scalar", Mock(side_effect=SQLAlchemyError("database failed")))
        try:
            auth_budget(db, request(), "login", "person@example.com")
        except HTTPException as exc:
            assert exc.status_code == 503
        else:
            raise AssertionError("Failed authentication budget must fail closed")
