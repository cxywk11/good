import copy
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta, timezone
from decimal import ROUND_UP, Decimal, FloatOperation, Inexact, localcontext
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from jc.analysis.contracts import FeatureData
from jc.analysis.features import get_or_create_snapshot
from jc.analysis.market import (
    MARKET_MODEL_VERSION,
    NORMALIZATION_METHOD,
    ProportionalNormalization,
    build_market_data,
)
from jc.analysis.market_snapshots import FeatureNotFound, get_or_create_market_snapshot
from jc.config import get_settings
from jc.models import FeatureSnapshot, MarketModelSnapshot, Match, MatchVersion, ProviderState
from jc.time import utcnow
from sqlalchemy import event, func, inspect, select, text
from sqlalchemy.exc import DatabaseError, IntegrityError
from test_features import Timeline

D = Decimal
TOLERANCE = D("1e-23")
THREE = ("HOME", "DRAW", "AWAY")


def quotes(
    prices=("2", "3.5", "4"),
    *,
    selections=THREE,
    provider="external",
    bookmaker="book",
    market="1X2",
    lines=None,
):
    return [
        dict(
            odds_snapshot_id=f"{provider}:{bookmaker}:{market}:{selection}:{line}",
            provider=provider,
            bookmaker=bookmaker,
            market_type=market,
            selection=selection,
            line=line,
            decimal_odds=price,
            mapping_id=None,
            mapping_version=None,
        )
        for selection, price, line in zip(selections, prices, lines or [None] * len(prices), strict=True)
    ]


def feature(items, movement=None):
    return FeatureData(
        market={"quotes": items},
        odds_movement={"items": movement or []},
        team_strength={},
        schedule={},
        squad={},
        context={"mock": True},
        data_quality={},
    )


def outcome_probabilities(source):
    return {o["selection"]: D(o["no_vig_probability"]) for o in source["outcomes"]}


def assert_close(actual, expected):
    assert abs(D(actual) - D(expected)) <= TOLERANCE


def assert_complete(source):
    assert source["complete"]
    assert_close(sum(outcome_probabilities(source).values()), 1)


def test_raw_vig_and_proportional_normalization():
    result = build_market_data(feature(quotes()))
    source = result["source_markets"][0]
    assert_complete(source)
    assert [D(o["raw_implied_probability"]) for o in source["outcomes"]] == [
        D("0.5"),
        D("0.285714285714285714285714"),
        D("0.25"),
    ]
    assert_close(source["overround"], D(29) / D(28))
    assert_close(source["vig"], D(1) / D(28))
    for selection, expected in zip(THREE, (D(14) / D(29), D(8) / D(29), D(7) / D(29)), strict=True):
        assert_close(outcome_probabilities(source)[selection], expected)
    assert result["version"] == MARKET_MODEL_VERSION
    assert result["normalization_method"] == NORMALIZATION_METHOD


def test_decimal_only_context_independent_and_input_unchanged(monkeypatch):
    frozen = feature(quotes())
    before = copy.deepcopy(frozen)
    original = ProportionalNormalization.normalize

    def checked(self, implied):
        assert all(isinstance(value, Decimal) for value in implied)
        values = original(self, implied)
        assert all(isinstance(value, Decimal) for value in values)
        return values

    monkeypatch.setattr(ProportionalNormalization, "normalize", checked)
    expected = build_market_data(frozen)
    with localcontext() as context:
        context.prec = 6
        context.rounding = ROUND_UP
        context.traps[FloatOperation] = True
        context.traps[Inexact] = True
        assert build_market_data(frozen) == expected
    assert frozen == before

    def no_floats(value):
        assert not isinstance(value, float)
        if isinstance(value, dict):
            for item in value.values():
                no_floats(item)
        elif isinstance(value, list):
            for item in value:
                no_floats(item)

    no_floats(expected)


