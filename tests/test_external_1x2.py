"""Synthetic external evidence and integration; no new real-provider fixtures."""

import json
from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlencode

import pytest
from jc.analysis.market import build_market_data
from jc.analysis.research_replay import (
    AvailabilityBasis,
    ReplayCutoffSpec,
    ResearchDataset,
    ResearchMatch,
    ResearchOddsQuote,
    ResearchSource,
    build_research_feature,
)
from jc.research.contracts import (
    ResearchImport,
    ResearchRawArtifactInput,
    ResearchRecordProvenance,
    ResearchSourceInput,
    SportteryVerificationInput,
    content_hash,
    dataset_content_hash,
    validate_import,
)
from jc.research.importer import import_research_dataset
from jc.research.pilot import assess_intake_gates
from jc.research.repository import DatasetConflict, load_research_dataset, verified_sporttery_targets
from jc.research.sina_1x2 import CUTOFFS, inspect_sina_1x2, map_sina_target
from jc.time import parse_time

KICKOFF = datetime(2024, 6, 1, 12, tzinfo=UTC)
MATCH = ResearchMatch(
    research_match_id="test-target", sporttery_match_id="123", competition_id="test-league",
    home_team_id="test-home", away_team_id="test-away", kickoff_at=KICKOFF, source="sporttery",
    source_record_id="123", replay_available_at=KICKOFF-timedelta(days=3),
    availability_basis=AvailabilityBasis.SOURCE_SNAPSHOT_AT,
)
IDENTITY = dict(match=MATCH, match_no="test-002", home="Test Home", away="Test Away", score=("1", "1"))


def raw(endpoint, rows, **binding):
    return ResearchRawArtifactInput(
        source_name="sina", artifact_type="SYNTHETIC_FIXTURE", retrieved_at=KICKOFF+timedelta(days=1),
        content_type="application/json", payload={"result": {"status": {"code": 0}, "data": rows}},
        external_ref="https://alpha.lottery.sina.com.cn/gateway/index/entry?" + urlencode(
            {"cat1": endpoint, **binding}), metadata={"http_status": 200, "retention": "UNCHANGED"},
    )


@pytest.fixture
def inputs():
    return {
        **IDENTITY, "company_id": "2", "offer_id": "1",
        "match_list": raw("jczqMatches", [{
            "matchId": "456", "tiCaiId": "123", "matchNo": "test-002", "team1": "Test Home",
            "team2": "Test Away", "score1": "1", "score2": "1", "matchTime": str(int(KICKOFF.timestamp())),
            "matchTimeFormat": "2024-06-01 20:00:00",
        }], date="2024-06-01"),
        "overview": raw("footballMatchOddsEuro", [{"companyId": "2", "offerId": "1", "companyName": "X*"}],
                        matchId="456"),
        "history": raw("footballMatchOddsEuroChange", [{
            "o1": "7.00", "o2": "4.00", "o3": "1.500",  # Home is deliberately not the lowest price.
            "oddsTime": str(int((KICKOFF-timedelta(hours=7)).timestamp())),
        }], matchId="456", companyId="2", offerId="1"),
    }


def test_mapping_prices_encoding_do_not_prove_availability(inputs):
    before = deepcopy(inputs)
    report = inspect_sina_1x2(**inputs)
    assert inputs == before
    assert report["external_match_id"] == "456" and report["role"] == "EXTERNAL_MAPPING_ONLY"
    assert report["bookmaker"] == "sina:2:1"
    row = report["rows"][0]
    assert row["prices"] == dict(HOME=Decimal("7"), DRAW=Decimal("4"), AWAY=Decimal("1.5"))
    assert all(isinstance(price, Decimal) for price in row["prices"].values())
    assert row["raw_oddsTime"] == "1717218000" and row["raw_timestamp_type"] == "str"
    assert row["UTC"] == "2024-06-01T05:00:00+00:00"
    assert row["Asia_Shanghai"] == "2024-06-01T13:00:00+08:00"
    assert row["browser_display_Asia_Shanghai"] == "06-01 13:00"
    assert row["replay_available_at"] is row["availability_basis"] is None
    assert report["time_status"] == "SINA_TIME_SEMANTICS_UNVERIFIED"
    assert report["timestamp_semantics"] == "UNKNOWN" and report["verification_status"] == "UNVERIFIED"
    assert report["quote_record_count"] == 0 and report["prematch_row_count"] == 1
    assert set(report["cutoffs"]) == {f"T-{minutes}" for minutes in CUTOFFS}
    assert all(item["status"] == "BLOCKED" and item["selected_record"] is None
               for item in report["cutoffs"].values())


