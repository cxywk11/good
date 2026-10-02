"""Synthetic as-of contract checks; real evidence stays in ignored artifacts."""

import json
from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from jc.research.contracts import dataset_content_hash
from jc.research.importer import import_research_dataset
from jc.research.oddspapi import assess_oddspapi_intake
from jc.research.oddspapi_asof import (
    POLICY,
    assess_oddspapi_asof_intake,
    audit_oddspapi_asof,
    build_oddspapi_asof_import,
)
from jc.research.repository import _read_import, load_research_dataset
from test_oddspapi import IDENTITY, KICKOFF, MATCH, SOURCE, evidence, packet
from test_oddspapi import candidate as v1_candidate

SEMANTICS = {
    "status": "VERIFIED",
    "policy": POLICY,
    "reviewed_at": KICKOFF.isoformat(),
    "review_note": "SYNTHETIC attestation; not evidence for any real provider",
    "bookmakers": ["synthetic-book"],
    "evidence": [{"url": "https://oddspapi.io/synthetic-test-only", "response_sha256": "a" * 64}],
}


def histories(series=None):
    series = series or {101: [(60, 2, True)], 102: [(70, 4, True)], 103: [(80, 4, True)]}
    raws = list(evidence())
    for pos, oid in enumerate((101, 102, 103), start=3):
        body = json.loads(raws[pos].payload)
        body["bookmakers"]["synthetic-book"]["markets"]["101"]["outcomes"][str(oid)]["players"]["0"] = [
            {
                "createdAt": (KICKOFF - timedelta(minutes=m)).isoformat(),
                "price": price,
                "active": active,
                "limit": None,
                "exchangeMeta": None,
            }
            for m, price, active in series[oid]
        ]
        raws[pos] = replace(raws[pos], payload=json.dumps(body))
    return tuple(raws)


def candidate(raws=None, semantics=None, source=SOURCE, version="synthetic-asof-v2"):
    return build_oddspapi_asof_import(
        packet(),
        raws=raws or histories(),
        identity=IDENTITY,
        semantics=semantics or SEMANTICS,
        source=source,
        dataset_version=version,
    )


def audit(raws):
    return audit_oddspapi_asof(raws, MATCH, IDENTITY, SEMANTICS)


def book_at(report, minutes=30):
    return report["cutoffs"][str(minutes)]["bookmakers"]["synthetic-book"]


def test_async_state_persists_and_keeps_original_times_and_raw_references():
    value = candidate()
    report = assess_oddspapi_asof_intake(value)
    for m in (30, 15, 5):
        book = book_at(report["audit"], m)
        assert book["market_state_status"] == "PASS"
        assert book["market_state_asof"] == (KICKOFF - timedelta(minutes=m)).isoformat()
        assert len({s["original_created_at"] for s in book["outcomes"].values()}) == 3
        for selection, state in book["outcomes"].items():
            quote = next(
                q for q in value.dataset.odds if q.provider == "oddspapi" and q.selection == selection
            )
            assert (
                quote.replay_available_at.isoformat()
                == state["source_created_at"]
                == state["original_created_at"]
            )
            assert quote.replay_available_at.isoformat() != book["market_state_asof"]
            assert state["source_raw_path"].endswith("players.0[0]")
            assert len(state["source_raw_hash"]) == 64 and state["active"] is True
        market = report["cutoff_markets"][str(m)][MATCH.research_match_id]
        assert {k: Decimal(v) for k, v in market["external_consensus"]["p_market"].items()} == {
            "HOME": Decimal("0.5"),
            "DRAW": Decimal("0.25"),
            "AWAY": Decimal("0.25"),
        }
    assert len(value.dataset.odds) == 57  # Identical selected states across cutoffs are not duplicate quotes.


def test_latest_inactive_blocks_old_active_and_later_active_restores():
    raw = histories(
        {101: [(60, 2, True), (20, 2, False), (10, 3, True)], 102: [(60, 4, True)], 103: [(60, 4, True)]}
    )
    value = candidate(raw)
    report = assess_oddspapi_asof_intake(value)
    paused = book_at(report["audit"], 15)
    assert paused["outcomes"]["HOME"]["reason"] == "INACTIVE"
    assert paused["market_state_status"] == "BLOCKED"
    assert report["cutoff_markets"]["15"][MATCH.research_match_id]["external_consensus"]["p_market"] is None
    assert book_at(report["audit"], 5)["outcomes"]["HOME"]["price"] == "3"
    assert report["cutoff_coverage"]["5"] == 1


@pytest.mark.parametrize(
    "minutes,price,reason",
    [(30, 1, "INVALID_PRICE"), (29, 2, "NO_DATA"), (0, 2, "NO_DATA"), (-1, 2, "NO_DATA")],
)
def test_invalid_price_future_and_kickoff_state_cannot_enter(minutes, price, reason):
    row = book_at(
        audit(histories({101: [(minutes, price, True)], 102: [(60, 4, True)], 103: [(60, 4, True)]}))
    )
    assert row["market_state_status"] == "BLOCKED" and row["outcomes"]["HOME"]["reason"] == reason


