"""Entirely synthetic provider responses; never evidence for a real source."""

import json
from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlencode

import pytest
from jc.analysis.research_replay import ResearchSource
from jc.research.contracts import ResearchRawArtifactInput, ResearchSourceInput, dataset_content_hash
from jc.research.importer import import_research_dataset
from jc.research.oddspapi import CUTOFFS, assess_oddspapi_intake, audit_oddspapi, build_oddspapi_import
from jc.research.repository import _read_import, load_research_dataset
from test_external_1x2 import KICKOFF, MATCH, packet

IDENTITY = {
    "canonical": {
        "sporttery_match_id": MATCH.sporttery_match_id,
        "home_team_id": MATCH.home_team_id,
        "away_team_id": MATCH.away_team_id,
    },
    "provider_fields": {
        "fixtureId": "synthetic-fixture",
        "participant1Id": 1,
        "participant2Id": 2,
        "participant1Name": "Test Home",
        "participant2Name": "Test Away",
        "sportId": 10,
        "sportName": "Soccer",
        "tournamentId": 3,
        "tournamentName": "Test Tournament",
        "categoryName": "Test Category",
    },
}
SOURCE = ResearchSourceInput(
    source=ResearchSource(
        source_name="oddspapi",
        source_type="EXTERNAL_ODDS_HISTORY",
        retrieval_note="SYNTHETIC integration test; not a real source qualification",
    ),
    provider_name="oddspapi",
    license_note="SYNTHETIC test declaration only",
    verification_status="VERIFIED",
    verified_at=KICKOFF,
    verification_note="SYNTHETIC time/identity/license declaration; no real evidence",
)


def raw(endpoint, body, **query):
    return ResearchRawArtifactInput(
        source_name="oddspapi",
        artifact_type="ODDSPAPI_HISTORY" if endpoint == "historical-odds" else f"ODDSPAPI_{endpoint.upper()}",
        retrieved_at=KICKOFF + timedelta(days=1),
        content_type="application/json",
        payload=json.dumps(body),
        external_ref=f"https://api.oddspapi.io/v4/{endpoint}?{urlencode(query)}",
        metadata={"http_status": 200, "retention": "UNCHANGED", "synthetic": True},
    )


def evidence(change=None):
    fixture = {**IDENTITY["provider_fields"], "startTime": KICKOFF.isoformat()}
    market = {
        "marketId": 101,
        "marketLength": 3,
        "sportId": 10,
        "marketType": "1x2",
        "period": "fulltime",
        "handicap": 0,
        "playerProp": False,
        "outcomes": [{"outcomeId": i, "outcomeName": n} for i, n in ((101, "1"), (102, "X"), (103, "2"))],
    }
    raws = [
        raw("fixtures", [fixture]),
        raw("markets", [market]),
        raw("bookmakers", [{"slug": "synthetic-book", "cloneOf": None}]),
    ]
    for oid in (101, 102, 103):
        rows = [
            {
                "createdAt": (KICKOFF - timedelta(minutes=m)).isoformat(),
                "active": True,
                "price": 2 if oid == 101 else 4,
                "exchangeMeta": None,
            }
            for m in (360, 30)
        ]
        # Later partial/inactive observations must block, not reuse the earlier whole snapshot.
        if oid == 101:
            rows += [
                {
                    "createdAt": (KICKOFF - timedelta(minutes=m)).isoformat(),
                    "active": m != 15,
                    "price": 3,
                    "exchangeMeta": None,
                }
                for m in (90, 15, 5)
            ]
        if change:
            change(oid, rows)
        body = {
            "fixtureId": "synthetic-fixture",
            "bookmakers": {
                "synthetic-book": {"markets": {"101": {"outcomes": {str(oid): {"players": {"0": rows}}}}}}
            },
        }
        raws.append(
            raw(
                "historical-odds",
                body,
                fixtureId="synthetic-fixture",
                bookmakers="synthetic-book",
                outcomeId=oid,
            )
        )
    return tuple(raws)


def candidate(raws=None, source=SOURCE):
    return build_oddspapi_import(
        packet(),
        raws=raws or evidence(),
        identity=IDENTITY,
        source=source,
        dataset_version="synthetic-oddspapi-v1",
    )


def test_real_flow_uses_same_time_triples_and_blocks_newer_partial_after_reload(sessions):
    value = candidate()
    expected = {"360": 1, "90": 0, "30": 1, "15": 0, "5": 0}
    report = assess_oddspapi_intake(value)
    assert report["gates"] == {"A": "PASS", "B": "PASS"} and report["cutoff_coverage"] == expected
    assert len(value.dataset.odds) == 60 and not value.dataset.results
    engine = sessions.kw["bind"]
    row = import_research_dataset(engine, value)
    assert row["status"] == "SEALED" and row["content_hash"] == dataset_content_hash(value)
    with engine.connect() as conn:
        loaded = load_research_dataset(conn, value.dataset.dataset_id, value.dataset.dataset_version)
        restored = _read_import(conn, row["id"])
        assert loaded == value.dataset
        assert assess_oddspapi_intake(restored) == report
    for minutes in CUTOFFS:
        market = report["cutoff_markets"][str(minutes)][MATCH.research_match_id]
        assert market["external_consensus"]["source_count"] == expected[str(minutes)]
        if expected[str(minutes)]:
            assert {k: Decimal(v) for k, v in market["external_consensus"]["p_market"].items()} == {
                "HOME": Decimal(".5"),
                "DRAW": Decimal(".25"),
                "AWAY": Decimal(".25"),
            }
        else:
            assert market["external_consensus"]["p_market"] is market["sporttery_external_gap"] is None


