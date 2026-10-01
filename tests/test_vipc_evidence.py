"""Synthetic, offline controls for the bounded VIPC inspector; no real-data claims."""

import json
from copy import deepcopy
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
from jc.research.providers.probe import probe_source
from jc.research.vipc_evidence import BASE_URL, inspect_saved_probes, inspect_vipc_history, report_section
from jc.time import BEIJING, parse_time


def row(time="2026-09-30 13:27:00", odds=None):
    return {
        "updateTime": time,
        "odds": odds or ["1.28", "4.15", "8.50"],
        "returnRatio": "87.73%",
        "oddsTrend": [0, 0, 0],
    }


def inputs(rows):
    return (
        {
            "type": "football",
            "model": {"matchId": "498257749", "issue": "synthetic-issue", "matchTime": "2026-09-30 14:00:00"},
        },
        {"odds": [{"companyId": "432", "companyName": "synthetic display"}]},
        {"companyId": "432", "companyName": "synthetic display", "issue": "synthetic-issue", "list": rows},
    )


@pytest.mark.parametrize("field", ["matchId", "companyId", "issue", "matchTime"])
def test_identity_and_kickoff_cannot_drift(field):
    detail, companies, history = inputs([row()])
    if field == "companyId":
        history[field] = "other"
    else:
        detail["model"][field] = "other"
    with pytest.raises(ValueError, match="identity or kickoff"):
        inspect_vipc_history(detail, companies, history)


def test_company_list_id_required_and_display_name_is_not_identity():
    args = inputs([row()])
    before = inspect_vipc_history(*args)
    args[1]["odds"][0]["companyName"] = "changed label"
    args[2]["companyName"] = "changed label"
    after = inspect_vipc_history(*args)
    assert before["bookmaker_identity"] == after["bookmaker_identity"] == "vipc:432"
    assert after["offer_id"] is after["company_code"] is None
    args[1]["odds"][0]["companyId"] = ""
    with pytest.raises(ValueError):
        inspect_vipc_history(*args)


@pytest.mark.parametrize("key", ["offerId", "companyCode"])
def test_missing_offer_id_is_not_invented_and_new_dimension_requires_review(key):
    args = inputs([row()])
    args[2][key] = "unreviewed"
    with pytest.raises(ValueError, match="Unreviewed"):
        inspect_vipc_history(*args)


def test_field_mapping_decimal_return_rate_and_ui_raw_agreement():
    report = inspect_vipc_history(*inputs([row()]))
    item = report["rows"][0]
    assert item["odds"] == {"HOME": Decimal("1.28"), "DRAW": Decimal("4.15"), "AWAY": Decimal("8.50")}
    assert all(isinstance(v, Decimal) for v in item["odds"].values())
    assert item["raw_time_field"] == "updateTime"
    assert item["raw_time_value"] == "2026-09-30 13:27:00"
    assert item["parsed_utc"] == "2026-09-30T05:27:00+00:00"
    assert (
        item["ui_time"]
        == "09-30 13:27"
        == parse_time(item["parsed_utc"]).astimezone(BEIJING).strftime("%m-%d %H:%M")
    )
    assert report["time_unit"] == "WALL_CLOCK_STRING_SECONDS"
    assert report["timezone"] is None
    assert report["candidate_timezone"] == "Asia/Shanghai"
    assert item["return_rate_matches"] is True
    assert abs(item["return_rate"] - Decimal(".8773")) < Decimal(".00005")
    # The symmetric return-rate formula verifies values, not their HOME/AWAY order.
    swapped = row(odds=["8.50", "4.15", "1.28"])
    swapped_rate = inspect_vipc_history(*inputs([swapped]))["rows"][0]["return_rate"]
    assert swapped_rate.quantize(Decimal(".0001")) == item["return_rate"].quantize(Decimal(".0001"))


@pytest.mark.parametrize("bad", ["NaN", "sNaN", "Infinity", "-Infinity", "1", "0", "-2", "bad", 1.28, None])
def test_invalid_odds_never_become_candidates(bad):
    report = inspect_vipc_history(*inputs([row(odds=[bad, "4.15", "8.50"])]))
    assert "INVALID_1X2" in report["rows"][0]["errors"]
    assert report["candidate_T30"]["value"] is None


@pytest.mark.parametrize(
    "bad", [None, "09-30 13:27", 1790746020, "2026-02-30 13:27:00", "2026-09-30T13:27:00Z"]
)
def test_no_guessing_ui_year_units_or_changed_time_schema(bad):
    report = inspect_vipc_history(*inputs([row(time=bad)]))
    assert report["invalid_time_rows"] == 1
    assert report["rows"][0]["parsed_utc"] is None
    assert report["candidate_T30"]["value"] is None