@pytest.mark.parametrize("price", [0, -1])
def test_nonpositive_recorded_price_rejected_at_raw_boundary(price):
    with pytest.raises(ValueError, match="positive"):
        audit(histories({101: [(30, price, True)], 102: [(60, 4, True)], 103: [(60, 4, True)]}))


def test_cutoff_equality_is_included_without_lookahead():
    row = book_at(
        audit(histories({101: [(30, 2, True), (29, 9, True)], 102: [(30, 4, True)], 103: [(30, 4, True)]}))
    )
    assert row["market_state_status"] == "PASS" and row["outcomes"]["HOME"]["price"] == "2"


@pytest.mark.parametrize(
    "failure", ["fixture", "market", "outcome", "bookmaker", "clone", "naive", "after_retrieval"]
)
def test_identity_and_time_fail_closed(failure):
    raws = list(histories())
    pos = 2 if failure == "clone" else 3
    body = json.loads(raws[pos].payload)
    if failure == "fixture":
        body["fixtureId"] = "wrong"
    elif failure == "bookmaker":
        body["bookmakers"]["wrong"] = body["bookmakers"].pop("synthetic-book")
    elif failure == "clone":
        body[0]["cloneOf"] = "some-book"
    else:
        markets = body["bookmakers"]["synthetic-book"]["markets"]
        if failure == "market":
            markets["999"] = markets.pop("101")
        elif failure == "outcome":
            markets["101"]["outcomes"]["999"] = markets["101"]["outcomes"].pop("101")
        else:
            row = markets["101"]["outcomes"]["101"]["players"]["0"][0]
            row["createdAt"] = (
                KICKOFF.replace(tzinfo=None) if failure == "naive" else KICKOFF + timedelta(days=2)
            ).isoformat()
    raws[pos] = replace(raws[pos], payload=json.dumps(body))
    with pytest.raises(ValueError):
        audit(tuple(raws))


@pytest.mark.parametrize("change", ["price", "active", "identical"])
def test_conflicts_block_and_identical_duplicates_retain_evidence(change):
    raws = list(histories())
    body = json.loads(raws[3].payload)
    rows = body["bookmakers"]["synthetic-book"]["markets"]["101"]["outcomes"]["101"]["players"]["0"]
    other = deepcopy(rows[0])
    if change == "price":
        other["price"] = 3
    elif change == "active":
        other["active"] = False
    rows.append(other)
    raws[3] = replace(raws[3], payload=json.dumps(body))
    result = audit(tuple(raws))
    row = book_at(result)["outcomes"]["HOME"]
    if change == "identical":
        assert row["status"] == "PASS" and row["identical_duplicate_count"] == 1
        assert len(row["raw_references"]) == 2
        assert result["books"]["synthetic-book"]["identical_duplicate_rows"] == 1
    else:
        assert row["reason"] == "CONFLICTING_STATE" and book_at(result)["market_state_status"] == "BLOCKED"


@pytest.mark.parametrize("change", ["raw", "quote", "provenance", "audit", "source"])
def test_reaudit_rejects_tampering(change):
    value = candidate()
    if change == "raw":
        target = next(r for r in value.raw_artifacts if r.artifact_type == "ODDSPAPI_HISTORY")
        body = json.loads(target.payload)
        body["bookmakers"]["synthetic-book"]["markets"]["101"]["outcomes"]["101"]["players"]["0"][0][
            "active"
        ] = False
        value = replace(
            value,
            raw_artifacts=tuple(
                replace(r, payload=json.dumps(body)) if r == target else r for r in value.raw_artifacts
            ),
        )
    elif change == "quote":
        value = replace(
            value,
            dataset=replace(
                value.dataset,
                odds=tuple(
                    replace(q, decimal_odds=Decimal(9)) if q.provider == "oddspapi" else q
                    for q in value.dataset.odds
                ),
            ),
        )
    elif change == "provenance":
        digest = next(r.content_hash for r in value.raw_artifacts if r.artifact_type == "ODDSPAPI_FIXTURES")
        value = replace(
            value,
            provenance=tuple(
                replace(p, raw_content_hash=digest) if p.source_name == "oddspapi" else p
                for p in value.provenance
            ),
        )
    elif change == "audit":
        manifest = deepcopy(value.manifest)
        manifest["oddspapi_asof_v2"]["audit"]["cutoffs"]["30"]["market_state_asof"] = KICKOFF.isoformat()
        value = replace(value, manifest=manifest)
    else:
        value = replace(
            value,
            sources=tuple(
                replace(s, verification_note="changed") if s.provider_name == "oddspapi" else s
                for s in value.sources
            ),
        )
    with pytest.raises(ValueError):
        assess_oddspapi_asof_intake(value)


