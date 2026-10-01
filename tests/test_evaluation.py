import copy
import json
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta, timezone
from decimal import ROUND_UP, Context, Decimal, FloatOperation, Inexact, localcontext
from itertools import permutations

import pytest
from jc.analysis.contracts import FeatureData
from jc.analysis.evaluation import (
    EVALUATION_VERSION,
    LOG_EPSILON,
    PROBABILITY_SUM_TOLERANCE,
    EvaluationSample,
    evaluate,
    evaluate_models,
    goals_evaluation_sample,
    market_evaluation_sample,
    temporal_split,
)
from jc.analysis.goals_baseline import estimate_goals_baseline
from jc.analysis.market import build_market_data

D = Decimal
OUTCOMES = ("HOME", "DRAW", "AWAY")


def sample(mid="m1", p=("0.7", "0.2", "0.1"), actual="HOME", source="market-v1", **kwargs):
    return EvaluationSample(
        f"{source}:{mid}", mid, source, dict(zip(OUTCOMES, p, strict=True)), actual, **kwargs
    )


@pytest.fixture
def golden():
    return (
        sample("m1"),
        sample("m2", ("0.2", "0.6", "0.2"), "DRAW"),
        sample("m3", ("0.1", "0.2", "0.7"), "AWAY"),
    )


def close(actual, expected):
    with localcontext(Context(prec=80)):
        assert abs(D(actual) - D(expected)) < D("1e-48")


def test_golden_three_matches_metrics_and_all_calibration_bins(golden):
    result = evaluate(golden)
    assert result["evaluation_version"] == EVALUATION_VERSION == "evaluation-v1"
    assert result["evaluation_mode"] == "FROZEN_SAMPLE_SET"
    assert result["sample_size"] == result["evaluated_samples"] == 3
    with localcontext(Context(prec=80)):
        # Independent hand formula: joint actual-probability product is .294.
        close(result["log_loss"], -D("0.294").ln() / 3)
        # (.09+.04+.01) + (.04+.16+.04) + (.01+.04+.09) = .52.
        close(result["brier_score"], D("0.52") / 3)
        close(result["ece"]["HOME"], D(1) / 5)
        close(result["ece"]["DRAW"], D(4) / 15)
        close(result["ece"]["AWAY"], D(1) / 5)
        close(result["ece"]["macro"], D(2) / 9)
    assert result["accuracy"] == "1" and result["clipping_count"] == 0
    # bin index -> (count, mean probability, empirical frequency, absolute error)
    expected = {
        "HOME": {1: (1, ".1", "0", ".1"), 2: (1, ".2", "0", ".2"), 7: (1, ".7", "1", ".3")},
        "DRAW": {2: (2, ".2", "0", ".2"), 6: (1, ".6", "1", ".4")},
        "AWAY": {1: (1, ".1", "0", ".1"), 2: (1, ".2", "0", ".2"), 7: (1, ".7", "1", ".3")},
    }
    for outcome, bins in result["calibration"].items():
        assert len(bins) == 10
        for i, row in enumerate(bins):
            assert D(row["lower_bound"]) == D(i) / 10
            assert D(row["upper_bound"]) == D(i + 1) / 10
            assert row["upper_inclusive"] == (i == 9)
            if i in expected[outcome]:
                count, mean, frequency, error = expected[outcome][i]
                assert row["count"] == count
                close(row["mean_predicted_probability"], mean)
                close(row["actual_frequency"], frequency)
                close(row["calibration_error"], error)
            else:
                assert row["count"] == 0
                assert row["mean_predicted_probability"] is None
                assert row["actual_frequency"] is row["calibration_error"] is None


@pytest.mark.parametrize("actual", OUTCOMES)
def test_perfect_prediction(actual):
    result = evaluate([sample(p=tuple("1" if k == actual else "0" for k in OUTCOMES), actual=actual)])
    assert result["log_loss"] == result["brier_score"] == "0"
    assert result["accuracy"] == "1" and result["clipping_count"] == 0
    assert set(result["ece"].values()) == {"0"}


