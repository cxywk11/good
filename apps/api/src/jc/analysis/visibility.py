"""Commit visibility proofs, independent of provider timestamps and mutable current rows.

The proof clock is sampled AFTER a separate connection reads committed input rows.
Even if the proof transaction commits later, the input was already visible at visible_at.
Never synthesize earlier proofs from created_at. Missing proofs fail closed.
"""

import logging
from datetime import datetime

from sqlalchemy import Engine, event, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from jc.time import utcnow

EVIDENCE_TABLES = (
    "provider_raw_payloads",
    "match_versions",
    "odds_snapshots",
    "odds_observations",
    "audit_logs",
    "match_results",
    "team_match_stats",
)
logger = logging.getLogger(__name__)


def record_visibility(engine: Engine) -> None:
    from jc.db import Base
    from jc.models import AnalysisVisibility

    proof = AnalysisVisibility.__table__
    with engine.begin() as connection:
        missing: list[dict] = []
        for name in EVIDENCE_TABLES:
            table = Base.metadata.tables[name]
            ids = connection.scalars(
                select(table.c.id).where(
                    ~select(proof.c.entity_id)
                    .where(
                        proof.c.entity_type == name,
                        proof.c.entity_id == table.c.id,
                    )
                    .exists()
                )
            ).all()
            # Sample only after the SELECT has completed, never before it.
            seen = utcnow()
            missing.extend({"entity_type": name, "entity_id": rid, "visible_at": seen} for rid in ids)
        insert = pg_insert if engine.dialect.name == "postgresql" else sqlite_insert
        for start in range(0, len(missing), 300):
            connection.execute(
                insert(AnalysisVisibility).values(missing[start : start + 300]).on_conflict_do_nothing()
            )


@event.listens_for(Session, "after_commit")
def after_commit(session: Session) -> None:
    try:
        record_visibility(session.get_bind().engine)
    except Exception:
        # The business transaction is already committed; unavailable proofs cannot authorize features.
        logger.exception("Analysis visibility recording failed; unproven inputs remain unavailable")


def proven(model, cutoff: datetime):
    from jc.models import AnalysisVisibility

    return (
        select(AnalysisVisibility.entity_id)
        .where(
            AnalysisVisibility.entity_type == model.__tablename__,
            AnalysisVisibility.entity_id == model.id,
            AnalysisVisibility.visible_at <= cutoff,
        )
        .exists()
    )


def temporal(model, cutoff: datetime, observed: str = "collected_at"):
    constraints = [getattr(model, observed) <= cutoff, model.created_at <= cutoff, proven(model, cutoff)]
    for name in ("published_at", "effective_at"):
        if hasattr(model, name):
            column = getattr(model, name)
            constraints.append(or_(column.is_(None), column <= cutoff))
    return constraints
