"""Explicit bootstrap: optional administrator and isolated, labelled demo fixtures."""

import asyncio

from sqlalchemy import select

from jc.auth import passwords
from jc.config import get_settings
from jc.db import SessionLocal
from jc.entities import bind_team
from jc.ingestion import IngestionService
from jc.models import AuditLog, CompetitionIdentity, Team, TeamIdentity, User
from jc.providers.mock import MockOddsProvider, MockSportteryProvider, read_fixture


def seed_demo_identities(sessions):
    links = read_fixture("entity_links")
    with sessions() as db:
        for item in links["teams"]:
            identity = db.scalar(
                select(TeamIdentity).where(
                    TeamIdentity.provider == "sporttery",
                    TeamIdentity.external_team_id == item["sporttery_external_id"],
                )
            )
            team = db.get(Team, identity.team_id)
            bind_team(db, item["provider"], item["external_id"], team.id, team.canonical_name, "MOCK_FIXTURE")
        for item in links["competitions"]:
            existing = db.scalar(
                select(CompetitionIdentity).where(
                    CompetitionIdentity.provider == item["provider"],
                    CompetitionIdentity.external_id == item["external_id"],
                )
            )
            if not existing:
                primary = db.scalar(
                    select(CompetitionIdentity).where(
                        CompetitionIdentity.provider == "sporttery",
                        CompetitionIdentity.external_id == item["sporttery_external_id"],
                    )
                )
                db.add(
                    CompetitionIdentity(
                        provider=item["provider"],
                        external_id=item["external_id"],
                        competition_id=primary.competition_id,
                    )
                )
        db.add(
            AuditLog(
                operation="DEMO_IDENTITY_SEED",
                entity_type="fixture",
                entity_id="entity_links.json",
                after={"mock": True},
                reason="Explicit fixture ID mapping",
            )
        )
        db.commit()


async def seed_demo(sessions):
    service = IngestionService(sessions)
    result = await service.run(MockSportteryProvider())
    if result["status"] != "SUCCESS":
        raise RuntimeError(f"Demo seed failed: {result}")
    seed_demo_identities(sessions)
    for name in ("pinnacle", "bet365", "macau", "williamhill"):
        for revision in (0, 1):
            result = await service.run(MockOddsProvider(name, revision=revision))
            if result["status"] != "SUCCESS":
                raise RuntimeError(f"Demo provider failed: {result}")


async def main():
    settings = get_settings()
    if settings.admin_email and settings.admin_password:
        if len(settings.admin_password) < 12:
            raise ValueError("ADMIN_PASSWORD must have at least 12 characters")
        with SessionLocal() as db:
            user = db.scalar(select(User).where(User.email == settings.admin_email.lower()))
            if user is None:
                user = User(
                    email=settings.admin_email.lower(),
                    password_hash=passwords.hash(settings.admin_password),
                    role="ADMIN",
                )
                db.add(user)
                db.flush()
                db.add(AuditLog(operation="BOOTSTRAP_ADMIN", entity_type="user", entity_id=user.id))
                db.commit()
    if settings.demo_mode:
        await seed_demo(SessionLocal)


if __name__ == "__main__":
    asyncio.run(main())
