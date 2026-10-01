import copy
import json
from datetime import UTC, datetime, timedelta
from decimal import ROUND_UP, Context, Decimal, FloatOperation, Inexact, localcontext
from random import Random

import pytest
from jc.analysis.contracts import FeatureData
from jc.analysis.features import get_or_create_snapshot
from jc.analysis.goals_baseline import (
    DECIMAL_PRECISION,
    GOALS_BASELINE_VERSION,
    MAX_MATCHES_PER_TEAM,
    MIN_MATCHES_PER_TEAM,
    estimate_goals_baseline,
)
from jc.analysis.score_matrix import build_score_matrix
from test_features import Timeline, add_past_facts

D = Decimal


def record(mid, home="home", away="opponent", hs=2, aws=1, day=0, **updates):
    return dict(
        match_id=mid,
        home_team_id=home,
        away_team_id=away,
        home_score=hs,
        away_score=aws,
        finished_at=(datetime(2025, 1, 1, tzinfo=UTC) + timedelta(days=day)).isoformat(),
        source="sporttery",
        **updates,
    )


def feature(rows):
    return FeatureData(
        market={},
        odds_movement={},
        team_strength={"past_results": rows, "past_stats": []},
        schedule={},
        squad={},
        context={"match": {"home_team_id": "home", "away_team_id": "away"}},
        data_quality={},
    )


@pytest.fixture
def golden():
    rows = []
    for team, gf, ga in (
        ("home", [2, 1, 3, 0, 4], [1, 1, 2, 1, 0]),
        ("away", [1, 1, 2, 1, 0], [2, 2, 1, 1, 4]),
    ):
        for i, (scored, conceded) in enumerate(zip(gf, ga, strict=True)):
            # Both target teams appear in both historical home/away roles.
            rows.append(
                record(f"{team}-{i}", "opponent", team, conceded, scored, i)
                if i % 2
                else record(f"{team}-{i}", team, "opponent", scored, conceded, i)
            )
    return feature(rows)


def test_versioned_rules():
    assert GOALS_BASELINE_VERSION == "goals-baseline-v1"
    assert MAX_MATCHES_PER_TEAM == 20
    assert MIN_MATCHES_PER_TEAM == 5
    assert DECIMAL_PRECISION == 50


def test_hand_calculated_golden_case(golden):
    result = estimate_goals_baseline(golden)
    assert result["version"] == GOALS_BASELINE_VERSION
    assert result["status"] == "OK"
    assert result["home_team_id"] == "home" and result["away_team_id"] == "away"
    assert result["home_history"]["matches_used"] == result["away_history"]["matches_used"] == 5
    assert (result["home_history"]["gf_rate"], result["home_history"]["ga_rate"]) == ("2", "1")
    assert (result["away_history"]["gf_rate"], result["away_history"]["ga_rate"]) == ("1", "2")
    assert (result["lambda_home"], result["lambda_away"]) == ("2", "1")
    assert result["rho"] == "0" and result["rho_source"] == "fixed-zero-v1"
    assert result["score_engine_version"] == "score-math-v1"
    assert result["score"] == build_score_matrix(D(2), D(1), D(0))
    assert result["diagnostics"] == result["excluded_match_ids"] == []


@pytest.mark.parametrize("target", ["home", "away"])
@pytest.mark.parametrize("historical_role", ["home", "away"])
def test_goals_follow_historical_team_identity(target, historical_role):
    rows = [
        record(str(i), target, "opponent", 3, 1)
        if historical_role == "home"
        else record(str(i), "opponent", target, 1, 3)
        for i in range(5)
    ]
    history = estimate_goals_baseline(feature(rows))[f"{target}_history"]
    assert history["matches_used"] == 5
    assert history["gf_rate"] == "3" and history["ga_rate"] == "1"


