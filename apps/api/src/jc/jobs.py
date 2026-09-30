"""Replaceable job boundary: APScheduler calls Coordinator; Celery can call execute()."""

import asyncio
import logging
import secrets
from datetime import datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from redis.asyncio import Redis
from sqlalchemy import select

from jc.config import Settings
from jc.db import SessionLocal
from jc.ingestion import IngestionService
from jc.models import Match, ProviderState, SyncRun
from jc.odds import finalize_keys
from jc.providers.registry import providers
from jc.time import utcnow

logger = logging.getLogger(__name__)


def sampling_interval(seconds_to_kickoff: float, provider_min_interval: int = 1) -> int | None:
    if seconds_to_kickoff <= 0:
        return None
    seconds = (
        1800
        if seconds_to_kickoff > 86400
        else 600
        if seconds_to_kickoff > 21600
        else 300
        if seconds_to_kickoff > 3600
        else 60
        if seconds_to_kickoff > 900
        else 30
    )
    return max(seconds, provider_min_interval)


class RedisRateLimiter:
    def __init__(self, client: Redis, settings: Settings):
        self.client, self.settings = client, settings

    async def acquire(self, provider: str):
        interval = (
            self.settings.odds_provider_min_interval
            if provider == "the_odds_api"
            else self.settings.provider_min_interval
        )
        key = "jc:rate:" + provider
        while True:
            # Account-wide gate, shared by all resources, retries, jobs and processes.
            if await self.client.set(key, "1", nx=True, ex=interval):
                return
            ttl = await self.client.ttl(key)
            await asyncio.sleep(min(max(ttl, 1), 30))

    async def cooldown(self, provider: str, seconds: int):
        await self.client.set("jc:rate:" + provider, "1", ex=max(seconds, 1))


