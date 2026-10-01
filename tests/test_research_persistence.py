"""Run the same contracts, migration and SQL bypass tests on SQLite and PostgreSQL."""

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal, localcontext
from pathlib import Path
from threading import Event
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from jc.analysis.goals_baseline import estimate_goals_baseline
from jc.analysis.market import build_market_data
from jc.analysis.research_replay import (
    AvailabilityBasis,
    ReplayCutoffSpec,
    ResearchDataset,
    ResearchMatch,
    ResearchOddsQuote,
    ResearchResult,
    ResearchSource,
    build_research_feature,
    run_research_evaluation,
)
from jc.db import Base
from jc.models import RawPayload
from jc.research import schema as s
from jc.research.contracts import (
    ResearchImport,
    ResearchRawArtifactInput,
    ResearchRecordProvenance,
    ResearchSourceInput,
    SportteryVerificationInput,
    canonical_bytes,
    content_hash,
    dataset_content_hash,
    validate_import,
)
from jc.research.importer import import_research_dataset
from jc.research.repository import (
    DatasetConflict,
    append_raw_artifact,
    append_record,
    append_records,
    append_source,
    create_research_dataset,
    dataset_row,
    load_research_dataset,
    reject_dataset,
    seal_dataset,
    verified_sporttery_targets,
)
from sqlalchemy import event, func, inspect, select, text
from sqlalchemy.exc import DatabaseError

T = datetime(2026, 10, 1, tzinfo=UTC)
MEMBERS = (s.sources, s.raw_artifacts, s.matches, s.odds_quotes, s.results)


@pytest.fixture
def engine(sessions):
    return sessions.kw["bind"]


@pytest.fixture
def packet():
    # Raw is constructed before parsing the frozen replay contracts.
    payload = json.loads(Path("tests/fixtures/research_history.json").read_text(encoding="utf-8"))
    raw = tuple(
        ResearchRawArtifactInput(
            source_name=source["source_name"],
            artifact_type="SYNTHETIC_FIXTURE",
            retrieved_at=T,
            content_type="application/json",
            payload=payload,
            external_ref="fixture://research_history.json",
            metadata={"synthetic": True},
        )
        for source in payload["source_manifest"]
    )

    def parse(kind, row):
        values = dict(row)
        for key, value in values.items():
            if key.endswith("_at") and value is not None:
                values[key] = datetime.fromisoformat(value)
            elif key in ("line", "decimal_odds") and value is not None:
                values[key] = Decimal(value)
        return kind(**values)

    ds = ResearchDataset(
        **{
            **payload,
            "matches": tuple(parse(ResearchMatch, r) for r in payload["matches"]),
            "odds": tuple(parse(ResearchOddsQuote, r) for r in payload["odds"]),
            "results": tuple(parse(ResearchResult, r) for r in payload["results"]),
            "source_manifest": tuple(ResearchSource(**r) for r in payload["source_manifest"]),
        }
    )
    artifacts = {a.source_name: a for a in raw}
    provenance = []
    for kind, rows in (("MATCH", ds.matches), ("ODDS", ds.odds), ("RESULT", ds.results)):
        for row in rows:
            source = row.provider if kind == "ODDS" else row.source
            provenance.append(
                ResearchRecordProvenance(
                    record_type=kind,
                    record_id=row.research_match_id if kind == "MATCH" else row.record_id,
                    source_name=source,
                    raw_content_hash=artifacts[source].content_hash,
                )
            )
    return ResearchImport(
        dataset=ds,
        description="Synthetic integration fixture; no real historical conclusions.",
        manifest={"synthetic": True, "fixture": "research_history.json"},
        sources=tuple(
            ResearchSourceInput(
                source=source, provider_name=source.source_name, license_note="Local synthetic test data."
            )
            for source in ds.source_manifest
        ),
        raw_artifacts=raw,
        provenance=tuple(provenance),
    )


def stage(connection, packet, *, records=True, raw=True):
    did = create_research_dataset(
        connection, packet.dataset, description=packet.description, manifest=packet.manifest
    )
    for source in packet.sources:
        append_source(connection, did, source)
    if raw:
        for artifact in packet.raw_artifacts:
            append_raw_artifact(connection, did, artifact)
    if records:
        append_records(connection, did, packet.dataset, packet.provenance, packet.sporttery_verifications)
    return did


def first(connection, table):
    return dict(connection.execute(select(table)).mappings().first())


def insert_copy(connection, table, **changes):
    row = first(connection, table)
    row.update(id=str(uuid4()), **changes)
    connection.execute(table.insert().values(**row))


