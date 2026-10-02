"""Evidence-only HAD audit: no publication timezone or Match availability attested.

The official frontend proves the publication label, not its timezone. There is
no accepted publication normalization rule; do not reuse the kickoff rule.
"""

import re
from collections import defaultdict
from datetime import datetime

from jc.providers.parsing import decimal_odds
from jc.research.contracts import canonical_bytes

HAD_AUDIT_VERSION = "SPORTTERY_HAD_EVIDENCE_AUDIT_V1"
HAD_FIELD = "getFixedBonusV1.value.oddsHistory.hadList"


def inspect_official_had(payload: dict, *, source_field: str, expected_match_id: str) -> dict:
    """Validate whole snapshots; retain duplicates/conflicts without making quotes.

    Naive datetime is used only to validate/order wall-clock strings. It is never
    compared with kickoff or converted to an instant, publication time or cutoff.
    """
    if source_field != HAD_FIELD:
        raise ValueError("HAD audit is restricted to getFixedBonusV1.value.oddsHistory.hadList")
    if not isinstance(expected_match_id, str) or not re.fullmatch(r"[1-9][0-9]*", expected_match_id):
        raise ValueError("Explicit Sporttery match identity required")
    if not isinstance(payload, dict) or payload.get("success") is not True or str(payload.get("errorCode")) != "0":
        raise ValueError("Successful official response body required")
    value = payload.get("value")
    history = value.get("oddsHistory") if isinstance(value, dict) else None
    if not isinstance(history, dict) or str(history.get("matchId")) != expected_match_id:
        raise ValueError("Official HAD match identity mismatch")
    raw_rows = history.get("hadList")
    if not isinstance(raw_rows, list) or not all(isinstance(row, dict) for row in raw_rows):
        raise ValueError("HAD snapshot list required")
    rows: list[dict] = []
    groups: dict[str, list[int]] = defaultdict(list)
    for index, raw in enumerate(raw_rows):
        day, clock = raw.get("updateDate"), raw.get("updateTime")
        if (
            not isinstance(day, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", day)
            or not isinstance(clock, str) or not re.fullmatch(r"[0-9]{2}:[0-9]{2}:[0-9]{2}", clock)
        ):
            raise ValueError("Full HAD updateDate and updateTime required")
        wall = day + " " + clock
        datetime.strptime(wall, "%Y-%m-%d %H:%M:%S")
        if any(not isinstance(raw.get(key), str) for key in ("h", "d", "a")) or raw.get("goalLine") not in (None, ""):
            raise ValueError("One HAD snapshot requires h/d/a Decimal strings and no handicap")
        prices = {selection: decimal_odds(raw[key]) for key, selection in
                  (("h", "HOME"), ("d", "DRAW"), ("a", "AWAY"))}
        groups[wall].append(index)
        rows.append({
            "raw_path": f"$.value.oddsHistory.hadList[{index}]",
            "raw_updateDate": day, "raw_updateTime": clock, "wall_time": wall,
            "raw_prices": {key: raw[key] for key in ("h", "d", "a")}, "prices": prices,
            "complete": True, "flags": [], "classification": "UNVERIFIED",
            "source_timezone_rule": None, "normalized_time": None, "UTC": None, "evidence_version": None,
            "published_at": None, "replay_available_at": None, "availability_basis": None,
        })
    for indexes in groups.values():
        if len(indexes) < 2:
            continue
        if len({tuple(rows[i]["prices"].items()) for i in indexes}) > 1:
            flag = "TIMESTAMP_CONFLICT"
        elif len({canonical_bytes(raw_rows[i]) for i in indexes}) > 1:
            flag = "TIMESTAMP_METADATA_CONFLICT"
        else:
            flag = "DUPLICATE_OBSERVATION"
        for i in indexes:
            rows[i]["flags"].append(flag)
    times = [row["wall_time"] for row in rows]
    return {
        "audit_version": HAD_AUDIT_VERSION, "source_field": source_field,
        "sporttery_match_id": expected_match_id, "provider": "sporttery", "bookmaker": "Sporttery",
        "market_type": "SPORTTERY_HAD", "evidence_only": True,
        "row_count": len(rows), "complete_row_count": len(rows),
        "price_value_count": sum(len(row["prices"]) for row in rows), "quote_record_count": 0,
        "rows": rows, "wall_clock_order": "ASCENDING" if times == sorted(times) else "UNORDERED",
        "first_wall_time": min(times, default=None), "last_wall_time": max(times, default=None),
        "duplicate_timestamp_groups": sum(len(indexes) > 1 for indexes in groups.values()),
        "timestamp_conflict_groups": sum(
            any("CONFLICT" in flag for flag in rows[indexes[0]]["flags"]) for indexes in groups.values()
        ),
        "publication_timezone": "UNVERIFIED", "publication_evidence_version": None,
        "published_at": None, "replay_available_at": None, "availability_basis": None,
        "post_kickoff_row_count": None, "prematch_row_count": None,
        "cutoffs": {key: {"status": "BLOCKED_PUBLICATION_TIMEZONE", "selected_record": None}
                    for key in ("T-360", "T-90", "T-30", "T-15", "T-5", "LAST_PREMATCH")},
        "match_availability": "UNVERIFIED", "match_replay_available_at": None,
        "match_published_at": None, "match_availability_basis": None,
    }
