import copy
import json
from decimal import ROUND_UP, Context, Decimal, FloatOperation, Inexact, localcontext
from math import factorial

import pytest
from jc.analysis.score_matrix import (
    DECIMAL_PRECISION,
    MAX_GOALS_CAP,
    SCORE_ENGINE_VERSION,
    SUM_TOLERANCE,
    TAIL_TOLERANCE,
    TailToleranceError,
    build_score_matrix,
    poisson_marginal,
    three_way_handicap,
    top_scores,
)

D = Decimal


@pytest.fixture(autouse=True)
def independent_check_precision():
    # Higher precision and direct factorial formulas independently check the engine.
    with localcontext(Context(prec=80)):
        yield


def close(actual, expected, tolerance=SUM_TOLERANCE):
    assert abs(D(actual) - D(expected)) <= tolerance


def cells(result):
    return [(i, j, D(p)) for i, row in enumerate(result["matrix"]) for j, p in enumerate(row)]


def direct_poisson(mean, goals):
    return (-mean).exp() * mean**goals / D(factorial(goals))


def test_versioned_rules():
    assert SCORE_ENGINE_VERSION == "score-math-v1"
    assert DECIMAL_PRECISION == 50
    assert TAIL_TOLERANCE == D("1e-12")
    assert MAX_GOALS_CAP == 30
    assert SUM_TOLERANCE == D("1e-45")


def test_poisson_p0():
    close(poisson_marginal(D(2)).probabilities[0], D(-2).exp())


def test_poisson_recurrence():
    marginal = poisson_marginal(D("1.75"))
    for k, p in enumerate(marginal.probabilities[:-1]):
        close(marginal.probabilities[k + 1], p * D("1.75") / (k + 1))


@pytest.mark.parametrize("mean", ["0", "1e-30", "0.1", "1", "2", "5", "6"])
def test_marginal_tail_bound_and_smallest_supported_range(mean):
    mean = D(mean)
    marginal = poisson_marginal(mean)
    k = len(marginal.probabilities) - 1
    # Independent high-precision CDF, not the implementation's geometric bound.
    cdf = D(1) if mean == 0 else sum(direct_poisson(mean, n) for n in range(k + 1))
    assert 0 <= 1 - cdf <= marginal.tail_upper_bound <= TAIL_TOLERANCE
    close(sum(marginal.probabilities), cdf)
    assert 1 <= k <= MAX_GOALS_CAP
    if k > 1:
        previous_bound = direct_poisson(mean, k) / (1 - mean / (k + 1))
        assert previous_bound + SUM_TOLERANCE > TAIL_TOLERANCE


def test_dynamic_goal_range_is_not_fixed_at_ten():
    small = poisson_marginal(D("0.1"))
    medium = poisson_marginal(D(2))
    large = poisson_marginal(D(5))
    assert len(small.probabilities) < len(medium.probabilities) < len(large.probabilities)
    assert len(large.probabilities) - 1 > 10
    result = build_score_matrix(D("0.1"), D(5), D(0))
    assert result["max_home_goals"] < result["max_away_goals"]


@pytest.mark.parametrize("mean", ["8", "30", "100", "1e1000"])
def test_cap_failure_is_explicit(mean):
    with pytest.raises(TailToleranceError, match="MAX_GOALS_CAP"):
        poisson_marginal(D(mean))
    with pytest.raises(TailToleranceError):
        build_score_matrix(D(1), D(mean), D(0))


@pytest.mark.parametrize("name", ["lambda_home", "lambda_away"])
def test_negative_lambda_rejected(name):
    parameters = dict(lambda_home=D(1), lambda_away=D(1), rho=D(0))
    parameters[name] = D("-0.01")
    with pytest.raises(ValueError, match="nonnegative"):
        build_score_matrix(**parameters)


@pytest.mark.parametrize("name", ["lambda_home", "lambda_away", "rho"])
@pytest.mark.parametrize("bad", [D("NaN"), D("sNaN"), D("Infinity"), D("-Infinity"), 1.5])
def test_nonfinite_and_float_parameters_rejected(name, bad):
    parameters = dict(lambda_home=D(1), lambda_away=D(1), rho=D(0))
    parameters[name] = bad
    with pytest.raises(ValueError, match="finite Decimal"):
        build_score_matrix(**parameters)


