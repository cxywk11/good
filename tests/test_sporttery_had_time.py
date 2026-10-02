"""Real HAD excerpt acceptance and synthetic mutations; no network or live writes."""

import json
from copy import deepcopy
from dataclasses import replace
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest
from jc.analysis.market import build_market_data
from jc.analysis.research_replay import (
    AvailabilityBasis,
    NotReplayable,
    ReplayCutoffSpec,
    ResearchDataset,
    ResearchMatch,
    ResearchSource,
    build_research_feature,
)
from jc.research.contracts import (
    ResearchImport,
    ResearchRawArtifactInput,
    ResearchRecordProvenance,
    ResearchSourceInput,
    SportteryVerificationInput,
    dataset_content_hash,
    validate_import,
)
from jc.research.importer import import_research_dataset
from jc.research.official_had import HAD_FIELD
from jc.research.pilot import assess_intake_gates
from jc.research.repository import DatasetConflict, load_research_dataset, verified_sporttery_targets
from jc.research.sporttery_had_time import (
    HAD_PUBLICATION_FIELDS,
    MATCH_AVAILABILITY_FROM_OFFICIAL_HAD_V1,
    SPORTTERY_HAD_PUBLISHED_TIME_V1,
    normalize_had_publication,
    qualify_official_had,
)


@pytest.fixture
def inputs():
    def read(path):
        return json.loads(Path(path).read_text("utf-8"))

    return {
        "payload": read("tests/fixtures/sporttery_2041790_had.json")["payload"],
        "source_field": HAD_FIELD,
        "match": ResearchMatch(
            research_match_id="2041790", sporttery_match_id="2041790", competition_id="83",
            home_team_id="2053", away_team_id="2060", kickoff_at=datetime.fromisoformat("2026-09-30T18:30:00+08:00"),
            source="sporttery", source_record_id="2041790", published_at=None,
            replay_available_at=None, availability_basis=None,
        ),
        "timezone_evidence": read("docs/sporttery-had-published-time-v1.json"),
        "publication_label_evidence": read("docs/sporttery-had-publication-label-v1.json"),
        "match_availability_evidence_version": MATCH_AVAILABILITY_FROM_OFFICIAL_HAD_V1,
    }


def test_user_attestation_and_official_label_stay_separate(inputs):
    tz, label = inputs["timezone_evidence"], inputs["publication_label_evidence"]
    assert tz["evidence_type"] == "USER_ATTESTED" and tz["attested_by"] == "USER"
    assert tz["source_timezone"] == "Asia/Shanghai" and tz["utc_offset"] == "+08:00"
    assert tz["evidence_version"] == SPORTTERY_HAD_PUBLISHED_TIME_V1
    assert datetime.fromisoformat(tz["attested_at"]).utcoffset() is not None
    assert tz["official_timezone_documentation_status"] == "UNVERIFIED"
    assert label["publication_label_status"] == "VERIFIED" and label["evidence_type"] == "OFFICIAL_DOCUMENTED"
    assert label["timezone_claim"] is None
    assert tz["allowed_fields"] == label["allowed_fields"] == list(HAD_PUBLICATION_FIELDS)


@pytest.mark.parametrize("key,value", [
    ("evidence_type", "OFFICIAL_DOCUMENTED"), ("attested_by", "OFFICIAL"),
    ("source_timezone", "UTC"), ("utc_offset", "+09:00"), ("attested_at", "2026-10-02T11:00:00"),
    ("evidence_version", "SPORTTERY_SCHEDULE_TIME_V1"), ("allowed_fields", ["updateTime"]),
])
def test_invalid_or_misattributed_timezone_attestation_rejected(inputs, key, value):
    inputs["timezone_evidence"][key] = value
    with pytest.raises(ValueError):
        qualify_official_had(**inputs)


@pytest.mark.parametrize("field", [
    "hhadList", "ttgList", "crsList", "hafuList", "lastUpdateTime", "finished_at",
    "getMatchHeadV1.value.matchDateTime", "otherAPI.updateTime",
])
def test_publication_rule_rejects_every_unreviewed_scope(inputs, field):
    with pytest.raises(ValueError, match="restricted"):
        normalize_had_publication("2026-09-30", "17:50:30", source_fields=(field,),
                                  evidence=inputs["timezone_evidence"])
    inputs["source_field"] = HAD_FIELD.replace("hadList", field)
    with pytest.raises(ValueError, match="restricted"):
        qualify_official_had(**inputs)