def test_strict_kickoff_boundary_and_three_candidates():
    times = ["07:59:00", "12:28:00", "13:27:00", "13:59:59", "14:00:00", "15:51:00"]
    report = inspect_vipc_history(*inputs([row("2026-09-30 " + t) for t in times]))
    assert report["prematch_rows"] == 4 and report["post_kickoff_rows"] == 2
    assert [r["classification"] for r in report["rows"][-3:]] == [
        "PREMATCH",
        "INPLAY_OR_POST_KICKOFF",
        "INPLAY_OR_POST_KICKOFF",
    ]
    for minutes, time in [(30, "13:27:00"), (90, "12:28:00"), (360, "07:59:00")]:
        value = report[f"candidate_T{minutes}"]["value"]
        assert value["raw_time_value"] == "2026-09-30 " + time
        assert parse_time(value["parsed_utc"]) <= parse_time(value["cutoff_utc"])
        assert value["replay_available_at"] is None
    after_only = inspect_vipc_history(*inputs([row("2026-09-30 14:00:00"), row("2026-09-30 15:51:00")]))
    assert all(after_only[f"candidate_T{m}"]["value"] is None for m in (30, 90, 360))


def test_equal_prices_different_times_and_identical_duplicates_are_preserved():
    a, b = row(), row("2026-09-30 13:25:00")
    report = inspect_vipc_history(*inputs([a, b, deepcopy(a)]))
    assert len(report["rows"]) == report["total_rows"] == 3
    assert report["rows"][0]["flags"] == report["rows"][2]["flags"] == ["duplicate_observation_candidate"]
    assert report["rows"][1]["flags"] == []
    assert report["candidate_T30"]["value"]["observation_indexes"] == [0, 2]


def test_timestamp_conflict_does_not_pick_a_price_or_silently_fall_back():
    report = inspect_vipc_history(
        *inputs([row(), row(odds=["1.30", "4.15", "8.50"]), row("2026-09-30 12:28:00")])
    )
    assert report["timestamp_conflict_groups"] == 1
    assert report["candidate_T30"] == {"value": None, "status": "TIMESTAMP_CONFLICT"}
    assert report["candidate_T90"]["value"] is not None


def test_return_rate_mismatch_does_not_fill_or_modify_prices():
    value = row()
    value["returnRatio"] = "99%"
    report = inspect_vipc_history(*inputs([value]))
    assert report["rows"][0]["odds"]["HOME"] == Decimal("1.28")
    assert report["return_rate_pass_rows"] == 0
    assert report["candidate_T30"]["value"] is None


def test_candidates_never_open_official_or_availability_gates():
    report = inspect_vipc_history(*inputs([row()]))
    assert report["candidate_T30"]["value"] is not None
    assert report["verified_targets"] == []
    assert report["official_mapping_candidate"] == "synthetic-issue"
    assert report["gate_a"] == report["gate_b"] == "BLOCKED"
    assert report["availability_status"] == "AVAILABILITY_SEMANTICS_UNVERIFIED"
    assert report["replay_available_at"] is report["availability_basis"] is None
    assert report["source_decision"] == "UNVERIFIED"
    assert "candidate_T30" in report_section(report)


@pytest.mark.parametrize("minutes,time", [(30, "13:30:00"), (90, "12:30:00"), (360, "08:00:00")])
def test_cutoff_is_inclusive(minutes, time):
    report = inspect_vipc_history(*inputs([row("2026-09-30 " + time)]))
    assert report[f"candidate_T{minutes}"]["value"]["raw_time_value"].endswith(time)


def test_offline_reader_requires_saved_matching_raw_and_detects_tampering(tmp_path):
    folder = tmp_path / "artifacts" / "vipc"
    summaries = []
    urls = [BASE_URL, BASE_URL + "/odds/euro", BASE_URL + "/odds/euro/432"]
    for i, (url, payload) in enumerate(zip(urls, inputs([row()]), strict=True)):
        body = json.dumps(payload)
        summaries.append(
            probe_source(
                folder,
                f"synthetic_vipc_{i}",
                url,
                transport=httpx.MockTransport(lambda request, body=body: httpx.Response(200, text=body)),
            )
        )
    report = inspect_saved_probes(folder, tmp_path)
    assert report["total_rows"] == 1
    assert len(report["evidence"]) == 3
    path = Path(summaries[-1]["raw_path"])
    stored = json.loads(path.read_text("utf-8"))
    stored["raw"]["payload"] = "{}"
    path.write_text(json.dumps(stored), "utf-8")
    with pytest.raises(ValueError, match="disagrees"):
        inspect_saved_probes(folder, tmp_path)