def test_consistent_sources_count_once_and_do_not_weight_rates(golden):
    before = estimate_goals_baseline(golden)
    rows = golden.team_strength["past_results"]
    rows.extend([{**rows[0], "source": "external"}, copy.deepcopy(rows[0])])
    result = estimate_goals_baseline(golden)
    assert result["home_history"]["matches_used"] == 5
    assert result["home_history"]["evidence_source_count"]["home-0"] == 2
    assert result["score"] == before["score"]
    assert result["diagnostics"] == []


def test_conflicting_sources_excluded_without_vote_latest_or_preference(golden):
    rows = golden.team_strength["past_results"]
    original = rows[0]
    rows.extend([{**original, "source": f"agree-{i}"} for i in range(4)])
    rows.append({**original, "source": "external", "home_score": 1, "observed_at": "2099-01-01"})
    result = estimate_goals_baseline(golden)
    assert result["excluded_match_ids"] == ["home-0"]
    assert result["diagnostics"] == ["CONFLICTING_RESULT_SOURCES", "INSUFFICIENT_HOME_HISTORY"]
    assert result["home_history"]["matches_used"] == 4
    assert result["lambda_home"] is result["lambda_away"] is result["score"] is None


def test_conflicts_keep_diagnostic_when_remaining_samples_suffice(golden):
    golden.team_strength["past_results"].extend(
        [record("conflict", hs=3), {**record("conflict", hs=4), "source": "external"}]
    )
    result = estimate_goals_baseline(golden)
    assert result["status"] == "OK"
    assert result["diagnostics"] == ["CONFLICTING_RESULT_SOURCES"]
    assert result["excluded_match_ids"] == ["conflict"]
    assert result["lambda_home"] == "2"


def test_head_to_head_counts_for_each_team():
    result = estimate_goals_baseline(feature([record(str(i), "away", "home", 1, 2) for i in range(5)]))
    assert result["status"] == "OK"
    assert result["home_history"]["match_ids"] == result["away_history"]["match_ids"]
    assert result["home_history"]["gf_rate"] == result["away_history"]["ga_rate"] == "2"
    assert result["away_history"]["gf_rate"] == result["home_history"]["ga_rate"] == "1"


def test_lambda_combines_attack_and_opponent_defence_with_equal_weight():
    rows = [record(f"h-{i}", hs=2, aws=1) for i in range(5)]
    rows += [record(f"a-{i}", "away", "opponent", 3, 4) for i in range(5)]
    result = estimate_goals_baseline(feature(rows))
    assert result["lambda_home"] == "3"  # (home GF=2 + away GA=4) / 2
    assert result["lambda_away"] == "2"  # (away GF=3 + home GA=1) / 2
    assert result["score"] == build_score_matrix(D(3), D(2), D(0))


def test_most_recent_twenty_per_team_no_day_window_or_time_weights():
    rows = [record(f"h-{i:02}", day=i * 100) for i in range(25)]
    rows += [record(f"a-{i:02}", "away", "opponent", 1, 2, i * 100) for i in range(22)]
    rows[0]["home_score"] = 99  # Old evidence must not inflate lambda.
    result = estimate_goals_baseline(feature(rows))
    assert result["home_history"]["match_ids"] == [f"h-{i:02}" for i in range(24, 4, -1)]
    assert result["away_history"]["match_ids"] == [f"a-{i:02}" for i in range(21, 1, -1)]
    assert result["home_history"]["matches_used"] == result["away_history"]["matches_used"] == 20
    assert result["lambda_home"] == "2" and result["lambda_away"] == "1"


def test_dedup_and_conflict_exclusion_precede_window():
    rows = [record(f"h-{i:02}", day=i) for i in range(22)]
    rows += [{**rows[-1], "source": "external", "home_score": 3}]
    rows += [{**rows[20], "source": f"external-{i}"} for i in range(25)]
    result = estimate_goals_baseline(feature(rows))
    assert result["home_history"]["match_ids"] == [f"h-{i:02}" for i in range(20, 0, -1)]
    assert result["excluded_match_ids"] == ["h-21"]