def test_migration_009_upgrade_check_downgrade(engine, packet):
    config = Config("alembic.ini")
    with engine.connect() as conn:
        assert (
            conn.scalar(text("SELECT version_num FROM alembic_version")) == "009_research_dataset_persistence"
        )
        tables = set(inspect(conn).get_table_names())
        assert set(s.metadata.tables) <= tables
        for table in s.metadata.tables:
            assert all(
                fk["referred_table"].startswith("research_") for fk in inspect(conn).get_foreign_keys(table)
            )
        numeric = {c["name"]: c["type"] for c in inspect(conn).get_columns("research_odds_quotes")}
        assert str(numeric["decimal_odds"]) == ("NUMERIC" if conn.dialect.name == "postgresql" else "TEXT")
    command.check(config)
    import_research_dataset(engine, packet)
    command.downgrade(config, "008_market_probability")
    with engine.connect() as conn:
        assert set(inspect(conn).get_table_names()) == tables - set(s.metadata.tables)
    command.upgrade(config, "head")
    command.check(config)
    command.downgrade(config, "base")
    with engine.connect() as conn:
        assert set(inspect(conn).get_table_names()) == {"alembic_version"}
    command.upgrade(config, "head")
    command.check(config)


def test_raw_first_building_source_members_and_quality(engine, packet):
    with engine.begin() as conn:
        did = stage(conn, packet, records=False, raw=False)
        assert dataset_row(conn, did)["status"] == "BUILDING"
        assert len(conn.execute(select(s.sources)).all()) == 2
        with pytest.raises(ValueError, match="Raw artifact"):
            append_records(conn, did, packet.dataset, packet.provenance)
        assert conn.scalar(select(func.count()).select_from(s.matches)) == 0
        for raw in packet.raw_artifacts:
            append_raw_artifact(conn, did, raw)
        append_records(conn, did, packet.dataset, packet.provenance)
        assert conn.scalar(select(func.count()).select_from(s.matches)) == 13
        assert conn.scalar(select(func.count()).select_from(s.odds_quotes)) == 12
        assert conn.scalar(select(func.count()).select_from(s.results)) == 13
        assert all(
            row == "UNVERIFIED" for row in conn.scalars(select(s.matches.c.sporttery_verification_status))
        )
        assert all(row == "UNVERIFIED" for row in conn.scalars(select(s.sources.c.verification_status)))
        sealed = seal_dataset(conn, did)
        q = sealed["quality_summary"]
        assert q == {
            "match_count": 13,
            "sporttery_target_verified_count": 0,
            "odds_count": 12,
            "result_count": 13,
            "sources_count": 2,
            "records_with_verified_availability": 38,
            "records_without_verified_availability": 0,
            "matches_missing_team_identity": 0,
            "results_missing_team_identity": 0,
            "date_min": min(m.kickoff_at for m in packet.dataset.matches).isoformat(),
            "date_max": max(m.kickoff_at for m in packet.dataset.matches).isoformat(),
        }
        assert sealed["sealed_at"] is not None and len(sealed["content_hash"]) == 64
        assert verified_sporttery_targets(conn, did) == ()


def test_round_trip_full_evaluation_and_live_sql_isolation(engine, packet):
    with engine.begin() as conn:
        # Leave an unproven LIVE raw row: any accidental Session commit would change visibility.
        conn.execute(
            RawPayload.__table__.insert().values(
                provider="test",
                resource_type="test",
                payload={"synthetic": True},
                source_url="fixture://live",
                collected_at=T,
                payload_hash="0" * 64,
            )
        )
        before = {
            name: conn.scalar(select(func.count()).select_from(table))
            for name, table in Base.metadata.tables.items()
        }
    sql = []

    def capture(conn, cursor, statement, parameters, context, many):
        sql.append(statement.lower())

    event.listen(engine, "before_cursor_execute", capture)
    try:
        sealed = import_research_dataset(engine, packet)
        with engine.connect() as conn:
            loaded = load_research_dataset(conn, packet.dataset.dataset_id, packet.dataset.dataset_version)
        assert loaded == packet.dataset
        spec = ReplayCutoffSpec(30)
        feature = build_research_feature(loaded, "target", spec)
        assert build_market_data(feature)["external_consensus"]["p_market"]
        assert estimate_goals_baseline(feature)["score"]["one_x_two"]
        report = run_research_evaluation(loaded, ["target"], spec)
        assert report == run_research_evaluation(packet.dataset, ["target"], spec)
        assert report["market_evaluable"] == report["goals_evaluable"] == 1
        assert report["live_visibility_proven"] is False
        assert sealed["content_hash"] == dataset_content_hash(packet)
    finally:
        event.remove(engine, "before_cursor_execute", capture)
    import re

    for name in Base.metadata.tables:
        assert not any(re.search(rf"\b{re.escape(name)}\b", statement) for statement in sql)
    with engine.connect() as conn:
        after = {
            name: conn.scalar(select(func.count()).select_from(table))
            for name, table in Base.metadata.tables.items()
        }
        assert before == after
        assert (
            after["feature_snapshots"] == after["market_model_snapshots"] == after["analysis_visibility"] == 0
        )


@pytest.mark.parametrize(
    "price,line",
    [
        ("2.123456789012345678901234567890123456789", "-0.12345678901234567890123456789"),
        ("1.000000000000000000000000000000000001", "0"),
        ("123456789012345678901234567890.1", "1.25000"),
    ],
)
def test_numeric_exact_roundtrip_without_decimal_context_rounding(engine, packet, price, line):
    q = replace(packet.dataset.odds[0], decimal_odds=Decimal(price), line=Decimal(line))
    packet = replace(packet, dataset=replace(packet.dataset, odds=(q, *packet.dataset.odds[1:])))
    with localcontext() as ctx:
        ctx.prec = 6
        import_research_dataset(engine, packet)
        with engine.connect() as conn:
            loaded = load_research_dataset(conn, packet.dataset.dataset_id, packet.dataset.dataset_version)
        assert loaded == packet.dataset


