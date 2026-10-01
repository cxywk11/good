"""Goals-only baseline from frozen FeatureData; no I/O, clocks or market inputs.

Selection, deduplication, weighting, minimum samples, precision, lambda formula
and rho policy are versioned together. This is not a final prediction model.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import (
    ROUND_HALF_EVEN,
    Context,
    Decimal,
    DivisionByZero,
    InvalidOperation,
    Overflow,
    Underflow,
    localcontext,
)
from typing import Literal, TypedDict

from jc.analysis.contracts import FeatureData
from jc.analysis.score_matrix import (
    SCORE_ENGINE_VERSION,
    ScoreMatrixResult,
    TailToleranceError,
    build_score_matrix,
)

GOALS_BASELINE_VERSION = "goals-baseline-v1"
MAX_MATCHES_PER_TEAM = 20
MIN_MATCHES_PER_TEAM = 5
DECIMAL_PRECISION = 50
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


class TeamHistory(TypedDict):
    matches_used: int
    match_ids: list[str]
    evidence_source_count: dict[str, int]
    gf_rate: str | None
    ga_rate: str | None


class GoalsBaselineResult(TypedDict):
    version: str
    status: Literal["OK", "INSUFFICIENT_DATA", "OUT_OF_RANGE"]
    home_team_id: str | None
    away_team_id: str | None
    home_history: TeamHistory
    away_history: TeamHistory
    lambda_home: str | None
    lambda_away: str | None
    rho: str
    rho_source: str
    score_engine_version: str
    score: ScoreMatrixResult | None
    diagnostics: list[str]
    excluded_match_ids: list[str]


@dataclass(frozen=True)
class _Result:
    match_id: str
    home_team_id: str
    away_team_id: str
    home_score: int
    away_score: int
    finished_at: datetime
    source: str


def _id(value: object) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _read_result(row: dict, targets: set[str]) -> _Result:
    match_id, home, away, source = (
        _id(row.get(key)) for key in ("match_id", "home_team_id", "away_team_id", "source")
    )
    if not match_id or not home or not away or not source or home == away or not targets & {home, away}:
        raise ValueError("Invalid result identity")
    hs, aws = row.get("home_score"), row.get("away_score")
    if type(hs) is not int or type(aws) is not int or hs < 0 or aws < 0:
        raise ValueError("Scores must be nonnegative integers")
    timestamp = row.get("finished_at")
    if not isinstance(timestamp, str):
        raise ValueError("Missing finished_at")
    finished = datetime.fromisoformat(timestamp)
    if finished.tzinfo is None:
        raise ValueError("finished_at requires timezone")
    return _Result(match_id, home, away, hs, aws, finished.astimezone(UTC), source)


def _deduplicate(
    rows: object, targets: set[str], diagnostics: set[str], excluded: set[str]
) -> list[tuple[_Result, int]]:
    if not isinstance(rows, list):
        diagnostics.add("INVALID_RESULT_RECORD")
        return []
    grouped: dict[str, list[_Result]] = defaultdict(list)
    for row in rows:
        try:
            if not isinstance(row, dict):
                raise ValueError("Result must be an object")
            parsed = _read_result(row, targets)
        except (ValueError, OverflowError):
            diagnostics.add("INVALID_RESULT_RECORD")
            if isinstance(row, dict) and (match_id := _id(row.get("match_id"))):
                # A malformed peer cannot silently disappear and resolve a match.
                excluded.add(match_id)
            continue
        grouped[parsed.match_id].append(parsed)

    results = []
    for match_id, peers in sorted(grouped.items()):
        if len({(p.home_score, p.away_score) for p in peers}) != 1:
            diagnostics.add("CONFLICTING_RESULT_SOURCES")
            excluded.add(match_id)
        if len({(p.home_team_id, p.away_team_id) for p in peers}) != 1:
            diagnostics.add("INVALID_RESULT_RECORD")
            excluded.add(match_id)
        if match_id not in excluded:
            # Scores/participants agree. Earliest finish is conservative for recency;
            # source is only a stable tie-break, never a score-resolution preference.
            representative = min(peers, key=lambda p: (p.finished_at, p.source))
            results.append((representative, len({p.source for p in peers})))
    # Stable secondary order: match_id ASC for equal UTC finished_at.
    return sorted(results, key=lambda item: item[0].finished_at, reverse=True)


def _history(team: str | None, results: list[tuple[_Result, int]]) -> TeamHistory:
    selected = [(r, n) for r, n in results if team in (r.home_team_id, r.away_team_id)][:MAX_MATCHES_PER_TEAM]
    gf = ga = 0
    for row, _ in selected:
        if team == row.home_team_id:
            gf += row.home_score
            ga += row.away_score
        else:
            gf += row.away_score
            ga += row.home_score
    count = len(selected)
    return TeamHistory(
        matches_used=count,
        match_ids=[r.match_id for r, _ in selected],
        evidence_source_count={r.match_id: n for r, n in selected},
        gf_rate=str(Decimal(gf) / count) if count else None,
        ga_rate=str(Decimal(ga) / count) if count else None,
    )


def estimate_goals_baseline(feature: FeatureData) -> GoalsBaselineResult:
    """Consume only context.match and team_strength.past_results of a frozen snapshot.

    The Feature builder owns cutoff/visibility and target-match exclusion. Feature v1
    does not embed target match_id/cutoff in FeatureData; never re-query to recover them.
    """
    with localcontext(_CONTEXT):
        diagnostics: set[str] = set()
        excluded: set[str] = set()
        match = feature.context.get("match")
        match = match if isinstance(match, dict) else {}
        home = _id(match.get("home_team_id"))
        away = _id(match.get("away_team_id"))
        if home is None:
            diagnostics.add("MISSING_HOME_TEAM_ID")
        if away is None:
            diagnostics.add("MISSING_AWAY_TEAM_ID")
        if home is not None and home == away:
            diagnostics.add("INVALID_TARGET_TEAMS")
        results = (
            _deduplicate(feature.team_strength.get("past_results", []), {home, away}, diagnostics, excluded)
            if home is not None and away is not None and home != away
            else []
        )
        home_history, away_history = _history(home, results), _history(away, results)
        if home_history["matches_used"] < MIN_MATCHES_PER_TEAM:
            diagnostics.add("INSUFFICIENT_HOME_HISTORY")
        if away_history["matches_used"] < MIN_MATCHES_PER_TEAM:
            diagnostics.add("INSUFFICIENT_AWAY_HISTORY")
        result = GoalsBaselineResult(
            version=GOALS_BASELINE_VERSION,
            status="INSUFFICIENT_DATA",
            home_team_id=home,
            away_team_id=away,
            home_history=home_history,
            away_history=away_history,
            lambda_home=None,
            lambda_away=None,
            rho="0",
            rho_source="fixed-zero-v1",
            score_engine_version=SCORE_ENGINE_VERSION,
            score=None,
            diagnostics=[],
            excluded_match_ids=sorted(excluded),
        )
        if min(home_history["matches_used"], away_history["matches_used"]) >= MIN_MATCHES_PER_TEAM:
            hgf, hga = home_history["gf_rate"], home_history["ga_rate"]
            agf, aga = away_history["gf_rate"], away_history["ga_rate"]
            assert hgf is not None and hga is not None and agf is not None and aga is not None
            lh = (Decimal(hgf) + Decimal(aga)) / 2
            la = (Decimal(agf) + Decimal(hga)) / 2
            result["status"] = "OK"
            result["lambda_home"], result["lambda_away"] = str(lh), str(la)
            try:
                result["score"] = build_score_matrix(lh, la, Decimal("0"))
            except TailToleranceError:
                result["status"] = "OUT_OF_RANGE"
                diagnostics.add("SCORE_ENGINE_RANGE_EXCEEDED")
        result["diagnostics"] = sorted(diagnostics)
        return result
