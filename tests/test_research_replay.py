import ast
import copy
import json
import subprocess
import sys
from dataclasses import FrozenInstanceError, asdict, replace
from datetime import UTC, datetime, timedelta, timezone
from decimal import Context, Decimal, Inexact, localcontext
from pathlib import Path

import pytest
from jc.analysis import research_replay as replay
from jc.analysis.evaluation import evaluate_models, goals_evaluation_sample, market_evaluation_sample
from jc.analysis.goals_baseline import estimate_goals_baseline
from jc.analysis.market import build_market_data
from jc.analysis.research_replay import (
    RESEARCH_REPLAY_VERSION,
    AvailabilityBasis,
    NotReplayable,
    ReplayCutoffSpec,
    ResearchDataset,
    ResearchMatch,
    ResearchOddsQuote,
    ResearchResult,
    ResearchSource,
    build_research_evaluation_samples,
    build_research_feature,
    run_research_evaluation,
)

D = Decimal
T = datetime(2024, 6, 1, 12, tzinfo=UTC)
CUTOFF = T - timedelta(minutes=30)
SPEC = ReplayCutoffSpec(30)
BASIS = AvailabilityBasis.SOURCE_SNAPSHOT_AT


def match(mid="target", home="home", away="away", kickoff=T, **changes):
    return replace(
        ResearchMatch(
            research_match_id=mid,
            sporttery_match_id=f"official:{mid}",
            competition_id="league",
            home_team_id=home,
            away_team_id=away,
            kickoff_at=kickoff,
            source="fixture",
            source_record_id=f"source:{mid}",
            published_at=kickoff - timedelta(days=2),
            replay_available_at=kickoff - timedelta(days=2),
            availability_basis=BASIS,
        ),
        **changes,
    )


def quote(rid="quote", **changes):
    return replace(
        ResearchOddsQuote(
            record_id=rid,
            research_match_id="target",
            provider="fixture",
            bookmaker="book-a",
            market_type="1X2",
            selection="HOME",
            line=None,
            decimal_odds=D("2.50"),
            published_at=T - timedelta(hours=8),
            effective_at=T - timedelta(hours=8),
            replay_available_at=T - timedelta(hours=8),
            availability_basis=BASIS,
        ),
        **changes,
    )


def result(m=None, rid=None, **changes):
    m = m or match()
    finish = m.kickoff_at + timedelta(hours=2)
    return replace(
        ResearchResult(
            record_id=rid or f"result:{m.research_match_id}",
            research_match_id=m.research_match_id,
            home_team_id=m.home_team_id,
            away_team_id=m.away_team_id,
            home_score=2,
            away_score=1,
            finished_at=finish,
            source="fixture",
            published_at=finish + timedelta(minutes=1),
            replay_available_at=finish + timedelta(minutes=1),
            availability_basis=BASIS,
        ),
        **changes,
    )


def dataset(matches=None, odds=(), results=(), **changes):
    return replace(
        ResearchDataset(
            dataset_id="synthetic-history",
            dataset_version="fixture-v1",
            replay_version=RESEARCH_REPLAY_VERSION,
            matches=tuple(matches or (match(),)),
            odds=tuple(odds),
            results=tuple(results),
            source_manifest=(
                ResearchSource(
                    source_name="fixture",
                    source_type="SYNTHETIC_FIXTURE",
                    retrieval_note="No retrieval; synthetic evidence for tests.",
                ),
                ResearchSource(
                    source_name="second",
                    source_type="SYNTHETIC_FIXTURE",
                    retrieval_note="Independent synthetic source.",
                ),
            ),
        ),
        **changes,
    )


@pytest.fixture
def historical():
    matches = [match()]
    for side in ("home", "away"):
        for i in range(6):
            # Vary venue; only canonical IDs identify the target participant.
            home, away = (side, f"opponent-{side}-{i}") if i % 2 else (f"opponent-{side}-{i}", side)
            matches.append(match(f"{side}-{i}", home, away, T - timedelta(days=i + 3)))
    odds = []
    for bookmaker in ("book-a", "book-b"):
        for selection, price in (("HOME", "2.5"), ("DRAW", "3.0"), ("AWAY", "3.5")):
            odds.append(
                quote(
                    f"{bookmaker}-{selection}-old",
                    bookmaker=bookmaker,
                    selection=selection,
                    decimal_odds=D(price),
                )
            )
            odds.append(
                quote(
                    f"{bookmaker}-{selection}-new",
                    bookmaker=bookmaker,
                    selection=selection,
                    decimal_odds=D(price),
                    effective_at=T - timedelta(hours=1),
                )
            )
    return dataset(matches, odds, [result(m) for m in matches])


def feature(ds):
    return build_research_feature(ds, "target", SPEC)


