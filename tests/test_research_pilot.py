"""Synthetic probe summaries are never passed off as real acquisition results."""

import json
from datetime import date, timedelta

import pytest
from jc.research import pilot
from jc.research.contracts import content_hash
from jc.time import BEIJING, utcnow


@pytest.mark.parametrize(
    "start,end", [(date(2026, 9, 1), date(2026, 9, 4)), (date(2026, 9, 4), date(2026, 9, 1))]
)
def test_pilot_refuses_expansion(start, end):
    with pytest.raises(ValueError, match="1 to 3"):
        pilot.validate_window(start, end)


def test_pilot_refuses_today_and_future():
    today = utcnow().astimezone(BEIJING).date()
    for day in (today, today + timedelta(days=1)):
        with pytest.raises(ValueError, match="past dates"):
            pilot.validate_window(day, day)


@pytest.mark.parametrize("status", ["BLOCKED", "FETCHED"])
def test_http_success_is_not_pool_verification_or_replay_success(status):
    probes = [{"source": "sporttery_history", "status": status, "raw_content_hash": "synthetic-hash"}]
    report = pilot.blocked_pilot_report(date(2026, 9, 26), date(2026, 9, 28), probes)
    assert report["message"] == "Pilot blocked by target-pool evidence"
    assert report["dataset"] is None
    assert report["verified_sale_dates"] == []
    assert report["coverage"]["coverage_percent"] is None
    assert report["coverage"]["verified_targets"] == 0
    assert report["probe_response_raw_count"] == 1
    assert report["dataset_raw_count"] == 0
    assert report["entity_mapping_hash"] == content_hash(report["entity_mapping"])
    assert all(g["status"] == "BLOCKED" for g in report["gates"].values())
    assert [r["cutoff_minutes"] for r in report["runs"]] == [30, 90, 360]
    assert all(r["status"] == "BLOCKED_NOT_RUN" and r["run_id"] is None for r in report["runs"])
    assert report["suitable_for_three_seasons"] is False


def test_third_party_and_claimed_verification_cannot_open_gate_a():
    for probes, message in [
        ([{"source": "third_party"}], "actual official"),
        ([{"source": "sporttery_history", "sporttery_verification_status": "VERIFIED"}], "cannot certify"),
    ]:
        with pytest.raises(ValueError, match=message):
            pilot.blocked_pilot_report(date(2026, 9, 26), date(2026, 9, 28), probes)


def test_discovery_stays_bounded_and_missing_credentials_are_recorded(tmp_path, monkeypatch):
    monkeypatch.setenv("RESEARCH_NETWORK_ENABLED", "1")
    monkeypatch.delenv("ODDS_PROVIDER_API_KEY", raising=False)
    monkeypatch.setattr(pilot, "dotenv_values", lambda path: {})
    requests = []

    def fetch(output, source, url, **kwargs):
        requests.append((url, kwargs["params"]))
        return {"source": source, "status": "BLOCKED", "http_status": 567, "raw_content_hash": "synthetic"}

    monkeypatch.setattr(pilot, "probe_source", fetch)
    output = tmp_path / "new-attempt"
    report = pilot.discover_pilot(date(2026, 9, 26), date(2026, 9, 28), output)
    assert len(requests) == 1
    assert requests[0][1]["pageSize"] == "30"
    assert requests[0][1]["pageNo"] == "1"
    assert report["probes"][1]["reason"] == "MISSING_API_KEY"
    assert json.loads((output / "pilot-report.json").read_text("utf-8"))["status"] == "BLOCKED"
    with pytest.raises(ValueError, match="new artifact directory"):
        pilot.discover_pilot(date(2026, 9, 26), date(2026, 9, 28), output)


def test_discovery_requires_network_opt_in(tmp_path, monkeypatch):
    monkeypatch.delenv("RESEARCH_NETWORK_ENABLED", raising=False)
    with pytest.raises(RuntimeError, match="RESEARCH_NETWORK_ENABLED"):
        pilot.discover_pilot(date(2026, 9, 26), date(2026, 9, 28), tmp_path / "new-attempt")