def test_wrong_high_confidence_and_maximum_brier():
    result = evaluate([sample(p=("0", "1", "0"))])
    assert D(result["log_loss"]) > 34
    assert result["brier_score"] == "2" and result["accuracy"] == "0"
    assert result["clipping_count"] == 1


@pytest.mark.parametrize("probability,clipped", [("0", 1), ("1e-30", 1), ("1e-15", 0), ("1e-14", 0)])
def test_epsilon_clips_only_actual_probability_below_threshold(probability, clipped):
    row = (
        sample(p=(probability, "1", "0"))
        if D(probability) < D("1e-23")
        else sample(p=(probability, str(1 - D(probability)), "0"))
    )
    before = dict(row.probabilities)
    result = evaluate([row])
    assert LOG_EPSILON == D("1e-15")
    with localcontext(Context(prec=80)):
        close(result["log_loss"], -max(D(probability), D("1e-15")).ln())
    assert result["clipping_count"] == clipped
    assert dict(row.probabilities) == before
    # Calibration retains the original probability, including exact zero.
    assert D(result["calibration"]["HOME"][0]["mean_predicted_probability"]) == D(probability)


def test_clipping_count_across_samples():
    rows = [sample("a", ("0", "1", "0")), sample("b", ("1e-30", "1", "0")), sample("c")]
    assert evaluate(rows)["clipping_count"] == 2


def test_brier_is_sum_across_classes_not_class_mean():
    assert D(evaluate([sample(p=(".5", ".3", ".2"))])["brier_score"]) == D(".38")


@pytest.mark.parametrize(
    "bad",
    [
        -0.1,
        0.7,
        1,
        True,
        None,
        "bad",
        "",
        "NaN",
        "sNaN",
        "Infinity",
        "-Infinity",
        D("NaN"),
        D("sNaN"),
        D("Infinity"),
        D("-.1"),
        "-1e-80",
        "1.00000000000000000000000001",
    ],
)
def test_invalid_probabilities_rejected(bad):
    with pytest.raises(ValueError):
        sample(p=(bad, ".2", ".1"))


@pytest.mark.parametrize("values", [{}, {"HOME": "1"}, {"HOME": "1", "DRAW": "0", "AWAY": "0", "TIE": "0"}])
def test_exact_outcome_keys_required(values):
    with pytest.raises(ValueError, match="exactly"):
        EvaluationSample("s", "m", "source", values, "HOME")


@pytest.mark.parametrize("p", [(".6", ".2", ".1"), (".8", ".2", ".1"), ("0", "0", "0")])
def test_wrong_sum_rejected(p):
    with pytest.raises(ValueError, match="sum"):
        sample(p=p)


def test_sum_tolerance_boundary_is_exact_and_never_renormalized():
    with localcontext(Context(prec=100)):
        tolerance = PROBABILITY_SUM_TOLERANCE
        assert tolerance == D("1e-23")
        for sign in (-1, 1):
            p = (D(".7") + sign * tolerance, D(".2"), D(".1"))
            row = sample(p=p)
            assert tuple(row.probabilities.values()) == p
            close(
                evaluate([row])["calibration"]["HOME"][6 if sign < 0 else 7]["mean_predicted_probability"],
                p[0],
            )
            # Far beyond 50 digits: must not round an invalid sum onto the boundary.
            with pytest.raises(ValueError, match="sum"):
                sample(p=(p[0] + sign * D("1e-70"), p[1], p[2]))


@pytest.mark.parametrize("actual", ["home", "TIE", "1-0", "", None, 1])
def test_actual_result_is_explicit_and_strict(actual):
    with pytest.raises(ValueError, match="actual_result"):
        sample(actual=actual)


@pytest.mark.parametrize("field", ["sample_id", "match_id", "prediction_source"])
@pytest.mark.parametrize("value", ["", " ", None, 1])
def test_invalid_identity(field, value):
    args = dict(
        sample_id="s",
        match_id="m",
        prediction_source="source",
        probabilities=dict(zip(OUTCOMES, ("1", "0", "0"), strict=True)),
        actual_result="HOME",
    )
    args[field] = value
    with pytest.raises(ValueError, match=field):
        EvaluationSample(**args)