def test_research_semantics_and_quality_are_explicit(historical):
    f = feature(historical)
    context = f.context["research"]
    assert RESEARCH_REPLAY_VERSION == "research-replay-v1"
    assert context["mode"] == context["evaluation_mode"] == "RESEARCH_REPLAY"
    assert context["live_visibility_proven"] is False
    assert "LIVE_AS_OBSERVED" not in f.model_dump_json()
    assert "availability-v1" not in f.model_dump_json()
    assert context["canonical_identity_basis"] == "RESEARCH_DATASET"
    assert f.data_quality == {
        "research_data_quality": {
            "match_available": True,
            "market_source_count": 2,
            "historical_result_count_home": 6,
            "historical_result_count_away": 6,
            "records_without_verified_availability": 0,
        }
    }
    assert f.team_strength["past_stats"] == [] and f.team_strength["rating"] is None


@pytest.mark.parametrize("minutes", [30, 90, 360])
def test_cutoff_is_fixed_before_kickoff(minutes):
    f = build_research_feature(dataset(), "target", ReplayCutoffSpec(minutes))
    assert datetime.fromisoformat(f.context["research"]["analysis_cutoff"]) == T - timedelta(minutes=minutes)
    assert f.schedule["seconds_to_kickoff"] == minutes * 60


@pytest.mark.parametrize("minutes", [0, -1, True, 30.0, "30"])
def test_invalid_cutoff_minutes_rejected(minutes):
    with pytest.raises(ValueError):
        ReplayCutoffSpec(minutes)


def test_unsupported_cutoff_kind_rejected():
    with pytest.raises(ValueError):
        ReplayCutoffSpec(30, "BEST_AVAILABLE")


@pytest.mark.parametrize("field", ["replay_available_at", "published_at", "effective_at"])
@pytest.mark.parametrize("offset,accepted", [(0, True), (1, False)])
def test_odds_each_time_gate(field, offset, accepted):
    q = quote(**{field: CUTOFF + timedelta(microseconds=offset)})
    f = feature(dataset(odds=[q]))
    assert bool(f.market["quotes"]) is accepted


@pytest.mark.parametrize("field", ["replay_available_at", "published_at", "effective_at"])
def test_target_match_unavailable_is_not_replayable(field):
    ds = dataset([match(**{field: CUTOFF + timedelta(microseconds=1)})])
    with pytest.raises(NotReplayable, match="NOT_REPLAYABLE"):
        feature(ds)
    report = run_research_evaluation(ds, ["target"], SPEC)
    assert report["matches_replayable"] == 0
    assert report["diagnostics"]["target"]["status"] == "NOT_REPLAYABLE"
    assert report["market_evaluable"] == report["goals_evaluable"] == 0


@pytest.mark.parametrize(
    "factory,field",
    [
        (match, "kickoff_at"),
        (match, "published_at"),
        (match, "effective_at"),
        (match, "replay_available_at"),
        (quote, "published_at"),
        (quote, "effective_at"),
        (quote, "replay_available_at"),
        (result, "finished_at"),
        (result, "published_at"),
        (result, "effective_at"),
        (result, "replay_available_at"),
    ],
)
def test_all_record_times_reject_naive(factory, field):
    with pytest.raises(ValueError, match="timezone-aware"):
        factory(**{field: T.replace(tzinfo=None)})


def test_all_time_fields_normalized_to_utc():
    east = timezone(timedelta(hours=8))
    for record in (match(), quote(), result()):
        for key, value in asdict(record).items():
            if isinstance(value, datetime):
                changed = replace(record, **{key: value.astimezone(east)})
                assert getattr(changed, key).tzinfo is UTC
                assert changed == record
    with pytest.raises(ValueError, match="timezone-aware"):
        SPEC.at(T.replace(tzinfo=None))


@pytest.mark.parametrize("basis", list(AvailabilityBasis))
def test_verified_basis_uses_explicit_evidence(basis):
    when = T - timedelta(hours=8)
    q = quote(availability_basis=basis, replay_available_at=when, published_at=when, effective_at=when)
    assert q.availability_basis == basis
    assert feature(dataset(odds=[q])).market["quotes"][0]["availability_basis"] == basis.value


@pytest.mark.parametrize("basis", ["GUESSED", "UNKNOWN", "invented", 3])
def test_unverified_basis_rejected(basis):
    with pytest.raises(ValueError):
        quote(availability_basis=basis)


@pytest.mark.parametrize(
    "basis,field",
    [
        (AvailabilityBasis.PROVIDER_PUBLISHED_AT, "published_at"),
        (AvailabilityBasis.PROVIDER_EFFECTIVE_AT, "effective_at"),
    ],
)
@pytest.mark.parametrize("evidence", [None, T])
def test_missing_or_unequal_named_evidence_rejected(basis, field, evidence):
    with pytest.raises(ValueError, match="named time evidence"):
        quote(availability_basis=basis, **{field: evidence})