@pytest.mark.parametrize("missing", THREE)
def test_incomplete_1x2_never_normalized_or_in_consensus(missing):
    result = build_market_data(feature([q for q in quotes() if q["selection"] != missing]))
    source = result["source_markets"][0]
    assert not source["complete"]
    assert f"MISSING_SELECTION:{missing}" in source["diagnostics"]
    assert source["overround"] is None and source["vig"] is None
    assert all(o["no_vig_probability"] is None for o in source["outcomes"])
    assert result["external_consensus"]["source_count"] == 0
    assert result["external_consensus"]["p_market"] is None


def test_no_cross_bookmaker_stitching():
    items = quotes()
    for index, q in enumerate(items):
        q["bookmaker"] = f"book-{index}"
    result = build_market_data(feature(items))
    assert len(result["source_markets"]) == 3
    assert not any(m["complete"] for m in result["source_markets"])
    assert result["external_consensus"]["source_count"] == 0


@pytest.mark.parametrize(
    "second_provider,second_book", [("external", "book-b"), ("another-provider", "book")]
)
def test_two_equal_sources_statistics_and_provider_identity(second_provider, second_book):
    result = build_market_data(
        feature(
            quotes(("2", "4", "4")) + quotes(("4", "2", "4"), provider=second_provider, bookmaker=second_book)
        )
    )
    consensus = result["external_consensus"]
    assert consensus["source_count"] == 2
    assert len(consensus["sources"]) == 2
    home = {key: D(value) for key, value in consensus["HOME"].items()}
    assert home == dict(
        mean=D("0.375"), median=D("0.375"), min=D("0.25"), max=D("0.5"), population_stddev=D("0.125")
    )
    assert D(consensus["AWAY"]["population_stddev"]) == 0
    assert sum(D(value) for value in consensus["p_market"].values()) == 1


def test_odd_count_median_population_stddev_and_single_source():
    items = (
        quotes(("2", "4", "4"))
        + quotes(("4", "2", "4"), bookmaker="b")
        + quotes(("4", "4", "2"), bookmaker="c")
    )
    home = build_market_data(feature(items))["external_consensus"]["HOME"]
    assert D(home["median"]) == D("0.25")
    assert_close(home["mean"], D(1) / 3)
    assert_close(home["population_stddev"], (D(1) / 72).sqrt())
    single = build_market_data(feature(quotes()))["external_consensus"]["HOME"]
    assert single["mean"] == single["median"] == single["min"] == single["max"]
    assert D(single["population_stddev"]) == 0


def test_each_source_normalized_before_equal_mean_anomalies_not_downweighted():
    result = build_market_data(feature(quotes(("2", "4", "4")) + quotes(("2", "2", "4"), bookmaker="b")))
    assert D(result["external_consensus"]["HOME"]["mean"]) == D("0.45")
    high_vig = next(m for m in result["source_markets"] if m["bookmaker"] == "b")
    assert "HIGH_OVERROUND" in high_vig["diagnostics"]
    assert result["external_consensus"]["source_count"] == 2


def test_sporttery_had_gap_direction_and_total_exclusion_from_external():
    had = quotes(("4", "2", "4"), provider="sporttery", market="SPORTTERY_HAD")
    # Even a Sporttery quote labelled 1X2 must be excluded by provider.
    result = build_market_data(feature(quotes(("2", "4", "4")) + had + quotes(provider="sporttery")))
    assert result["external_consensus"]["source_count"] == 1
    assert result["external_consensus"]["sources"] == [{"provider": "external", "bookmaker": "book"}]
    assert_complete(result["sporttery"]["HAD"][0])
    assert {s: D(v) for s, v in result["sporttery_external_gap"].items()} == dict(
        HOME=D("0.25"), DRAW=D("-0.25"), AWAY=D(0)
    )
    assert "edge" not in json.dumps(result).lower()
    alone = build_market_data(feature(had))
    assert_complete(alone["sporttery"]["HAD"][0])
    assert alone["sporttery_external_gap"] is None
    assert alone["external_consensus"]["source_count"] == 0


