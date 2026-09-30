import re
import unicodedata
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import select

from jc.config import Settings
from jc.models import (
    AuditLog,
    Competition,
    CompetitionIdentity,
    Match,
    MatchMapping,
    ProviderMatch,
    Team,
    TeamAlias,
    TeamIdentity,
)
from jc.providers.contracts import FetchedPayload, NormalizedMatch
from jc.providers.http import ProviderError
from jc.time import utcnow

CONFIRMED = ("AUTO_CONFIRMED", "CONFIRMED")


def normalize_name(name: str) -> str:
    text = unicodedata.normalize("NFKC", name).casefold().strip()
    return re.sub(r"[^\w]+", " ", text, flags=re.UNICODE).strip()


def bind_team(db, provider: str, external_id: str, team_id: str, name: str, source: str):
    identity = db.scalar(
        select(TeamIdentity).where(
            TeamIdentity.provider == provider, TeamIdentity.external_team_id == external_id
        )
    )
    if identity and identity.team_id != team_id:
        raise ProviderError("IDENTITY_CONFLICT", "Provider team ID is already bound to another team")
    if identity is None:
        db.add(
            TeamIdentity(
                provider=provider, external_team_id=external_id, team_id=team_id, mapping_source=source
            )
        )
    normalized = normalize_name(name)
    alias = db.scalar(
        select(TeamAlias).where(
            TeamAlias.provider == provider,
            TeamAlias.external_team_id == external_id,
            TeamAlias.normalized_name == normalized,
        )
    )
    if alias is None:
        db.add(
            TeamAlias(
                team_id=team_id,
                provider=provider,
                external_team_id=external_id,
                alias_name=name,
                normalized_name=normalized,
                confidence=Decimal(100),
                mapping_source=source,
            )
        )
    db.flush()


def primary_team(db, external_id: str | None, name: str) -> str | None:
    if not external_id:
        return None
    identity = db.scalar(
        select(TeamIdentity).where(
            TeamIdentity.provider == "sporttery", TeamIdentity.external_team_id == external_id
        )
    )
    if identity:
        team_id = identity.team_id
    else:
        team = Team(canonical_name=name, name_zh=name, source="sporttery")
        db.add(team)
        db.flush()
        team_id = team.id
    bind_team(db, "sporttery", external_id, team_id, name, "PROVIDER_ID")
    return team_id


def primary_competition(db, external_id: str | None, name: str) -> str | None:
    if not external_id:
        return None
    identity = db.scalar(
        select(CompetitionIdentity).where(
            CompetitionIdentity.provider == "sporttery", CompetitionIdentity.external_id == external_id
        )
    )
    if identity:
        return identity.competition_id
    competition = Competition(canonical_name=name, source="sporttery")
    db.add(competition)
    db.flush()
    db.add(CompetitionIdentity(provider="sporttery", external_id=external_id, competition_id=competition.id))
    db.flush()
    return competition.id


def mapping_state(mapping: MatchMapping) -> dict:
    return {
        "match_id": mapping.match_id,
        "status": mapping.status,
        "version": mapping.version,
        "confidence": str(mapping.confidence),
        "method": mapping.match_method,
    }


def invalidate_mapping(db, mapping: MatchMapping, reason: str):
    before = mapping_state(mapping)
    mapping.status, mapping.review_required = "REVIEW", True
    mapping.match_method = "INVALIDATED"
    mapping.confirmed_at = None
    mapping.version += 1
    db.add(
        AuditLog(
            operation="MAPPING_INVALIDATED",
            entity_type="mapping",
            entity_id=mapping.id,
            before=before,
            after=mapping_state(mapping),
            reason=reason,
        )
    )


def score_match(home_id, away_id, competition_id, kickoff, match: Match) -> tuple[float, dict]:
    difference = abs((kickoff - match.kickoff_at).total_seconds()) / 60
    evidence = {
        "home": 35 if home_id and home_id == match.home_team_id else 0,
        "away": 35 if away_id and away_id == match.away_team_id else 0,
        "kickoff": 20 if difference <= 5 else 15 if difference <= 30 else 5 if difference <= 120 else 0,
        "competition": 10 if competition_id and competition_id == match.competition_id else 0,
    }
    return float(sum(evidence.values())), evidence


