"""score-math-v1: explicit parameters -> score probabilities, without I/O.

No parameter estimation or match prediction. Changes to algorithms, precision,
tail bounds, normalization or mappings require a new SCORE_ENGINE_VERSION.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from decimal import (
    ROUND_HALF_EVEN,
    Context,
    Decimal,
    DecimalException,
    DivisionByZero,
    InvalidOperation,
    Overflow,
    Underflow,
    localcontext,
)
from typing import TypedDict

SCORE_ENGINE_VERSION = "score-math-v1"
DECIMAL_PRECISION = 50
TAIL_TOLERANCE = Decimal("1e-12")  # Per marginal; joint bound is their sum.
MAX_GOALS_CAP = 30
SUM_TOLERANCE = Decimal("1e-45")
ZERO, ONE = Decimal(0), Decimal(1)
_CONTEXT = Context(
    prec=DECIMAL_PRECISION,
    rounding=ROUND_HALF_EVEN,
    Emin=-999999,
    Emax=999999,
    capitals=1,
    clamp=0,
    flags=[],
    traps=[InvalidOperation, DivisionByZero, Overflow, Underflow],
)


class TailToleranceError(ValueError):
    """The versioned goal cap cannot satisfy the requested tail tolerance."""


@dataclass(frozen=True)
class PoissonMarginal:
    probabilities: tuple[Decimal, ...]
    tail_upper_bound: Decimal


class ScoreMatrixResult(TypedDict):
    engine_version: str
    lambda_home: str
    lambda_away: str
    rho: str
    max_home_goals: int
    max_away_goals: int
    tail_upper_bound: str
    pre_normalization_mass: str
    normalization_factor: str
    matrix: list[list[str]]  # matrix[home_goals][away_goals], including zeros.
    one_x_two: dict[str, str]
    total_goals: dict[str, str]
    sporttery_ttg: dict[str, str]
    handicap: dict[str, dict[str, str]]  # Canonical integer home-handicap keys.


class ScoreProbability(TypedDict):
    home_goals: int
    away_goals: int
    probability: str


def _parameter(value: Decimal, name: str) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError(f"{name} must be a finite Decimal (no float coercion)")
    return ZERO if value.is_zero() else value


def _integer(value: int, name: str) -> int:
    if type(value) is not int:  # bool and fractional/Decimal/float lines are not int contracts.
        raise ValueError(f"{name} must be an integer")
    return value


def poisson_marginal(mean: Decimal) -> PoissonMarginal:
    """Unnormalized P(0)..P(K), K >= 1, with a conservative omitted-tail bound.

    For K+2 > mean, subsequent ratios decrease, so the remaining series is at
    most P(K+1)/(1-mean/(K+2)). A 1e-45 guard covers 50-digit rounding within
    the 30-goal cap. Keeping K >= 1 includes the entire DC correction block.
    """
    with localcontext(_CONTEXT):
        mean = _parameter(mean, "lambda")
        if mean < ZERO:
            raise ValueError("lambda must be nonnegative")
        if mean > MAX_GOALS_CAP:
            raise TailToleranceError("lambda exceeds MAX_GOALS_CAP=30; tail tolerance cannot be met")
        try:
            probabilities = [(-mean).exp()]
            for goals in range(1, MAX_GOALS_CAP + 1):
                probabilities.append(probabilities[-1] * mean / goals)
                if mean < goals + 2:
                    first_omitted = probabilities[-1] * mean / (goals + 1)
                    tail = first_omitted / (ONE - mean / (goals + 2)) + SUM_TOLERANCE if mean else ZERO
                    if tail <= TAIL_TOLERANCE:
                        return PoissonMarginal(tuple(probabilities), tail)
        except DecimalException as exc:
            raise ValueError("lambda exceeds score-math-v1 Decimal numeric range") from exc
        raise TailToleranceError("MAX_GOALS_CAP=30 reached before tail <= 1e-12")


def _encoded(values: dict[str, Decimal]) -> dict[str, str]:
    return {key: str(value) for key, value in values.items()}


def three_way_handicap(matrix: Sequence[Sequence[str]], home_handicap: int) -> dict[str, str]:
    """Sum an engine-produced normalized matrix using SPORTTERY_HHAD semantics.

    The matrix is indexed [home][away]; this helper does not normalize it again.
    A zero home handicap is also the sole implementation of 1X2.
    """
    home_handicap = _integer(home_handicap, "home_handicap")
    with localcontext(_CONTEXT):
        totals = dict.fromkeys(("HOME", "DRAW", "AWAY"), ZERO)
        for home, row in enumerate(matrix):
            for away, probability in enumerate(row):
                difference = home + home_handicap - away
                selection = "HOME" if difference > 0 else "AWAY" if difference < 0 else "DRAW"
                totals[selection] += Decimal(probability)
        return _encoded(totals)


def build_score_matrix(
    lambda_home: Decimal, lambda_away: Decimal, rho: Decimal, lines: Iterable[int] = ()
) -> ScoreMatrixResult:
    """Pure, deterministic transform. All three parameters are required Decimals.

    The JSON-ready result retains full Decimal strings, with no quantization or
    residual bucket. Only the supplied integer handicap lines are computed.
    """
    with localcontext(_CONTEXT):
        lambda_home = _parameter(lambda_home, "lambda_home")
        lambda_away = _parameter(lambda_away, "lambda_away")
        rho = _parameter(rho, "rho")
        requested_lines = sorted({_integer(line, "home_handicap") for line in lines})
        home = poisson_marginal(lambda_home)
        away = poisson_marginal(lambda_away)
        try:
            # Dixon-Coles: tau00=1-lh*la*rho, tau01=1+lh*rho,
            # tau10=1+la*rho, tau11=1-rho; all other tau=1.
            # Preserve product coefficients for validity checks: rounding a value
            # just above 1 down to 1 must never disguise a negative tau as zero.
            with localcontext(_CONTEXT) as validation:
                validation.prec = max(
                    DECIMAL_PRECISION,
                    sum(len(value.as_tuple().digits) for value in (lambda_home, lambda_away, rho)) + 1,
                )
                tau = (
                    (ONE - lambda_home * lambda_away * rho, ONE + lambda_home * rho),
                    (ONE + lambda_away * rho, ONE - rho),
                )
        except DecimalException as exc:
            raise ValueError("rho exceeds score-math-v1 Decimal numeric range") from exc
        if any(value < ZERO for row in tau for value in row):
            raise ValueError("Invalid rho: Dixon-Coles tau must be nonnegative in all four cells")
        probabilities = [
            [ph * pa * (tau[i][j] if i < 2 and j < 2 else ONE) for j, pa in enumerate(away.probabilities)]
            for i, ph in enumerate(home.probabilities)
        ]
        mass = sum((p for row in probabilities for p in row), ZERO)
        factor = ONE / mass
        probabilities = [[p * factor for p in row] for row in probabilities]
        if abs(sum((p for row in probabilities for p in row), ZERO) - ONE) > SUM_TOLERANCE:
            raise ArithmeticError("Score matrix sum outside score-math-v1 tolerance")
        matrix = [[str(p) for p in row] for row in probabilities]
        totals = {str(n): ZERO for n in range(len(home.probabilities) + len(away.probabilities) - 1)}
        ttg = dict.fromkeys(("0", "1", "2", "3", "4", "5", "6", "7+"), ZERO)
        for i, row in enumerate(probabilities):
            for j, p in enumerate(row):
                totals[str(i + j)] += p
                ttg[str(i + j) if i + j < 7 else "7+"] += p
        return ScoreMatrixResult(
            engine_version=SCORE_ENGINE_VERSION,
            lambda_home=str(lambda_home),
            lambda_away=str(lambda_away),
            rho=str(rho),
            max_home_goals=len(home.probabilities) - 1,
            max_away_goals=len(away.probabilities) - 1,
            tail_upper_bound=str(home.tail_upper_bound + away.tail_upper_bound),
            pre_normalization_mass=str(mass),
            normalization_factor=str(factor),
            matrix=matrix,
            one_x_two=three_way_handicap(matrix, 0),
            total_goals=_encoded(totals),
            sporttery_ttg=_encoded(ttg),
            handicap={str(line): three_way_handicap(matrix, line) for line in requested_lines},
        )


def top_scores(result: ScoreMatrixResult, n: int) -> list[ScoreProbability]:
    """Display only: probability DESC, home ASC, away ASC; never changes result."""
    if _integer(n, "n") < 0:
        raise ValueError("n must be nonnegative")
    scores = [
        ScoreProbability(home_goals=i, away_goals=j, probability=p)
        for i, row in enumerate(result["matrix"])
        for j, p in enumerate(row)
    ]
    # copy_negate is exact and independent of the caller's Decimal context.
    return sorted(
        scores,
        key=lambda s: (Decimal(s["probability"]).copy_negate(), s["home_goals"], s["away_goals"]),
    )[:n]
