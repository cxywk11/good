"""Synthetic parser controls and checks of the real qualification report.

No synthetic test establishes a publication timezone or source availability.
"""

import json
from copy import deepcopy
from decimal import Decimal
from pathlib import Path

import pytest
from jc.research.official_had import HAD_AUDIT_VERSION, HAD_FIELD, inspect_official_had


def row(clock="09:55:48"):
    return {"updateDate": "2026-09-29", "updateTime": clock, "h": "4.45", "d": "3.35", "a": "1.65"}


def body(rows):
    return {"success": True, "errorCode": "0", "value": {"oddsHistory": {"matchId": 2041790, "hadList": rows}}}


def inspect(rows):
    return inspect_official_had(body(rows), source_field=HAD_FIELD, expected_match_id="2041790")


def test_18_whole_snapshots_preserve_decimal_prices_but_create_no_quotes_or_times():
    rows = [row(f"09:{minute:02}:48") for minute in range(18)]
    before = deepcopy(rows)
    report = inspect(rows)
    assert report["audit_version"] == HAD_AUDIT_VERSION
    assert report["row_count"] == report["complete_row_count"] == 18
    assert report["price_value_count"] == 54 and report["quote_record_count"] == 0
    assert report["publication_evidence_version"] is None
    assert report["wall_clock_order"] == "ASCENDING"
    assert report["first_wall_time"] == "2026-09-29 09:00:48"
    assert report["last_wall_time"] == "2026-09-29 09:17:48"
    assert report["provider"] == "sporttery" and report["bookmaker"] == "Sporttery"
    assert report["market_type"] == "SPORTTERY_HAD"
    for snapshot in report["rows"]:
        assert snapshot["prices"] == {"HOME": Decimal("4.45"), "DRAW": Decimal("3.35"), "AWAY": Decimal("1.65")}
        assert all(isinstance(price, Decimal) for price in snapshot["prices"].values())
        assert all(snapshot[key] is None for key in (
            "source_timezone_rule", "normalized_time", "UTC", "evidence_version",
            "published_at", "replay_available_at", "availability_basis",
        ))
    assert rows == before


@pytest.mark.parametrize("field", ["updateDate", "updateTime"])
@pytest.mark.parametrize("bad", [None, "", "9:55:48", "2026-9-29", "2026-02-30", "25:61:61", "09:55:48+08:00"])
def test_missing_invalid_or_offset_time_is_rejected(field, bad):
    raw = row()
    raw[field] = bad
    with pytest.raises(ValueError):
        inspect([raw])


@pytest.mark.parametrize("field", ["updateDate", "updateTime", "h", "d", "a"])
def test_missing_fields_are_not_stitched_from_sibling_snapshot(field):
    incomplete = row()
    del incomplete[field]
    with pytest.raises(ValueError):
        inspect([row("09:50:00"), incomplete, row("10:00:00")])


@pytest.mark.parametrize("bad", [1.65, None, "", "NaN", "Infinity", "1", "0", "-2"])
def test_invalid_or_float_price_is_rejected(bad):
    raw = row()
    raw["a"] = bad
    with pytest.raises(ValueError):
        inspect([raw])


@pytest.mark.parametrize("field", [
    "getFixedBonusV1.value.oddsHistory.hhadList", "getFixedBonusV1.value.oddsHistory.ttgList",
    "getFixedBonusV1.value.oddsHistory.crsList", "getFixedBonusV1.value.oddsHistory.hafuList",
    "finished_at", "getMatchHeadV1.value.matchDateTime", "kickoff_at", "lastUpdateTime",
    "updateTime", "anotherAPI.value.oddsHistory.hadList",
])
def test_scope_does_not_include_other_pools_or_timestamp_fields(field):
    with pytest.raises(ValueError, match="restricted"):
        inspect_official_had(body([row()]), source_field=field, expected_match_id="2041790")


def test_reversed_input_is_reported_not_silently_reordered():
    report = inspect([row("10:00:00"), row("09:00:00")])
    assert report["wall_clock_order"] == "UNORDERED"
    assert report["first_wall_time"] == "2026-09-29 09:00:00"
    assert report["rows"][0]["raw_updateTime"] == "10:00:00"