@pytest.mark.parametrize("changes", [{"replay_available_at": None}, {"availability_basis": None}])
def test_partial_availability_pair_rejected(changes):
    with pytest.raises(ValueError):
        quote(**changes)


def test_unavailable_records_retained_but_excluded():
    missing = {"replay_available_at": None, "availability_basis": None}
    h = match("past", kickoff=T - timedelta(days=3))
    ds = dataset([match(), h], [quote(**missing)], [result(h, **missing)])
    assert ds.odds[0].replay_status == "REPLAY_UNAVAILABLE"
    assert feature(ds).market["quotes"] == []
    assert feature(ds).team_strength["past_results"] == []
    assert feature(ds).data_quality["research_data_quality"]["records_without_verified_availability"] == 2
    with pytest.raises(NotReplayable):
        feature(dataset([match(**missing)]))


def test_latest_previous_stable_tie_and_fallbacks():
    rows = [
        quote("a", effective_at=CUTOFF),
        quote("b", effective_at=None, published_at=CUTOFF),
        quote("c", effective_at=None, published_at=None, replay_available_at=CUTOFF),
        quote("future", effective_at=CUTOFF + timedelta(seconds=1)),
    ]
    ds = dataset(odds=rows)
    f = feature(ds)
    assert f.market["quotes"][0]["odds_snapshot_id"] == "c"
    movement = f.odds_movement["items"][0]
    assert movement["previous_snapshot_id"] == "b"
    assert movement["previous_quote"]["published_at"] == CUTOFF.isoformat()
    assert f.context["research"]["input_record_ids"]["odds"] == ["b", "c"]
    assert feature(replace(ds, odds=tuple(reversed(rows)))) == f


def test_priority_is_coalesced_timestamp_not_input_order_or_availability():
    earlier = quote("z", effective_at=T - timedelta(hours=4), replay_available_at=CUTOFF)
    later = quote("a", effective_at=T - timedelta(hours=1))
    assert feature(dataset(odds=[later, earlier])).market["quotes"][0]["odds_snapshot_id"] == "a"


@pytest.mark.parametrize("field", ["replay_available_at", "published_at", "effective_at"])
def test_invisible_quotes_never_fill_previous(field):
    late = quote("late", **{field: T})
    f = feature(dataset(odds=[quote(), late]))
    assert f.odds_movement["items"][0]["previous_snapshot_id"] is None
    assert build_market_data(f)["movement"]["items"][0]["previous_odds"] is None


@pytest.mark.parametrize(
    "changes",
    [
        {"provider": "second"},
        {"bookmaker": "book-b"},
        {"selection": "AWAY"},
        {"market_type": "TOTALS"},
        {"line": D("1.5")},
    ],
)
def test_series_never_mix(changes):
    first = quote("one", line=D("1.25"))
    second = replace(first, record_id="two", **changes)
    f = feature(dataset(odds=[first, second]))
    assert len(f.market["quotes"]) == 2
    assert all(m["previous_snapshot_id"] is None for m in f.odds_movement["items"])


def test_equal_raw_decimal_lines_share_series_without_rounding():
    f = feature(dataset(odds=[quote("a", line=D("-0.5000")), quote("b", line=D("-0.5"))]))
    assert len(f.market["quotes"]) == 1
    assert f.odds_movement["items"][0]["previous_snapshot_id"] == "a"
    # Preserve distinct values beyond caller precision; no Decimal.normalize rounding.
    ds = dataset(odds=[quote("a", line=D("1.123456789")), quote("b", line=D("1.123456788"))])
    with localcontext(Context(prec=3, traps=[Inexact])):
        assert len(feature(ds).market["quotes"]) == 2


@pytest.mark.parametrize(
    "field,offset,accepted",
    [
        ("finished_at", -1, True),
        ("finished_at", 0, False),
        ("finished_at", 1, False),
        ("replay_available_at", 0, True),
        ("replay_available_at", 1, False),
        ("published_at", 0, True),
        ("published_at", 1, False),
        ("effective_at", 0, True),
        ("effective_at", 1, False),
    ],
)
def test_history_time_boundaries(field, offset, accepted):
    h = match("past", kickoff=T - timedelta(days=3))
    changes = {field: CUTOFF + timedelta(microseconds=offset)}
    if field == "finished_at":
        changes["replay_available_at"] = changes[field]
    r = result(h, **changes)
    assert bool(feature(dataset([match(), h], results=[r])).team_strength["past_results"]) is accepted


@pytest.mark.parametrize(
    "changes",
    [
        {"kickoff_at": CUTOFF},
        {"kickoff_at": T},
        {"replay_available_at": T},
        {"published_at": T},
        {"effective_at": T},
    ],
)
def test_historical_match_itself_must_be_available_and_earlier(changes):
    h = replace(match("past", kickoff=T - timedelta(days=3)), **changes)
    assert feature(dataset([match(), h], results=[result(h)])).team_strength["past_results"] == []