def test_duplicate_source_and_match_rejected_despite_different_sample_ids():
    first = sample()
    duplicate = EvaluationSample(
        "other-cutoff", first.match_id, first.prediction_source, first.probabilities, "HOME"
    )
    with pytest.raises(ValueError, match="Duplicate"):
        evaluate([first, duplicate])
    with pytest.raises(ValueError, match="Duplicate"):
        evaluate_models({"market-v1": [first, duplicate]}, baseline="market-v1")


@pytest.mark.parametrize(
    "p,winner",
    [
        ((".4", ".4", ".2"), "HOME"),
        ((".4", ".2", ".4"), "HOME"),
        ((".2", ".4", ".4"), "DRAW"),
        ((".333333333333333333333333",) * 3, "HOME"),
    ],
)
def test_accuracy_tie_priority_is_home_draw_away(p, winner):
    for actual in OUTCOMES:
        assert evaluate([sample(p=p, actual=actual)])["accuracy"] == ("1" if actual == winner else "0")


def test_accuracy_counts_correct_predictions():
    rows = [sample("a"), sample("b", actual="AWAY"), sample("c")]
    with localcontext(Context(prec=80)):
        close(evaluate(rows)["accuracy"], D(2) / 3)


@pytest.mark.parametrize(
    "p,index",
    [
        ("0", 0),
        (".099999999999999999999999999999999999999999999999999999999", 0),
        (".1", 1),
        (".2", 2),
        (".3", 3),
        (".4", 4),
        (".5", 5),
        (".6", 6),
        (".7", 7),
        (".8", 8),
        (".9", 9),
        ("1", 9),
    ],
)
def test_calibration_exact_bin_boundaries(p, index):
    with localcontext(Context(prec=100)):
        row = sample(p=(p, str(1 - D(p)), "0"))
    bins = evaluate([row])["calibration"]["HOME"]
    assert [i for i, b in enumerate(bins) if b["count"]] == [index]


def test_calibration_bin_error_is_absolute_difference_of_means():
    rows = [sample("a", (".21", ".70", ".09")), sample("b", (".29", ".70", ".01"), "DRAW")]
    result = evaluate(rows)
    bin_ = result["calibration"]["HOME"][2]
    assert bin_["count"] == 2
    assert D(bin_["mean_predicted_probability"]) == D(".25")
    assert D(bin_["actual_frequency"]) == D(".5")
    assert D(bin_["calibration_error"]) == D(".25")
    assert D(result["ece"]["HOME"]) == D(".25")


def test_empty_samples_have_null_metrics_and_all_empty_bins():
    result = evaluate([])
    assert result["sample_size"] == result["evaluated_samples"] == result["clipping_count"] == 0
    assert result["log_loss"] is result["brier_score"] is result["accuracy"] is None
    assert result["eligible_samples"] is result["coverage"] is result["prediction_source"] is None
    assert set(result["ece"].values()) == {None}
    assert all(
        b["count"] == 0
        and b["mean_predicted_probability"] is None
        and b["actual_frequency"] is None
        and b["calibration_error"] is None
        for bins in result["calibration"].values()
        for b in bins
    )


@pytest.mark.parametrize("eligible,coverage", [(3, "1"), (6, ".5"), (100, ".03"), (None, None)])
def test_coverage_uses_only_supplied_denominator(golden, eligible, coverage):
    result = evaluate(golden, eligible_samples=eligible)
    assert result["eligible_samples"] == eligible and result["evaluated_samples"] == 3
    assert result["coverage"] is None if coverage is None else D(result["coverage"]) == D(coverage)


@pytest.mark.parametrize("eligible", [-1, 2, 3.0, "3", True])
def test_invalid_coverage_denominator_rejected(golden, eligible):
    with pytest.raises(ValueError, match="eligible_samples"):
        evaluate(golden, eligible_samples=eligible)


def test_empty_coverage_zero_and_unknown_denominators():
    assert evaluate([], eligible_samples=0)["coverage"] is None
    assert evaluate([], eligible_samples=10)["coverage"] == "0"