def test_hash_order_uuid_lifecycle_independence_and_idempotency(engine, packet):
    shuffled = replace(
        packet,
        sources=tuple(reversed(packet.sources)),
        raw_artifacts=tuple(reversed(packet.raw_artifacts)),
        provenance=tuple(reversed(packet.provenance)),
        manifest=dict(reversed(list(packet.manifest.items()))),
        dataset=replace(
            packet.dataset,
            matches=tuple(reversed(packet.dataset.matches)),
            odds=tuple(reversed(packet.dataset.odds)),
            results=tuple(reversed(packet.dataset.results)),
            source_manifest=tuple(reversed(packet.dataset.source_manifest)),
        ),
    )
    a = import_research_dataset(engine, packet)
    b = import_research_dataset(engine, shuffled)
    assert a == b
    other_version = replace(packet, dataset=replace(packet.dataset, dataset_version="fixture-v2"))
    c = import_research_dataset(engine, other_version)
    assert c["id"] != a["id"] and c["content_hash"] == a["content_hash"]
    assert content_hash({"a": 1, "b": [2, 3]}) == content_hash({"b": [2, 3], "a": 1})
    assert a["content_hash"] != packet.raw_artifacts[0].content_hash


@pytest.mark.parametrize(
    "change", ["manifest", "description", "license", "retrieval", "verification", "odds", "raw_metadata"]
)
def test_same_version_changed_business_content_conflicts(engine, packet, change):
    original = import_research_dataset(engine, packet)
    if change == "manifest":
        changed = replace(packet, manifest={**packet.manifest, "season": "2024"})
    elif change == "description":
        changed = replace(packet, description="Changed description")
    elif change == "license":
        changed = replace(
            packet, sources=(replace(packet.sources[0], license_note="Different license"), packet.sources[1])
        )
    elif change == "retrieval":
        source = replace(packet.dataset.source_manifest[0], retrieval_note="Different source declaration")
        changed = replace(
            packet,
            dataset=replace(packet.dataset, source_manifest=(source, packet.dataset.source_manifest[1])),
            sources=(replace(packet.sources[0], source=source), packet.sources[1]),
        )
    elif change == "verification":
        changed = replace(
            packet,
            sources=(replace(packet.sources[0], verification_note="Still unverified"), packet.sources[1]),
        )
    elif change == "odds":
        changed = replace(
            packet,
            dataset=replace(
                packet.dataset,
                odds=(replace(packet.dataset.odds[0], decimal_odds=Decimal("7")), *packet.dataset.odds[1:]),
            ),
        )
    else:
        changed = replace(
            packet,
            raw_artifacts=(
                replace(packet.raw_artifacts[0], metadata={"synthetic": True, "note": "revision"}),
                packet.raw_artifacts[1],
            ),
        )
    assert dataset_content_hash(changed) != original["content_hash"]
    with pytest.raises(DatasetConflict, match="CONFLICT"):
        import_research_dataset(engine, changed)


def test_raw_hash_idempotent_corrections_are_appended(engine, packet):
    with engine.begin() as conn:
        did = stage(conn, packet, records=False)
        raw = packet.raw_artifacts[0]
        assert append_raw_artifact(conn, did, raw) == append_raw_artifact(conn, did, raw)
        correction = replace(raw, payload={"corrected": True})
        assert append_raw_artifact(conn, did, correction) != append_raw_artifact(conn, did, raw)
        with pytest.raises(DatasetConflict):
            append_raw_artifact(conn, did, replace(raw, external_ref="fixture://changed"))
        assert conn.scalar(select(func.count()).select_from(s.raw_artifacts)) == 3


@pytest.mark.parametrize("table", MEMBERS, ids=lambda t: t.name)
@pytest.mark.parametrize("operation", ["update", "delete"])
@pytest.mark.parametrize("sealed", [False, True])
def test_all_members_append_only_even_sql_bypass(engine, packet, table, operation, sealed):
    with engine.begin() as conn:
        did = stage(conn, packet)
        if sealed:
            seal_dataset(conn, did)
        with pytest.raises(DatabaseError), conn.begin_nested():
            conn.execute(table.update().values(created_at=T) if operation == "update" else table.delete())


@pytest.mark.parametrize("table", MEMBERS, ids=lambda t: t.name)
@pytest.mark.parametrize("status", ["SEALED", "REJECTED"])
def test_no_member_insert_after_terminal_state(engine, packet, table, status):
    with engine.begin() as conn:
        did = stage(conn, packet)
        seal_dataset(conn, did) if status == "SEALED" else reject_dataset(conn, did)
        with pytest.raises(DatabaseError, match="BUILDING"), conn.begin_nested():
            insert_copy(conn, table)


