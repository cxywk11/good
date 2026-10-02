"""Sina single-match evidence audit. Encoding evidence is not availability evidence.

No Sina timestamp meaning has been verified, so this module cannot emit quotes
or certify a source. Raw stays outside Git; tests use synthetic responses.
"""

import json
import re
from collections import defaultdict
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlsplit

from jc.analysis.research_replay import ReplayCutoffSpec, ResearchMatch
from jc.providers.parsing import decimal_odds
from jc.research.contracts import ResearchRawArtifactInput, canonical_bytes
from jc.time import BEIJING

CUTOFFS = (360, 90, 30, 15, 5)


def _id(value: object) -> str:
    if type(value) not in (str, int) or not re.fullmatch(r"[1-9][0-9]*", str(value)):
        raise ValueError("Stable numeric identity required")
    return str(value)


def _unix_seconds(value: object) -> datetime:
    if type(value) not in (str, int) or not re.fullmatch(r"[0-9]+", str(value)):
        raise ValueError("Unix seconds must be an integer or digit string")
    try:
        return datetime.fromtimestamp(int(str(value)), UTC)
    except (ValueError, OverflowError, OSError) as exc:
        raise ValueError("Invalid Unix seconds; milliseconds are not accepted") from exc


def _response(raw: ResearchRawArtifactInput, endpoint: str, **binding: str) -> list[dict]:
    parts = urlsplit(raw.external_ref or "")
    query = parse_qs(parts.query)
    if (parts.scheme, parts.hostname, parts.path) != (
        "https", "alpha.lottery.sina.com.cn", "/gateway/index/entry"
    ) or any(query.get(key) != [value] for key, value in {"cat1": endpoint, **binding}.items()):
        raise ValueError("Preserved request must bind endpoint, match and bookmaker")
    if raw.metadata.get("http_status") != 200 or raw.metadata.get("retention") != "UNCHANGED":
        raise ValueError("Unchanged successful Raw required")
    payload = json.loads(raw.payload) if isinstance(raw.payload, str) else raw.payload
    result = payload.get("result") if isinstance(payload, dict) else None
    if (not isinstance(result, dict) or not isinstance(result.get("status"), dict)
            or type(result["status"].get("code")) is not int or result["status"]["code"] != 0):
        raise ValueError("Successful Sina schema required")
    rows = result.get("data")
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise ValueError("Sina data must contain objects")
    return rows


def map_sina_target(
    raw: ResearchRawArtifactInput, *, match: ResearchMatch, match_no: str,
    home: str, away: str, score: tuple[str, str],
) -> dict:
    """Cross-check an existing official target; never certify Gate A from Sina."""
    rows = _response(raw, "jczqMatches", date=match.kickoff_at.astimezone(BEIJING).date().isoformat())
    targets = [row for row in rows if str(row.get("tiCaiId")) == match.sporttery_match_id]
    if len(targets) != 1:
        raise ValueError("Exactly one tiCaiId mapping required")
    row = targets[0]
    mid = _id(row.get("matchId"))
    if sum(str(item.get("matchId")) == mid for item in rows) != 1:
        raise ValueError("Duplicate external match identity")
    expected = {"matchNo": match_no, "team1": home, "team2": away,
                "score1": score[0], "score2": score[1]}
    if any(row.get(key) != value for key, value in expected.items()):
        raise ValueError("External match number, ordered teams or score mismatch")
    if (_unix_seconds(row.get("matchTime")) != match.kickoff_at
            or row.get("matchTimeFormat") != match.kickoff_at.astimezone(BEIJING).strftime("%Y-%m-%d %H:%M:%S")):
        raise ValueError("External kickoff mismatch")
    return {"external_match_id": mid, "sporttery_match_id": match.sporttery_match_id,
            "identity_status": "VALID", "role": "EXTERNAL_MAPPING_ONLY"}