def test_paired_intersection_direction_coverage_and_different_full_sets():
    base = [sample("common", (".5", ".3", ".2")), sample("base-only", ("0", "1", "0"))]
    candidate = [
        sample("common", source="goals-baseline-v1"),
        sample("candidate-only", ("1", "0", "0"), source="goals-baseline-v1"),
    ]
    result = evaluate_models(
        {"market-v1": base, "goals-baseline-v1": candidate},
        baseline="market-v1",
        eligible_samples={"market-v1": 4},
    )
    pair = result["paired_comparisons"][0]
    assert pair["baseline"] == "market-v1" and pair["candidate"] == "goals-baseline-v1"
    assert pair["direction"] == "candidate - baseline" and pair["negative_means"] == "candidate loss is lower"
    assert pair["common_sample_size"] == 1
    with localcontext(Context(prec=80)):
        close(pair["mean_log_loss_difference"], D(5).ln() - D(7).ln())
    close(pair["mean_brier_difference"], "-.24")
    assert result["models"]["market-v1"]["coverage"] == "0.5"
    assert result["models"]["goals-baseline-v1"]["coverage"] is None
    assert all(m["sample_size"] == 2 for m in result["models"].values())
    assert D(pair["mean_brier_difference"]) != D(result["models"]["goals-baseline-v1"]["brier_score"]) - D(
        result["models"]["market-v1"]["brier_score"]
    )
    reverse = evaluate_models(
        {"market-v1": base, "goals-baseline-v1": candidate}, baseline="goals-baseline-v1"
    )
    close(reverse["paired_comparisons"][0]["mean_brier_difference"], ".24")


def test_paired_mean_over_multiple_matches():
    result = evaluate_models(
        {
            "base": [sample("a", (".5", ".3", ".2"), source="base"), sample("b", source="base")],
            "candidate": [sample("a", source="candidate"), sample("b", source="candidate")],
        },
        baseline="base",
    )
    pair = result["paired_comparisons"][0]
    assert pair["common_sample_size"] == 2
    close(pair["mean_brier_difference"], "-.12")


@pytest.mark.parametrize("candidate", [[], [sample("unmatched", source="candidate")]])
def test_paired_no_common_samples(candidate):
    result = evaluate_models({"market-v1": [sample()], "candidate": candidate}, baseline="market-v1")
    pair = result["paired_comparisons"][0]
    assert pair["common_sample_size"] == 0
    assert pair["mean_log_loss_difference"] is pair["mean_brier_difference"] is None
    assert result["models"]["candidate"]["prediction_source"] == "candidate"


def test_model_validation_rejects_mixed_sources_bad_labels_and_conflicting_truth():
    with pytest.raises(ValueError, match="one prediction_source"):
        evaluate([sample(), sample(source="other")])
    with pytest.raises(ValueError, match="Model key"):
        evaluate_models({"wrong": [sample()]}, baseline="wrong")
    with pytest.raises(ValueError, match="baseline"):
        evaluate_models({}, baseline="absent")
    with pytest.raises(ValueError, match="Unknown model"):
        evaluate_models({"market-v1": []}, baseline="market-v1", eligible_samples={"other": 3})
    with pytest.raises(ValueError, match="Conflicting actual_result"):
        evaluate_models(
            {"market-v1": [sample()], "other": [sample(actual="AWAY", source="other")]}, baseline="market-v1"
        )
    with pytest.raises(ValueError, match="EvaluationSample"):
        evaluate([{}])


def test_all_input_orders_and_generators_have_identical_json(golden):
    expected = json.dumps(evaluate(golden))
    for order in permutations(golden):
        assert json.dumps(evaluate(iter(order))) == expected
    other = [sample(s.match_id, tuple(s.probabilities.values()), s.actual_result, "other") for s in golden]
    first = evaluate_models({"market-v1": golden, "other": other}, baseline="market-v1")
    second = evaluate_models({"other": reversed(other), "market-v1": reversed(golden)}, baseline="market-v1")
    assert json.dumps(first) == json.dumps(second)