@pytest.mark.parametrize(
    "state,new_state",
    [
        ("SEALED", "BUILDING"),
        ("SEALED", "REJECTED"),
        ("REJECTED", "BUILDING"),
        ("REJECTED", "SEALED"),
        ("BUILDING", "BUILDING"),
    ],
)
def test_dataset_illegal_transitions(engine, packet, state, new_state):
    with engine.begin() as conn:
        did = stage(conn, packet)
        if state == "SEALED":
            seal_dataset(conn, did)
        elif state == "REJECTED":
            reject_dataset(conn, did)
        with pytest.raises(DatabaseError), conn.begin_nested():
            conn.execute(s.datasets.update().values(status=new_state))


@pytest.mark.parametrize(
    "field,value",
    [
        ("description", "altered"),
        ("dataset_key", "new-key"),
        ("dataset_version", "v999"),
        ("manifest_json", {}),
    ],
)
def test_transition_cannot_change_other_fields(engine, packet, field, value):
    with engine.begin() as conn:
        stage(conn, packet)
        with pytest.raises(DatabaseError), conn.begin_nested():
            conn.execute(s.datasets.update().values(status="REJECTED", **{field: value}))


@pytest.mark.parametrize("status", ["BUILDING", "REJECTED", "SEALED"])
def test_dataset_delete_forbidden(engine, packet, status):
    with engine.begin() as conn:
        did = stage(conn, packet)
        if status == "SEALED":
            seal_dataset(conn, did)
        elif status == "REJECTED":
            reject_dataset(conn, did)
        with pytest.raises(DatabaseError), conn.begin_nested():
            conn.execute(s.datasets.delete())


def test_cannot_insert_already_sealed_dataset(engine, packet):
    with engine.begin() as conn:
        did = stage(conn, packet)
        seal_dataset(conn, did)
        with pytest.raises(DatabaseError, match="start BUILDING"), conn.begin_nested():
            insert_copy(conn, s.datasets, dataset_version="another")


@pytest.mark.parametrize("status", ["BUILDING", "REJECTED"])
def test_load_only_sealed_and_unfinished_version_conflicts(engine, packet, status):
    with engine.begin() as conn:
        did = stage(conn, packet)
        if status == "REJECTED":
            reject_dataset(conn, did)
        with pytest.raises(ValueError, match="SEALED"):
            load_research_dataset(conn, packet.dataset.dataset_id, packet.dataset.dataset_version)
    with pytest.raises(DatasetConflict):
        import_research_dataset(engine, packet)


@pytest.mark.parametrize("table", [s.matches, s.odds_quotes, s.results], ids=lambda t: t.name)
def test_duplicate_normalized_record_rejected_by_database(engine, packet, table):
    with engine.begin() as conn:
        stage(conn, packet)
        with pytest.raises(DatabaseError), conn.begin_nested():
            insert_copy(conn, table)


def test_duplicate_source_record_composite_identity(engine, packet):
    with engine.begin() as conn:
        stage(conn, packet)
        with pytest.raises(DatabaseError), conn.begin_nested():
            insert_copy(conn, s.matches, research_match_id="different-canonical-id")


@pytest.mark.parametrize("table", [s.matches, s.odds_quotes, s.results], ids=lambda t: t.name)
@pytest.mark.parametrize("fault", ["missing_raw", "other_source", "other_dataset"])
def test_raw_provenance_fks_cannot_be_bypassed(engine, packet, table, fault):
    with engine.begin() as conn:
        did = stage(conn, packet)
        key = "research_match_id" if table is s.matches else "record_id"
        changes = {key: "new-record"}
        if table is s.matches:
            changes["source_record_id"] = "new-source-record"
        if fault == "missing_raw":
            changes["raw_artifact_id"] = None
        elif fault == "other_source":
            second = conn.scalar(select(s.sources.c.id).where(s.sources.c.source_name == "second"))
            changes["raw_artifact_id"] = conn.scalar(
                select(s.raw_artifacts.c.id).where(s.raw_artifacts.c.source_id == second)
            )
        else:
            other = replace(packet, dataset=replace(packet.dataset, dataset_version="other"))
            other_id = stage(conn, other, records=False)
            changes["raw_artifact_id"] = conn.scalar(
                select(s.raw_artifacts.c.id).where(s.raw_artifacts.c.dataset_id == other_id)
            )
        with pytest.raises(DatabaseError), conn.begin_nested():
            insert_copy(conn, table, **changes)
        assert dataset_row(conn, did)["status"] == "BUILDING"


@pytest.mark.parametrize(
    "fault", ["before_kickoff", "at_kickoff", "available_before_finished", "dangling_match", "team_mismatch"]
)
def test_result_chronology_and_identity_sql_guards(engine, packet, fault):
    with engine.begin() as conn:
        stage(conn, packet)
        row = first(conn, s.results)
        match = (
            conn.execute(select(s.matches).where(s.matches.c.research_match_id == row["research_match_id"]))
            .mappings()
            .one()
        )
        changes = {"record_id": "bad-result"}
        if fault in ("before_kickoff", "at_kickoff"):
            changes["finished_at"] = match["kickoff_at"] - timedelta(seconds=int(fault == "before_kickoff"))
        elif fault == "available_before_finished":
            changes["replay_available_at"] = row["finished_at"] - timedelta(seconds=1)
        elif fault == "dangling_match":
            changes["research_match_id"] = "unknown"
        else:
            changes["home_team_id"] = "wrong-team"
        with pytest.raises(DatabaseError), conn.begin_nested():
            insert_copy(conn, s.results, **changes)