def test_equal_timestamps_use_match_id_and_ignore_input_dict_source_order():
    rows = [record(f"m-{i:02}", "home", "away", 2, 1) for i in range(25)]
    rows += [{**rows[-1], "source": "external"}]
    expected = estimate_goals_baseline(feature(rows))
    assert expected["home_history"]["match_ids"] == [f"m-{i:02}" for i in range(20)]
    for seed in range(5):
        shuffled = [dict(reversed(list(row.items()))) for row in rows]
        Random(seed).shuffle(shuffled)
        assert estimate_goals_baseline(feature(shuffled)) == expected


def test_finished_at_compares_utc_and_uses_earliest_agreeing_evidence():
    rows = [record("a"), record("b")]
    rows[0]["finished_at"] = "2025-01-01T01:00:00+02:00"
    rows[1]["finished_at"] = "2025-01-01T00:00:00Z"
    rows.append({**rows[0], "source": "external", "finished_at": "2025-01-01T02:00:00Z"})
    assert estimate_goals_baseline(feature(rows))["home_history"]["match_ids"] == ["b", "a"]


@pytest.mark.parametrize("side", ["home", "away"])
def test_insufficient_history_has_no_default_or_engine_call(golden, monkeypatch, side):
    golden.team_strength["past_results"] = [
        row for row in golden.team_strength["past_results"] if row["match_id"] != f"{side}-0"
    ]
    monkeypatch.setattr("jc.analysis.goals_baseline.build_score_matrix", forbidden)
    result = estimate_goals_baseline(golden)
    assert result["status"] == "INSUFFICIENT_DATA"
    assert result["diagnostics"] == [f"INSUFFICIENT_{side.upper()}_HISTORY"]
    assert result["lambda_home"] is result["lambda_away"] is result["score"] is None


@pytest.mark.parametrize("side", ["home", "away"])
@pytest.mark.parametrize("missing", [None, "", " ", 12])
def test_missing_team_id_never_uses_names(golden, side, missing):
    golden.context["match"][f"{side}_team_id"] = missing
    golden.context["match"][f"{side}_team_name"] = side
    result = estimate_goals_baseline(golden)
    assert result["status"] == "INSUFFICIENT_DATA"
    assert f"MISSING_{side.upper()}_TEAM_ID" in result["diagnostics"]
    assert result["lambda_home"] is result["lambda_away"] is result["score"] is None


def test_same_target_team_is_rejected(golden):
    golden.context["match"]["away_team_id"] = "home"
    result = estimate_goals_baseline(golden)
    assert result["status"] == "INSUFFICIENT_DATA"
    assert "INVALID_TARGET_TEAMS" in result["diagnostics"]
    assert result["score"] is None


@pytest.mark.parametrize(
    "updates",
    [
        {"home_score": -1},
        {"away_score": -1},
        {"home_score": True},
        {"away_score": 1.0},
        {"home_score": "2"},
        {"away_score": None},
        {"match_id": None},
        {"match_id": []},
        {"home_team_id": "unrelated"},
        {"away_team_id": "home"},
        {"home_team_id": None},
        {"source": None},
        {"finished_at": None},
        {"finished_at": "bad"},
        {"finished_at": "2025-01-01T00:00:00"},
    ],
)
def test_invalid_records_do_not_enter_rates(golden, updates):
    bad = {**record("bad"), **updates}
    golden.team_strength["past_results"].append(bad)
    result = estimate_goals_baseline(golden)
    assert result["status"] == "OK"
    assert result["diagnostics"] == ["INVALID_RESULT_RECORD"]
    assert result["home_history"]["matches_used"] == 5
    assert result["lambda_home"] == "2" and result["lambda_away"] == "1"
    assert result["excluded_match_ids"] == (["bad"] if bad["match_id"] == "bad" else [])


@pytest.mark.parametrize("bad", [None, 1, "bad", []])
def test_malformed_row_is_diagnostic(golden, bad):
    golden.team_strength["past_results"].append(bad)
    assert estimate_goals_baseline(golden)["diagnostics"] == ["INVALID_RESULT_RECORD"]