def inspect_sina_1x2(
    match_list: ResearchRawArtifactInput, overview: ResearchRawArtifactInput,
    history: ResearchRawArtifactInput, *, match: ResearchMatch, match_no: str,
    home: str, away: str, score: tuple[str, str], company_id: str, offer_id: str,
) -> dict:
    mapping = map_sina_target(match_list, match=match, match_no=match_no, home=home, away=away, score=score)
    mid, company, offer = mapping["external_match_id"], _id(company_id), _id(offer_id)
    companies = _response(overview, "footballMatchOddsEuro", matchId=mid)
    selected = [row for row in companies if str(row.get("companyId")) == company
                and str(row.get("offerId")) == offer]
    if len(selected) != 1:
        raise ValueError("Exactly one stable bookmaker binding required")
    # The observed official and handicap rows are not external 1X2 bookmakers.
    if company in {"19", "9999"} or "官方" in str(selected[0].get("companyName", "")):
        raise ValueError("Official mirror is not an external bookmaker")
    raw_rows = _response(history, "footballMatchOddsEuroChange", matchId=mid,
                         companyId=company, offerId=offer)
    rows: list[dict] = []
    groups: dict[datetime, list[int]] = defaultdict(list)
    for index, raw in enumerate(raw_rows):
        if any(not isinstance(raw.get(key), str) for key in ("o1", "o2", "o3")):
            raise ValueError("Complete same-row 1X2 Decimal strings required; no cross-time stitching")
        stamp = _unix_seconds(raw.get("oddsTime"))
        if stamp > history.retrieved_at:
            raise ValueError("Raw timestamp is after retrieval")
        groups[stamp].append(index)
        rows.append({
            "raw_index": index, "raw_oddsTime": raw["oddsTime"],
            "raw_timestamp_type": type(raw["oddsTime"]).__name__, "unit": "UNIX_SECONDS",
            "UTC": stamp.isoformat(), "Asia_Shanghai": stamp.astimezone(BEIJING).isoformat(),
            "browser_display_Asia_Shanghai": stamp.astimezone(BEIJING).strftime("%m-%d %H:%M"),
            "prices": {selection: decimal_odds(raw[key]) for key, selection in
                       (("o1", "HOME"), ("o2", "DRAW"), ("o3", "AWAY"))},
            "classification": "PREMATCH_CANDIDATE" if stamp < match.kickoff_at else "POST_KICKOFF",
            "flags": [], "replay_available_at": None, "availability_basis": None,
        })
    for indexes in groups.values():
        if len(indexes) > 1:
            flag = ("DUPLICATE_TIMESTAMP" if len({canonical_bytes(raw_rows[i]) for i in indexes}) == 1
                    else "CONFLICTING_TIMESTAMP")
            for index in indexes:
                rows[index]["flags"].append(flag)
    return {
        **mapping, "provider": "sina", "bookmaker": f"sina:{company}:{offer}",
        "companyId": company, "offerId": offer, "market_type": "1X2",
        "row_count": len(rows), "complete_row_count": len(rows),
        "prematch_row_count": sum(row["classification"] == "PREMATCH_CANDIDATE" for row in rows),
        "post_kickoff_row_count": sum(row["classification"] == "POST_KICKOFF" for row in rows),
        "duplicate_timestamp_groups": sum(len(indexes) > 1 for indexes in groups.values()),
        "conflicting_timestamp_groups": sum("CONFLICTING_TIMESTAMP" in rows[indexes[0]]["flags"]
                                            for indexes in groups.values()),
        "rows": rows, "timestamp_source_field": "$.result.data[*].oddsTime",
        "timestamp_semantics": "UNKNOWN", "time_status": "SINA_TIME_SEMANTICS_UNVERIFIED",
        "replay_available_at": None, "availability_basis": None,
        "verification_status": "UNVERIFIED", "quote_record_count": 0,
        "cutoffs": {f"T-{minutes}": {"cutoff": ReplayCutoffSpec(minutes).at(match.kickoff_at).isoformat(),
                                    "status": "BLOCKED", "selected_record": None,
                                    "reason": "SINA_TIME_SEMANTICS_UNVERIFIED"}
                    for minutes in CUTOFFS},
    }