@pytest.mark.parametrize("table", [s.matches, s.odds_quotes, s.results], ids=lambda t: t.name)
@pytest.mark.parametrize(
    "fault", ["no_basis", "no_time", "invalid_basis", "published_mismatch", "effective_mismatch"]
)
def test_availability_sql_constraints(engine, packet, table, fault):
    with engine.begin() as conn:
        stage(conn, packet)
        changes = {"research_match_id" if table is s.matches else "record_id": "new-record"}
        if table is s.matches:
            changes["source_record_id"] = "new-source-record"
        changes.update(
            {
                "no_basis": {"availability_basis": None},
                "no_time": {"replay_available_at": None},
                "invalid_basis": {"availability_basis": "GUESSED"},
                "published_mismatch": {"availability_basis": "PROVIDER_PUBLISHED_AT", "published_at": None},
                "effective_mismatch": {"availability_basis": "PROVIDER_EFFECTIVE_AT", "effective_at": T},
            }[fault]
        )
        with pytest.raises(DatabaseError), conn.begin_nested():
            insert_copy(conn, table, **changes)


@pytest.mark.parametrize("basis", [None, *AvailabilityBasis])
def test_availability_is_explicit_and_missing_remains_null(engine, packet, basis):
    def amend(row):
        if basis is None:
            return replace(row, replay_available_at=None, availability_basis=None)
        timestamp = row.replay_available_at
        return replace(row, availability_basis=basis, published_at=timestamp, effective_at=timestamp)

    ds = replace(
        packet.dataset,
        matches=tuple(amend(r) for r in packet.dataset.matches),
        odds=tuple(amend(r) for r in packet.dataset.odds),
        results=tuple(amend(r) for r in packet.dataset.results),
    )
    packet = replace(packet, dataset=ds)
    sealed = import_research_dataset(engine, packet)
    with engine.connect() as conn:
        assert load_research_dataset(conn, ds.dataset_id, ds.dataset_version) == ds
    assert sealed["quality_summary"]["records_without_verified_availability"] == (38 if basis is None else 0)


@pytest.mark.parametrize("fault", ["raw_hash", "invalid_identity", "missing_source_manifest", "invalid_odds"])
def test_failed_seal_keeps_building_without_skipping_bad_records(engine, packet, fault):
    with engine.begin() as conn:
        did = stage(conn, packet, records=False)
        if fault == "raw_hash":
            insert_copy(conn, s.raw_artifacts, content_hash="f" * 64)
        elif fault == "missing_source_manifest":
            insert_copy(conn, s.sources, source_name="undeclared")
        else:
            append_records(conn, did, packet.dataset, packet.provenance)
            if fault == "invalid_identity":
                insert_copy(conn, s.matches, research_match_id="  ", source_record_id="new-source-id")
            else:
                # Bad input caught by the DB or the frozen contract; never rounded/skipped into a seal.
                with pytest.raises(DatabaseError), conn.begin_nested():
                    insert_copy(conn, s.odds_quotes, record_id="bad", decimal_odds="0.5")
                insert_copy(conn, s.odds_quotes, record_id="bad-market", market_type="  ")
        with pytest.raises(ValueError):
            seal_dataset(conn, did)
        row = dataset_row(conn, did)
        assert row["status"] == "BUILDING" and row["content_hash"] is row["sealed_at"] is None


@pytest.mark.parametrize("fault", ["no_raw", "wrong_source", "extra_provenance", "missing_provenance"])
def test_import_rejects_incomplete_provenance_before_writing(engine, packet, fault):
    if fault == "no_raw":
        bad = replace(packet, raw_artifacts=())
    elif fault == "wrong_source":
        bad = replace(
            packet, provenance=(replace(packet.provenance[0], source_name="second"), *packet.provenance[1:])
        )
    elif fault == "extra_provenance":
        bad = replace(packet, provenance=packet.provenance + (packet.provenance[0],))
    else:
        bad = replace(packet, provenance=packet.provenance[1:])
    with pytest.raises(ValueError):
        import_research_dataset(engine, bad)
    with engine.connect() as conn:
        assert conn.scalar(select(func.count()).select_from(s.datasets)) == 0


@pytest.mark.parametrize(
    "key", ["api_key", "API-Key", "Authorization", "Cookie", "cookies", "password", "access_token", "token"]
)
def test_secret_metadata_rejected_never_written(engine, packet, key):
    # Mutation of nested user input cannot bypass validation at import time.
    packet.raw_artifacts[0].metadata.update({"nested": [{key: "must-not-persist"}]})
    with pytest.raises(ValueError, match="prohibited"):
        import_research_dataset(engine, packet)
    with engine.connect() as conn:
        assert conn.scalar(select(func.count()).select_from(s.raw_artifacts)) == 0
        assert conn.scalar(select(func.count()).select_from(s.datasets)) == 0