@pytest.mark.parametrize("offset", [-1, 0])
def test_impossible_historical_finish_rejected_by_dataset(offset):
    h = match("past", kickoff=T - timedelta(days=3))
    r = result(h, finished_at=h.kickoff_at + timedelta(microseconds=offset))
    with pytest.raises(ValueError, match="strictly after match kickoff_at"):
        dataset([match(), h], results=[r])


def test_target_result_with_forged_early_times_rejected_by_dataset(historical):
    early = result(
        finished_at=T - timedelta(days=20),
        published_at=T - timedelta(days=20),
        replay_available_at=T - timedelta(days=20),
    )
    with pytest.raises(ValueError, match="strictly after match kickoff_at"):
        replace(
            historical,
            results=tuple(r for r in historical.results if r.research_match_id != "target") + (early,),
        )


@pytest.mark.parametrize("offset", [-1, 0])
def test_target_finish_must_be_strictly_after_kickoff(offset):
    r = result(finished_at=T + timedelta(microseconds=offset))
    with pytest.raises(ValueError, match="strictly after match kickoff_at"):
        dataset(results=[r])


@pytest.mark.parametrize("historical_result", [False, True])
@pytest.mark.parametrize("basis", list(AvailabilityBasis))
@pytest.mark.parametrize("offset", [-1, 0])
def test_result_availability_cannot_precede_finish(historical_result, basis, offset):
    m = match("past", kickoff=T - timedelta(days=3)) if historical_result else match()
    r = result(m)
    when = r.finished_at + timedelta(microseconds=offset)
    r = replace(r, replay_available_at=when, availability_basis=basis, published_at=when, effective_at=when)
    matches = [match(), m] if historical_result else [m]
    if offset < 0:
        with pytest.raises(ValueError, match="replay_available_at must not precede finished_at"):
            dataset(matches, results=[r])
    else:
        ds = dataset(matches, results=[r])
        assert ds.results == (r,)
        assert r.replay_available_at == r.finished_at


@pytest.mark.parametrize("field", ["published_at", "effective_at"])
def test_non_basis_provider_time_may_precede_finish(historical, field):
    rows = tuple(replace(r, **{field: r.finished_at - timedelta(hours=3)}) for r in historical.results)
    ds = replace(historical, results=rows)
    report = run_research_evaluation(ds, ["target"], SPEC)
    assert report["market_evaluable"] == report["goals_evaluable"] == 1
    assert ds.results == rows  # No automatic time correction.


def test_target_labels_cannot_change_feature_quality_or_provenance(historical):
    without = replace(
        historical, results=tuple(r for r in historical.results if r.research_match_id != "target")
    )
    unavailable = result(replay_available_at=None, availability_basis=None)
    with_unavailable = replace(without, results=without.results + (unavailable,))
    assert feature(without) == feature(with_unavailable) == feature(historical)


def test_head_to_head_history_belongs_to_both_teams():
    h = match("past", "away", "home", T - timedelta(days=3))
    f = feature(dataset([match(), h], results=[result(h)]))
    quality = f.data_quality["research_data_quality"]
    assert quality["historical_result_count_home"] == quality["historical_result_count_away"] == 1
    goals = estimate_goals_baseline(f)
    assert goals["home_history"]["match_ids"] == goals["away_history"]["match_ids"] == ["past"]
    assert goals["home_history"]["gf_rate"] == "1"
    assert goals["away_history"]["gf_rate"] == "2"


@pytest.mark.parametrize("record_kind", ["match", "result"])
@pytest.mark.parametrize("field", ["home_team_id", "away_team_id"])
def test_missing_canonical_ids_exclude_history(record_kind, field):
    h = match("past", kickoff=T - timedelta(days=3))
    r = result(h)
    h = replace(h, **{field: None}) if record_kind == "match" else h
    r = replace(r, **{field: None}) if record_kind == "result" else r
    assert feature(dataset([match(), h], results=[r])).team_strength["past_results"] == []


def test_unrelated_teams_are_not_history_and_identity_mismatch_rejected():
    h = match("past", "unrelated-1", "unrelated-2", T - timedelta(days=3))
    assert feature(dataset([match(), h], results=[result(h)])).team_strength["past_results"] == []
    with pytest.raises(ValueError, match="canonical team identity"):
        dataset([match(), h], results=[result(h, home_team_id="home")])