def resolve_mapping(db, pm: ProviderMatch, settings: Settings) -> MatchMapping:
    existing = db.scalar(select(MatchMapping).where(MatchMapping.provider_match_id == pm.id))
    if existing and (existing.status in (*CONFIRMED, "REJECTED") or existing.match_method == "INVALIDATED"):
        return existing

    def team_id(external_id):
        return (
            db.scalar(
                select(TeamIdentity.team_id).where(
                    TeamIdentity.provider == pm.provider, TeamIdentity.external_team_id == external_id
                )
            )
            if external_id
            else None
        )

    home_id, away_id = team_id(pm.home_provider_team_id), team_id(pm.away_provider_team_id)
    competition_id = db.scalar(
        select(CompetitionIdentity.competition_id).where(
            CompetitionIdentity.provider == pm.provider, CompetitionIdentity.external_id == pm.competition
        )
    )
    candidates = []
    for match in db.scalars(
        select(Match).where(
            Match.kickoff_at.between(pm.kickoff_at - timedelta(hours=4), pm.kickoff_at + timedelta(hours=4)),
            Match.mock == pm.mock,
        )
    ):
        score, evidence = score_match(home_id, away_id, competition_id, pm.kickoff_at, match)
        candidates.append({"match_id": match.id, "score": score, "evidence": evidence})
    candidates.sort(key=lambda c: (-c["score"], c["match_id"]))
    best = candidates[0] if candidates else None
    score = best["score"] if best else 0
    ambiguous = len(candidates) > 1 and score - candidates[1]["score"] < settings.mapping_ambiguity_margin
    target = best["match_id"] if best and score >= settings.mapping_review_threshold else None
    status = "UNMATCHED"
    if score >= settings.mapping_review_threshold:
        status = "REVIEW"
    if score >= settings.mapping_auto_threshold and not ambiguous and home_id and away_id:
        conflict = db.scalar(
            select(MatchMapping).where(
                MatchMapping.provider == pm.provider,
                MatchMapping.match_id == target,
                MatchMapping.status.in_(CONFIRMED),
                MatchMapping.provider_match_id != pm.id,
            )
        )
        if not conflict:
            status = "AUTO_CONFIRMED"
    mapping = existing or MatchMapping(provider_match_id=pm.id, provider=pm.provider, version=1)
    before = mapping_state(existing) if existing else None
    mapping.match_id, mapping.confidence = target, Decimal(score)
    mapping.status, mapping.match_method = status, "ENTITY_IDS_TIME_COMPETITION"
    mapping.review_required, mapping.candidates = status != "AUTO_CONFIRMED", candidates[:10]
    mapping.confirmed_at = utcnow() if status == "AUTO_CONFIRMED" else None
    db.add(mapping)
    db.flush()
    if before != mapping_state(mapping):
        db.add(
            AuditLog(
                operation="MAPPING_SCORED",
                entity_type="mapping",
                entity_id=mapping.id,
                before=before,
                after=mapping_state(mapping),
            )
        )
    return mapping


def ingest_external_match(
    db, provider: str, fetched: FetchedPayload, item: NormalizedMatch, settings: Settings
):
    pm = db.scalar(
        select(ProviderMatch).where(
            ProviderMatch.provider == provider, ProviderMatch.provider_match_id == item.external_id
        )
    )
    if pm and pm.mock != fetched.mock:
        raise ProviderError("MODE_CONFLICT", "Cannot mix mock and live data")
    if pm and fetched.collected_at < pm.collected_at:
        return resolve_mapping(db, pm, settings)
    values = {
        "provider": provider,
        "provider_match_id": item.external_id,
        "home_provider_team_id": item.home_external_id,
        "away_provider_team_id": item.away_external_id,
        "home_name": item.home_name,
        "away_name": item.away_name,
        "competition": item.competition_external_id or item.competition,
        "kickoff_at": item.kickoff_at,
        "raw_payload_id": fetched.raw_id,
        "collected_at": fetched.collected_at,
        "mock": fetched.mock,
    }
    if pm:
        changed = any(
            getattr(pm, key) != values[key]
            for key in ("home_provider_team_id", "away_provider_team_id", "kickoff_at", "competition")
        )
        if changed:
            mapping = db.scalar(select(MatchMapping).where(MatchMapping.provider_match_id == pm.id))
            if mapping and mapping.status in CONFIRMED:
                invalidate_mapping(db, mapping, "Provider identity or kickoff changed")
        for key, value in values.items():
            setattr(pm, key, value)
    else:
        pm = ProviderMatch(**values)
        db.add(pm)
    db.flush()
    return resolve_mapping(db, pm, settings)
