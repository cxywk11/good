"""Inspect preserved responses, without guessing adapters or certifying targets."""

import json
import re
from html.parser import HTMLParser

from jc.time import parse_time

# Frontend references documented in RESEARCH_SOURCES; these are NOT observations.
EXPECTED_FROM_JS = {
    "results": [
        "errorCode",
        "value.matchResult",
        "matchId",
        "matchNum",
        "matchNumStr",
        "matchDate",
        "leagueId",
        "leagueName",
        "homeTeamId",
        "awayTeamId",
        "homeTeam",
        "awayTeam",
        "allHomeTeam",
        "allAwayTeam",
        "sectionsNo1",
        "sectionsNo999",
        "matchResultStatus",
        "goalLine",
        "h",
        "d",
        "a",
        "bettingSingle",
    ],
    "odds_history": ["updateDate", "updateTime"],
}
MATCH_FIELDS = (
    "matchId",
    "matchNum",
    "matchNumStr",
    "matchDate",
    "businessDate",
    "saleDate",
    "league",
    "leagueId",
    "leagueName",
    "homeTeamId",
    "awayTeamId",
    "homeTeam",
    "awayTeam",
    "allHomeTeam",
    "allAwayTeam",
    "kickoff",
    "kickoffTime",
    "matchTime",
    "matchDateTime",
    "HAD",
    "HHAD",
    "TTG",
    "had",
    "hhad",
    "ttg",
    "matchResult",
    "matchResultStatus",
    "sectionsNo1",
    "sectionsNo999",
    "oddsHistory",
    "updateDate",
    "updateTime",
)
BLOCK_PAGE = re.compile(
    r"captcha|waf|wzws|访问.{0,8}(验证|受限|异常|拒绝)|安全验证|人机验证|验证码|"
    r"access denied|forbidden|verify.{0,20}(human|browser)|challenge|"
    r"<title[^>]*>\s*(?:error|错误|登录|login|sign in)|type\s*=\s*['\"]?password",
    re.I,
)