@pytest.mark.parametrize("change,flag", [
    ({}, "DUPLICATE_OBSERVATION"), ({"h": "4.46"}, "TIMESTAMP_CONFLICT"),
    ({"hf": "1"}, "TIMESTAMP_METADATA_CONFLICT"),
])
def test_duplicate_conflict_retains_all_evidence_and_never_selects_price(change, flag):
    report = inspect([row(), {**row(), **change}])
    assert report["row_count"] == 2 and report["duplicate_timestamp_groups"] == 1
    assert report["timestamp_conflict_groups"] == int("CONFLICT" in flag)
    assert all(snapshot["flags"] == [flag] for snapshot in report["rows"])
    assert report["quote_record_count"] == 0
    assert all(cutoff["selected_record"] is None for cutoff in report["cutoffs"].values())


def test_no_timezone_or_match_availability_inferred_from_other_fields():
    raw = row()
    raw.update(kickoff_at="2026-09-30T18:30:00+08:00", retrieved_at="2026-10-02T10:02:21+08:00",
               publication_timezone="Asia/Shanghai", evidence_version="SPORTTERY_SCHEDULE_TIME_V1")
    report = inspect([raw])
    assert report["publication_timezone"] == report["match_availability"] == "UNVERIFIED"
    assert report["match_published_at"] is report["match_replay_available_at"] is report["match_availability_basis"] is None
    assert report["prematch_row_count"] is report["post_kickoff_row_count"] is None
    assert set(report["cutoffs"]) == {"T-360", "T-90", "T-30", "T-15", "T-5", "LAST_PREMATCH"}
    assert all(cutoff["status"] == "BLOCKED_PUBLICATION_TIMEZONE" for cutoff in report["cutoffs"].values())


@pytest.mark.parametrize("clock", ["17:50:30", "18:30:00", "18:30:01"])
def test_unqualified_wall_time_including_kickoff_equality_never_enters_any_cutoff(clock):
    report = inspect([{**row(clock), "updateDate": "2026-09-30"}])
    assert report["rows"][0]["classification"] == "UNVERIFIED"
    assert all(cutoff["selected_record"] is None for cutoff in report["cutoffs"].values())


@pytest.mark.parametrize("change", [
    {"success": False}, {"errorCode": "567"}, {"value": []},
    {"value": {"oddsHistory": {"matchId": 2041789, "hadList": []}}},
    {"value": {"oddsHistory": {"matchId": 2041790, "hadList": {}}}},
])
def test_wrong_response_identity_and_schema_rejected(change):
    with pytest.raises(ValueError):
        inspect_official_had({**body([row()]), **change}, source_field=HAD_FIELD, expected_match_id="2041790")


def test_current_state_matches_real_qualification_without_changing_historical_snapshot():
    state = json.loads(Path("docs/RESEARCH_CURRENT_STATE.json").read_text("utf-8"))
    qualification = json.loads(Path("docs/official-had-qualification.json").read_text("utf-8"))
    current = json.loads(Path(state["qualification_report"]).read_text("utf-8"))
    baseline = json.loads(Path("docs/sporttery-gate-a-result.json").read_text("utf-8"))
    assert qualification["gates"] == {"A": "PASS", "B": "BLOCKED", "C": "BLOCKED"}
    assert state["gates"] == {"A": "PASS", "B": "PASS", "C": "BLOCKED"}
    assert state["verified_target_count"] == 1
    assert baseline["dataset_hash"] == qualification["old_dataset_hash_after"]
    assert state["frozen_dataset_checks"]["versions"]["2041790-official-had-v1"] == current["latest_dataset_hash"]
    assert state["official_had_dataset_version"] == current["latest_dataset_version"]
    assert qualification["new_dataset_created"] is False
    assert qualification["publication_evidence_version"] is None
    assert qualification["had"]["row_count"] == qualification["had"]["complete_row_count"] == 18
    assert qualification["had"]["price_value_count"] == 54
    assert qualification["had"]["quote_record_count"] == 0
    assert current["had"]["quote_record_count"] == state["official_had_quote_count"]
    assert qualification["old_dataset_unchanged"] and qualification["frozen_files_unchanged"]
    assert qualification["publication_timezone"] == qualification["match_availability_status"] == "UNVERIFIED"
    assert qualification["replay_status"] == "REPLAY_STILL_BLOCKED"
    assert all(item["classification"] == "HISTORICAL SNAPSHOT" for item in state["historical_snapshots"])