@pytest.mark.parametrize("conflict", [False, True])
def test_historical_multisource_records_preserved_for_baseline(historical, conflict):
    peer = next(r for r in historical.results if r.research_match_id == "home-0")
    peer = replace(
        peer, record_id="second-home-0", source="second", home_score=3 if conflict else peer.home_score
    )
    f = feature(replace(historical, results=historical.results + (peer,)))
    assert len([r for r in f.team_strength["past_results"] if r["match_id"] == "home-0"]) == 2
    goals = estimate_goals_baseline(f)
    assert goals["status"] == "OK"
    assert ("home-0" in goals["excluded_match_ids"]) is conflict
    assert goals["home_history"]["matches_used"] == (5 if conflict else 6)
    if not conflict:
        assert goals["home_history"]["evidence_source_count"]["home-0"] == 2


def test_full_research_evaluation_integration(historical):
    assert len(historical.matches) == 13
    f = feature(historical)
    market, goals = build_market_data(f), estimate_goals_baseline(f)
    assert market["external_consensus"]["source_count"] == 2
    assert goals["home_history"]["matches_used"] == goals["away_history"]["matches_used"] == 6
    market_sample = market_evaluation_sample(
        market, sample_id="market", match_id="target", actual_result="HOME", match_time=T
    )
    goals_sample = goals_evaluation_sample(
        goals, sample_id="goals", match_id="target", actual_result="HOME", match_time=T
    )
    assert market_sample is not None and goals_sample is not None
    evaluated = evaluate_models(
        {"market-v1": [market_sample], "goals-baseline-v1": [goals_sample]}, baseline="market-v1"
    )
    for metrics in evaluated["models"].values():
        assert metrics["sample_size"] == 1
        assert D(metrics["log_loss"]).is_finite()
        assert D(metrics["brier_score"]).is_finite()
    report = run_research_evaluation(historical, ["target"], SPEC)
    assert report["market_evaluable"] == report["goals_evaluable"] == 1
    assert report["evaluation_mode"] == "RESEARCH_REPLAY"
    assert report["live_visibility_proven"] is False
    # Core's narrower frozen-sample assertion is unchanged inside the envelope.
    assert report["evaluation"]["evaluation_mode"] == "FROZEN_SAMPLE_SET"
    assert set(report["evaluation"]["models"]) == {
        "market-v1@research-T30M",
        "goals-baseline-v1@research-T30M",
    }


@pytest.mark.parametrize("scores,actual", [((2, 1), "HOME"), ((1, 1), "DRAW"), ((0, 1), "AWAY")])
def test_target_result_is_post_cutoff_label_only(historical, scores, actual):
    ds = replace(
        historical,
        results=tuple(
            replace(r, home_score=scores[0], away_score=scores[1]) if r.research_match_id == "target" else r
            for r in historical.results
        ),
    )
    assert feature(ds) == feature(historical)
    samples, report = build_research_evaluation_samples(ds, ["target"], SPEC)
    assert {s.actual_result for group in samples.values() for s in group} == {actual}
    detail = report["diagnostics"]["target"]
    assert detail["label_record_ids"] == ["result:target"]
    for ids in detail["input_record_ids"].values():
        assert set(detail["label_record_ids"]).isdisjoint(ids)
    assert "result:target" not in f"{feature(ds).model_dump()}"


@pytest.mark.parametrize("field", ["home_team_id", "away_team_id"])
@pytest.mark.parametrize("valid_peer", [False, True])
def test_target_result_missing_identity_cannot_evaluate(historical, field, valid_peer):
    rows = tuple(r for r in historical.results if r.research_match_id != "target")
    rows += (result(**{field: None}),)
    if valid_peer:
        rows += (result(rid="peer-target", source="second"),)
    ds = replace(historical, results=rows)
    assert feature(ds) == feature(historical)
    samples, report = build_research_evaluation_samples(ds, ["target"], SPEC)
    assert all(not group for group in samples.values())
    detail = report["diagnostics"]["target"]
    assert detail["status"] == "NOT_EVALUABLE"
    assert detail["diagnostics"] == ["TARGET_RESULT_CANONICAL_IDENTITY_MISSING"]
    assert detail["label_record_ids"] == (
        ["peer-target", "result:target"] if valid_peer else ["result:target"]
    )


@pytest.mark.parametrize("field", ["home_team_id", "away_team_id"])
def test_target_result_identity_mismatch_rejected(field):
    with pytest.raises(ValueError, match="canonical team identity"):
        dataset(results=[result(**{field: "wrong-team"})])


@pytest.mark.parametrize("field", ["home_team_id", "away_team_id"])
def test_target_missing_identity_cannot_evaluate_even_with_market(historical, field):
    ds = replace(
        historical,
        matches=tuple(
            replace(m, **{field: None}) if m.research_match_id == "target" else m for m in historical.matches
        ),
    )
    assert build_market_data(feature(ds))["external_consensus"]["p_market"] is not None
    report = run_research_evaluation(ds, ["target"], SPEC)
    assert report["matches_replayable"] == 1
    assert report["market_evaluable"] == report["goals_evaluable"] == 0
    assert report["diagnostics"]["target"]["status"] == "NOT_EVALUABLE"
    assert report["diagnostics"]["target"]["diagnostics"] == ["TARGET_CANONICAL_IDENTITY_MISSING"]