def test_ambiguous_sporttery_had_does_not_choose_arbitrary_gap():
    items = (
        quotes()
        + quotes(provider="sporttery", market="SPORTTERY_HAD")
        + quotes(provider="sporttery", bookmaker="b", market="SPORTTERY_HAD")
    )
    result = build_market_data(feature(items))
    assert result["sporttery_external_gap"] is None
    assert "AMBIGUOUS_SPORTTERY_HAD" in result["diagnostics"]


@pytest.mark.parametrize(
    "home_line,away_line,canonical", [("-0.5", "+0.500", "-0.5"), ("0", "-0", "0"), ("0.25", "-0.25", "0.25")]
)
def test_asian_handicap_canonical_home_line(home_line, away_line, canonical):
    result = build_market_data(
        feature(
            quotes(
                ("1.9", "2"),
                selections=("HOME", "AWAY"),
                market="ASIAN_HANDICAP",
                lines=[home_line, away_line],
            )
        )
    )
    assert len(result["source_markets"]) == 1
    source = result["source_markets"][0]
    assert_complete(source)
    assert source["canonical_home_line"] == source["canonical_line"] == canonical
    assert_close(outcome_probabilities(source)["HOME"], D(20) / 39)
    assert result["sporttery"]["HHAD"] == []
    assert result["external_consensus"]["source_count"] == 0


def test_handicap_mismatch_never_silently_fixed():
    result = build_market_data(
        feature(
            quotes(("2", "2"), selections=("HOME", "AWAY"), market="ASIAN_HANDICAP", lines=["-0.5", "-0.5"])
        )
    )
    assert len(result["source_markets"]) == 2
    for source in result["source_markets"]:
        assert not source["complete"]
        assert "HANDICAP_LINE_MISMATCH" in source["diagnostics"]
        assert source["outcomes"][0]["no_vig_probability"] is None


def test_multiple_handicap_lines_remain_independent():
    items = sum(
        (
            quotes(("2", "2"), selections=("HOME", "AWAY"), market="ASIAN_HANDICAP", lines=lines)
            for lines in (["-0.5", "0.5"], ["-1", "1"])
        ),
        [],
    )
    result = build_market_data(feature(items))
    assert len(result["source_markets"]) == 2
    for source in result["source_markets"]:
        assert_complete(source)
        assert source["diagnostics"] == []


@pytest.mark.parametrize("lines,complete", [(["2.5", "2.500"], True), (["2.5", "3.5"], False)])
def test_totals_same_line_only_and_no_ttg_conversion(lines, complete):
    result = build_market_data(
        feature(quotes(("1.9", "2"), selections=("OVER", "UNDER"), market="TOTALS", lines=lines))
    )
    assert result["sporttery"]["TTG"] == []
    for source in result["source_markets"]:
        assert source["complete"] == complete
        if complete:
            assert_complete(source)
            assert_close(outcome_probabilities(source)["OVER"], D(20) / 39)
        else:
            assert source["overround"] is None


def test_sporttery_hhad_is_three_way_on_one_common_line():
    items = quotes(provider="sporttery", market="SPORTTERY_HHAD", lines=["-1"] * 3)
    result = build_market_data(feature(items))
    assert_complete(result["sporttery"]["HHAD"][0])
    assert result["sporttery"]["HHAD"][0]["canonical_line"] == "-1"
    items[-1]["line"] = "1"
    assert not any(m["complete"] for m in build_market_data(feature(items))["source_markets"])