def test_no_cross_bookmaker_market_and_explicit_semantics_required():
    raws = list(histories())
    raws[2] = replace(
        raws[2], payload=json.dumps([{"slug": b, "cloneOf": None} for b in ("synthetic-book", "second-book")])
    )
    for pos in (3, 4, 5):
        body = json.loads(raws[pos].payload)
        body["bookmakers"]["second-book"] = deepcopy(body["bookmakers"]["synthetic-book"])
        oid = str(101 + pos - 3)
        empty_book = "second-book" if oid == "101" else "synthetic-book"
        body["bookmakers"][empty_book]["markets"]["101"]["outcomes"][oid]["players"]["0"] = []
        raws[pos] = replace(
            raws[pos],
            payload=json.dumps(body),
            external_ref=raws[pos].external_ref.replace(
                "bookmakers=synthetic-book", "bookmakers=synthetic-book%2Csecond-book"
            ),
        )
    review = {**SEMANTICS, "bookmakers": ["synthetic-book", "second-book"]}
    result = audit_oddspapi_asof(tuple(raws), MATCH, IDENTITY, review)
    assert all(b["market_state_status"] == "BLOCKED" for b in result["cutoffs"]["30"]["bookmakers"].values())
    with pytest.raises(ValueError, match="No complete"):
        candidate(tuple(raws), semantics=review)
    with pytest.raises(ValueError, match="semantics"):
        candidate(semantics={**SEMANTICS, "status": "UNVERIFIED"})
    with pytest.raises(ValueError, match="VERIFIED"):
        candidate(source=replace(SOURCE, verification_status="UNVERIFIED"))
    with pytest.raises(ValueError, match="V2"):
        candidate(version="2041790-external-1x2-v1")


def test_v2_reload_and_immutability_preserve_independent_v1_result(sessions):
    engine = sessions.kw["bind"]
    v1 = v1_candidate()
    original = dataset_content_hash(v1)
    before = assess_oddspapi_intake(v1)
    v1_row = import_research_dataset(engine, v1)
    value = candidate(evidence())
    report = assess_oddspapi_asof_intake(value)
    assert before["cutoff_coverage"] == {"360": 1, "90": 0, "30": 1, "15": 0, "5": 0}
    assert report["cutoff_coverage"] == {"360": 1, "90": 1, "30": 1, "15": 0, "5": 1}
    row = import_research_dataset(engine, value)
    assert row["status"] == "SEALED" and row["content_hash"] == dataset_content_hash(value)
    assert import_research_dataset(engine, value)["id"] == row["id"]
    with engine.connect() as conn:
        assert (
            load_research_dataset(conn, value.dataset.dataset_id, value.dataset.dataset_version)
            == value.dataset
        )
        assert assess_oddspapi_asof_intake(_read_import(conn, row["id"])) == report
        restored_v1 = _read_import(conn, v1_row["id"])
        assert dataset_content_hash(restored_v1) == original and assess_oddspapi_intake(restored_v1) == before
    with pytest.raises(ValueError):
        import_research_dataset(engine, replace(value, description="different immutable packet"))


def test_three_accepted_dataset_hashes_remain_frozen():
    state = json.loads(Path("docs/RESEARCH_CURRENT_STATE.json").read_text("utf-8"))
    hashes = state["frozen_dataset_checks"]["versions"]
    assert hashes["2041790-gate-a-v1"] == "2e7efbcc160e182b975c5918bcdea9ffefd9364d4aaf83529f4a1864a23f1e89"
    assert (
        hashes["2041790-official-had-v1"]
        == "ebf451127c7e49a308b2d75116607c2df67449e4a0cfc50d4fd003ed20fb2095"
    )
    assert (
        hashes["2041790-external-1x2-v1"]
        == state["oddspapi_qualification"]["new_dataset_hash"]
        == "4ddd648d9c90a1811c4235085cd38317c1932735104e23400b9da0106c944cce"
    )
    assert state["oddspapi_qualification"]["cutoff_policy"] == "oddspapi-same-instant-latest-1x2-v1"


def test_current_v2_state_coverage_is_derived_from_independent_books():
    state = json.loads(Path("docs/RESEARCH_CURRENT_STATE.json").read_text("utf-8"))
    v2 = state["oddspapi_asof_v2"]
    assert state["latest_dataset_version"] == v2["new_dataset_version"] == "2041790-external-1x2-asof-v2"
    assert state["latest_dataset_hash"] == v2["new_dataset_hash"]
    assert v2["policy"] == POLICY and v2["semantics_status"] == "VERIFIED"
    assert state["gates"] == {"A": "PASS", "B": "PASS", "C": "BLOCKED"}
    assert state["market_evaluation_status"] == "NOT_EVALUABLE" and state["result_count"] == 0
    covered = 0
    for minutes, row in v2["audit"]["cutoffs"].items():
        admitted = sum(b["market_state_status"] == "PASS" for b in row["bookmakers"].values())
        result = v2["comparison"][minutes]["v2"]
        assert result["source_count"] == admitted
        assert (result["p_market"] is not None) == (admitted > 0)
        covered += admitted > 0
    assert state["external_cutoff_coverage"] == v2["v2_coverage"] == {"passed": covered, "total": 5}
    assert v2["v1_coverage"] == {"passed": 2, "total": 5}
    assert (
        state["external_quote_count"] == v2["external_quote_count"] == v2["dataset_counts"]["external_quotes"]
    )