@pytest.mark.parametrize(
    "failure",
    [
        "wrong_fixture",
        "wrong_home",
        "wrong_competition",
        "kickoff",
        "wrong_market",
        "wrong_outcome",
        "clone",
        "redacted",
        "http_error",
        "filtered_active",
        "missing_outcome_request",
        "future_time",
        "naive_time",
        "invalid_active",
        "nonfinite_price",
    ],
)
def test_untrusted_evidence_fails_closed(failure):
    raws = list(evidence())
    pos = (
        0
        if failure in {"wrong_fixture", "wrong_home", "wrong_competition", "kickoff"}
        else 1
        if failure in {"wrong_market", "wrong_outcome"}
        else 2
        if failure == "clone"
        else 3
    )
    body = json.loads(raws[pos].payload)
    if failure == "wrong_fixture":
        body[0]["fixtureId"] = "other"
    elif failure == "wrong_home":
        body[0]["participant1Name"] = "Other Home"
    elif failure == "wrong_competition":
        body[0]["tournamentId"] = 44
    elif failure == "kickoff":
        body[0]["startTime"] = (KICKOFF + timedelta(minutes=1)).isoformat()
    elif failure == "wrong_market":
        body[0]["period"] = "firsthalf"
    elif failure == "wrong_outcome":
        body[0]["outcomes"][1]["outcomeName"] = "2"
    elif failure == "clone":
        body[0]["cloneOf"] = "another-book"
    elif failure in {"future_time", "naive_time", "invalid_active", "nonfinite_price"}:
        entry = body["bookmakers"]["synthetic-book"]["markets"]["101"]["outcomes"]["101"]["players"]["0"][0]
        if failure == "future_time":
            entry["createdAt"] = (KICKOFF + timedelta(days=2)).isoformat()
        elif failure == "naive_time":
            entry["createdAt"] = KICKOFF.replace(tzinfo=None).isoformat()
        elif failure == "invalid_active":
            entry["active"] = "true"
        else:
            entry["price"] = "NaN"
    raws[pos] = replace(raws[pos], payload=json.dumps(body))
    if failure == "redacted":
        raws[pos] = replace(raws[pos], metadata={**raws[pos].metadata, "retention": "REDACTED"})
    elif failure == "http_error":
        raws[pos] = replace(raws[pos], metadata={**raws[pos].metadata, "http_status": 403})
    elif failure == "filtered_active":
        raws[pos] = replace(raws[pos], external_ref=raws[pos].external_ref + "&active=true")
    elif failure == "missing_outcome_request":
        raws.pop()
    with pytest.raises(ValueError):
        candidate(tuple(raws))


@pytest.mark.parametrize("issue", ["duplicate", "suspended", "invalid_price", "different_time"])
def test_never_fills_or_resurrects_invalid_latest_snapshot(issue):
    def change(oid, rows):
        if oid != 101:
            return
        latest = rows[1]
        if issue == "duplicate":
            rows.append(deepcopy(latest))
        elif issue == "suspended":
            latest["active"] = False
        elif issue == "invalid_price":
            latest["price"] = 1
        else:
            latest["createdAt"] = (KICKOFF - timedelta(minutes=30, seconds=1)).isoformat()

    audit = audit_oddspapi(evidence(change), MATCH, IDENTITY)
    assert audit["cutoffs"]["30"]["bookmakers"]["synthetic-book"]["status"] == "BLOCKED"


def test_source_attestation_and_raw_quote_binding_are_required():
    with pytest.raises(ValueError, match="VERIFIED"):
        candidate(source=replace(SOURCE, verification_status="UNVERIFIED"))
    value = candidate()
    quote = next(q for q in value.dataset.odds if q.provider == "oddspapi")
    altered = replace(
        value,
        dataset=replace(
            value.dataset,
            odds=tuple(
                replace(q, decimal_odds=Decimal(9)) if q.record_id == quote.record_id else q
                for q in value.dataset.odds
            ),
        ),
    )
    with pytest.raises(ValueError, match="must agree"):
        assess_oddspapi_intake(altered)


def test_current_state_reports_only_qualified_cutoffs_and_preserves_result_block():
    state = json.loads(Path("docs/RESEARCH_CURRENT_STATE.json").read_text("utf-8"))
    admission = state["oddspapi_qualification"]
    assert state["gates"] == admission["gates"] == {"A": "PASS", "B": "PASS", "C": "BLOCKED"}
    assert state["latest_dataset_version"] == admission["new_dataset_version"] == "2041790-external-1x2-v1"
    assert state["latest_dataset_hash"] == admission["new_dataset_hash"]
    assert admission["dataset_counts"] == {
        "verified_targets": 1,
        "sporttery_had_quotes": 54,
        "external_quotes": 6,
        "results": 0,
        "raw_artifacts": 16,
    }
    assert admission["qualified_snapshot_count"] == admission["qualified_cutoff_count"] == 2
    assert admission["bookmakers_admitted"] == ["oddspapi:pinnacle"]
    for cutoff, row in admission["cutoffs"].items():
        passed = cutoff in {"T-360", "T-30"}
        assert row["status"] == ("PASS" if passed else "BLOCKED")
        assert row["external_consensus"]["source_count"] == int(passed)
        assert (row["p_market"] is not None) is passed
        assert (row["sporttery_external_gap"] is not None) is passed
        if not passed:
            assert row["blocker_class"] == "NO_DATA" and row["reason"] == "INCOMPLETE_SNAPSHOT"
    assert state["external_qualification"]["external_quote_count"] == 0