def test_target_outside_sporttery_pool_is_not_replayable(historical):
    ds = replace(
        historical,
        matches=historical.matches + (match("external", sporttery_match_id=None),),
        odds=historical.odds
        + tuple(
            replace(q, record_id=f"external:{q.record_id}", research_match_id="external")
            for q in historical.odds
        ),
        results=historical.results + (result(match("external", sporttery_match_id=None)),),
    )
    with pytest.raises(NotReplayable, match="TARGET_NOT_IN_SPORTTERY_POOL") as error:
        build_research_feature(ds, "external", SPEC)
    assert error.value.diagnostic == "TARGET_NOT_IN_SPORTTERY_POOL"
    report = run_research_evaluation(ds, ["target", "external"], SPEC)
    assert report["matches_total"] == 2 and report["matches_replayable"] == 1
    assert report["market_evaluable"] == report["goals_evaluable"] == 1
    detail = report["diagnostics"]["external"]
    assert detail["status"] == "NOT_REPLAYABLE"
    assert detail["diagnostics"] == ["TARGET_NOT_IN_SPORTTERY_POOL"]
    assert detail["input_match_ids"] == []
    assert detail["input_record_ids"] == {"match_source_records": [], "odds": [], "results": []}
    for metrics in report["evaluation"]["models"].values():
        assert metrics["eligible_samples"] == 2 and metrics["coverage"] == "0.5"


@pytest.mark.parametrize("value", ["", "   ", 123])
def test_sporttery_id_must_be_nonempty_string_when_present(value):
    with pytest.raises(ValueError, match="sporttery_match_id must be a nonempty string"):
        match(sporttery_match_id=value)


def test_non_sporttery_history_still_feeds_goals(historical):
    ds = replace(
        historical,
        matches=tuple(
            replace(m, sporttery_match_id=None) if m.research_match_id != "target" else m
            for m in historical.matches
        ),
    )
    assert feature(ds) == feature(historical)
    report = run_research_evaluation(ds, ["target", "home-0"], SPEC)
    assert report["market_evaluable"] == report["goals_evaluable"] == 1
    assert report["diagnostics"]["home-0"]["diagnostics"] == ["TARGET_NOT_IN_SPORTTERY_POOL"]


@pytest.mark.parametrize("other_score", [1, 3])
def test_conflicting_target_scores_not_evaluable_even_if_outcome_agrees(historical, other_score):
    ds = replace(
        historical,
        results=historical.results + (result(rid="peer-target", source="second", home_score=other_score),),
    )
    samples, report = build_research_evaluation_samples(ds, ["target"], SPEC)
    assert all(not rows for rows in samples.values())
    assert report["matches_replayable"] == 1
    assert report["diagnostics"]["target"]["status"] == "NOT_EVALUABLE"
    assert report["diagnostics"]["target"]["diagnostics"] == ["CONFLICTING_TARGET_RESULT"]


def test_consistent_multisource_label_produces_only_one_sample_per_model(historical):
    ds = replace(historical, results=historical.results + (result(rid="peer-target", source="second"),))
    samples, report = build_research_evaluation_samples(ds, ["target"], SPEC)
    assert all(len(rows) == 1 for rows in samples.values())
    assert report["diagnostics"]["target"]["label_record_ids"] == ["peer-target", "result:target"]


@pytest.mark.parametrize("missing", [True, False])
def test_missing_or_unverified_label_cannot_evaluate(historical, missing):
    rows = tuple(r for r in historical.results if r.research_match_id != "target")
    if not missing:
        rows += (result(replay_available_at=None, availability_basis=None),)
    report = run_research_evaluation(replace(historical, results=rows), ["target"], SPEC)
    assert report["market_evaluable"] == report["goals_evaluable"] == 0
    assert report["diagnostics"]["target"]["diagnostics"] == [
        "MISSING_TARGET_RESULT" if missing else "TARGET_RESULT_REPLAY_UNAVAILABLE"
    ]


def test_one_policy_per_run_and_denominator_includes_failed_targets(historical):
    ds = replace(historical, matches=historical.matches + (match("unavailable", replay_available_at=T),))
    for minutes in (30, 360):
        report = run_research_evaluation(ds, ["unavailable", "target"], ReplayCutoffSpec(minutes))
        assert report["matches_total"] == 2 and report["matches_replayable"] == 1
        assert report["cutoff"] == {"kind": "MINUTES_BEFORE_KICKOFF", "minutes": minutes}
        for source, metrics in report["evaluation"]["models"].items():
            assert source.endswith(f"@research-T{minutes}M")
            assert metrics["eligible_samples"] == 2
            assert metrics["coverage"] == "0.5"