def test_samples_freeze_copied_probabilities_and_do_not_mutate_input():
    probabilities = {"HOME": D(".7"), "DRAW": ".2", "AWAY": ".1"}
    before = copy.deepcopy(probabilities)
    row = EvaluationSample("s", "m", "source", probabilities, "HOME")
    expected = evaluate([row])
    assert probabilities == before
    probabilities["HOME"] = "0"
    assert evaluate([row]) == expected
    with pytest.raises(FrozenInstanceError):
        row.actual_result = "AWAY"
    with pytest.raises(TypeError):
        row.probabilities["HOME"] = D("0")


def test_external_decimal_context_is_ignored_and_unchanged(golden):
    expected = evaluate(golden)
    models = {"market-v1": golden, "other": [sample(source="other")]}
    paired = evaluate_models(models, baseline="market-v1")
    with localcontext() as context:
        context.prec, context.rounding = 3, ROUND_UP
        context.Emin, context.Emax, context.capitals, context.clamp = -2, 2, 0, 1
        context.traps[FloatOperation] = context.traps[Inexact] = True
        context.clear_flags()
        assert evaluate(golden) == expected
        assert evaluate_models(models, baseline="market-v1") == paired
        assert evaluate([sample()]) == evaluate([golden[0]])
        with pytest.raises(ValueError):
            sample(p=("not a number", "0", "1"))
        assert not any(context.flags.values())


def test_results_are_json_ready_without_float_or_ranking(golden):
    result = evaluate_models({"market-v1": golden, "other": []}, baseline="market-v1")
    forbidden = {
        "winner",
        "best_model",
        "confidence",
        "confidence_score",
        "roi",
        "yield",
        "ev",
        "clv",
        "edge",
        "p_final",
    }

    def check(value):
        assert not isinstance(value, (float, Decimal))
        if isinstance(value, dict):
            assert not {k.lower() for k in value} & forbidden
            for item in value.values():
                check(item)
        elif isinstance(value, list):
            for item in value:
                check(item)

    check(result)
    assert json.loads(json.dumps(result, allow_nan=False)) == result


def feature(rows=(), quotes=()):
    return FeatureData(
        market={"quotes": list(quotes)},
        odds_movement={"items": []},
        team_strength={"past_results": list(rows)},
        schedule={},
        squad={},
        context={"match": {"home_team_id": "h", "away_team_id": "a"}},
        data_quality={},
    )


def test_market_adapter_consumes_real_frozen_market_output_and_copies_it():
    quotes = [
        {
            "odds_snapshot_id": str(i),
            "provider": "external",
            "bookmaker": "book",
            "market_type": "1X2",
            "selection": k,
            "line": None,
            "decimal_odds": "3",
        }
        for i, k in enumerate(OUTCOMES)
    ]
    market = build_market_data(feature(quotes=quotes))
    before = copy.deepcopy(market)
    row = market_evaluation_sample(market, sample_id="s", match_id="m", actual_result="DRAW")
    assert row.prediction_source == "market-v1"
    assert row.probabilities == {k: D(v) for k, v in market["external_consensus"]["p_market"].items()}
    assert evaluate([row])["sample_size"] == 1
    assert market == before
    market["external_consensus"]["p_market"]["DRAW"] = "0"
    assert row.probabilities["DRAW"] > 0


def test_market_null_is_not_evaluable_even_with_sporttery_prices():
    market = {
        "version": "market-v1",
        "external_consensus": {"p_market": None},
        "sporttery": {"p_market": {"HOME": "1", "DRAW": "0", "AWAY": "0"}},
    }
    assert market_evaluation_sample(market, sample_id="s", match_id="m", actual_result="HOME") is None


@pytest.mark.parametrize("goals,status", [(2, "OK"), (8, "OUT_OF_RANGE"), (None, "INSUFFICIENT_DATA")])
def test_goals_adapter_real_result_status_and_no_mutation(goals, status):
    rows = (
        []
        if goals is None
        else [
            {
                "match_id": str(i),
                "home_team_id": "h",
                "away_team_id": "a",
                "home_score": goals,
                "away_score": 1,
                "finished_at": f"2024-01-0{i + 1}T00:00:00Z",
                "source": "fixture",
            }
            for i in range(5)
        ]
    )
    result = estimate_goals_baseline(feature(rows))
    before = copy.deepcopy(result)
    assert result["status"] == status
    row = goals_evaluation_sample(result, sample_id="s", match_id="m", actual_result="HOME")
    if status == "OK":
        assert row.prediction_source == "goals-baseline-v1"
        assert row.probabilities == {k: D(v) for k, v in result["score"]["one_x_two"].items()}
        assert evaluate([row])["sample_size"] == 1
    else:
        assert row is None
    assert result == before


