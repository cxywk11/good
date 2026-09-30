import asyncio
import hashlib
import json
import logging
import time
from typing import Any
from uuid import uuid4

from fastapi.encoders import jsonable_encoder
from sqlalchemy import select

from jc.config import get_settings
from jc.entities import (
    CONFIRMED,
    ingest_external_match,
    invalidate_mapping,
    primary_competition,
    primary_team,
)
from jc.models import Match, MatchMapping, MatchVersion, ProviderState, RawPayload, SyncRun
from jc.odds import store_quotes
from jc.providers.base import OddsProvider
from jc.providers.contracts import FetchedPayload, NormalizedBatch
from jc.providers.http import ProviderError
from jc.time import utcnow

logger = logging.getLogger(__name__)


def payload_hash(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


class IngestionService:
    def __init__(self, sessions):
        self.sessions = sessions

    def record_raw(self, fetched: FetchedPayload) -> str:
        with self.sessions() as db:
            raw = RawPayload(
                provider=fetched.provider,
                resource_type=fetched.resource_type,
                external_id=fetched.external_id,
                payload=fetched.payload,
                source_url=fetched.source_url,
                http_status=fetched.http_status,
                collected_at=fetched.collected_at,
                payload_hash=payload_hash(fetched.payload),
                mock=fetched.mock,
            )
            db.add(raw)
            db.commit()
            fetched.raw_id = raw.id
            return raw.id

    def persist_batch(
        self, db, provider: OddsProvider, fetched: FetchedPayload, batch: NormalizedBatch
    ) -> int:
        if db.scalar(select(Match.id).where(Match.mock != fetched.mock).limit(1)):
            raise ProviderError("MODE_CONFLICT", "Demo and live data require separate databases")
        if not provider.is_primary:
            for item in batch.matches:
                ingest_external_match(db, provider.name, fetched, item, get_settings())
            return len(batch.matches) + store_quotes(db, provider, fetched, batch.odds)
        count = 0
        for item in batch.matches:
            existing = db.scalar(select(Match).where(Match.sporttery_match_id == item.external_id))
            # Unopened external fixtures can never create rows in the main pool.
            if existing is None and item.sell_status != "ON_SALE":
                continue
            if existing is not None and existing.mock != fetched.mock:
                raise ProviderError("MODE_CONFLICT", "Use separate databases for demo and live data")
            if existing is not None and fetched.collected_at < existing.collected_at:
                continue  # Replaying older Raw must not revert the current match state.
            values = {
                "sporttery_match_id": item.external_id,
                "match_num": item.match_num,
                "match_date": item.match_date,
                "sell_date": item.sell_date,
                "competition_name": item.competition,
                "competition_code": item.competition_external_id,
                "home_team_name": item.home_name,
                "away_team_name": item.away_name,
                "kickoff_at": item.kickoff_at,
                "local_timezone": item.local_timezone,
                "sell_status": item.sell_status,
                "single_allowed": item.single_allowed,
                "markets": item.markets,
                "raw_payload_id": fetched.raw_id,
                "collected_at": fetched.collected_at,
                "mock": fetched.mock,
                "published_at": item.published_at,
                "effective_at": item.effective_at,
            }
            values.update(
                home_team_id=primary_team(db, item.home_external_id, item.home_name),
                away_team_id=primary_team(db, item.away_external_id, item.away_name),
                competition_id=primary_competition(db, item.competition_external_id, item.competition),
            )
            match = existing or Match(**values)
            if existing:
                if any(
                    getattr(existing, key) != values[key]
                    for key in ("home_team_id", "away_team_id", "kickoff_at")
                ):
                    for mapping in db.scalars(
                        select(MatchMapping).where(
                            MatchMapping.match_id == existing.id, MatchMapping.status.in_(CONFIRMED)
                        )
                    ):
                        invalidate_mapping(db, mapping, "Sporttery identity or kickoff changed")
                for key, value in values.items():
                    setattr(match, key, value)
            db.add(match)
            db.flush()
            db.add(
                MatchVersion(
                    match_id=match.id,
                    raw_payload_id=fetched.raw_id,
                    collected_at=fetched.collected_at,
                    effective_at=item.effective_at,
                    published_at=item.published_at,
                    state=jsonable_encoder(values),
                )
            )
            count += 1
        return count + store_quotes(db, provider, fetched, batch.odds)

    async def run(
        self,
        provider: OddsProvider,
        operation: str = "matches",
        request_id: str | None = None,
        run_id: str | None = None,
    ) -> dict:
        request_id = request_id or str(uuid4())
        started = time.perf_counter()
        with self.sessions() as db:
            state = db.get(ProviderState, provider.name)
            if state and not state.enabled:
                if run_id:
                    skipped = db.get(SyncRun, run_id)
                    if skipped:
                        skipped.status, skipped.finished_at = "DISABLED", utcnow()
                        db.commit()
                return {"status": "DISABLED", "records": 0}
            run = db.get(SyncRun, run_id) if run_id else None
            run = run or SyncRun(
                provider=provider.name, operation=operation, request_id=request_id, status="RUNNING"
            )
            run.status = "RUNNING"
            db.add(run)
            db.commit()
            run_id = run.id
        records = 0
        error_code = error_message = None
        last_raw = None
        status = "SUCCESS"
        try:
            fetched_list = await (
                provider.fetch_matches() if operation == "matches" else provider.fetch_odds()
            )
            for fetched in fetched_list:
                last_raw = fetched.raw_id or self.record_raw(fetched)
                batch = provider.normalize(fetched)
                with self.sessions() as db:
                    with db.begin():
                        records += self.persist_batch(db, provider, fetched, batch)
            if not fetched_list or not records:
                status = "EMPTY"
        except asyncio.CancelledError:
            status, error_code, error_message = (
                "FAILED",
                "CANCELLED",
                "Job interrupted or exceeded its time limit",
            )
        except Exception as exc:
            status = "FAILED"
            last_raw = getattr(exc, "raw_id", None) or last_raw
            error_code = exc.code if isinstance(exc, ProviderError) else type(exc).__name__
            error_message = (
                str(exc)
                if isinstance(exc, ProviderError)
                else "Ingestion transaction failed; inspect raw data"
            )
            logger.error(
                "Ingestion failed",
                extra={
                    "provider": provider.name,
                    "operation": operation,
                    "request_id": request_id,
                    "status": status,
                    "error_code": error_code,
                },
            )
        duration = int((time.perf_counter() - started) * 1000)
        with self.sessions() as db:
            run = db.get(SyncRun, run_id)
            run.status, run.records, run.finished_at, run.duration_ms = status, records, utcnow(), duration
            run.error_code, run.error_message, run.raw_payload_id = error_code, error_message, last_raw
            state = db.get(ProviderState, provider.name) or ProviderState(provider=provider.name)
            if status == "FAILED":
                state.last_failure_at = utcnow()
                state.consecutive_failures = (state.consecutive_failures or 0) + 1
                state.status = "DOWN" if state.consecutive_failures >= 3 else "DEGRADED"
            else:
                state.last_success_at, state.consecutive_failures = utcnow(), 0
                state.status = "DEGRADED" if status == "EMPTY" else "HEALTHY"
            state.latency = duration
            db.add(state)
            db.commit()
        return {"id": run_id, "status": status, "records": records, "error_code": error_code}