@pytest.mark.parametrize("missing", [None, "0", "1", "2", "3", "4", "5", "6", "7+"])
def test_ttg_requires_all_eight_selections(missing):
    selections = ("0", "1", "2", "3", "4", "5", "6", "7+")
    items = quotes(("8",) * 8, selections=selections, provider="sporttery", market="SPORTTERY_TTG")
    items = [q for q in items if q["selection"] != missing]
    # A complete totals market must never fill a missing TTG selection.
    items += quotes(("2", "2"), selections=("OVER", "UNDER"), market="TOTALS", lines=["2.5"] * 2)
    source = build_market_data(feature(items))["sporttery"]["TTG"][0]
    assert source["complete"] == (missing is None)
    if missing is None:
        assert_complete(source)
        assert set(outcome_probabilities(source).values()) == {D("0.125")}
    else:
        assert f"MISSING_SELECTION:{missing}" in source["diagnostics"]


@pytest.mark.parametrize("market", ["SPORTTERY_CRS", "SPORTTERY_HAFU", "CORRECT_SCORE", "FUTURE_MARKET"])
def test_unsupported_markets_keep_odds_and_do_not_crash(market):
    result = build_market_data(feature(quotes(market=market)))
    source = result["source_markets"][0]
    assert source["unsupported_for_v1"] and not source["complete"]
    assert "UNSUPPORTED_FOR_V1" in source["diagnostics"]
    assert len(source["outcomes"]) == 3
    assert all(o["no_vig_probability"] is None for o in source["outcomes"])


@pytest.mark.parametrize(
    "prices,overround,diagnostic",
    [
        (("4", "4", "4"), "0.75", "NEGATIVE_OVERROUND"),
        (("2", "2", "2"), "1.5", "HIGH_OVERROUND"),
        (("2.5",) * 3, "1.2", None),
    ],
)
def test_overround_diagnostics_preserve_actual_values(prices, overround, diagnostic):
    result = build_market_data(feature(quotes(prices)))
    source = result["source_markets"][0]
    assert_complete(source)
    assert D(source["overround"]) == D(overround)
    assert D(source["vig"]) == D(overround) - 1
    assert source["diagnostics"] == ([diagnostic] if diagnostic else [])
    assert result["external_consensus"]["source_count"] == 1


@pytest.mark.parametrize("bad", ["NaN", "Infinity", "1", "0", "invalid", 2.0])
def test_invalid_odds_are_not_normalized(bad):
    items = quotes()
    items[0]["decimal_odds"] = bad
    result = build_market_data(feature(items))
    assert not result["source_markets"][0]["complete"]
    assert "INVALID_DECIMAL_ODDS" in result["source_markets"][0]["diagnostics"]
    assert result["external_consensus"]["source_count"] == 0


@pytest.mark.parametrize("problem", ["duplicate", "unexpected", "binding", "line"])
def test_ambiguous_or_incompatible_inputs_fail_closed(problem):
    items = quotes()
    if problem in {"duplicate", "unexpected"}:
        extra = {**items[0], "odds_snapshot_id": "extra"}
        if problem == "unexpected":
            extra["selection"] = "OTHER"
        items.append(extra)
    elif problem == "binding":
        items[0]["mapping_version"] = 2
    else:
        for q in items:
            q["line"] = "0"
    result = build_market_data(feature(items))
    assert not result["source_markets"][0]["complete"]
    assert result["external_consensus"]["source_count"] == 0


def test_individual_movements_missing_previous_stays_null():
    items = quotes(("2.5", "4", "4"))
    movement = [
        dict(
            odds_snapshot_id=items[0]["odds_snapshot_id"],
            previous_snapshot_id="old-home",
            previous_odds="2",
            current_odds="2.5",
        )
    ]
    result = build_market_data(feature(items, movement))
    home = next(m for m in result["movement"]["items"] if m["selection"] == "HOME")
    assert D(home["odds_delta"]) == D("0.5")
    assert D(home["odds_pct_delta"]) == 25
    assert D(home["raw_implied_probability_delta"]) == D("-0.1")
    for item in result["movement"]["items"]:
        if item["selection"] != "HOME":
            assert (
                item["odds_delta"] is item["odds_pct_delta"] is item["raw_implied_probability_delta"] is None
            )
    assert "previous_market_probability" not in json.dumps(result)


def test_deterministic_input_order_and_no_fabricated_empty_data():
    items = quotes() + quotes(bookmaker="b")
    assert build_market_data(feature(items)) == build_market_data(feature(list(reversed(items))))
    empty = build_market_data(feature([]))
    assert empty["source_markets"] == []
    assert empty["sporttery_external_gap"] is None
    assert empty["external_consensus"]["p_market"] is None
    assert empty["movement"]["items"] == []


@pytest.mark.parametrize("problem", ["duplicate", "previous_zero", "current_mismatch"])
def test_invalid_movement_never_fabricates_delta(problem):
    items = quotes()
    movement = dict(
        odds_snapshot_id=items[0]["odds_snapshot_id"],
        previous_snapshot_id="old",
        previous_odds="3",
        current_odds="2",
    )
    if problem == "previous_zero":
        movement["previous_odds"] = "0"
    elif problem == "current_mismatch":
        movement["current_odds"] = "4"
    rows = [movement, movement] if problem == "duplicate" else [movement]
    result = build_market_data(feature(items, rows))
    home = next(m for m in result["movement"]["items"] if m["selection"] == "HOME")
    assert home["diagnostics"]
    assert home["odds_delta"] is home["odds_pct_delta"] is home["raw_implied_probability_delta"] is None


@pytest.fixture
def timeline(sessions, monkeypatch):
    result = Timeline(sessions, monkeypatch)
    with sessions() as db:
        mapping = result.external(db)
        for selection, price in zip(THREE, ("2", "3.5", "4"), strict=True):
            result.quote(
                db, price, provider="external", selection=selection, mapping_id=mapping.id, mapping_version=1
            )
            result.quote(db, price, market_type="SPORTTERY_HAD", selection=selection)
        db.commit()
    return result


def freeze(sessions, timeline):
    with sessions() as db:
        row = get_or_create_snapshot(db, timeline.match_id, timeline.cutoff, mock=True)
        db.commit()
        return row


def test_market_service_reads_only_one_frozen_feature_even_after_later_data(sessions, timeline):
    frozen = freeze(sessions, timeline)
    before = copy.deepcopy(frozen.feature_data)
    expected = build_market_data(FeatureData.model_validate(before))
    timeline.now = timeline.cutoff + timedelta(minutes=1)
    with sessions() as db:
        timeline.quote(db, "9", market_type="SPORTTERY_HAD")
        current = db.get(Match, timeline.match_id)
        current.home_team_name = "Later current row"
        current.kickoff_at += timedelta(days=2)
        db.add(ProviderState(provider="sporttery", status="DOWN"))
        old = db.get(MatchVersion, timeline.version_id)
        raw = timeline.raw(db)
        db.add(
            MatchVersion(
                match_id=current.id,
                raw_payload_id=raw.id,
                collected_at=timeline.now,
                created_at=timeline.now,
                state={**old.state, "kickoff_at": current.kickoff_at.isoformat()},
            )
        )
        db.commit()

    statements = []

    def only_snapshots(conn, cursor, statement, parameters, context, executemany):
        sql = statement.lower()
        statements.append(sql)
        assert not any(
            f"from {table}" in sql
            for table in (
                "odds_snapshots",
                "odds_observations",
                "matches",
                "match_versions",
                "provider_states",
                "provider_raw_payloads",
                "audit_logs",
                "analysis_visibility",
            )
        )
        if sql.startswith("select"):
            assert "where" in sql  # ID lookup, no full-history scan.

    with sessions() as db:
        engine = db.get_bind()
        event.listen(engine, "before_cursor_execute", only_snapshots)
        try:
            market = get_or_create_market_snapshot(db, frozen.id, mock=True)
            assert market.market_data == expected
            assert market.match_id == frozen.match_id and market.analysis_cutoff == frozen.analysis_cutoff
            assert get_or_create_market_snapshot(db, frozen.id, mock=True).id == market.id
        finally:
            event.remove(engine, "before_cursor_execute", only_snapshots)
        # Existing after_commit visibility hook is intentionally unchanged and outside the engine.
        db.commit()
        assert db.get(FeatureSnapshot, frozen.id).feature_data == before
        assert db.get(MarketModelSnapshot, market.id).market_data == expected
    assert sum("from feature_snapshots" in statement for statement in statements) == 2