@pytest.mark.parametrize("change", [
    {"tiCaiId": "999"}, {"team1": "Test Away", "team2": "Test Home"}, {"matchTime": "1717243201"},
    {"matchTimeFormat": "2024-06-01 12:00:00"}, {"matchNo": "test-003"}, {"score1": "2"}, {"matchId": ""},
])
def test_wrong_mapping_rejected(inputs, change):
    inputs["match_list"].payload["result"]["data"][0].update(change)
    with pytest.raises(ValueError):
        map_sina_target(inputs["match_list"], **IDENTITY)


@pytest.mark.parametrize("same_target", [True, False])
def test_duplicate_matches_rejected(inputs, same_target):
    rows = inputs["match_list"].payload["result"]["data"]
    rows.append({**rows[0], "tiCaiId": "123" if same_target else "999"})
    with pytest.raises(ValueError):
        inspect_sina_1x2(**inputs)


@pytest.mark.parametrize("change", [
    {"o2": None}, {"o1": 2.5}, {"o3": "1"}, {"o1": "NaN"}, {"o2": "Infinity"},
    {"oddsTime": None}, {"oddsTime": True}, {"oddsTime": 1717218000.0},
    {"oddsTime": "1717218000000"}, {"oddsTime": "2024-06-01 05:00:00"}, {"oddsTime": "1717502400"},
])
def test_invalid_odds_and_timestamps_rejected(inputs, change):
    inputs["history"].payload["result"]["data"][0].update(change)
    with pytest.raises(ValueError):
        inspect_sina_1x2(**inputs)


def test_cross_time_stitch_rejected(inputs):
    row = inputs["history"].payload["result"]["data"][0]
    inputs["history"].payload["result"]["data"] = [
        {"oddsTime": str(int(row["oddsTime"])+i), field: row[field]}
        for i, field in enumerate(("o1", "o2", "o3"))
    ]
    with pytest.raises(ValueError, match="same-row"):
        inspect_sina_1x2(**inputs)


@pytest.mark.parametrize("conflict", [False, True])
def test_duplicate_or_conflicting_timestamp_retains_evidence_only(inputs, conflict):
    rows = inputs["history"].payload["result"]["data"]
    rows.append({**rows[0], "o1": "9.00" if conflict else rows[0]["o1"]})
    report = inspect_sina_1x2(**inputs)
    assert report["duplicate_timestamp_groups"] == 1
    assert report["conflicting_timestamp_groups"] == int(conflict)
    assert report["rows"][0]["flags"] == ["CONFLICTING_TIMESTAMP" if conflict else "DUPLICATE_TIMESTAMP"]
    assert report["quote_record_count"] == 0


@pytest.mark.parametrize("offset,expected", [(-1, "PREMATCH_CANDIDATE"), (0, "POST_KICKOFF"), (1, "POST_KICKOFF")])
def test_strict_prematch_and_kickoff_equality(inputs, offset, expected):
    inputs["history"].payload["result"]["data"][0]["oddsTime"] = int(KICKOFF.timestamp())+offset
    report = inspect_sina_1x2(**inputs)
    assert report["rows"][0]["classification"] == expected
    assert report["post_kickoff_row_count"] == int(offset >= 0)
    assert report["quote_record_count"] == 0