def test_models_with_missing_predictions_are_retained():
    report = run_research_evaluation(dataset(results=[result()]), ["target"], SPEC)
    assert report["diagnostics"]["target"]["status"] == "NOT_EVALUABLE"
    assert len(report["evaluation"]["models"]) == 2
    assert all(m["coverage"] == "0" for m in report["evaluation"]["models"].values())


@pytest.mark.parametrize("ids", [["target", "target"], ["unknown"]])
def test_invalid_run_cohort_rejected(ids):
    with pytest.raises(ValueError):
        run_research_evaluation(dataset(), ids, SPEC)


def test_unknown_feature_target_returns_stable_business_error():
    with pytest.raises(ValueError, match="^Unknown research target$"):
        build_research_feature(dataset(), "unknown", SPEC)


def test_empty_run_is_explicit():
    report = run_research_evaluation(dataset(), [], SPEC)
    assert report["matches_total"] == 0
    assert all(m["coverage"] is None for m in report["evaluation"]["models"].values())


def test_provenance_order_and_all_input_orders_deterministic(historical):
    shuffled = replace(
        historical,
        matches=historical.matches[::-1],
        odds=historical.odds[::-1],
        results=historical.results[::-1],
        source_manifest=historical.source_manifest[::-1],
    )
    f = feature(historical)
    assert f.model_dump_json() == feature(shuffled).model_dump_json()
    assert run_research_evaluation(historical, ["target", "home-0"], SPEC) == run_research_evaluation(
        shuffled, ["home-0", "target"], SPEC
    )
    meta = f.context["research"]
    assert meta["source_manifest"][0]["retrieval_note"].startswith("No retrieval")
    assert meta["dataset_id"] == historical.dataset_id and meta["dataset_version"] == "fixture-v1"
    for ids in meta["input_record_ids"].values():
        assert ids == sorted(ids)
    assert len(meta["input_record_ids"]["odds"]) == 12  # Includes every previous quote.
    assert len(meta["match_records"]) == 13
    assert {m["source_record_id"] for m in meta["match_records"]} == {
        m.source_record_id for m in historical.matches
    }


def test_match_provenance_separates_canonical_and_source_ids(historical):
    # An unused match is not an input; source IDs deliberately sort differently.
    ds = replace(
        historical,
        matches=tuple(
            replace(m, source_record_id=f"source:{i:02}") for i, m in enumerate(reversed(historical.matches))
        )
        + (match("unused", "unrelated-home", "unrelated-away"),),
    )
    meta = feature(ds).context["research"]
    canonical = sorted(m.research_match_id for m in historical.matches)
    source_ids = sorted(m.source_record_id for m in ds.matches if m.research_match_id != "unused")
    assert meta["input_match_ids"] == canonical
    assert meta["input_record_ids"]["match_source_records"] == source_ids
    assert set(meta["input_record_ids"]) == {"match_source_records", "odds", "results"}
    assert {(m["research_match_id"], m["source"], m["source_record_id"]) for m in meta["match_records"]} == {
        (m.research_match_id, m.source, m.source_record_id)
        for m in ds.matches
        if m.research_match_id != "unused"
    }
    detail = run_research_evaluation(ds, ["target"], SPEC)["diagnostics"]["target"]
    assert detail["input_match_ids"] == canonical
    assert detail["input_record_ids"] == meta["input_record_ids"]
    for ids in meta["input_record_ids"].values():
        assert set(detail["label_record_ids"]).isdisjoint(ids)


def test_duplicate_match_source_record_identity_rejected():
    with pytest.raises(ValueError, match="Duplicate match source record identity"):
        dataset([match(), match("other", source_record_id="source:target")])


def test_match_source_record_identity_is_scoped_by_source():
    ds = dataset([match(), match("other", source="second", source_record_id="source:target")])
    assert len(ds.matches) == 2


@pytest.mark.parametrize(
    "field,value",
    [
        ("decimal_odds", 2.5),
        ("decimal_odds", "2.5"),
        ("decimal_odds", D("NaN")),
        ("decimal_odds", D("Infinity")),
        ("decimal_odds", D("1")),
        ("line", 0.5),
        ("line", D("NaN")),
        ("line", D("Infinity")),
    ],
)
def test_odds_contract_rejects_float_and_invalid_decimal(field, value):
    with pytest.raises(ValueError):
        quote(**{field: value})


@pytest.mark.parametrize(
    "changes",
    [
        {"score_scope": "EXTRA_TIME"},
        {"home_score": -1},
        {"away_score": 1.0},
        {"home_score": True},
    ],
)
def test_regulation_integer_scores_only(changes):
    with pytest.raises(ValueError):
        result(**changes)