def test_concurrent_market_snapshot_idempotency(sessions, timeline):
    frozen = freeze(sessions, timeline)

    def create(_):
        with sessions() as db:
            row = get_or_create_market_snapshot(db, frozen.id, mock=True)
            db.commit()
            return row.id, row.market_data

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(create, range(4)))
    assert all(result == results[0] for result in results)
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(MarketModelSnapshot)) == 1


@pytest.mark.parametrize("operation", ["UPDATE", "DELETE"])
def test_market_snapshot_database_immutability(sessions, timeline, operation):
    frozen = freeze(sessions, timeline)
    with sessions() as db:
        row = get_or_create_market_snapshot(db, frozen.id, mock=True)
        db.commit()
        sql = (
            "UPDATE market_model_snapshots SET market_model_version='changed'"
            if operation == "UPDATE"
            else "DELETE FROM market_model_snapshots"
        )
        with pytest.raises(DatabaseError, match="append-only"):
            db.execute(text(sql))
            db.commit()
        db.rollback()
        assert db.get(MarketModelSnapshot, row.id).market_model_version == MARKET_MODEL_VERSION


def test_unique_constraint_and_versions_cannot_be_relabeled(sessions, timeline):
    frozen = freeze(sessions, timeline)
    with sessions() as db:
        with pytest.raises(ValueError, match="market_model_version"):
            get_or_create_market_snapshot(db, frozen.id, "invented-version", mock=True)
        row = get_or_create_market_snapshot(db, frozen.id, mock=True)
        db.commit()
        values = {column.name: getattr(row, column.name) for column in MarketModelSnapshot.__table__.columns}
        values["id"] = str(uuid4())
        with pytest.raises(IntegrityError):
            db.execute(MarketModelSnapshot.__table__.insert().values(**values))
        db.rollback()


def test_market_v1_rejects_unknown_feature_contract(sessions, timeline):
    frozen = freeze(sessions, timeline)
    with sessions() as db:
        unknown = FeatureSnapshot(
            match_id=frozen.match_id,
            analysis_cutoff=frozen.analysis_cutoff,
            feature_version="future-feature",
            feature_data=frozen.feature_data,
            data_quality_score=frozen.data_quality_score,
            mock=True,
        )
        db.add(unknown)
        db.commit()
        with pytest.raises(ValueError, match="feature_version"):
            get_or_create_market_snapshot(db, unknown.id, mock=True)
        assert db.scalar(select(func.count()).select_from(MarketModelSnapshot)) == 0


def test_api_envelope_cutoff_validation_and_idempotency(client, timeline, sessions):
    path = f"/api/v1/matches/{timeline.match_id}/market-model"
    params = {"analysis_cutoff": timeline.cutoff.isoformat()}
    first = client.get(path, params=params)
    assert first.status_code == 200
    body = first.json()
    assert body["success"] and body["request_id"]
    data = body["data"]
    assert data["mock"] is True
    assert data["market_model_version"] == MARKET_MODEL_VERSION
    assert data["normalization_method"] == NORMALIZATION_METHOD
    assert data == client.get(path, params=params).json()["data"]
    beijing = timeline.cutoff.astimezone(timezone(timedelta(hours=8))).isoformat()
    assert data == client.get(path, params={"analysis_cutoff": beijing}).json()["data"]
    with sessions() as db:
        assert db.get(FeatureSnapshot, data["feature_snapshot_id"])
        assert db.get(MarketModelSnapshot, data["market_snapshot_id"])
    for cutoff in ("2026-09-01T12:00:00", (utcnow() + timedelta(days=1)).isoformat()):
        assert client.get(path, params={"analysis_cutoff": cutoff}).status_code == 422
    assert client.get(path).status_code == 422
    assert (
        client.get(
            path, params={"analysis_cutoff": (timeline.start - timedelta(seconds=1)).isoformat()}
        ).status_code
        == 404
    )
    assert client.get(f"/api/v1/matches/{uuid4()}/market-model", params=params).status_code == 404
    with sessions() as db:
        mid, _ = timeline.match(db, kickoff=timeline.start + timedelta(hours=1))
        db.commit()
    assert client.get(f"/api/v1/matches/{mid}/market-model", params=params).status_code == 422


