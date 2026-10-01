"""market-v1: pure Decimal pricing of a frozen FeatureData, without I/O or clocks.

Changing precision, selection rules, thresholds or aggregation requires a new version.
Two-way handicap/totals outputs are normalized prices, not a score distribution
or unconditional win probabilities for lines with pushes/partial settlements.
"""

from collections import Counter, defaultdict
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Context, Decimal, InvalidOperation, localcontext
from statistics import mean, median, pstdev
from typing import Protocol

from jc.analysis.contracts import FeatureData

MARKET_MODEL_VERSION = "market-v1"
NORMALIZATION_METHOD = "proportional-v1"
DECIMAL_PRECISION = 50
OUTPUT_QUANTUM = Decimal("1e-24")
SUM_TOLERANCE = Decimal("1e-45")
HIGH_OVERROUND_THRESHOLD = Decimal("1.20")  # Diagnostic only; never changes source weight.
ONE = Decimal(1)
ZERO = Decimal(0)
THREE_WAY = ("HOME", "DRAW", "AWAY")
SELECTIONS = {
    "1X2": THREE_WAY,
    "SPORTTERY_HAD": THREE_WAY,
    "SPORTTERY_HHAD": THREE_WAY,
    "ASIAN_HANDICAP": ("HOME", "AWAY"),
    "TOTALS": ("OVER", "UNDER"),
    "SPORTTERY_TTG": ("0", "1", "2", "3", "4", "5", "6", "7+"),
}
LINE_MARKETS = {"ASIAN_HANDICAP", "TOTALS", "SPORTTERY_HHAD"}


class MarginRemovalMethod(Protocol):
    def normalize(self, implied: list[Decimal]) -> list[Decimal]: ...


class ProportionalNormalization:
    def normalize(self, implied: list[Decimal]) -> list[Decimal]:
        total = sum(implied, ZERO)
        return [value / total for value in implied]


def number(value: object) -> Decimal:
    # Frozen Feature v1 uses strings. Never introduce binary floats via Decimal(float).
    if not isinstance(value, (str, Decimal)):
        raise ValueError("Expected a Decimal string")
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError("Invalid Decimal") from exc
    if not result.is_finite():
        raise ValueError("Non-finite Decimal")
    return result


def price(value: object) -> Decimal:
    result = number(value)
    if result <= ONE:
        raise ValueError("Decimal odds must exceed one")
    return result


def encoded(value: Decimal) -> str:
    rounded = value.quantize(OUTPUT_QUANTUM)
    return format(abs(rounded) if rounded == ZERO else rounded, "f")


def line_text(value: Decimal | None) -> str | None:
    return format(value.normalize(), "f") if value else ("0" if value is not None else None)


@dataclass
class Quote:
    frozen: dict
    line: Decimal | None
    canonical_line: Decimal | None
    odds: Decimal | None
    diagnostics: list[str]


@dataclass
class SourceMarket:
    data: dict
    probabilities: dict[str, Decimal]


def read_quote(frozen: dict) -> Quote:
    diagnostics = []
    line = None
    if frozen["line"] is not None:
        try:
            line = number(frozen["line"])
            if line % Decimal("0.25") != ZERO:
                diagnostics.append("INVALID_QUARTER_LINE")
        except ValueError:
            diagnostics.append("INVALID_LINE")
    market = frozen["market_type"]
    if market in LINE_MARKETS and line is None:
        diagnostics.append("MISSING_LINE")
    if market == "TOTALS" and line is not None and line < ZERO:
        diagnostics.append("NEGATIVE_TOTALS_LINE")
    if market in {"1X2", "SPORTTERY_HAD", "SPORTTERY_TTG"} and line is not None:
        diagnostics.append("UNEXPECTED_LINE")
    canonical = (
        -line if market == "ASIAN_HANDICAP" and frozen["selection"] == "AWAY" and line is not None else line
    )
    try:
        odds = price(frozen["decimal_odds"])
    except ValueError:
        odds = None
        diagnostics.append("INVALID_DECIMAL_ODDS")
    return Quote(frozen, line, canonical, odds, diagnostics)