@pytest.mark.parametrize("day,clock", [
    (None, "17:50:30"), ("2026-09-30", None), ("2026-02-30", "17:50:30"),
    ("2026-09-30", "24:00:00"), ("2026-9-30", "17:50:30"), ("2026-09-30", "17:50:30+08:00"),
])
def test_publication_rule_rejects_missing_or_invalid_wall_time(inputs, day, clock):
    with pytest.raises(ValueError):
        normalize_had_publication(day, clock, source_fields=HAD_PUBLICATION_FIELDS,
                                  evidence=inputs["timezone_evidence"])


def test_actual_18_snapshots_produce_54_decimal_quotes_and_independent_match_derivation(inputs):
    before = deepcopy(inputs["payload"])
    report, match, quotes = qualify_official_had(**inputs)
    first = datetime.fromisoformat("2026-09-29T09:55:48+08:00")
    last = datetime.fromisoformat("2026-09-30T17:50:30+08:00")
    assert report["row_count"] == report["complete_row_count"] == report["prematch_row_count"] == 18
    assert report["post_kickoff_row_count"] == 0
    assert report["quote_record_count"] == len(quotes) == 54
    assert report["first_published_at"] == first and report["last_published_at"] == last
    assert inputs["payload"] == before and inputs["match"].replay_available_at is None
    assert match.published_at == match.replay_available_at == first
    assert match.availability_basis == AvailabilityBasis.PROVIDER_PUBLISHED_AT
    derived = report["match_availability_evidence"]
    assert derived["evidence_version"] == MATCH_AVAILABILITY_FROM_OFFICIAL_HAD_V1
    assert derived["evidence_type"] == "DERIVED_FROM_VERIFIED_OFFICIAL_MARKET_PUBLICATION"
    assert derived["sporttery_match_id"] == "2041790" and not derived["match_head_publication_timestamp"]
    for snapshot in report["rows"]:
        assert snapshot["timezone_evidence_type"] == "USER_ATTESTED"
        assert snapshot["published_at"] == snapshot["replay_available_at"]
        assert snapshot["published_at"].utcoffset() is not None
        assert snapshot["availability_basis"] == AvailabilityBasis.PROVIDER_PUBLISHED_AT
        grouped = [q for q in quotes if q.record_id in snapshot["quote_record_ids"]]
        assert {q.selection: q.decimal_odds for q in grouped} == snapshot["prices"]
        assert all(isinstance(q.decimal_odds, Decimal) and q.published_at == snapshot["published_at"] for q in grouped)
        assert all((q.provider, q.bookmaker, q.market_type) == ("sporttery", "Sporttery", "SPORTTERY_HAD") for q in grouped)
    assert report["rows"][-1]["normalized_time"] == "2026-09-30T17:50:30+08:00"
    assert report["rows"][-1]["UTC"] == "2026-09-30T09:50:30Z"


@pytest.mark.parametrize("cutoff,wall,prices", [
    ("T-360", "12:12:26", ("5.65", "3.67", "1.47")),
    ("T-90", "16:48:02", ("6.00", "3.66", "1.45")),
    *[(key, "17:50:30", ("6.30", "3.45", "1.47")) for key in ("T-30", "T-15", "T-5", "LAST_PREMATCH")],
])
def test_actual_cutoffs_match_raw_acceptance(inputs, cutoff, wall, prices):
    report, _, _ = qualify_official_had(**inputs)
    selected = report["cutoffs"][cutoff]["selected_record"]
    assert selected["normalized_time"] == f"2026-09-30T{wall}+08:00"
    assert selected["prices"] == dict(zip(("HOME", "DRAW", "AWAY"), map(Decimal, prices), strict=True))


def test_equal_cutoff_is_included_but_equal_kickoff_and_post_kickoff_are_evidence_only(inputs):
    rows = inputs["payload"]["value"]["oddsHistory"]["hadList"]
    for clock in ("12:30:00", "12:30:01", "18:29:59", "18:30:00", "18:30:01"):
        rows.append({**rows[-1], "updateDate": "2026-09-30", "updateTime": clock})
    report, _, quotes = qualify_official_had(**inputs)
    assert report["post_kickoff_row_count"] == 2 and report["prematch_row_count"] == 21
    assert report["cutoffs"]["T-360"]["selected_record"]["normalized_time"] == "2026-09-30T12:30:00+08:00"
    assert report["cutoffs"]["LAST_PREMATCH"]["selected_record"]["normalized_time"] == "2026-09-30T18:29:59+08:00"
    assert len(quotes) == 63 and all(q.published_at < inputs["match"].kickoff_at for q in quotes)
    assert all(not row["quote_record_ids"] for row in report["rows"] if row["classification"] == "POST_KICKOFF")


@pytest.mark.parametrize("field,value", [("matchId", 2041789), ("homeTeamId", 2054), ("awayTeamId", 2061)])
def test_mismatched_official_identity_cannot_qualify_match_availability(inputs, field, value):
    inputs["payload"]["value"]["oddsHistory"][field] = value
    with pytest.raises(ValueError, match="identity mismatch"):
        qualify_official_had(**inputs)


@pytest.mark.parametrize("fault", ["duplicate", "conflict", "empty", "unverified_label", "missing_away"])
def test_ambiguous_incomplete_or_unverified_evidence_fails_closed(inputs, fault):
    rows = inputs["payload"]["value"]["oddsHistory"]["hadList"]
    if fault in ("duplicate", "conflict"):
        rows.append({**rows[0], **({"h": "9.99"} if fault == "conflict" else {})})
    elif fault == "empty":
        rows.clear()
    elif fault == "unverified_label":
        inputs["publication_label_evidence"]["publication_label_status"] = "UNVERIFIED"
    else:
        del rows[0]["a"]
    with pytest.raises(ValueError):
        qualify_official_had(**inputs)


def test_match_availability_requires_separate_opt_in_even_with_qualified_quotes(inputs):
    inputs["match_availability_evidence_version"] = None
    report, match, quotes = qualify_official_had(**inputs)
    assert len(quotes) == 54 and match.published_at is match.replay_available_at is match.availability_basis is None
    assert report["match_availability_evidence"] is None
    ds = ResearchDataset(dataset_id="test", dataset_version="test", replay_version="research-replay-v1",
                         matches=(match,), odds=quotes, results=(), source_manifest=(ResearchSource(
                             source_name="sporttery", source_type="SYNTHETIC_FIXTURE", retrieval_note="test only"),))
    with pytest.raises(NotReplayable, match="MATCH_UNAVAILABLE_AT_CUTOFF"):
        build_research_feature(ds, "2041790", ReplayCutoffSpec(30))


def test_real_sealed_report_current_state_and_historical_hash_agree():
    state = json.loads(Path("docs/RESEARCH_CURRENT_STATE.json").read_text("utf-8"))
    report = json.loads(Path(state["qualification_report"]).read_text("utf-8"))
    old = json.loads(Path("docs/sporttery-gate-a-result.json").read_text("utf-8"))
    evidence = json.loads(Path("docs/match-2041790-availability-from-had-v1.json").read_text("utf-8"))
    assert state["publication_timezone_status"] == report["publication_timezone_status"] == "USER_ATTESTED"
    assert state["publication_timezone"] == "Asia/Shanghai"
    assert state["publication_evidence_version"] == SPORTTERY_HAD_PUBLISHED_TIME_V1
    assert state["latest_dataset_version"] == report["latest_dataset_version"] == "2041790-official-had-v1"
    assert state["latest_dataset_hash"] == report["latest_dataset_hash"]
    assert report["old_dataset_hash"] == old["dataset_hash"] and report["old_dataset_unchanged"]
    assert report["dataset_status"] == "SEALED" and report["validate_import"] == "PASS"
    assert report["quality_summary"]["match_count"] == report["verified_target_count"] == 1
    assert report["quality_summary"]["odds_count"] == state["official_had_quote_count"] == 54
    assert report["quality_summary"]["result_count"] == state["post_kickoff_had_rows"] == 0
    assert state["prematch_had_rows"] == 18
    assert state["match_availability_evidence_version"] == evidence["evidence_version"] == MATCH_AVAILABILITY_FROM_OFFICIAL_HAD_V1
    assert report["match_availability_evidence"] == evidence
    assert state["match_replay_available_at"] == evidence["replay_available_at"] == "2026-09-29T01:55:48+00:00"
    assert state["match_availability_basis"] == "PROVIDER_PUBLISHED_AT"
    assert report["replay_status"] == "PASS" and all(row["status"] == "PASS" for row in report["replay"].values())
    assert state["gates"] == report["gates"] == {"A":"PASS","B":"BLOCKED","C":"BLOCKED"}
    assert not report["market_model_evaluable"] and not report["external_consensus_available"]
    assert report["finished_at"] is None and not report["frozen_contract_modified"]


def test_qualified_had_d2a_roundtrip_immutable_versions_and_market_isolation(inputs, sessions):
    report, match, quotes = qualify_official_had(**inputs)
    engine = sessions.kw["bind"]
    # Contract control in an isolated test DB; this declaration does not certify a real source.
    source = ResearchSourceInput(source=ResearchSource(source_name="sporttery", source_type="OFFICIAL_SPORTTERY_HISTORY",
        retrieval_note="Test-only explicit declaration"), provider_name="sporttery", license_note="test only",
        verification_status="VERIFIED", verified_at=datetime.fromisoformat(inputs["timezone_evidence"]["attested_at"]),
        verification_note="Synthetic persistence control, not a real verifier attestation")
    pool = ResearchRawArtifactInput(source_name="sporttery", artifact_type="SPORTTERY_POOL", content_type="application/json",
        retrieved_at=source.verified_at, payload={"synthetic_pool": True}, metadata={"sporttery_pool_evidence": {
            "sporttery_match_id": match.sporttery_match_id, "home_team_id": match.home_team_id,
            "away_team_id": match.away_team_id, "kickoff_at": match.kickoff_at.isoformat()}})
    raw = replace(pool, artifact_type="OFFICIAL_RAW_EXCERPT_TEST", payload=inputs["payload"], metadata={})
    base = ResearchImport(dataset=ResearchDataset(dataset_id="test-official-had", dataset_version="2041790-gate-a-v1",
        replay_version="research-replay-v1", matches=(inputs["match"],), odds=(), results=(), source_manifest=(source.source,)),
        description="Test-only version immutability", manifest={}, sources=(source,), raw_artifacts=(pool,),
        provenance=(ResearchRecordProvenance(record_type="MATCH",record_id="2041790",source_name="sporttery",
            raw_content_hash=pool.content_hash),), sporttery_verifications=(SportteryVerificationInput(
                research_match_id="2041790",status="VERIFIED",artifact_source_name="sporttery",artifact_content_hash=pool.content_hash),))
    old = import_research_dataset(engine, base)
    packet = validate_import(replace(base, dataset=replace(base.dataset, dataset_version="2041790-official-had-v1",
        matches=(match,), odds=quotes), raw_artifacts=(pool,raw), provenance=(*base.provenance, *(ResearchRecordProvenance(
            record_type="ODDS",record_id=q.record_id,source_name="sporttery",raw_content_hash=raw.content_hash) for q in quotes))))
    with pytest.raises(DatasetConflict):
        import_research_dataset(engine, replace(packet,dataset=replace(packet.dataset,dataset_version=base.dataset.dataset_version)))
    sealed = import_research_dataset(engine, packet)
    assert sealed["status"] == "SEALED" and sealed["content_hash"] == dataset_content_hash(packet)
    assert import_research_dataset(engine, base)["content_hash"] == old["content_hash"]
    assert import_research_dataset(engine, packet)["content_hash"] == sealed["content_hash"]
    with engine.connect() as conn:
        loaded = load_research_dataset(conn,packet.dataset.dataset_id,packet.dataset.dataset_version)
        assert loaded == packet.dataset and len(loaded.odds) == 54
        assert verified_sporttery_targets(conn,sealed["id"]) == ("2041790",)
    assert assess_intake_gates(packet)["gates"] == {"A":"PASS","B":"BLOCKED"}
    assert not loaded.results
    for minutes in (360,90,30,15,5):
        feature = build_research_feature(loaded,"2041790",ReplayCutoffSpec(minutes))
        selected = report["cutoffs"][f"T-{minutes}"]["selected_record"]
        assert {q["selection"]:Decimal(q["decimal_odds"]) for q in feature.market["quotes"]} == selected["prices"]
        assert all(datetime.fromisoformat(q["published_at"]) <= ReplayCutoffSpec(minutes).at(match.kickoff_at)
                   for q in feature.market["quotes"])
        market = build_market_data(feature)
        assert market["external_consensus"]["source_count"] == 0 and market["external_consensus"]["p_market"] is None
        assert market["sporttery"]["HAD"][0]["complete"] and market["sporttery_external_gap"] is None