@pytest.mark.parametrize("bad", [True, 1, "1", None])
def test_decimal_input_contract_has_no_implicit_coercion(bad):
    with pytest.raises(ValueError, match="finite Decimal"):
        poisson_marginal(bad)


def test_rho_has_no_default():
    with pytest.raises(TypeError):
        build_score_matrix(D(1), D(1))


def test_zero_lambda_marginal():
    marginal = poisson_marginal(D(0))
    assert marginal.probabilities == (D(1), D(0))
    assert marginal.tail_upper_bound == 0


def test_both_zero_lambdas():
    result = build_score_matrix(D(0), D(0), D(0), [-1, 0, 1])
    assert D(result["matrix"][0][0]) == 1
    assert all(p == 0 for i, j, p in cells(result) if (i, j) != (0, 0))
    assert result["one_x_two"] == dict(HOME="0", DRAW="1", AWAY="0")
    assert result["sporttery_ttg"]["0"] == "1"
    assert result["pre_normalization_mass"] == result["normalization_factor"] == "1"
    assert result["tail_upper_bound"] == "0"


@pytest.mark.parametrize("home,away", [("2", "0"), ("0", "2")])
def test_one_sided_zero_lambda(home, away):
    result = build_score_matrix(D(home), D(away), D("-0.1"))
    assert all(p == 0 for i, j, p in cells(result) if (j if away == "0" else i) > 0)
    assert D(result["one_x_two"]["AWAY" if away == "0" else "HOME"]) == 0
    close(sum(p for _, _, p in cells(result)), 1)


@pytest.mark.parametrize("home,away", [("1", "1"), ("2", "1")])
def test_golden_scores_direct_factorial_formula(home, away):
    home, away = D(home), D(away)
    result = build_score_matrix(home, away, D(0))
    factor = D(result["normalization_factor"])
    for i, j in [(0, 0), (1, 0), (0, 1), (1, 1), (2, 0), (2, 1), (3, 2)]:
        expected = direct_poisson(home, i) * direct_poisson(away, j)
        close(result["matrix"][i][j], expected * factor)
        close(result["matrix"][i][j], expected, D(result["tail_upper_bound"]))
    # Human-checkable anchors: e^-2 for four cells; e^-3, 2e^-3 for lambda=(2,1).
    close(D(result["matrix"][0][0]) / factor, (-(home + away)).exp())


def test_rho_zero_matches_entire_independent_poisson_matrix():
    result = build_score_matrix(D(2), D(1), D(0))
    for i, j, p in cells(result):
        expected = direct_poisson(D(2), i) * direct_poisson(D(1), j)
        close(p, expected * D(result["normalization_factor"]))


@pytest.mark.parametrize("rho", ["0", "-0.1", "0.2"])
def test_normalized_matrix_mass_tail_and_uniform_normalization(rho):
    result = build_score_matrix(D(2), D(1), D(rho))
    mass = D(result["pre_normalization_mass"])
    tail = D(result["tail_upper_bound"])
    assert 0 < 1 - mass <= tail <= 2 * TAIL_TOLERANCE
    close(mass * D(result["normalization_factor"]), 1)
    close(sum(p for _, _, p in cells(result)), 1)
    assert all(0 <= p <= 1 for _, _, p in cells(result))
    # No final-score residual bucket: even the final cell has the same multiplier.
    i, j = result["max_home_goals"], result["max_away_goals"]
    expected_last = direct_poisson(D(2), i) * direct_poisson(D(1), j)
    close(D(result["matrix"][i][j]) / expected_last, result["normalization_factor"])


@pytest.mark.parametrize("rho", ["-0.1", "0.2"])
def test_dixon_coles_four_factors_and_unchanged_other_scores(rho):
    result = build_score_matrix(D(2), D(1), D(rho))
    expected = (
        {(0, 0): "1.2", (0, 1): "0.8", (1, 0): "0.9", (1, 1): "1.1"}
        if rho == "-0.1"
        else {(0, 0): "0.6", (0, 1): "1.4", (1, 0): "1.2", (1, 1): "0.8"}
    )
    for i, j, p in cells(result):
        raw = direct_poisson(D(2), i) * direct_poisson(D(1), j)
        close(p, raw * D(expected.get((i, j), "1")) * D(result["normalization_factor"]))
    baseline = build_score_matrix(D(2), D(1), D(0))
    close(result["pre_normalization_mass"], baseline["pre_normalization_mass"])