def source_market(
    quotes: list[Quote], peer_selections: set[str], method: MarginRemovalMethod
) -> SourceMarket:
    first = quotes[0].frozen
    kind = first["market_type"]
    expected = SELECTIONS.get(kind, ())
    order = {selection: index for index, selection in enumerate(expected)}
    quotes = sorted(
        quotes,
        key=lambda q: (
            order.get(q.frozen["selection"], len(order)),
            q.frozen["selection"],
            q.frozen["odds_snapshot_id"],
        ),
    )
    diagnostics = {diagnostic for q in quotes for diagnostic in q.diagnostics}
    counts = Counter(q.frozen["selection"] for q in quotes)
    if not expected:
        diagnostics.add("UNSUPPORTED_FOR_V1")
    else:
        diagnostics.update(f"MISSING_SELECTION:{s}" for s in expected if not counts[s])
        diagnostics.update(f"UNEXPECTED_SELECTION:{s}" for s in counts if s not in expected)
    diagnostics.update(f"DUPLICATE_SELECTION:{s}" for s, count in counts.items() if count > 1)
    if len({(q.frozen.get("mapping_id"), q.frozen.get("mapping_version")) for q in quotes}) > 1:
        diagnostics.add("MIXED_MAPPING_BINDING")
    if kind.startswith("SPORTTERY_") and first["provider"] != "sporttery":
        diagnostics.add("SPORTTERY_PROVIDER_MISMATCH")
    if kind in {"ASIAN_HANDICAP", "TOTALS"}:
        # Retain unmatched canonical groups. An opposite outcome elsewhere cannot fill the gap.
        opposite = {"HOME": "AWAY", "AWAY": "HOME", "OVER": "UNDER", "UNDER": "OVER"}
        for q in quotes:
            other = opposite.get(q.frozen["selection"])
            if other and not counts[other] and other in peer_selections:
                diagnostics.add(
                    "HANDICAP_LINE_MISMATCH" if kind == "ASIAN_HANDICAP" else "TOTALS_LINE_MISMATCH"
                )
        if kind == "ASIAN_HANDICAP" and counts["HOME"] == counts["AWAY"] == 1:
            home = next(q.line for q in quotes if q.frozen["selection"] == "HOME")
            away = next(q.line for q in quotes if q.frozen["selection"] == "AWAY")
            if home is None or away is None or away != -home:
                diagnostics.add("HANDICAP_LINE_MISMATCH")

    complete = bool(expected) and not diagnostics
    raw = [ONE / q.odds if q.odds is not None else None for q in quotes]
    probabilities: dict[str, Decimal] = {}
    overround = vig = None
    if complete:
        implied = [value for value in raw if value is not None]
        overround = sum(implied, ZERO)
        vig = overround - ONE
        normalized = method.normalize(implied)
        if abs(sum(normalized, ZERO) - ONE) > SUM_TOLERANCE:
            raise ArithmeticError("Normalized probability sum outside market-v1 tolerance")
        probabilities = {q.frozen["selection"]: value for q, value in zip(quotes, normalized, strict=True)}
        if overround < ONE:
            diagnostics.add("NEGATIVE_OVERROUND")
        if overround > HIGH_OVERROUND_THRESHOLD:
            diagnostics.add("HIGH_OVERROUND")

    data = {
        "provider": first["provider"],
        "bookmaker": first["bookmaker"],
        "market_type": kind,
        "canonical_line": line_text(quotes[0].canonical_line),
        "canonical_home_line": line_text(quotes[0].canonical_line) if kind == "ASIAN_HANDICAP" else None,
        "complete": complete,
        "unsupported_for_v1": not bool(expected),
        "diagnostics": sorted(diagnostics),
        "overround": encoded(overround) if overround is not None else None,
        "vig": encoded(vig) if vig is not None else None,
        "outcomes": [
            {
                "selection": q.frozen["selection"],
                "odds_snapshot_id": q.frozen["odds_snapshot_id"],
                "line": q.frozen["line"],
                "decimal_odds": q.frozen["decimal_odds"],
                "raw_implied_probability": encoded(implied) if implied is not None else None,
                "no_vig_probability": encoded(probabilities[q.frozen["selection"]]) if complete else None,
            }
            for q, implied in zip(quotes, raw, strict=True)
        ],
    }
    return SourceMarket(data, probabilities)


def consensus(markets: list[SourceMarket]) -> tuple[dict, dict[str, Decimal]]:
    sources = [
        m
        for m in markets
        if m.data["complete"] and m.data["market_type"] == "1X2" and m.data["provider"] != "sporttery"
    ]
    data: dict = {
        "market_type": "1X2",
        "aggregation": "equal-source-arithmetic-mean-v1",
        "source_count": len(sources),
        "sources": [{"provider": m.data["provider"], "bookmaker": m.data["bookmaker"]} for m in sources],
        "p_market": None,
        **dict.fromkeys(THREE_WAY),
    }
    means = {}
    if sources:
        for selection in THREE_WAY:
            values = sorted(m.probabilities[selection] for m in sources)
            means[selection] = mean(values)
            data[selection] = {
                "mean": encoded(means[selection]),
                "median": encoded(median(values)),
                "min": encoded(values[0]),
                "max": encoded(values[-1]),
                "population_stddev": encoded(pstdev(values)),
            }
        if abs(sum(means.values(), ZERO) - ONE) > SUM_TOLERANCE:
            raise ArithmeticError("Consensus probability sum outside market-v1 tolerance")
        data["p_market"] = {selection: encoded(value) for selection, value in means.items()}
    return data, means