@pytest.mark.parametrize("rows", [None, {}, "bad"])
def test_malformed_history_fails_safely(rows):
    result = estimate_goals_baseline(feature(rows))
    assert result["status"] == "INSUFFICIENT_DATA" and result["score"] is None
    assert "INVALID_RESULT_RECORD" in result["diagnostics"]


def test_invalid_peer_and_participant_conflict_exclude_whole_match(golden):
    rows = golden.team_strength["past_results"]
    rows += [{**rows[0], "source": "external", "finished_at": "bad"}]
    rows += [{**rows[1], "source": "external", "home_team_id": "other"}]
    result = estimate_goals_baseline(golden)
    assert result["excluded_match_ids"] == ["home-0", "home-1"]
    assert result["home_history"]["matches_used"] == 3
    assert "INVALID_RESULT_RECORD" in result["diagnostics"]


@pytest.mark.parametrize("section", ["market", "odds_movement", "past_stats"])
def test_market_odds_movement_and_xg_do_not_change_result(golden, section):
    before = estimate_goals_baseline(golden)
    if section == "past_stats":
        golden.team_strength[section] = [{"xg": "999", "xga": "999"}]
    else:
        setattr(golden, section, {"quotes": [{"decimal_odds": "999"}], "items": [{"line": "2.75"}]})
    assert estimate_goals_baseline(golden) == before


def forbidden(*args, **kwargs):
    raise AssertionError("Unexpected dependency access")


def test_only_allowed_feature_fields_are_read(golden):
    class RestrictedFeature(FeatureData):
        def __getattribute__(self, name):
            if name in {"market", "odds_movement", "schedule", "squad", "data_quality"}:
                forbidden()
            return super().__getattribute__(name)

    class RestrictedDict(dict):
        def get(self, key, *args):
            if key not in {"match", "past_results"}:
                forbidden()
            return super().get(key, *args)

        def __getitem__(self, key):
            if key not in {"match", "past_results"}:
                forbidden()
            return super().__getitem__(key)

        __iter__ = items = values = forbidden

    restricted = RestrictedFeature(**golden.model_dump())
    restricted.team_strength = RestrictedDict(restricted.team_strength)
    restricted.context = RestrictedDict(restricted.context)
    assert estimate_goals_baseline(restricted) == estimate_goals_baseline(golden)


def test_one_x_two_and_ttg_are_sums_of_computed_matrix(golden):
    score = estimate_goals_baseline(golden)["score"]
    with localcontext(Context(prec=80)):
        cells = [(i, j, D(p)) for i, row in enumerate(score["matrix"]) for j, p in enumerate(row)]
        expected = {
            "HOME": sum(p for i, j, p in cells if i > j),
            "DRAW": sum(p for i, j, p in cells if i == j),
            "AWAY": sum(p for i, j, p in cells if i < j),
        }
        for key, probability in expected.items():
            assert abs(D(score["one_x_two"][key]) - probability) < D("1e-45")
        for n in range(8):
            key = str(n) if n < 7 else "7+"
            probability = sum(p for i, j, p in cells if (i + j == n if n < 7 else i + j >= 7))
            assert abs(D(score["sporttery_ttg"][key]) - probability) < D("1e-45")


@pytest.mark.parametrize("goals", [8, 31])
def test_score_engine_range_error_preserves_lambda_without_clamp(goals):
    result = estimate_goals_baseline(feature([record(str(i), "home", "away", goals, 1) for i in range(5)]))
    assert result["status"] == "OUT_OF_RANGE"
    assert result["lambda_home"] == str(goals) and result["lambda_away"] == "1"
    assert result["score"] is None
    assert result["diagnostics"] == ["SCORE_ENGINE_RANGE_EXCEEDED"]


def test_zero_goal_history_does_not_invent_prior():
    result = estimate_goals_baseline(feature([record(str(i), "home", "away", 0, 0) for i in range(5)]))
    assert result["status"] == "OK"
    assert result["lambda_home"] == result["lambda_away"] == "0"
    assert result["score"]["one_x_two"] == {"HOME": "0", "DRAW": "1", "AWAY": "0"}


def test_empty_history_keeps_unknown_rates_and_lambdas():
    result = estimate_goals_baseline(feature([]))
    assert result["home_history"]["gf_rate"] is result["away_history"]["ga_rate"] is None
    assert result["lambda_home"] is result["lambda_away"] is result["score"] is None


def test_context_determinism_input_immutability_and_json(golden):
    # Six matches force recurring decimals, exercising the estimator's own context.
    golden.team_strength["past_results"].append(record("extra", hs=1, aws=0))
    before = copy.deepcopy(golden)
    expected = estimate_goals_baseline(golden)
    with localcontext() as ctx:
        ctx.prec, ctx.rounding = 3, ROUND_UP
        ctx.Emin, ctx.Emax, ctx.capitals, ctx.clamp = -2, 2, 0, 1
        ctx.traps[Inexact] = ctx.traps[FloatOperation] = True
        ctx.clear_flags()
        for _ in range(3):
            assert estimate_goals_baseline(golden) == expected
        assert not any(ctx.flags.values())
    assert golden == before
    assert json.loads(json.dumps(expected, allow_nan=False)) == expected

    def check(value):
        assert not isinstance(value, (float, Decimal))
        if isinstance(value, dict):
            assert not set(value) & {"P_final", "Edge", "EV", "CORE", "WATCH", "PASS", "confidence"}
            for item in value.values():
                check(item)
        elif isinstance(value, list):
            for item in value:
                check(item)

    check(expected)


def test_diagnostics_and_excluded_ids_have_stable_unique_order(golden):
    rows = golden.team_strength["past_results"]
    rows += [record("z", hs=-1), record("a", hs=-1), {**rows[0], "source": "external", "home_score": 9}]
    expected = estimate_goals_baseline(golden)
    assert expected["diagnostics"] == [
        "CONFLICTING_RESULT_SOURCES",
        "INSUFFICIENT_HOME_HISTORY",
        "INVALID_RESULT_RECORD",
    ]
    assert expected["excluded_match_ids"] == ["a", "home-0", "z"]
    rows.reverse()
    assert estimate_goals_baseline(golden) == expected


def test_frozen_snapshot_target_exclusion_and_no_io_after_database_changes(sessions, monkeypatch):
    timeline = Timeline(sessions, monkeypatch)
    with sessions() as db:
        for i in range(5):
            mid, vid = timeline.match(db, kickoff=timeline.start - timedelta(days=i + 1))
            add_past_facts(timeline, db, mid, vid)
        add_past_facts(timeline, db, timeline.match_id, timeline.version_id)
        db.commit()
        snapshot = get_or_create_snapshot(db, timeline.match_id, timeline.cutoff, mock=True)
        db.commit()
        frozen = FeatureData.model_validate(snapshot.feature_data)
    before = copy.deepcopy(frozen)
    assert all(r["match_id"] != timeline.match_id for r in frozen.team_strength["past_results"])
    expected = estimate_goals_baseline(frozen)
    assert expected["status"] == "OK" and expected["home_history"]["matches_used"] == 5
    timeline.now = timeline.cutoff + timedelta(minutes=1)
    with sessions() as db:
        mid, vid = timeline.match(db, kickoff=timeline.start - timedelta(days=10))
        add_past_facts(timeline, db, mid, vid, xg="99")
        db.commit()
    with monkeypatch.context() as guard:
        guard.setattr("sqlalchemy.engine.Connection.execute", forbidden)
        guard.setattr("sqlalchemy.orm.Session.execute", forbidden)
        guard.setattr("socket.socket", forbidden)
        guard.setattr("jc.time.utcnow", forbidden)
        assert estimate_goals_baseline(frozen) == expected
    assert frozen == before