@pytest.mark.parametrize("kind", ["missing_company", "missing_offer", "name_only", "official", "wrong_url", "duplicate"])
def test_bookmaker_requires_stable_bound_identity(inputs, kind):
    rows = inputs["overview"].payload["result"]["data"]
    if kind == "missing_company":
        del rows[0]["companyId"]
    elif kind == "missing_offer":
        del rows[0]["offerId"]
    elif kind == "name_only":
        inputs["company_id"] = "X*"
    elif kind == "official":
        rows[0]["companyName"] = "竞彩官方"
    elif kind == "duplicate":
        rows.append(dict(rows[0]))
    else:
        inputs["history"] = replace(inputs["history"], external_ref=inputs["history"].external_ref.replace("matchId=456", "matchId=789"))
    with pytest.raises(ValueError):
        inspect_sina_1x2(**inputs)


def quotes(provider, minutes, prices=("2", "4", "4"), *, bookmaker=None):
    stamp = KICKOFF-timedelta(minutes=minutes)
    return tuple(ResearchOddsQuote(
        record_id=f"{provider}:{bookmaker}:{minutes}:{selection}", research_match_id=MATCH.research_match_id,
        provider=provider, bookmaker=bookmaker or ("Sporttery" if provider == "sporttery" else "sina:2:1"),
        market_type="SPORTTERY_HAD" if provider == "sporttery" else "1X2", selection=selection, line=None,
        decimal_odds=Decimal(price), replay_available_at=stamp, availability_basis=AvailabilityBasis.SOURCE_SNAPSHOT_AT,
    ) for selection, price in zip(("HOME", "DRAW", "AWAY"), prices, strict=True))


def packet(external=()):
    """Simulated VERIFIED declarations only, never used for real Sina admission."""
    sources = tuple(ResearchSourceInput(
        source=ResearchSource(source_name=name, source_type=kind, retrieval_note="SYNTHETIC ONLY"),
        provider_name=name, license_note="Locally generated synthetic data only",
        verification_status="VERIFIED", verified_at=KICKOFF+timedelta(days=1),
        verification_note="SIMULATED verifier for integration tests; no real source attestation",
    ) for name, kind in (("sporttery", "OFFICIAL_SPORTTERY_HISTORY"), ("sina", "EXTERNAL_ODDS_HISTORY")))
    official = tuple(q for i in range(18) for q in quotes("sporttery", 1000+i, ("4", "4", "2")))
    artifacts = tuple(ResearchRawArtifactInput(
        source_name=name, artifact_type="SPORTTERY_POOL" if name == "sporttery" else "SYNTHETIC_FIXTURE",
        retrieved_at=KICKOFF+timedelta(days=1), content_type="application/json", payload={"synthetic": name},
        metadata={"sporttery_pool_evidence": {"sporttery_match_id": "123", "home_team_id": "test-home",
                   "away_team_id": "test-away", "kickoff_at": KICKOFF.isoformat()}},
    ) for name in ("sporttery", "sina"))
    raw_by_source = {r.source_name: r for r in artifacts}
    odds = (*official, *external)
    return validate_import(ResearchImport(
        dataset=ResearchDataset(dataset_id="synthetic-external-pilot", dataset_version="base-v1",
            replay_version="research-replay-v1", matches=(MATCH,), odds=odds, results=(),
            source_manifest=tuple(s.source for s in sources)),
        description="SYNTHETIC single-target integration", manifest={"synthetic": True}, sources=sources,
        raw_artifacts=artifacts,
        provenance=tuple(ResearchRecordProvenance(record_type=kind, record_id=rid, source_name=provider,
                         raw_content_hash=raw_by_source[provider].content_hash)
                         for kind, rid, provider in [("MATCH", MATCH.research_match_id, "sporttery"),
                                                    *(("ODDS", q.record_id, q.provider) for q in odds)]),
        sporttery_verifications=(SportteryVerificationInput(research_match_id=MATCH.research_match_id,
            status="VERIFIED", artifact_source_name="sporttery", artifact_content_hash=artifacts[0].content_hash),),
    ))


@pytest.mark.parametrize("minutes", CUTOFFS)
def test_last_complete_at_or_before_cutoff_no_closest_after(minutes):
    value = packet((*quotes("sina", minutes), *quotes("sina", minutes-1, ("4", "4", "2"))))
    report = assess_intake_gates(value, cutoff_minutes=(minutes,))
    market = report["cutoff_markets"][str(minutes)][MATCH.research_match_id]
    assert report["gates"] == {"A": "PASS", "B": "PASS"}
    assert market["external_consensus"]["source_count"] == 1
    assert {k: Decimal(v) for k, v in market["external_consensus"]["p_market"].items()} == {
        "HOME": Decimal(".5"), "DRAW": Decimal(".25"), "AWAY": Decimal(".25")}
    assert {k: Decimal(v) for k, v in market["sporttery_external_gap"].items()} == {
        "HOME": Decimal(".25"), "DRAW": Decimal(0), "AWAY": Decimal("-.25")}
    assert len(market["sporttery"]["HAD"]) == 1 and market["sporttery"]["HAD"][0]["complete"]
    assert not value.dataset.results  # Market inputs can exist without an evaluable target result.


@pytest.mark.parametrize("reason", ["unverified_source", "missing_time", "incomplete", "cross_time",
    "duplicate", "conflict", "kickoff", "post_kickoff", "wrong_target", "non_1x2", "sporttery_alias"])
def test_gate_b_rejects_unqualified_external(reason):
    external = quotes("sina", 10)
    if reason == "missing_time":
        external = tuple(replace(q, replay_available_at=None, availability_basis=None) for q in external)
    elif reason == "incomplete":
        external = external[:2]
    elif reason == "cross_time":
        external = tuple(replace(q, replay_available_at=q.replay_available_at-timedelta(seconds=i))
                         for i, q in enumerate(external))
    elif reason in {"duplicate", "conflict"}:
        external += (replace(external[0], record_id="duplicate", decimal_odds=Decimal("3") if reason == "conflict" else Decimal("2")),)
    elif reason in {"kickoff", "post_kickoff"}:
        external = quotes("sina", 0 if reason == "kickoff" else -1)
    elif reason == "non_1x2":
        external = tuple(replace(q, market_type="SPORTTERY_HAD") for q in external)
    value = packet(external)
    if reason in {"unverified_source", "sporttery_alias"}:
        value = replace(value, sources=tuple(
            s if s.source.source_name != "sina" else (
                replace(s, verification_status="UNVERIFIED") if reason == "unverified_source"
                else replace(s, provider_name="sporttery"))
            for s in value.sources))
    elif reason == "wrong_target":
        other = replace(MATCH, research_match_id="other", sporttery_match_id=None, source_record_id="other")
        value = replace(value, dataset=replace(value.dataset, matches=(MATCH, other), odds=tuple(
            replace(q, research_match_id="other") if q.provider == "sina" else q for q in value.dataset.odds)),
            provenance=(*value.provenance, replace(value.provenance[0], record_type="MATCH", record_id="other")))
    report = assess_intake_gates(value, cutoff_minutes=CUTOFFS)
    assert report["gates"] == {"A": "PASS", "B": "BLOCKED"}
    assert not any(report["cutoff_coverage"].values())


def test_partial_new_snapshot_uses_previous_whole_snapshot_and_counts_bookmakers():
    value = packet((*quotes("sina", 90), *quotes("sina", 30)[:1],
                    *quotes("sina", 100, bookmaker="sina:5:1")))
    report = assess_intake_gates(value, cutoff_minutes=(5,))
    consensus = report["cutoff_markets"]["5"][MATCH.research_match_id]["external_consensus"]
    assert consensus["source_count"] == 2
    assert {s["bookmaker"] for s in consensus["sources"]} == {"sina:2:1", "sina:5:1"}


@pytest.mark.parametrize("basis", ["GUESSED", "ASSUMED", "APPROXIMATE"])
def test_guessed_availability_rejected(basis):
    with pytest.raises(ValueError):
        replace(quotes("sina", 10)[0], availability_basis=basis)


@pytest.mark.parametrize("basis", list(AvailabilityBasis))
def test_only_explicit_matching_semantic_basis_accepted(basis):
    quote = quotes("sina", 10)[0]
    evidence = {}
    if basis == AvailabilityBasis.PROVIDER_PUBLISHED_AT:
        evidence["published_at"] = quote.replay_available_at
    elif basis == AvailabilityBasis.PROVIDER_EFFECTIVE_AT:
        evidence["effective_at"] = quote.replay_available_at
    assert replace(quote, availability_basis=basis, **evidence).availability_basis == basis
    for field in evidence:
        with pytest.raises(ValueError, match="named time evidence"):
            replace(quote, availability_basis=basis, **{field: quote.replay_available_at+timedelta(seconds=1)})
    with pytest.raises(ValueError, match="timezone-aware"):
        replace(quote, replay_available_at=quote.replay_available_at.replace(tzinfo=None))


def test_sporttery_1x2_never_counts_and_effective_time_cannot_hide_future_publication():
    official_mirror = tuple(replace(q, market_type="1X2", record_id="mirror:"+q.record_id)
                            for q in quotes("sporttery", 10))
    future = tuple(replace(q, published_at=KICKOFF) for q in quotes("sina", 10))
    report = assess_intake_gates(packet((*official_mirror, *future)), cutoff_minutes=(5,))
    market = report["cutoff_markets"]["5"][MATCH.research_match_id]
    assert market["external_consensus"]["source_count"] == 0
    assert market["external_consensus"]["p_market"] is None and market["sporttery_external_gap"] is None
    assert report["gates"]["B"] == "BLOCKED"


def test_new_dataset_roundtrip_immutable_and_two_old_versions_unchanged(sessions):
    engine = sessions.kw["bind"]
    original = packet()
    gate_a = replace(original, dataset=replace(original.dataset, dataset_version="gate-a-v1", odds=()),
                     provenance=tuple(p for p in original.provenance if p.record_type == "MATCH"))
    baseline = [import_research_dataset(engine, p) for p in (gate_a, original)]
    new = packet(tuple(q for minutes in CUTOFFS for q in quotes("sina", minutes)))
    new = replace(new, dataset=replace(new.dataset, dataset_version="external-v1"))
    row = import_research_dataset(engine, new)
    assert row["status"] == "SEALED" and row["content_hash"] == dataset_content_hash(new)
    with engine.connect() as conn:
        loaded = load_research_dataset(conn, new.dataset.dataset_id, "external-v1")
        assert loaded == new.dataset and len(loaded.odds) == 69
        assert sum(q.provider == "sporttery" for q in loaded.odds) == 54
        assert verified_sporttery_targets(conn, row["id"]) == (MATCH.research_match_id,)
        for before, old in zip(baseline, (gate_a, original), strict=True):
            assert load_research_dataset(conn, old.dataset.dataset_id, old.dataset.dataset_version) == old.dataset
            assert before["content_hash"] == dataset_content_hash(old)
        for minutes in CUTOFFS:
            market = build_market_data(build_research_feature(loaded, MATCH.research_match_id, ReplayCutoffSpec(minutes)))
            assert market["external_consensus"]["source_count"] == 1 and market["external_consensus"]["p_market"]
            assert market["sporttery"]["HAD"][0]["complete"] and market["sporttery_external_gap"]
    with pytest.raises(DatasetConflict):
        import_research_dataset(engine, replace(new, description="attempted overwrite"))


def test_current_single_target_state_keeps_time_license_and_gates_separate():
    state = json.loads(Path("docs/RESEARCH_CURRENT_STATE.json").read_text("utf-8"))
    audit = state["external_qualification"]
    assert state["current_phase"] == "P4-4D2B.7"
    assert state["the_odds_api_credential_status"] == "NOT_AVAILABLE"
    assert state["the_odds_api_target_coverage"] == "NOT_TESTED_NO_KEY"
    assert audit["target"] == "2041790" and audit["external_match_id"] == "3867327"
    assert audit["bookmaker"] == "sina:2:1"
    assert audit["historical_rows"] == audit["complete_rows"] == audit["prematch_rows_by_raw_timestamp"] == 5
    assert audit["post_kickoff_rows_by_raw_timestamp"] == 0
    assert audit["source_checks"] == {"transport":"VALID", "schema":"VALID", "identity":"VALID",
                                     "time":"UNVERIFIED", "license_use":"UNVERIFIED", "replay":"BLOCKED"}
    assert audit["replay_available_at"] is audit["availability_basis"] is None
    assert state["external_quote_count"] == 0 and not state["external_dataset_created"]
    assert state["gates"] == {"A":"PASS", "B":"BLOCKED", "C":"BLOCKED"}
    assert state["finished_at"] is None and state["result_count"] == 0
    assert state["official_had_quote_count"] == 54 and state["verified_target_count"] == 1
    assert state["market_model_data_status"] == "NOT_AVAILABLE"
    assert state["market_evaluation_status"] == "NOT_EVALUABLE"
    for minutes in CUTOFFS:
        cutoff = audit["cutoffs"][f"T-{minutes}"]
        assert cutoff["status"] == "BLOCKED" and cutoff["official_had"] == "AVAILABLE"
        assert cutoff["selected_record"] is cutoff["p_market"] is cutoff["sporttery_external_gap"] is None
        assert cutoff["external_consensus_source_count"] == 0


def test_no_access_qualification_never_promotes_documentation_or_changes_sina():
    state = json.loads(Path("docs/RESEARCH_CURRENT_STATE.json").read_text("utf-8"))
    qualification = state["historical_source_qualification"]
    primary = qualification["primary_source"]
    assert state["blocker_classification"] == primary["blocker_class"] == "NO_ACCESS"
    assert primary["credential_status"] == "NOT_AVAILABLE" and primary["status"] == "NO_KEY"
    assert not primary["historical_endpoint_called"]
    assert primary["historical_http_status"] is primary["historical_response_sha256"] is None
    assert primary["historical_raw_content_hash"] is primary["external_event_id"] is None
    assert primary["historical_snapshot_count"] == primary["complete_1x2_count"] == primary["external_quote_count"] == 0
    assert primary["verification_status"] == "UNVERIFIED"
    assert primary["target_mapping"] == "UNVERIFIED" and primary["target_coverage"] == "NOT_TESTED_NO_KEY"
    assert primary["license_use"] == "VERIFIED" and primary["timestamp_semantics_response"] == "UNVERIFIED"
    assert primary["replay_available_at"] is primary["availability_basis"] is None
    assert qualification["sina_frozen_qualification_hash"] == content_hash(state["external_qualification"])
    # Pin the accepted Sina evidence, not just two mutually editable state fields.
    assert qualification["sina_frozen_qualification_hash"] == "4a2878d1175ff48af2c63d1c7dcba993fcd162533a9167dc8ac177ee5e774ecd"
    checks = {"transport", "schema", "match_identity", "bookmaker_identity", "one_x_two_mapping",
              "historical_timestamp", "availability_semantics", "license_use", "replay"}
    assert set(primary["source_checks"]) == checks
    for candidate in qualification["candidate_discovery"]:
        assert set(candidate["source_checks"]) == checks
        assert candidate["verification_status"] == "UNVERIFIED"
        assert candidate["replay_available_at"] is candidate["availability_basis"] is None
    assert not qualification["dataset_created"]
    assert qualification["new_dataset_version"] is qualification["new_dataset_hash"] is None
    assert not qualification["raw_artifacts_in_git"] and not qualification["real_provider_fixtures_added"]
    for minutes in CUTOFFS:
        cutoff = qualification["cutoffs"][f"T-{minutes}"]
        assert parse_time(cutoff["cutoff"]) == parse_time("2026-09-30T10:30:00Z") - timedelta(minutes=minutes)
        assert cutoff["status"] == "BLOCKED" and cutoff["reason"] == "NO_ACCESS"
        assert not cutoff["request_executed"]
        assert cutoff["selected_snapshot_timestamp"] is cutoff["p_market"] is cutoff["sporttery_external_gap"] is None
        assert cutoff["external_consensus_source_count"] == 0 and cutoff["official_had"] == "AVAILABLE"