def _walk(value, path="$"):
    yield path, value
    if isinstance(value, dict):
        for key in sorted(value):
            yield from _walk(value[key], f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _walk(item, f"{path}[{index}]")


class _EmbeddedJSON(HTMLParser):
    """Only inert application/json script bodies; never execute page JavaScript."""

    def __init__(self):
        super().__init__()
        self.bodies: list[str] = []
        self.active = False

    def handle_starttag(self, tag, attrs):
        if tag == "script":
            self.active = dict(attrs).get("type", "").lower() == "application/json"
            if self.active:
                self.bodies.append("")

    def handle_endtag(self, tag):
        if tag == "script":
            self.active = False

    def handle_data(self, data):
        if self.active:
            self.bodies[-1] += data


def inspect_sporttery_history_payload(body: str) -> dict:
    """Report literal fields/paths. Missing or ambiguous values stay missing.

    This is not an adapter. Even complete candidate rows require provenance,
    pool membership, timezone and identity review through the D2A contracts.
    """
    report: dict = {
        "schema_status": "INVALID_EVIDENCE",
        "evidence_decision": "BLOCKED",
        "EXPECTED_FROM_JS": EXPECTED_FROM_JS,
        "OBSERVED_IN_REAL_RESPONSE": {"top_level_fields": [], "fields": [], "matches": []},
        "match_count": 0,
        "success_structure": "UNVERIFIED",
        "sale_date_status": "SALE_DATE_UNVERIFIED",
        "timestamp_status": "TIMESTAMP_SEMANTICS_UNVERIFIED",
        "replay_available_at": None,
        "availability_basis": None,
        "verified_targets": [],
    }
    if not body.strip():
        report["reason"] = "EMPTY_RESPONSE"
        return report
    if body.lstrip().startswith("<"):
        if BLOCK_PAGE.search(body):
            report["reason"] = "ACCESS_OR_ERROR_PAGE"
            return report
        parser = _EmbeddedJSON()
        parser.feed(body)
        # HTML is retained for human review, including literal table markup.
        # No table layout or script assignment is assumed from frontend code.
        report["schema_status"] = "HTML_REVIEW_REQUIRED"
        report["evidence_decision"] = "UNVERIFIED"
        report["embedded_json"] = [inspect_sporttery_history_payload(item) for item in parser.bodies]
        report["reason"] = "HTML_REQUIRES_REVIEW"
        return report
    try:
        payload = json.loads(body)
    except ValueError:
        report["reason"] = "NOT_JSON_OR_HTML"
        return report
    if not isinstance(payload, dict) or not payload:
        report["reason"] = "NO_RESPONSE_OBJECT"
        return report
    if isinstance(payload.get("log"), dict) and "entries" in payload["log"]:
        report["reason"] = "SELECT_SINGLE_HAR_RESPONSE_BODY"
        return report
    observed = report["OBSERVED_IN_REAL_RESPONSE"]
    observed["top_level_fields"] = sorted(payload)
    observed["fields"] = [{"path": path, "type": type(item).__name__} for path, item in _walk(payload)]
    # Explicit markers are reported as observed, not a guess at an undocumented success schema.
    markers = {key: payload[key] for key in ("errorCode", "success", "code") if key in payload}
    observed["success_markers"] = markers
    if (
        ("errorCode" in payload and str(payload["errorCode"]) != "0")
        or payload.get("success") is False
        or payload.get("error")
        or payload.get("error_code")
        or str(payload.get("code")) in {"400", "401", "403", "404", "429", "500", "502", "503", "567"}
    ):
        report["reason"] = "ERROR_RESPONSE"
        return report
    if str(payload.get("errorCode")) == "0" or payload.get("success") is True:
        report["success_structure"] = "SUCCESS_MARKER_OBSERVED"
    report["schema_status"] = "JSON_OBSERVED_REVIEW_REQUIRED"
    report["evidence_decision"] = "UNVERIFIED"
    observed["timestamps"] = []
    for path, item in _walk(payload):
        if not isinstance(item, dict):
            continue
        if "updateDate" in item or "updateTime" in item:
            observed["timestamps"].append(
                {
                    "path": path,
                    "updateDate": item.get("updateDate"),
                    "updateTime": item.get("updateTime"),
                }
            )
        if "matchId" in item:
            observed["matches"].append(
                {
                    "path": path,
                    "fields": {key: item[key] for key in MATCH_FIELDS if key in item},
                    "missing": [key for key in MATCH_FIELDS if key not in item or item[key] in (None, "")],
                    "present_markets": [
                        key for key in ("HAD", "HHAD", "TTG", "had", "hhad", "ttg") if key in item
                    ],
                }
            )
    # These are candidate objects, not normalized matches or verified targets.
    report["match_count"] = len(observed["matches"])
    report["reason"] = "REVIEW_REAL_FIELDS_AND_POOL_MEMBERSHIP"
    return report


def inspect_odds_history_payload(body: str, *, requested_at=None, retrieved_at=None) -> dict:
    """The Odds API envelope time, never request time, last_update or retrieval time."""
    report: dict = {
        "schema_status": "INVALID_EVIDENCE",
        "evidence_decision": "BLOCKED",
        "timestamp": None,
        "previous_timestamp": None,
        "next_timestamp": None,
        "replay_available_at": None,
        "availability_basis": None,
        "event_count": 0,
    }
    try:
        payload = json.loads(body)
    except ValueError:
        return report
    if not isinstance(payload, dict):
        return report
    for key in ("timestamp", "previous_timestamp", "next_timestamp"):
        report[key] = payload.get(key)  # Original values are preserved, including invalid ones.
    if not isinstance(payload.get("data"), list) or not isinstance(payload.get("timestamp"), str):
        return report
    try:
        stamp = parse_time(payload["timestamp"])
        if (requested_at is not None and stamp > requested_at) or (
            retrieved_at is not None and stamp > retrieved_at
        ):
            return report
        previous, following = payload.get("previous_timestamp"), payload.get("next_timestamp")
        if previous is not None and parse_time(previous) >= stamp:
            return report
        if following is not None and parse_time(following) <= stamp:
            return report
    except (ValueError, TypeError, AttributeError):
        return report
    if any(not isinstance(event, dict) for event in payload["data"]):
        return report
    report.update(
        schema_status="HISTORICAL_ENVELOPE_OBSERVED",
        evidence_decision="PILOT_ONLY",
        replay_available_at=stamp.isoformat(),
        availability_basis="SOURCE_SNAPSHOT_AT",
        event_count=len(payload["data"]),
    )
    return report