@pytest.mark.parametrize(
    "home,away,rho",
    [("2", "1", "0.51"), ("2", "1", "-0.51"), ("1", "2", "-0.51"), ("0.5", "0.5", "1.01"), ("0", "0", "2")],
)
def test_invalid_tau_rejected_without_clamping(home, away, rho):
    with pytest.raises(ValueError, match="tau must be nonnegative"):
        build_score_matrix(D(home), D(away), D(rho))


@pytest.mark.parametrize(
    "home,away,rho",
    [
        ("2", "1", "0.500000000000000000000000000000000000000000000000001"),
        ("2", "1", "-0.500000000000000000000000000000000000000000000000001"),
        ("1", "2", "-0.500000000000000000000000000000000000000000000000001"),
        ("0.5", "0.5", "1.000000000000000000000000000000000000000000000000001"),
    ],
)
def test_rounding_cannot_hide_negative_tau_beyond_fifty_digits(home, away, rho):
    with pytest.raises(ValueError, match="tau must be nonnegative"):
        build_score_matrix(D(home), D(away), D(rho))


@pytest.mark.parametrize("rho,zero_cell", [("0.5", (0, 0)), ("-0.5", (0, 1))])
def test_zero_tau_boundary_is_valid(rho, zero_cell):
    result = build_score_matrix(D(2), D(1), D(rho))
    i, j = zero_cell
    assert D(result["matrix"][i][j]) == 0
    close(sum(p for _, _, p in cells(result)), 1)


def test_tiny_lambdas_retain_whole_dc_block():
    result = build_score_matrix(D("1e-20"), D("1e-20"), D("-1e20"))
    assert result["max_home_goals"] == result["max_away_goals"] == 1
    assert D(result["matrix"][0][1]) == D(result["matrix"][1][0]) == 0
    assert D(result["matrix"][1][1]) > 0
    close(sum(p for _, _, p in cells(result)), 1)


def test_one_x_two_derived_from_matrix_and_sums_to_one():
    result = build_score_matrix(D(2), D(1), D("-0.1"))
    values = cells(result)
    close(result["one_x_two"]["HOME"], sum(p for i, j, p in values if i > j))
    close(result["one_x_two"]["DRAW"], sum(p for i, j, p in values if i == j))
    close(result["one_x_two"]["AWAY"], sum(p for i, j, p in values if i < j))
    close(sum(map(D, result["one_x_two"].values())), 1)


def test_symmetric_matrix_and_home_away_probabilities():
    result = build_score_matrix(D("1.7"), D("1.7"), D(0))
    for i, j, p in cells(result):
        assert p == D(result["matrix"][j][i])
    close(result["one_x_two"]["HOME"], result["one_x_two"]["AWAY"])


def test_total_goals_and_ttg_from_matrix_including_seven_plus():
    result = build_score_matrix(D(5), D(2), D("-0.1"))
    values = cells(result)
    for n, probability in result["total_goals"].items():
        close(probability, sum(p for i, j, p in values if i + j == int(n)))
    assert list(result["sporttery_ttg"]) == ["0", "1", "2", "3", "4", "5", "6", "7+"]
    for n in range(7):
        assert result["sporttery_ttg"][str(n)] == result["total_goals"][str(n)]
    close(result["sporttery_ttg"]["7+"], sum(p for i, j, p in values if i + j >= 7))
    close(sum(map(D, result["total_goals"].values())), 1)
    close(sum(map(D, result["sporttery_ttg"].values())), 1)


def test_zero_handicap_is_strictly_identical_to_one_x_two():
    result = build_score_matrix(D(2), D(1), D("-0.1"), [0])
    assert result["handicap"]["0"] == result["one_x_two"]
    assert three_way_handicap(result["matrix"], 0) == result["one_x_two"]