def test_goals_adapter_requires_score_and_rejects_unknown_status():
    result = estimate_goals_baseline(feature())
    result["status"] = "OK"
    assert goals_evaluation_sample(result, sample_id="s", match_id="m", actual_result="HOME") is None
    result["status"] = "UNKNOWN"
    with pytest.raises(ValueError, match="status"):
        goals_evaluation_sample(result, sample_id="s", match_id="m", actual_result="HOME")


def test_adapters_validate_evaluable_probabilities_instead_of_repairing():
    market = {
        "version": "market-v1",
        "external_consensus": {"p_market": {"HOME": ".7", "DRAW": ".2", "AWAY": ".2"}},
    }
    with pytest.raises(ValueError, match="sum"):
        market_evaluation_sample(market, sample_id="s", match_id="m", actual_result="HOME")
    with pytest.raises(KeyError):
        market_evaluation_sample({"version": "market-v1"}, sample_id="s", match_id="m", actual_result="HOME")


def test_temporal_split_is_past_to_future_utc_with_stable_ties():
    cutoff = datetime(2024, 1, 2, tzinfo=UTC)
    rows = [
        sample("future", match_time=cutoff + timedelta(days=1)),
        sample("b", match_time=cutoff),
        sample("past", match_time=cutoff - timedelta(days=1)),
        sample("a", match_time=cutoff.astimezone(timezone(timedelta(hours=8)))),
    ]
    past, future = temporal_split(rows, cutoff)
    assert [s.match_id for s in past] == ["past"]
    assert [s.match_id for s in future] == ["a", "b", "future"]
    assert temporal_split(reversed(rows), cutoff) == (past, future)
    assert rows[0].match_id == "future"
    assert all(s.match_time.tzinfo == UTC for s in past + future)
    assert temporal_split([], cutoff) == ((), ())


@pytest.mark.parametrize("bad", [datetime(2024, 1, 1), "2024-01-01", None])
def test_temporal_split_rejects_implicit_time(bad):
    with pytest.raises(ValueError, match="timezone-aware"):
        temporal_split([], bad)
    if bad is not None:
        with pytest.raises(ValueError, match="timezone-aware"):
            sample(match_time=bad)


def test_temporal_split_rejects_missing_and_conflicting_match_times():
    cutoff = datetime(2024, 1, 2, tzinfo=UTC)
    with pytest.raises(ValueError, match="requires match_time"):
        temporal_split([sample()], cutoff)
    with pytest.raises(ValueError, match="Conflicting match_time"):
        temporal_split(
            [sample(match_time=cutoff), sample(source="other", match_time=cutoff + timedelta(days=1))], cutoff
        )


def test_evaluation_has_no_io_clock_or_random_dependency(golden, monkeypatch):
    import jc.analysis.evaluation as module

    def forbidden(*args, **kwargs):
        raise AssertionError("Unexpected I/O, clock or random dependency")

    class NoClock(datetime):
        now = utcnow = today = forbidden

    with monkeypatch.context() as guard:
        guard.setattr("sqlalchemy.engine.Connection.execute", forbidden)
        guard.setattr("sqlalchemy.orm.Session.execute", forbidden)
        guard.setattr("socket.socket", forbidden)
        guard.setattr("jc.time.utcnow", forbidden)
        guard.setattr("time.time", forbidden)
        guard.setattr("random.random", forbidden)
        guard.setattr("builtins.open", forbidden)
        guard.setattr(module, "datetime", NoClock)
        assert evaluate(golden)["sample_size"] == 3
        assert evaluate_models({"market-v1": golden}, baseline="market-v1")["paired_comparisons"] == []
