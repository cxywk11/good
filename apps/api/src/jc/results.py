"""Store validated post-match contracts through existing canonical entity bindings."""

from sqlalchemy import select

from jc.entities import CONFIRMED
from jc.models import (
    Match,
    MatchMapping,
    MatchResult,
    MatchVersion,
    ProviderMatch,
    RawPayload,
    TeamIdentity,
    TeamMatchStats,
)
from jc.odds import fingerprint, insert_ignoring_duplicate
from jc.providers.contracts import FetchedPayload, NormalizedBatch, NormalizedTeamStats
from jc.providers.http import ProviderError
from jc.time import parse_time, utcnow


def store_post_match(db, provider, fetched: FetchedPayload, batch: NormalizedBatch) -> int:
    if not batch.results and not batch.team_stats:
        return 0
    raw = db.get(RawPayload, fetched.raw_id)
    if (
        not raw
        or raw.provider != provider.name
        or raw.mock != fetched.mock
        or raw.collected_at != fetched.collected_at
    ):
        raise ProviderError("RAW_MISMATCH", "Post-match facts require matching persisted Raw")
    targets = {}
    if provider.is_primary:
        if provider.name != "sporttery":
            raise ProviderError("PRIMARY_ONLY", "Only sporttery can resolve primary IDs")
        for match in db.scalars(select(Match)):
            targets[match.sporttery_match_id] = (match, None)
    else:
        for pm, mapping, match in db.execute(
            select(ProviderMatch, MatchMapping, Match)
            .join(MatchMapping, MatchMapping.provider_match_id == ProviderMatch.id)
            .join(Match, Match.id == MatchMapping.match_id)
            .where(ProviderMatch.provider == provider.name, MatchMapping.status.in_(CONFIRMED))
        ):
            targets[pm.provider_match_id] = (match, mapping)
    count = 0
    for model, items in ((MatchResult, batch.results), (TeamMatchStats, batch.team_stats)):
        seen = set()
        for item in items:
            target = targets.get(item.external_match_id)
            if not target:
                continue  # Unresolved events remain in Raw, never expand the primary pool.
            match, mapping = target
            if match.mock != fetched.mock:
                raise ProviderError("MODE_CONFLICT", "Cannot mix fixture and live facts")
            version = db.scalar(
                select(MatchVersion)
                .where(MatchVersion.match_id == match.id)
                .order_by(
                    MatchVersion.collected_at.desc(), MatchVersion.created_at.desc(), MatchVersion.id.desc()
                )
                .limit(1)
            )
            if not version:
                raise ProviderError("MISSING_MATCH_VERSION", "Post-match facts require a match version")
            if not parse_time(version.state["kickoff_at"]) < item.finished_at <= fetched.collected_at:
                raise ProviderError(
                    "INVALID_FINISH_TIME", "Final facts must be observed after the match finished"
                )
            values = item.model_dump(exclude={"external_match_id", "external_team_id", "period", "status"})
            key = (match.id, None)
            if model is TeamMatchStats:
                assert isinstance(item, NormalizedTeamStats)
                team_id = db.scalar(
                    select(TeamIdentity.team_id).where(
                        TeamIdentity.provider == provider.name,
                        TeamIdentity.external_team_id == item.external_team_id,
                    )
                )
                if not team_id or team_id not in {
                    version.state.get("home_team_id"),
                    version.state.get("away_team_id"),
                }:
                    raise ProviderError("UNRESOLVED_TEAM", "Stats require an explicit participant team ID")
                values["team_id"] = team_id
                key = (match.id, team_id)
            if key in seen:
                raise ProviderError("DUPLICATE_CONFLICT", "Duplicate final fact in one payload")
            seen.add(key)
            values.update(
                match_id=match.id,
                match_version_id=version.id,
                source=provider.name,
                raw_payload_id=raw.id,
                observed_at=fetched.collected_at,
                mock=fetched.mock,
                mapping_id=mapping.id if mapping else None,
                mapping_version=mapping.version if mapping else None,
                created_at=utcnow(),
                dedup_key=fingerprint(
                    [
                        match.id,
                        key[1],
                        provider.name,
                        raw.id,
                        version.id,
                        mapping.id if mapping else None,
                        mapping.version if mapping else None,
                    ]
                ),
            )
            insert_ignoring_duplicate(db, model, [values])
            count += 1
    return count