class Coordinator:
    def __init__(self, settings: Settings, sessions=SessionLocal):
        self.settings, self.sessions = settings, sessions
        self.service = IngestionService(sessions)
        self.redis = Redis.from_url(settings.redis_url, socket_timeout=3, socket_connect_timeout=3)
        self.limiter = RedisRateLimiter(self.redis, settings)
        self.adapters = providers(settings, self.service.record_raw, before_request=self.limiter.acquire)
        for adapter in self.adapters.values():
            transport = getattr(adapter, "transport", None)
            if transport:
                transport.on_rate_limit = self.limiter.cooldown
        self.last_match_sync: dict[str, datetime] = {}
        self.local_running: set[str] = set()

    def initialize_states(self):
        expected = {"sporttery", "pinnacle", "bet365", "macau", "williamhill", "the_odds_api"}
        with self.sessions() as db:
            for run in db.scalars(
                select(SyncRun).where(
                    SyncRun.status.in_(["RUNNING", "QUEUED"]),
                    SyncRun.started_at < utcnow() - timedelta(minutes=11),
                )
            ):
                run.status, run.error_code, run.finished_at = "FAILED", "INTERRUPTED", utcnow()
            for name in expected:
                state = db.get(ProviderState, name)
                if state is None:
                    active = name in self.adapters
                    db.add(
                        ProviderState(
                            provider=name, enabled=active, status="DEGRADED" if active else "DISABLED"
                        )
                    )
                elif name not in self.adapters:
                    state.status, state.enabled = "DISABLED", False
            db.commit()

    async def execute(
        self, name: str, operation: str = "matches", request_id: str | None = None, run_id: str | None = None
    ):
        if name not in self.adapters:
            self.finish_skipped(run_id, "DISABLED")
            return {"status": "DISABLED", "records": 0}
        if name in self.local_running:
            self.finish_skipped(run_id, "BUSY")
            return {"status": "BUSY", "records": 0}
        token = secrets.token_hex(16)
        locked = False
        self.local_running.add(name)
        try:
            if not self.settings.demo_mode:
                locked = bool(await self.redis.set("jc:sync:" + name, token, nx=True, ex=660))
                if not locked:
                    self.finish_skipped(run_id, "BUSY")
                    return {"status": "BUSY", "records": 0}
            result = await asyncio.wait_for(
                self.service.run(self.adapters[name], operation, request_id, run_id), timeout=600
            )
            return result
        except Exception as exc:
            with self.sessions() as db:
                run = (
                    db.get(SyncRun, run_id)
                    if run_id
                    else SyncRun(
                        provider=name, operation=operation, request_id=request_id or token, status="RUNNING"
                    )
                )
                if run:
                    was_failed = run.status == "FAILED"
                    run.status, run.error_code, run.finished_at = "FAILED", type(exc).__name__, utcnow()
                    run.error_message = "Job coordination failed before provider ingestion"
                    db.add(run)
                    state = db.get(ProviderState, name)
                    if state and not was_failed:
                        state.consecutive_failures += 1
                        state.last_failure_at = utcnow()
                        state.status = "DOWN" if state.consecutive_failures >= 3 else "DEGRADED"
                    db.commit()
            logger.error(
                "Job coordination failed",
                extra={
                    "provider": name,
                    "operation": operation,
                    "request_id": request_id,
                    "status": "FAILED",
                    "error_code": type(exc).__name__,
                },
            )
            return {"status": "FAILED", "error_code": type(exc).__name__, "records": 0}
        finally:
            self.local_running.discard(name)
            if locked:
                try:
                    await self.redis.eval(
                        "if redis.call('get',KEYS[1]) == ARGV[1] then return redis.call('del',KEYS[1]) else return 0 end",
                        1,
                        "jc:sync:" + name,
                        token,
                    )
                except Exception:
                    logger.warning(
                        "Job lock release failed", extra={"provider": name, "error_code": "REDIS_LOCK"}
                    )

    def finish_skipped(self, run_id: str | None, reason: str):
        if run_id:
            with self.sessions() as db:
                run = db.get(SyncRun, run_id)
                if run and run.status == "QUEUED":
                    run.status, run.error_code, run.finished_at = "SKIPPED", reason, utcnow()
                    db.commit()

    async def tick(self, only_provider: str | None = None):
        now = utcnow()
        with self.sessions() as db:
            matches = list(
                db.scalars(
                    select(Match).where(
                        Match.mock == self.settings.demo_mode, Match.kickoff_at >= now - timedelta(hours=1)
                    )
                )
            )
            if only_provider in (None, "sporttery"):
                for match in matches:
                    finalize_keys(db, match, now)
            states = {state.provider: state for state in db.scalars(select(ProviderState))}
            db.commit()
        for name in self.adapters:
            if only_provider is not None and name != only_provider:
                continue
            state = states.get(name)
            previous_match_sync = self.last_match_sync.get(name)
            catalog_due = previous_match_sync is None or (now - previous_match_sync).total_seconds() >= 300
            odds_due = not state or not state.next_allowed_at or state.next_allowed_at <= now
            if state and not state.enabled:
                continue
            if not catalog_due and not odds_due:
                continue
            if state and state.consecutive_failures and not odds_due:
                continue
            upcoming = [
                (match.kickoff_at - now).total_seconds() for match in matches if match.kickoff_at > now
            ]
            minimum = (
                self.settings.odds_provider_min_interval
                if name == "the_odds_api"
                else self.settings.provider_min_interval
            )
            cadence = sampling_interval(min(upcoming), minimum) if upcoming else max(300, minimum)
            operation = "matches" if catalog_due else "odds"
            if not upcoming and operation == "odds":
                continue
            result = await self.execute(name, operation)
            if operation == "matches":
                self.last_match_sync[name] = utcnow()
                if self.adapters[name].is_primary and result["status"] == "SUCCESS" and odds_due:
                    result = await self.execute(name, "odds")
            with self.sessions() as db:
                state = db.get(ProviderState, name)
                if state:
                    delay = max(cadence or 300, minimum)
                    if result["status"] == "FAILED":
                        delay = max(delay, min(1800, 2 ** min(state.consecutive_failures, 8) * 30))
                    state.next_allowed_at = utcnow() + timedelta(seconds=delay)
                    state.rate_limit_status = (
                        "COOLDOWN" if result.get("error_code") == "RATE_LIMITED" else "AVAILABLE"
                    )
                    db.commit()

    async def close(self):
        await self.redis.aclose()


def start_scheduler(coordinator: Coordinator):
    scheduler = AsyncIOScheduler(timezone="UTC")
    for name in coordinator.adapters:
        scheduler.add_job(
            coordinator.tick,
            "interval",
            seconds=5,
            id="ingestion:" + name,
            kwargs={"only_provider": name},
            max_instances=1,
            coalesce=True,
            misfire_grace_time=30,
        )
    scheduler.start()
    return scheduler