@pytest.mark.parametrize(
    "changes",
    [
        {"replay_version": "research-replay-v2"},
        {"matches": (match(), match())},
        {"odds": (quote(), quote())},
        {"results": (result(), result())},
        {"source_manifest": ()},
        {"odds": (quote(provider="unlisted"),)},
        {"odds": (quote(research_match_id="unknown"),)},
        {"matches": ({"fake": "orm"},)},
    ],
)
def test_invalid_dataset_rejected(changes):
    with pytest.raises(ValueError):
        dataset(**changes)


def test_contracts_and_caller_containers_immutable(historical):
    original = copy.deepcopy(historical)
    matches, odds, results = list(historical.matches), list(historical.odds), list(historical.results)
    ds = replace(historical, matches=matches, odds=odds, results=results)
    run_research_evaluation(ds, ["target"], SPEC)
    assert (matches, odds, results) == (list(original.matches), list(original.odds), list(original.results))
    matches.clear()
    odds.clear()
    results.clear()
    assert ds == original == historical
    for obj, field in (
        (ds, "dataset_id"),
        (ds.matches[0], "source"),
        (ds.odds[0], "bookmaker"),
        (ds.results[0], "source"),
        (ds.source_manifest[0], "retrieval_note"),
        (SPEC, "minutes"),
    ):
        with pytest.raises(FrozenInstanceError):
            setattr(obj, field, "mutated")
    built = feature(ds)
    built.market["quotes"].clear()
    assert feature(ds) == feature(original)


def test_decimal_and_json_no_float(historical):
    assert all(isinstance(q.decimal_odds, Decimal) for q in historical.odds)

    def no_float(value):
        if isinstance(value, dict):
            for item in value.values():
                no_float(item)
        elif isinstance(value, list):
            for item in value:
                no_float(item)
        else:
            assert not isinstance(value, float)

    f = feature(historical)
    no_float(json.loads(f.model_dump_json()))
    no_float(json.loads(json.dumps(run_research_evaluation(historical, ["target"], SPEC))))
    assert all(q["mapping_id"] is None and q["mapping_version"] is None for q in f.market["quotes"])
    assert D(
        feature(dataset(odds=[quote(decimal_odds=D("2.12345678901234567890123456789"))])).market["quotes"][0][
            "decimal_odds"
        ]
    ) == D("2.12345678901234567890123456789")


def test_no_io_no_live_reads_or_snapshot_writes(historical, monkeypatch):
    expected = run_research_evaluation(historical, ["target"], SPEC)

    def forbidden(*args, **kwargs):
        pytest.fail("Research pipeline attempted I/O or live state access")

    with monkeypatch.context() as guard:
        for path in (
            "sqlalchemy.engine.Connection.execute",
            "sqlalchemy.engine.Engine.connect",
            "sqlalchemy.orm.Session.execute",
            "sqlalchemy.orm.Session.add",
            "sqlalchemy.orm.Session.flush",
            "jc.analysis.visibility.record_visibility",
            "jc.analysis.visibility.proven",
            "jc.analysis.features.get_or_create_snapshot",
            "jc.time.utcnow",
            "socket.socket",
            "builtins.open",
            "time.time",
        ):
            guard.setattr(path, forbidden)
        assert run_research_evaluation(historical, ["target"], SPEC) == expected


def test_architecture_has_no_forbidden_imports_calls_or_identifiers():
    tree = ast.parse(Path(replay.__file__).read_text(encoding="utf-8"))
    allowed = {
        "collections",
        "collections.abc",
        "dataclasses",
        "datetime",
        "decimal",
        "enum",
        "jc.analysis.contracts",
        "jc.analysis.evaluation",
        "jc.analysis.goals_baseline",
        "jc.analysis.market",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert node.module in allowed
        if isinstance(node, ast.Import):
            assert all(alias.name in allowed for alias in node.names)
        if isinstance(node, ast.Name):
            assert node.id not in {
                "AnalysisVisibility",
                "record_visibility",
                "proven",
                "FeatureSnapshot",
                "MarketModelSnapshot",
                "open",
                "eval",
                "exec",
                "__import__",
            }
        if isinstance(node, ast.Attribute):
            assert node.attr not in {"now", "utcnow", "today", "read_text", "read_bytes"}


def test_fresh_import_needs_no_live_modules():
    script = """
import sys
class Guard:
    def find_spec(self, fullname, *args):
        if fullname.startswith(('sqlalchemy', 'jc.models', 'jc.db', 'jc.providers', 'jc.analysis.features', 'jc.analysis.visibility', 'jc.analysis.market_snapshots')):
            raise AssertionError(fullname)
sys.meta_path.insert(0, Guard())
from jc.analysis.research_replay import RESEARCH_REPLAY_VERSION
assert RESEARCH_REPLAY_VERSION == 'research-replay-v1'
"""
    completed = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr
