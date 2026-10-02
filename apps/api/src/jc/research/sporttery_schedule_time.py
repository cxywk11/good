"""Reviewed kickoff-only rule; evidence: docs/SPORTTERY_SCHEDULE_TIME_V1.md.

This is source normalization before D2A, never a change to replay-v1 or a
publication/availability rule. Source and target verification remain explicit.
"""

import re

from jc.time import BEIJING, parse_time

SPORTTERY_SCHEDULE_TIME_V1 = "SPORTTERY_SCHEDULE_TIME_V1"
MATCH_HEAD_KICKOFF_FIELD = "getMatchHeadV1.value.matchDateTime"


def normalize_sporttery_kickoff(
    raw_time: str, *, source_field: str, evidence_version: str,
) -> dict[str, str]:
    if evidence_version != SPORTTERY_SCHEDULE_TIME_V1:
        raise ValueError("Unreviewed Sporttery timezone evidence version")
    if source_field != MATCH_HEAD_KICKOFF_FIELD:
        raise ValueError("Sporttery schedule timezone rule is restricted to reviewed kickoff fields")
    if not isinstance(raw_time, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}", raw_time):
        raise ValueError("Expected naive Sporttery kickoff in YYYY-MM-DD HH:MM format")
    utc = parse_time(raw_time, source_timezone=BEIJING.key)
    return {
        "raw_time": raw_time,
        "source_field": source_field,
        "source_timezone_rule": SPORTTERY_SCHEDULE_TIME_V1,
        "source_timezone": BEIJING.key,
        "normalized_time": utc.astimezone(BEIJING).isoformat(),
        "UTC": utc.isoformat().replace("+00:00", "Z"),
        "evidence_version": evidence_version,
    }