def test_mock_live_isolation_even_with_cached_market(client, sessions, timeline, monkeypatch):
    frozen = freeze(sessions, timeline)
    with sessions() as db:
        get_or_create_market_snapshot(db, frozen.id, mock=True)
        db.commit()
        with pytest.raises(FeatureNotFound):
            get_or_create_market_snapshot(db, frozen.id, mock=False)
        with pytest.raises(FeatureNotFound):
            get_or_create_market_snapshot(db, str(uuid4()), mock=True)
    monkeypatch.setattr(get_settings(), "demo_mode", False)
    path = f"/api/v1/matches/{timeline.match_id}/market-model"
    assert client.get(path, params={"analysis_cutoff": timeline.cutoff.isoformat()}).status_code == 404


def test_live_snapshot_does_not_enter_mock_mode(client, sessions, timeline, monkeypatch):
    # Synthetic fixtures exercise the live flag path; this is not a real Provider validation.
    original_raw = timeline.raw

    def live_raw(db, provider="sporttery", **updates):
        return original_raw(db, provider, **{**updates, "mock": False})

    monkeypatch.setattr(timeline, "raw", live_raw)
    with sessions() as db:
        timeline.match_id, timeline.version_id = timeline.match(db, mock=False)
        for selection in THREE:
            timeline.quote(db, "3", market_type="SPORTTERY_HAD", selection=selection, mock=False)
        db.commit()
    monkeypatch.setattr(get_settings(), "demo_mode", False)
    path = f"/api/v1/matches/{timeline.match_id}/market-model"
    params = {"analysis_cutoff": timeline.cutoff.isoformat()}
    response = client.get(path, params=params)
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["mock"] is False
    assert_complete(data["market_data"]["sporttery"]["HAD"][0])
    with sessions() as db, pytest.raises(FeatureNotFound):
        get_or_create_market_snapshot(db, data["feature_snapshot_id"], mock=True)
    monkeypatch.setattr(get_settings(), "demo_mode", True)
    assert client.get(path, params=params).status_code == 404


def test_migration_upgrade_check_downgrade_preserves_features(sessions, timeline):
    frozen = freeze(sessions, timeline)
    with sessions() as db:
        get_or_create_market_snapshot(db, frozen.id, mock=True)
        db.commit()
        if db.bind.dialect.name == "postgresql":
            columns = {
                c["name"]: str(c["type"]) for c in inspect(db.bind).get_columns("market_model_snapshots")
            }
            assert columns["market_data"] == "JSONB"
    config = Config("alembic.ini")
    command.check(config)
    command.downgrade(config, "007_feature_foundation")
    with sessions() as db:
        assert "market_model_snapshots" not in inspect(db.bind).get_table_names()
        assert db.get(FeatureSnapshot, frozen.id).feature_data == frozen.feature_data
        with pytest.raises(DatabaseError, match="append-only"):
            db.execute(text("UPDATE feature_snapshots SET feature_version=feature_version"))
        db.rollback()
    command.upgrade(config, "head")
    command.check(config)
    with sessions() as db:
        row = get_or_create_market_snapshot(db, frozen.id, mock=True)
        assert row.market_data == build_market_data(FeatureData.model_validate(frozen.feature_data))
        db.commit()