def movements(feature: FeatureData, quotes: list[Quote]) -> dict:
    by_id: dict[str, list[dict]] = defaultdict(list)
    for item in feature.odds_movement["items"]:
        by_id[item["odds_snapshot_id"]].append(item)
    items = []
    for q in sorted(quotes, key=lambda q: q.frozen["odds_snapshot_id"]):
        rows = by_id[q.frozen["odds_snapshot_id"]]
        movement = rows[0] if len(rows) == 1 else {}
        previous = None
        diagnostics = ["DUPLICATE_MOVEMENT"] if len(rows) > 1 else []
        if movement.get("previous_odds") is not None:
            try:
                previous = price(movement["previous_odds"])
                if price(movement["current_odds"]) != q.odds or not movement.get("previous_snapshot_id"):
                    raise ValueError("Movement does not match its quote")
            except (KeyError, ValueError):
                previous = None
                diagnostics.append("INVALID_MOVEMENT")
        deltas: dict[str, str | None] = dict.fromkeys(
            (
                "odds_delta",
                "odds_pct_delta",
                "raw_implied_probability_delta",
            )
        )
        if previous is not None and q.odds is not None:
            deltas = {
                "odds_delta": encoded(q.odds - previous),
                "odds_pct_delta": encoded((q.odds - previous) / previous * Decimal(100)),
                "raw_implied_probability_delta": encoded(ONE / q.odds - ONE / previous),
            }
        # Each series has its own previous observation. No previous market or no-vig delta is invented.
        items.append(
            {
                **{
                    key: q.frozen[key]
                    for key in (
                        "odds_snapshot_id",
                        "provider",
                        "bookmaker",
                        "market_type",
                        "selection",
                        "line",
                    )
                },
                "previous_snapshot_id": movement.get("previous_snapshot_id"),
                "current_odds": q.frozen["decimal_odds"],
                "previous_odds": movement.get("previous_odds"),
                **deltas,
                "diagnostics": diagnostics,
            }
        )
    return {"pct_delta_unit": "percent", "items": items}


def build_market_data(feature: FeatureData) -> dict:
    """Only frozen input; deterministic even if the caller changes the Decimal context."""
    with localcontext(Context(prec=DECIMAL_PRECISION, rounding=ROUND_HALF_EVEN)):
        quotes = [read_quote(q) for q in feature.market["quotes"]]
        groups: dict[tuple, list[Quote]] = defaultdict(list)
        peers: dict[tuple, set[str]] = defaultdict(set)
        for q in quotes:
            source = (q.frozen["provider"], q.frozen["bookmaker"], q.frozen["market_type"])
            groups[(*source, q.canonical_line)].append(q)
            peers[source].add(q.frozen["selection"])
        method: MarginRemovalMethod = ProportionalNormalization()
        markets = [
            source_market(groups[key], peers[key[:3]], method)
            for key in sorted(groups, key=lambda key: (*key[:3], key[3] is not None, key[3] or ZERO))
        ]
        external, means = consensus(markets)
        sporttery = {
            pool: [
                m.data
                for m in markets
                if m.data["provider"] == "sporttery" and m.data["market_type"] == "SPORTTERY_" + pool
            ]
            for pool in ("HAD", "HHAD", "TTG")
        }
        had = [
            m
            for m in markets
            if m.data["provider"] == "sporttery"
            and m.data["market_type"] == "SPORTTERY_HAD"
            and m.data["complete"]
        ]
        diagnostics = []
        if not means:
            diagnostics.append("NO_COMPLETE_EXTERNAL_1X2")
        if len(had) > 1:
            diagnostics.append("AMBIGUOUS_SPORTTERY_HAD")
        gap = (
            {s: encoded(means[s] - had[0].probabilities[s]) for s in THREE_WAY}
            if means and len(had) == 1
            else None
        )
        return {
            "version": MARKET_MODEL_VERSION,
            "normalization_method": NORMALIZATION_METHOD,
            "rules": {
                "decimal_precision": DECIMAL_PRECISION,
                "output_decimal_places": 24,
                "rounding": ROUND_HALF_EVEN,
                "high_overround_threshold": str(HIGH_OVERROUND_THRESHOLD),
                "gap_direction": "external_consensus_minus_sporttery_no_vig",
                "source_identity": ["provider", "bookmaker"],
            },
            "source_markets": [m.data for m in markets],
            "external_consensus": external,
            "sporttery": sporttery,
            "sporttery_external_gap": gap,
            "movement": movements(feature, quotes),
            "diagnostics": diagnostics,
        }
