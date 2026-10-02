"""Scoped, user-attested HAD normalization before the unchanged D2A/replay contracts."""

import re
from dataclasses import replace
from datetime import datetime, timedelta

from jc.analysis.research_replay import AvailabilityBasis, ResearchMatch, ResearchOddsQuote
from jc.research.contracts import content_hash
from jc.research.official_had import HAD_FIELD, inspect_official_had
from jc.time import BEIJING, as_utc, parse_time

SPORTTERY_HAD_PUBLISHED_TIME_V1 = "SPORTTERY_HAD_PUBLISHED_TIME_V1"
HAD_PUBLICATION_FIELDS = (f"{HAD_FIELD}[].updateDate", f"{HAD_FIELD}[].updateTime")
MATCH_AVAILABILITY_FROM_OFFICIAL_HAD_V1 = "MATCH_AVAILABILITY_FROM_OFFICIAL_HAD_V1"


def normalize_had_publication(
    raw_update_date: str, raw_update_time: str, *, source_fields: tuple[str, ...], evidence: dict,
) -> dict:
    if source_fields != HAD_PUBLICATION_FIELDS or evidence.get("allowed_fields") != list(HAD_PUBLICATION_FIELDS):
        raise ValueError("HAD publication rule is restricted to the reviewed updateDate/updateTime pair")
    if evidence.get("evidence_version") != SPORTTERY_HAD_PUBLISHED_TIME_V1:
        raise ValueError("Unreviewed HAD publication evidence version")
    if evidence.get("evidence_type") != "USER_ATTESTED" or evidence.get("attested_by") != "USER":
        raise ValueError("This timezone evidence must remain USER_ATTESTED by USER")
    if evidence.get("source_timezone") != BEIJING.key or evidence.get("utc_offset") != "+08:00":
        raise ValueError("User attestation requires Asia/Shanghai and +08:00")
    attested_at = datetime.fromisoformat(evidence.get("attested_at", ""))
    if attested_at.tzinfo is None or attested_at.utcoffset() is None:
        raise ValueError("Aware attestation recording time required")
    if (
        not isinstance(raw_update_date, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", raw_update_date)
        or not isinstance(raw_update_time, str) or not re.fullmatch(r"[0-9]{2}:[0-9]{2}:[0-9]{2}", raw_update_time)
    ):
        raise ValueError("Full HAD updateDate and updateTime required")
    published = parse_time(raw_update_date + " " + raw_update_time, source_timezone=BEIJING.key)
    local = published.astimezone(BEIJING)
    if local.utcoffset() != timedelta(hours=8):
        raise ValueError("Date outside the attested +08:00 offset")
    return {
        "raw_updateDate": raw_update_date, "raw_updateTime": raw_update_time,
        "source_timezone": BEIJING.key, "source_timezone_rule": SPORTTERY_HAD_PUBLISHED_TIME_V1,
        "timezone_evidence_type": "USER_ATTESTED", "evidence_version": SPORTTERY_HAD_PUBLISHED_TIME_V1,
        "normalized_time": local.isoformat(), "UTC": published.isoformat().replace("+00:00", "Z"),
        "published_at": published, "replay_available_at": published,
        "availability_basis": AvailabilityBasis.PROVIDER_PUBLISHED_AT,
    }


def qualify_official_had(
    payload: dict, *, source_field: str, match: ResearchMatch, timezone_evidence: dict,
    publication_label_evidence: dict, match_availability_evidence_version: str | None = None,
) -> tuple[dict, ResearchMatch, tuple[ResearchOddsQuote, ...]]:
    """Consume explicitly reviewed evidence; never certify a domain or source.

    Match availability is a separate opt-in derivation. Post-kickoff snapshots
    remain in the audit, never in returned prematch quotes or cutoff selections.
    """
    if match_availability_evidence_version not in (None, MATCH_AVAILABILITY_FROM_OFFICIAL_HAD_V1):
        raise ValueError("Unreviewed Match availability evidence version")
    if not match.sporttery_match_id or timezone_evidence.get("sporttery_match_id") != match.sporttery_match_id:
        raise ValueError("Match identity outside the user-attested pilot scope")
    if (
        publication_label_evidence.get("evidence_version") != "SPORTTERY_HAD_PUBLICATION_LABEL_V1"
        or publication_label_evidence.get("evidence_type") != "OFFICIAL_DOCUMENTED"
        or publication_label_evidence.get("publication_label_status") != "VERIFIED"
        or publication_label_evidence.get("allowed_fields") != list(HAD_PUBLICATION_FIELDS)
    ):
        raise ValueError("Independent verified official publication label evidence required")
    audit = inspect_official_had(payload, source_field=source_field, expected_match_id=match.sporttery_match_id)
    history = payload["value"]["oddsHistory"]
    if any(
        expected is None or str(history.get(field)) != expected
        for field, expected in (("homeTeamId", match.home_team_id), ("awayTeamId", match.away_team_id))
    ):
        raise ValueError("Official HAD team identity mismatch")
    if not audit["rows"] or audit["duplicate_timestamp_groups"]:
        raise ValueError("Nonempty unambiguous HAD snapshots required; duplicates/conflicts need review")
    quotes = []
    for row in audit["rows"]:
        row.update(normalize_had_publication(
            row["raw_updateDate"], row["raw_updateTime"], source_fields=HAD_PUBLICATION_FIELDS,
            evidence=timezone_evidence,
        ))
        published = row["published_at"]
        row["classification"] = "PREMATCH" if published < match.kickoff_at else "POST_KICKOFF"
        row["quote_record_ids"] = []
        if row["classification"] == "PREMATCH":
            for selection, price in row["prices"].items():
                record_id = f"sporttery:{match.sporttery_match_id}:HAD:{published:%Y%m%dT%H%M%SZ}:{selection}"
                row["quote_record_ids"].append(record_id)
                quotes.append(ResearchOddsQuote(
                    record_id=record_id, research_match_id=match.research_match_id,
                    provider="sporttery", bookmaker="Sporttery", market_type="SPORTTERY_HAD",
                    selection=selection, line=None, decimal_odds=price,
                    published_at=published, replay_available_at=published,
                    availability_basis=AvailabilityBasis.PROVIDER_PUBLISHED_AT,
                ))
    prematch = [row for row in audit["rows"] if row["classification"] == "PREMATCH"]
    cutoffs = {}
    for key, minutes in (("T-360", 360), ("T-90", 90), ("T-30", 30), ("T-15", 15), ("T-5", 5),
                         ("LAST_PREMATCH", 0)):
        cutoff = as_utc(match.kickoff_at) - timedelta(minutes=minutes)
        eligible = [row for row in prematch if row["published_at"] <= cutoff]
        selected = max(eligible, key=lambda row: row["published_at"], default=None)
        cutoffs[key] = {
            "cutoff_at": cutoff, "status": "PASS" if selected else "NO_PREMATCH_SNAPSHOT",
            "selected_record": {field: selected[field] for field in (
                "raw_path", "normalized_time", "published_at", "prices", "quote_record_ids",
            )} if selected else None,
        }
    first = min(audit["rows"], key=lambda row: row["published_at"])
    last = max(audit["rows"], key=lambda row: row["published_at"])
    match_evidence = None
    if match_availability_evidence_version is not None:
        if not prematch:
            raise ValueError("No verified prematch HAD publication to support Match availability")
        match = replace(match, published_at=first["published_at"], replay_available_at=first["published_at"],
                        availability_basis=AvailabilityBasis.PROVIDER_PUBLISHED_AT)
        match_evidence = {
            "evidence_version": match_availability_evidence_version,
            "evidence_type": "DERIVED_FROM_VERIFIED_OFFICIAL_MARKET_PUBLICATION",
            "statement": "The match is provably available no later than the first verified provider-published "
                         "Sporttery HAD snapshot explicitly bound to the same sporttery_match_id.",
            "sporttery_match_id": match.sporttery_match_id,
            "home_team_id": match.home_team_id, "away_team_id": match.away_team_id,
            "first_snapshot_raw_path": first["raw_path"], "published_at": match.published_at,
            "replay_available_at": match.replay_available_at, "availability_basis": match.availability_basis,
            "parsed_payload_hash": content_hash(payload),
            "publication_label_evidence_hash": content_hash(publication_label_evidence),
            "timezone_evidence_hash": content_hash(timezone_evidence), "timezone_evidence_type": "USER_ATTESTED",
            "match_head_publication_timestamp": False,
        }
    return {
        **audit, "evidence_only": False, "quote_record_count": len(quotes),
        "publication_label_status": "VERIFIED", "publication_timezone": BEIJING.key,
        "publication_timezone_status": "USER_ATTESTED", "publication_evidence_version": SPORTTERY_HAD_PUBLISHED_TIME_V1,
        "availability_basis": AvailabilityBasis.PROVIDER_PUBLISHED_AT,
        "first_published_at": first["published_at"], "last_published_at": last["published_at"],
        "prematch_row_count": len(prematch), "post_kickoff_row_count": len(audit["rows"]) - len(prematch),
        "cutoffs": cutoffs, "match_availability_evidence": match_evidence,
        "match_availability": "VERIFIED" if match_evidence else "UNVERIFIED",
        "match_published_at": match.published_at, "match_replay_available_at": match.replay_available_at,
        "match_availability_basis": match.availability_basis,
    }, match, tuple(quotes)