@pytest.mark.parametrize(
    "field,value",
    [
        ("external_ref", "https://example.invalid/file?api_key=must-not-persist"),
        ("external_ref", "https://user:password@example.invalid/file"),
        ("payload", "Authorization: Bearer must-not-persist"),
        ("payload", "password=must-not-persist"),
    ],
)
def test_secret_text_and_urls_rejected(packet, field, value):
    with pytest.raises(ValueError):
        replace(packet.raw_artifacts[0], **{field: value})


def test_fixture_cannot_be_verified(packet):
    with pytest.raises(ValueError, match="UNVERIFIED"):
        replace(packet.sources[0], verification_status="VERIFIED", verified_at=T, verification_note="Fake")


@pytest.mark.parametrize(
    "fault", ["missing_artifact", "fixture_artifact", "unverified_source", "wrong_match"]
)
def test_sporttery_verified_requires_official_matching_evidence(engine, packet, fault):
    if fault in ("unverified_source", "wrong_match"):
        packet = official_test_declaration(packet)
        if fault == "unverified_source":
            packet = replace(
                packet,
                sources=tuple(
                    replace(src, verification_status="UNVERIFIED")
                    if src.source.source_name == "official-test"
                    else src
                    for src in packet.sources
                ),
            )
        else:
            evidence = packet.raw_artifacts[-1]
            evidence.metadata["sporttery_pool_evidence"]["home_team_id"] = "wrong-team"
    else:
        raw = packet.raw_artifacts[0]
        v = SportteryVerificationInput(
            research_match_id="target",
            status="VERIFIED",
            artifact_source_name=raw.source_name if fault == "fixture_artifact" else None,
            artifact_content_hash=raw.content_hash if fault == "fixture_artifact" else None,
        )
        packet = replace(packet, sporttery_verifications=(v,))
    with pytest.raises(ValueError):
        import_research_dataset(engine, packet)


def official_test_declaration(packet):
    """Unit-test simulation of an explicit attestation; it is NOT real source verification."""
    source = ResearchSource(
        source_name="official-test",
        source_type="OFFICIAL_SPORTTERY_HISTORY",
        retrieval_note="Simulated verifier declaration for SQL constraint testing only.",
    )
    target = next(m for m in packet.dataset.matches if m.research_match_id == "target")
    artifact = ResearchRawArtifactInput(
        source_name=source.source_name,
        artifact_type="SPORTTERY_POOL",
        retrieved_at=T,
        content_type="text/plain",
        payload="Unit-test placeholder for preserved official response; not historical data.",
        metadata={
            "sporttery_pool_evidence": {
                "sporttery_match_id": target.sporttery_match_id,
                "home_team_id": target.home_team_id,
                "away_team_id": target.away_team_id,
                "kickoff_at": target.kickoff_at.isoformat(),
            }
        },
    )
    return replace(
        packet,
        dataset=replace(packet.dataset, source_manifest=(*packet.dataset.source_manifest, source)),
        sources=(
            *packet.sources,
            ResearchSourceInput(
                source=source,
                provider_name="sporttery",
                license_note="Unit test",
                verification_status="VERIFIED",
                verified_at=T,
                verification_note="Explicit simulated verifier",
            ),
        ),
        raw_artifacts=(*packet.raw_artifacts, artifact),
        sporttery_verifications=(
            SportteryVerificationInput(
                research_match_id="target",
                status="VERIFIED",
                artifact_source_name=source.source_name,
                artifact_content_hash=artifact.content_hash,
            ),
        ),
    )


def test_intake_gate_a_uses_d2a_and_does_not_open_other_gates(packet):
    from jc.research.pilot import assess_intake_gates

    assert assess_intake_gates(packet)["gates"] == {"A":"BLOCKED", "B":"BLOCKED"}
    verified = official_test_declaration(packet)
    assert assess_intake_gates(verified)["gates"] == {"A":"PASS", "B":"BLOCKED"}
    invalid = replace(packet, sporttery_verifications=verified.sporttery_verifications)
    with pytest.raises(ValueError, match="artifact missing"):
        assess_intake_gates(invalid)


@pytest.mark.parametrize("time_kind", ["opening", "closing", "snapshot"])
def test_external_complete_1x2_without_snapshot_has_zero_cutoff_coverage(packet, time_kind):
    from jc.research.pilot import assess_intake_gates

    packet = official_test_declaration(packet)
    odds_sources = {q.provider for q in packet.dataset.odds}
    sources = tuple(
        replace(source, source=replace(source.source, source_type="EXTERNAL_ODDS_HISTORY"),
                verification_status="VERIFIED", verified_at=T, verification_note="Synthetic test only")
        if source.source.source_name in odds_sources else source for source in packet.sources
    )
    odds = tuple(
        replace(q, replay_available_at=None, availability_basis=None) if time_kind != "snapshot" else q
        for q in packet.dataset.odds
    )
    packet = replace(packet, sources=sources, dataset=replace(
        packet.dataset, odds=odds, source_manifest=tuple(s.source for s in sources),
    ))
    report = assess_intake_gates(packet)
    assert report["gates"]["A"] == "PASS"
    if time_kind == "snapshot":
        assert report["gates"]["B"] == "PASS"
        assert report["cutoff_coverage"]["30"] == 1
        partial = replace(packet, dataset=replace(packet.dataset, odds=tuple(q for q in odds if q.selection != "DRAW")))
        partial = replace(partial, provenance=tuple(p for p in partial.provenance if p.record_type != "ODDS" or p.record_id in {q.record_id for q in partial.dataset.odds}))
        assert assess_intake_gates(partial)["gates"]["B"] == "BLOCKED"
    else:
        assert report["gates"]["B"] == "BLOCKED"
        assert report["cutoff_coverage"] == {"30":0,"90":0,"360":0}