@pytest.mark.parametrize("line", [-2, -1, 1, 2])
def test_integer_handicap_mapping(line):
    result = build_score_matrix(D(2), D(1), D(0), [line])
    probabilities = result["handicap"][str(line)]
    values = cells(result)
    close(probabilities["HOME"], sum(p for i, j, p in values if i + line > j))
    close(probabilities["DRAW"], sum(p for i, j, p in values if i + line == j))
    close(probabilities["AWAY"], sum(p for i, j, p in values if i + line < j))
    close(sum(map(D, probabilities.values())), 1)


@pytest.mark.parametrize("bad", [-0.5, -0.75, 1.0, D("-0.5"), D(1), "1", True, None])
def test_non_integer_handicap_rejected(bad):
    with pytest.raises(ValueError, match="integer"):
        build_score_matrix(D(1), D(1), D(0), [bad])
    with pytest.raises(ValueError, match="integer"):
        three_way_handicap([["1"]], bad)


def test_top_scores_tie_order_and_input_unchanged():
    result = build_score_matrix(D(1), D(1), D(0))
    before = copy.deepcopy(result)
    scores = top_scores(result, 4)
    assert [(s["home_goals"], s["away_goals"]) for s in scores] == [(0, 0), (0, 1), (1, 0), (1, 1)]
    assert len({s["probability"] for s in scores}) == 1
    assert top_scores(result, 0) == []
    assert len(top_scores(result, 10000)) == len(cells(result))
    assert result == before


@pytest.mark.parametrize("bad", [-1, 1.5, True])
def test_invalid_top_score_count_rejected(bad):
    with pytest.raises(ValueError):
        top_scores(build_score_matrix(D(0), D(0), D(0)), bad)


def test_context_precision_rounding_traps_and_exponents_do_not_change_results():
    args = (D(2), D(1), D("-0.1"), [-1, 0, 1])
    expected = build_score_matrix(*args)
    expected_top = top_scores(expected, 10)
    marginal = poisson_marginal(D(2))
    with localcontext() as context:
        context.prec = 3
        context.rounding = ROUND_UP
        context.Emin, context.Emax = -2, 2
        context.capitals, context.clamp = 0, 1
        context.traps[FloatOperation] = context.traps[Inexact] = True
        context.clear_flags()
        assert build_score_matrix(*args) == expected
        assert poisson_marginal(D(2)) == marginal
        assert three_way_handicap(expected["matrix"], 0) == expected["one_x_two"]
        assert top_scores(expected, 10) == expected_top
        assert not any(context.flags.values())


def test_json_schema_decimal_strings_and_no_prediction_semantics():
    result = build_score_matrix(D(2), D(1), D(0), [-1, 0, 1])
    assert result["engine_version"] == SCORE_ENGINE_VERSION
    assert len(result["matrix"]) == result["max_home_goals"] + 1
    assert all(len(row) == result["max_away_goals"] + 1 for row in result["matrix"])

    def check(value):
        assert not isinstance(value, (float, Decimal))
        if isinstance(value, dict):
            for item in value.values():
                check(item)
        elif isinstance(value, list):
            for item in value:
                check(item)

    check(result)
    assert all(isinstance(p, str) for row in result["matrix"] for p in row)
    assert json.loads(json.dumps(result, allow_nan=False)) == result
    forbidden = ("p_model", "p_final", "recommendation", "edge", "ev", "confidence", "core", "watch", "pass")
    assert not any(key.lower() in forbidden for key in result)


def test_repeated_calls_keyword_order_and_lines_order_do_not_mutate_inputs():
    parameters = dict(lambda_home=D(2), lambda_away=D(1), rho=D(0), lines=[2, -1, 0, 2])
    before = copy.deepcopy(parameters)
    result = build_score_matrix(**parameters)
    assert result == build_score_matrix(**parameters)
    assert result == build_score_matrix(rho=D(0), lambda_away=D(1), lambda_home=D(2), lines=[0, 2, -1])
    assert parameters == before
    assert list(result["handicap"]) == ["-1", "0", "2"]
    assert build_score_matrix(D(2), D(1), D(0))["handicap"] == {}
