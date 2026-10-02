"""Kickoff normalization boundaries; no synthetic response certifies a source."""

import json
from pathlib import Path

import pytest
from jc.research.contracts import content_hash
from jc.research.sporttery_schedule_time import (
    MATCH_HEAD_KICKOFF_FIELD,
    SPORTTERY_SCHEDULE_TIME_V1,
    normalize_sporttery_kickoff,
)


def test_reviewed_source_timezone_evidence_version():
    evidence = json.loads(Path("docs/sporttery-schedule-time-v1.json").read_text("utf-8"))
    assert evidence["evidence_version"] == SPORTTERY_SCHEDULE_TIME_V1
    assert evidence["allowed_fields"] == [MATCH_HEAD_KICKOFF_FIELD]
    assert evidence["source_timezone"] == "Asia/Shanghai"
    assert evidence["status"] == "VERIFIED"
    assert len(evidence["same_page_evidence"]) == 2
    assert all(len(row["response_sha256"]) == 64 for row in evidence["same_page_evidence"])


def test_naive_match_head_kickoff_normalizes_with_audit_record():
    normalized = normalize_sporttery_kickoff(
        "2026-09-30 18:30", source_field=MATCH_HEAD_KICKOFF_FIELD,
        evidence_version=SPORTTERY_SCHEDULE_TIME_V1,
    )
    assert normalized == {
        "raw_time": "2026-09-30 18:30",
        "source_field": MATCH_HEAD_KICKOFF_FIELD,
        "source_timezone_rule": SPORTTERY_SCHEDULE_TIME_V1,
        "source_timezone": "Asia/Shanghai",
        "normalized_time": "2026-09-30T18:30:00+08:00",
        "UTC": "2026-09-30T10:30:00Z",
        "evidence_version": SPORTTERY_SCHEDULE_TIME_V1,
    }


@pytest.mark.parametrize("field", [
    "updateTime", "updateDate", "lastUpdateTime", "finished_at", "matchDateTime",
    "getFixedBonusV1.value.oddsHistory.hadList.updateTime",
    "getMatchHeadV1.value.finished_at", "getUniformMatchResultV1.value.matchDateTime",
])
def test_kickoff_rule_rejects_publication_finish_and_unreviewed_fields(field):
    with pytest.raises(ValueError, match="restricted"):
        normalize_sporttery_kickoff(
            "2026-09-30 18:30", source_field=field, evidence_version=SPORTTERY_SCHEDULE_TIME_V1,
        )


@pytest.mark.parametrize("raw", [
    "2026-09-30", "18:30", "2026-09-30T18:30:00+08:00", "2026-09-30 18:30Z",
    "2026-02-30 18:30", "2026-09-30 24:00", "2026-9-30 18:30", "2026-09-30 18:30:00",
])
def test_kickoff_rule_does_not_reinterpret_invalid_or_other_timestamp_formats(raw):
    with pytest.raises(ValueError):
        normalize_sporttery_kickoff(
            raw, source_field=MATCH_HEAD_KICKOFF_FIELD, evidence_version=SPORTTERY_SCHEDULE_TIME_V1,
        )


def test_unreviewed_rule_version_rejected():
    with pytest.raises(ValueError, match="version"):
        normalize_sporttery_kickoff(
            "2026-09-30 18:30", source_field=MATCH_HEAD_KICKOFF_FIELD,
            evidence_version="SPORTTERY_SCHEDULE_TIME_V2",
        )


def test_real_pilot_attestation_and_saved_gate_boundaries():
    attestation = json.loads(Path("docs/sporttery-2041790-gate-a-attestation.json").read_text("utf-8"))
    report = json.loads(Path("docs/sporttery-gate-a-result.json").read_text("utf-8"))
    assert report["source_attestation_hash"] == content_hash(attestation)
    assert attestation["source_type"] == "OFFICIAL_SPORTTERY_HISTORY"
    assert attestation["provider_name"] == "sporttery"
    assert attestation["verification_status"] == report["source_verification"] == "VERIFIED"
    assert len(attestation["raw_evidence"]) == 3
    assert attestation["timezone_evidence_version"] == SPORTTERY_SCHEDULE_TIME_V1
    assert report["sporttery_pool_metadata"] == attestation["sporttery_pool_evidence"] == {
        "sporttery_match_id": "2041790", "home_team_id": "2053", "away_team_id": "2060",
        "kickoff_at": "2026-09-30T10:30:00+00:00",
    }
    assert report["verified_targets"] == ["2041790"] and report["validate_import"] == "PASS"
    assert report["dataset_created"] and report["dataset_sealed"]
    assert report["dataset_key"] == "jc-football-official-pilot"
    assert report["gates"] == {"A": "PASS", "C": "BLOCKED", "B": "BLOCKED"}
    assert report["quality_summary"]["odds_count"] == report["quality_summary"]["result_count"] == 0
    assert report["had"] == {"rows": 18, "complete": 18, "evidence_only": True, "imported": 0}
    assert report["publication_timezone"] == "UNVERIFIED"
    assert report["published_at"] is report["replay_available_at"] is report["availability_basis"] is None
    assert report["finished_at"] is None
    assert set(report["cutoffs"]) == {"T-360", "T-90", "T-30", "T-15", "T-5", "LAST_PREMATCH"}
    assert all(row["status"] == "BLOCKED" for row in report["cutoffs"].values())
    assert report["frozen_contract_modified"] is False