def test_explicit_official_attestation_persistence_and_target_admission(engine, packet):
    packet = official_test_declaration(packet)
    row = import_research_dataset(engine, packet)
    with engine.connect() as conn:
        assert verified_sporttery_targets(conn, row["id"]) == ("target",)
        assert (
            load_research_dataset(conn, packet.dataset.dataset_id, packet.dataset.dataset_version)
            == packet.dataset
        )
    assert row["quality_summary"]["sporttery_target_verified_count"] == 1


@pytest.mark.parametrize("fault", ["missing_evidence", "fixture_evidence"])
def test_sql_cannot_mark_arbitrary_sporttery_id_verified(engine, packet, fault):
    with engine.begin() as conn:
        stage(conn, packet)
        raw_id = first(conn, s.raw_artifacts)["id"] if fault == "fixture_evidence" else None
        with pytest.raises(DatabaseError), conn.begin_nested():
            insert_copy(
                conn,
                s.matches,
                research_match_id="bad-target",
                source_record_id="bad-source",
                sporttery_match_id="123",
                sporttery_verification_status="VERIFIED",
                sporttery_verification_artifact_id=raw_id,
            )


def test_research_repository_rejects_orm_session(sessions, packet):
    with sessions() as db, pytest.raises(TypeError, match="Core Connection"):
        create_research_dataset(db, packet.dataset, description="fixture", manifest={})


def test_input_hash_has_explicit_canonical_serialization(packet):
    assert validate_import(packet).dataset == packet.dataset
    assert (
        canonical_bytes({"decimal": Decimal("2.5000"), "at": T})
        == b'{"at":"2026-10-01T00:00:00+00:00","decimal":"2.5"}'
    )


@pytest.mark.parametrize("kind", ["MATCH", "ODDS", "RESULT"])
def test_building_incremental_record_append_and_duplicates(engine, packet, kind):
    with engine.begin() as conn:
        did = stage(conn, packet)
        if kind == "MATCH":
            record = replace(
                packet.dataset.matches[0],
                research_match_id="additional",
                source_record_id="additional-source",
            )
        elif kind == "ODDS":
            record = replace(packet.dataset.odds[0], record_id="additional", decimal_odds=Decimal("2.11"))
        else:
            record = replace(packet.dataset.results[0], record_id="additional")
        provenance = ResearchRecordProvenance(
            record_type=kind,
            record_id="additional",
            source_name="fixture",
            raw_content_hash=packet.raw_artifacts[0].content_hash,
        )
        append_record(conn, did, record, provenance)
        with pytest.raises(ValueError, match="Duplicate"):
            append_record(conn, did, record, provenance)
        sealed = seal_dataset(conn, did)
        assert sealed["status"] == "SEALED"
        loaded = load_research_dataset(conn, packet.dataset.dataset_id, packet.dataset.dataset_version)
        rows = {"MATCH": loaded.matches, "ODDS": loaded.odds, "RESULT": loaded.results}[kind]
        assert record in rows


def test_import_seal_failure_leaves_committed_building(engine, packet, monkeypatch):
    def fail(*args):
        raise ValueError("seal validation failed")

    monkeypatch.setattr("jc.research.importer.seal_dataset", fail)
    with pytest.raises(ValueError, match="seal validation"):
        import_research_dataset(engine, packet)
    with engine.connect() as conn:
        row = first(conn, s.datasets)
        assert row["status"] == "BUILDING" and row["content_hash"] is None
        assert conn.scalar(select(func.count()).select_from(s.matches)) == 13


def test_jsonb_number_canonical_hash_survives_roundtrip(engine, packet):
    raw = replace(
        packet.raw_artifacts[1], payload={"numbers": [1e30, 1.2345678901234567e30, -0.0, 1e-7, 1.0]}
    )
    packet = replace(packet, raw_artifacts=(packet.raw_artifacts[0], raw), manifest={"number": 1e30})
    assert content_hash(1.0) == content_hash(1)
    row = import_research_dataset(engine, packet)
    assert row["content_hash"] == dataset_content_hash(packet)
    with engine.connect() as conn:
        assert (
            load_research_dataset(conn, packet.dataset.dataset_id, packet.dataset.dataset_version)
            == packet.dataset
        )


