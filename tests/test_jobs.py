from unittest.mock import AsyncMock

import pytest
from jc.config import Settings
from jc.jobs import Coordinator, sampling_interval
from jc.models import ProviderState, SyncRun


@pytest.mark.parametrize(
    "seconds,expected",
    [
        (90000, 1800),
        (86400, 600),
        (21600, 300),
        (3600, 60),
        (901, 60),
        (900, 30),
        (1, 30),
        (0, None),
        (-10, None),
    ],
)
def test_dynamic_cadence(seconds, expected):
    assert sampling_interval(seconds) == expected


def test_provider_minimum_wins():
    assert sampling_interval(500, 120) == 120


async def test_busy_job_finishes_queued_run(sessions):
    coordinator = Coordinator(Settings(demo_mode=True), sessions)
    coordinator.local_running.add("sporttery")
    with sessions() as db:
        run = SyncRun(provider="sporttery", operation="matches", request_id="busy-test", status="QUEUED")
        db.add(run)
        db.commit()
        run_id = run.id
    assert (await coordinator.execute("sporttery", run_id=run_id))["status"] == "BUSY"
    with sessions() as db:
        run = db.get(SyncRun, run_id)
        assert run.status == "SKIPPED" and run.error_code == "BUSY" and run.finished_at
    await coordinator.close()


async def test_redis_failure_is_visible_in_provider_health(sessions):
    coordinator = Coordinator(Settings(demo_mode=False, sporttery_enabled=True), sessions)
    coordinator.initialize_states()
    coordinator.redis.set = AsyncMock(side_effect=ConnectionError("Redis unavailable"))
    with sessions() as db:
        run = SyncRun(provider="sporttery", operation="matches", request_id="redis-test", status="QUEUED")
        db.add(run)
        db.commit()
        run_id = run.id
    assert (await coordinator.execute("sporttery", run_id=run_id))["status"] == "FAILED"
    with sessions() as db:
        state = db.get(ProviderState, "sporttery")
        assert state.consecutive_failures == 1 and state.last_failure_at
        assert db.get(SyncRun, run_id).status == "FAILED"
    await coordinator.close()