@pytest.mark.parametrize("first_action", ["seal", "insert"])
def test_concurrent_seal_serializes_with_member_insert(engine, packet, first_action):
    with engine.begin() as conn:
        did = stage(conn, packet)
        raw = first(conn, s.raw_artifacts)
    attempted = Event()
    raw.update(id=str(uuid4()), payload={"new": True}, content_hash=content_hash({"new": True}))

    def capture(conn, cursor, statement, parameters, context, many):
        if conn.info.get("research_racer"):
            attempted.set()

    def racer():
        with engine.begin() as conn:
            conn.info["research_racer"] = True
            try:
                if first_action == "seal":
                    conn.execute(s.raw_artifacts.insert().values(**raw))
                else:
                    seal_dataset(conn, did)
            finally:
                conn.info.pop("research_racer", None)

    event.listen(engine, "before_cursor_execute", capture)
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            with engine.begin() as conn:
                if first_action == "seal":
                    seal_dataset(conn, did)
                else:
                    conn.execute(s.raw_artifacts.insert().values(**raw))
                future = pool.submit(racer)
                assert attempted.wait(5)
            if first_action == "seal":
                with pytest.raises(DatabaseError):
                    future.result(timeout=10)
            else:
                future.result(timeout=10)
    finally:
        event.remove(engine, "before_cursor_execute", capture)
    with engine.connect() as conn:
        assert (
            load_research_dataset(conn, packet.dataset.dataset_id, packet.dataset.dataset_version)
            == packet.dataset
        )
        assert conn.scalar(select(func.count()).select_from(s.raw_artifacts)) == (
            2 if first_action == "seal" else 3
        )


def test_quality_missing_identity_is_factual_not_a_score(engine, packet):
    ds = replace(
        packet.dataset,
        matches=tuple(replace(r, home_team_id=None) for r in packet.dataset.matches),
        results=tuple(replace(r, home_team_id=None) for r in packet.dataset.results),
    )
    row = import_research_dataset(engine, replace(packet, dataset=ds))
    assert row["quality_summary"]["matches_missing_team_identity"] == 13
    assert row["quality_summary"]["results_missing_team_identity"] == 13
    assert "quality_score" not in row["quality_summary"]


def test_autocommit_cannot_partially_import(engine, packet):
    with pytest.raises(ValueError, match="AUTOCOMMIT"):
        import_research_dataset(engine.execution_options(isolation_level="AUTOCOMMIT"), packet)
    with engine.connect() as conn:
        assert conn.scalar(select(func.count()).select_from(s.datasets)) == 0


def test_write_snapshot_safety(engine, packet):
    with engine.begin() as conn:
        did = stage(conn, packet)
    if engine.dialect.name == "postgresql":
        with engine.connect().execution_options(isolation_level="REPEATABLE READ") as conn:
            with pytest.raises(ValueError, match="READ COMMITTED"):
                seal_dataset(conn, did)
            conn.rollback()
    else:
        with engine.begin() as conn:
            assert not conn.connection.driver_connection.in_transaction
            seal_dataset(conn, did)
            assert conn.connection.driver_connection.in_transaction


@pytest.mark.parametrize("fault", ["content_hash", "quality_summary"])
def test_materializer_rechecks_direct_sql_seal_metadata(engine, packet, fault):
    with engine.begin() as conn:
        stage(conn, packet)
        # Legal lifecycle SQL alone does not constitute a validated seal.
        conn.execute(
            s.datasets.update().values(
                status="SEALED",
                sealed_at=T,
                content_hash="0" * 64 if fault == "content_hash" else dataset_content_hash(packet),
                quality_summary={},
            )
        )
        with pytest.raises(ValueError, match="content or quality"):
            load_research_dataset(conn, packet.dataset.dataset_id, packet.dataset.dataset_version)


def test_source_identity_and_odds_provider_cannot_be_forged(engine, packet):
    with engine.begin() as conn:
        stage(conn, packet)
        with pytest.raises(DatabaseError), conn.begin_nested():
            insert_copy(conn, s.sources)
        with pytest.raises(DatabaseError), conn.begin_nested():
            insert_copy(conn, s.odds_quotes, record_id="other-provider", provider="second")


def test_raw_before_source_and_invalid_contract_before_import(engine, packet):
    with engine.begin() as conn:
        did = create_research_dataset(
            conn, packet.dataset, description=packet.description, manifest=packet.manifest
        )
        with pytest.raises(ValueError, match="source before raw"):
            append_raw_artifact(conn, did, packet.raw_artifacts[0])
        with pytest.raises(ValueError, match="source_manifest"):
            seal_dataset(conn, did)
        assert dataset_row(conn, did)["status"] == "BUILDING"


@pytest.mark.parametrize("field", ["matches", "odds", "results"])
def test_duplicate_frozen_contract_revalidated_at_import(engine, packet, field):
    # frozen=True can be bypassed by hostile Python; the importer revalidates, never trusts it blindly.
    object.__setattr__(
        packet.dataset, field, (*getattr(packet.dataset, field), getattr(packet.dataset, field)[0])
    )
    with pytest.raises(ValueError, match="Duplicate"):
        import_research_dataset(engine, packet)
    with engine.connect() as conn:
        assert conn.scalar(select(func.count()).select_from(s.datasets)) == 0
