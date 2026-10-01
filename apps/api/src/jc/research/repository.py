"""Core-only repository. The caller owns the transaction; never pass an ORM Session."""

from dataclasses import asdict, fields, replace
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import Connection, select, update

from jc.analysis.research_replay import (
    ResearchDataset,
    ResearchMatch,
    ResearchOddsQuote,
    ResearchResult,
    ResearchSource,
)
from jc.research import schema as s
from jc.research.contracts import (
    ResearchImport,
    ResearchRawArtifactInput,
    ResearchRecordProvenance,
    ResearchSourceInput,
    SportteryVerificationInput,
    dataset_content_hash,
    decimal_text,
    reject_secrets,
    validate_import,
)
from jc.time import utcnow


class DatasetConflict(ValueError):
    """The immutable identity already names different content or an unfinished version."""


def _connection(connection: Connection) -> None:
    if not isinstance(connection, Connection):
        raise TypeError("Research persistence requires a Core Connection, never an ORM Session")


def _write_connection(connection: Connection) -> None:
    _connection(connection)
    driver = connection.connection.driver_connection
    if (
        connection.get_execution_options().get("isolation_level") == "AUTOCOMMIT"
        or getattr(driver, "autocommit", False) is True
    ):
        raise ValueError("Research writes require an explicit transaction, not AUTOCOMMIT")
    if connection.dialect.name == "postgresql" and connection.get_isolation_level() != "READ COMMITTED":
        raise ValueError("Research writes require READ COMMITTED to seal a fresh snapshot after locking")


def dataset_row(connection: Connection, dataset_id: str, *, lock: bool = False) -> dict:
    _connection(connection)
    query = select(s.datasets).where(s.datasets.c.id == dataset_id)
    if lock:
        query = query.with_for_update()
    row = connection.execute(query).mappings().one_or_none()
    if row is None:
        raise ValueError("Unknown research dataset")
    return dict(row)


def _building(connection: Connection, dataset_id: str) -> dict:
    _write_connection(connection)
    driver = connection.connection.driver_connection
    if connection.dialect.name == "sqlite" and driver is not None and not driver.in_transaction:
        # Legacy sqlite3 does not BEGIN on SELECT. Acquire the writer lock before
        # reading a seal candidate, so no member can slip in between hash and seal.
        connection.exec_driver_sql("BEGIN IMMEDIATE")
    row = dataset_row(connection, dataset_id, lock=True)
    if row["status"] != "BUILDING":
        raise ValueError("Research dataset must be BUILDING")
    return row


def create_research_dataset(
    connection: Connection, dataset: ResearchDataset, *, description: str, manifest: dict
) -> str:
    _write_connection(connection)
    reject_secrets({"description": description, "manifest": manifest, "dataset": asdict(dataset)})
    dataset_id = str(uuid4())
    connection.execute(
        s.datasets.insert().values(
            id=dataset_id,
            dataset_key=dataset.dataset_id,
            dataset_version=dataset.dataset_version,
            replay_version=dataset.replay_version,
            status="BUILDING",
            description=description,
            manifest_json={
                "manifest": manifest,
                "source_manifest": [asdict(a) for a in dataset.source_manifest],
            },
        )
    )
    return dataset_id


def append_source(connection: Connection, dataset_id: str, source: ResearchSourceInput) -> str:
    row = _building(connection, dataset_id)
    # Constructor validates explicit verification and prohibits secrets.
    source = ResearchSourceInput(**{**asdict(source), "source": source.source})
    if asdict(source.source) not in row["manifest_json"]["source_manifest"]:
        raise ValueError("Source missing from declared source_manifest")
    values = asdict(source)
    values.pop("source")
    source_id = str(uuid4())
    connection.execute(
        s.sources.insert().values(id=source_id, dataset_id=dataset_id, **asdict(source.source), **values)
    )
    return source_id


def _rows(connection: Connection, table, dataset_id: str) -> list[dict]:
    return [
        dict(row)
        for row in connection.execute(select(table).where(table.c.dataset_id == dataset_id)).mappings()
    ]


def _utc(value: datetime | None) -> datetime | None:
    # SQLite's DateTime storage omits the zone; all writes have already been converted to UTC.
    return value.replace(tzinfo=UTC) if value is not None and value.tzinfo is None else value


def _raw_contract(row: dict, source_name: str) -> ResearchRawArtifactInput:
    retrieved_at = _utc(row["retrieved_at"])
    if retrieved_at is None:
        raise ValueError("Raw retrieval time is required")
    return ResearchRawArtifactInput(
        source_name=source_name,
        artifact_type=row["artifact_type"],
        external_ref=row["external_ref"],
        retrieved_at=retrieved_at,
        content_type=row["content_type"],
        payload=row["payload"],
        metadata=row["metadata"],
    )


def append_raw_artifact(connection: Connection, dataset_id: str, artifact: ResearchRawArtifactInput) -> str:
    _building(connection, dataset_id)
    artifact = ResearchRawArtifactInput(**asdict(artifact))
    source_id = connection.scalar(
        select(s.sources.c.id).where(
            s.sources.c.dataset_id == dataset_id, s.sources.c.source_name == artifact.source_name
        )
    )
    if source_id is None:
        raise ValueError("Persist source before raw artifact")
    existing = (
        connection.execute(
            select(s.raw_artifacts).where(
                s.raw_artifacts.c.dataset_id == dataset_id,
                s.raw_artifacts.c.source_id == source_id,
                s.raw_artifacts.c.content_hash == artifact.content_hash,
            )
        )
        .mappings()
        .one_or_none()
    )
    if existing:
        if _raw_contract(dict(existing), artifact.source_name) != artifact:
            raise DatasetConflict("Same raw hash has conflicting metadata; use a new dataset version")
        return existing["id"]
    values = asdict(artifact)
    values.pop("source_name")
    artifact_id = str(uuid4())
    connection.execute(
        s.raw_artifacts.insert().values(
            id=artifact_id,
            dataset_id=dataset_id,
            source_id=source_id,
            content_hash=artifact.content_hash,
            **values,
        )
    )
    return artifact_id


def _read_import(connection: Connection, dataset_id: str) -> ResearchImport:
    header = dataset_row(connection, dataset_id)
    sources = {row["id"]: row for row in _rows(connection, s.sources, dataset_id)}
    raw = {row["id"]: row for row in _rows(connection, s.raw_artifacts, dataset_id)}
    source_inputs = tuple(
        ResearchSourceInput(
            source=ResearchSource(**{k: row[k] for k in ("source_name", "source_type", "retrieval_note")}),
            provider_name=row["provider_name"],
            license_note=row["license_note"],
            base_url=row["base_url"],
            verification_status=row["verification_status"],
            verified_at=_utc(row["verified_at"]),
            verification_note=row["verification_note"],
        )
        for row in sources.values()
    )
    raw_inputs = []
    for row in raw.values():
        if row["source_id"] not in sources:
            raise ValueError("Missing raw source")
        raw_input = _raw_contract(row, sources[row["source_id"]]["source_name"])
        if raw_input.content_hash != row["content_hash"]:
            raise ValueError("Raw payload hash mismatch")
        raw_inputs.append(raw_input)
    members: dict[str, list] = {"matches": [], "odds": [], "results": []}
    provenance, verifications = [], []
    for table, kind, record_type, collection in (
        (s.matches, ResearchMatch, "MATCH", "matches"),
        (s.odds_quotes, ResearchOddsQuote, "ODDS", "odds"),
        (s.results, ResearchResult, "RESULT", "results"),
    ):
        for row in _rows(connection, table, dataset_id):
            source, artifact = sources.get(row["source_id"]), raw.get(row["raw_artifact_id"])
            if source is None or artifact is None or artifact["source_id"] != row["source_id"]:
                raise ValueError("Missing or inconsistent raw/source provenance")
            values = {}
            for field in fields(kind):
                name = field.name
                value = source["source_name"] if name == "source" else row[name]
                if name.endswith("_at"):
                    value = _utc(value)
                if name in ("line", "decimal_odds") and value is not None:
                    value = Decimal(value)
                values[name] = value
            if record_type == "ODDS" and values["provider"] != source["source_name"]:
                raise ValueError("Odds provider must match its source")
            members[collection].append(kind(**values))
            record_id = row["research_match_id"] if record_type == "MATCH" else row["record_id"]
            provenance.append(
                ResearchRecordProvenance(
                    record_type=record_type,
                    record_id=record_id,
                    source_name=source["source_name"],
                    raw_content_hash=artifact["content_hash"],
                )
            )
            if record_type == "MATCH":
                evidence_id = row["sporttery_verification_artifact_id"]
                evidence = raw.get(evidence_id) if evidence_id else None
                if evidence_id and evidence is None:
                    raise ValueError("Sporttery verification raw missing")
                verifications.append(
                    SportteryVerificationInput(
                        research_match_id=record_id,
                        status=row["sporttery_verification_status"],
                        artifact_source_name=sources[evidence["source_id"]]["source_name"]
                        if evidence
                        else None,
                        artifact_content_hash=evidence["content_hash"] if evidence else None,
                    )
                )
    ds = ResearchDataset(
        dataset_id=header["dataset_key"],
        dataset_version=header["dataset_version"],
        replay_version=header["replay_version"],
        source_manifest=tuple(ResearchSource(**v) for v in header["manifest_json"]["source_manifest"]),
        matches=tuple(members["matches"]),
        odds=tuple(members["odds"]),
        results=tuple(members["results"]),
    )
    return ResearchImport(
        dataset=ds,
        description=header["description"],
        manifest=header["manifest_json"]["manifest"],
        sources=source_inputs,
        raw_artifacts=tuple(raw_inputs),
        provenance=tuple(provenance),
        sporttery_verifications=tuple(verifications),
    )


def append_records(
    connection: Connection,
    dataset_id: str,
    dataset: ResearchDataset,
    provenance: tuple[ResearchRecordProvenance, ...],
    sporttery_verifications: tuple[SportteryVerificationInput, ...] = (),
) -> None:
    """Append an explicit contract batch; raw and source records must already exist."""
    _building(connection, dataset_id)
    current = _read_import(connection, dataset_id)
    if (dataset.dataset_id, dataset.dataset_version, dataset.replay_version, dataset.source_manifest) != (
        current.dataset.dataset_id,
        current.dataset.dataset_version,
        current.dataset.replay_version,
        current.dataset.source_manifest,
    ):
        raise ValueError("Dataset batch identity/manifest mismatch")
    combined = ResearchDataset(
        dataset_id=dataset.dataset_id,
        dataset_version=dataset.dataset_version,
        replay_version=dataset.replay_version,
        source_manifest=dataset.source_manifest,
        matches=current.dataset.matches + dataset.matches,
        odds=current.dataset.odds + dataset.odds,
        results=current.dataset.results + dataset.results,
    )
    valid = validate_import(
        ResearchImport(
            dataset=combined,
            description=current.description,
            manifest=current.manifest,
            sources=current.sources,
            raw_artifacts=current.raw_artifacts,
            provenance=current.provenance + provenance,
            sporttery_verifications=current.sporttery_verifications + sporttery_verifications,
        )
    )
    _insert_records(connection, dataset_id, dataset.matches, dataset.odds, dataset.results, valid)


def append_record(
    connection: Connection,
    dataset_id: str,
    record: ResearchMatch | ResearchOddsQuote | ResearchResult,
    provenance: ResearchRecordProvenance,
    verification: SportteryVerificationInput | None = None,
) -> None:
    """Append a correction/new record to existing BUILDING context; never replace an ID."""
    _building(connection, dataset_id)
    current = _read_import(connection, dataset_id)
    if isinstance(record, ResearchMatch):
        combined = replace(current.dataset, matches=(*current.dataset.matches, record))
    elif isinstance(record, ResearchOddsQuote):
        combined = replace(current.dataset, odds=(*current.dataset.odds, record))
    elif isinstance(record, ResearchResult):
        combined = replace(current.dataset, results=(*current.dataset.results, record))
    else:
        raise TypeError("An explicit frozen research record is required")
    valid = validate_import(
        replace(
            current,
            dataset=combined,
            provenance=(*current.provenance, provenance),
            sporttery_verifications=(*current.sporttery_verifications, verification)
            if verification
            else current.sporttery_verifications,
        )
    )
    _insert_records(
        connection,
        dataset_id,
        (record,) if isinstance(record, ResearchMatch) else (),
        (record,) if isinstance(record, ResearchOddsQuote) else (),
        (record,) if isinstance(record, ResearchResult) else (),
        valid,
    )


def _insert_records(connection, dataset_id, matches, odds, results, valid):
    sources = {row["source_name"]: row["id"] for row in _rows(connection, s.sources, dataset_id)}
    raw = {
        (row["source_id"], row["content_hash"]): row["id"]
        for row in _rows(connection, s.raw_artifacts, dataset_id)
    }
    links = {(p.record_type, p.record_id): p for p in valid.provenance}
    verification = {v.research_match_id: v for v in valid.sporttery_verifications}
    for table, rows, record_type in (
        (s.matches, matches, "MATCH"),
        (s.odds_quotes, odds, "ODDS"),
        (s.results, results, "RESULT"),
    ):
        for record in rows:
            values = asdict(record)
            record_id = values["research_match_id"] if record_type == "MATCH" else values["record_id"]
            p = links[(record_type, record_id)]
            source_id = sources[p.source_name]
            values.pop("source", None)
            if connection.dialect.name == "sqlite":
                for name in ("line", "decimal_odds"):
                    if values.get(name) is not None:
                        values[name] = decimal_text(values[name])
            if record_type == "MATCH":
                v = verification[record_id]
                values.update(
                    sporttery_verification_status=v.status,
                    sporttery_verification_artifact_id=(
                        raw[(sources[v.artifact_source_name], v.artifact_content_hash)]
                        if v.artifact_source_name
                        else None
                    ),
                )
            connection.execute(
                table.insert().values(
                    dataset_id=dataset_id,
                    source_id=source_id,
                    raw_artifact_id=raw[(source_id, p.raw_content_hash)],
                    **values,
                )
            )


def quality_summary(value: ResearchImport) -> dict:
    ds = value.dataset
    rows = (*ds.matches, *ds.odds, *ds.results)
    dates = [m.kickoff_at for m in ds.matches]
    available = sum(r.replay_available_at is not None for r in rows)
    return {
        "match_count": len(ds.matches),
        "sporttery_target_verified_count": sum(v.status == "VERIFIED" for v in value.sporttery_verifications),
        "odds_count": len(ds.odds),
        "result_count": len(ds.results),
        "sources_count": len(ds.source_manifest),
        "records_with_verified_availability": available,
        "records_without_verified_availability": len(rows) - available,
        "matches_missing_team_identity": sum(
            m.home_team_id is None or m.away_team_id is None for m in ds.matches
        ),
        "results_missing_team_identity": sum(
            r.home_team_id is None or r.away_team_id is None for r in ds.results
        ),
        "date_min": min(dates).isoformat() if dates else None,
        "date_max": max(dates).isoformat() if dates else None,
    }


def seal_dataset(connection: Connection, dataset_id: str) -> dict:
    _building(connection, dataset_id)  # Parent lock serializes seal with member inserts on PostgreSQL.
    value = validate_import(_read_import(connection, dataset_id))
    digest, summary = dataset_content_hash(value), quality_summary(value)
    connection.execute(
        update(s.datasets)
        .where(s.datasets.c.id == dataset_id)
        .values(
            status="SEALED",
            content_hash=digest,
            quality_summary=summary,
            sealed_at=utcnow(),
        )
    )
    return dataset_row(connection, dataset_id)


def reject_dataset(connection: Connection, dataset_id: str) -> None:
    _building(connection, dataset_id)
    connection.execute(update(s.datasets).where(s.datasets.c.id == dataset_id).values(status="REJECTED"))


def load_research_dataset(connection: Connection, dataset_key: str, dataset_version: str) -> ResearchDataset:
    _connection(connection)
    header = (
        connection.execute(
            select(s.datasets).where(
                s.datasets.c.dataset_key == dataset_key,
                s.datasets.c.dataset_version == dataset_version,
            )
        )
        .mappings()
        .one_or_none()
    )
    if header is None or header["status"] != "SEALED":
        raise ValueError("Only SEALED research datasets can be loaded")
    value = validate_import(_read_import(connection, header["id"]))
    if (
        dataset_content_hash(value) != header["content_hash"]
        or quality_summary(value) != header["quality_summary"]
    ):
        raise ValueError("Sealed dataset content or quality summary mismatch")
    return value.dataset


def verified_sporttery_targets(connection: Connection, dataset_id: str) -> tuple[str, ...]:
    """Explicit target admission for future real research; does not change v1 selection rules."""
    row = dataset_row(connection, dataset_id)
    load_research_dataset(connection, row["dataset_key"], row["dataset_version"])
    return tuple(
        connection.scalars(
            select(s.matches.c.research_match_id)
            .where(
                s.matches.c.dataset_id == dataset_id,
                s.matches.c.sporttery_verification_status == "VERIFIED",
            )
            .order_by(s.matches.c.research_match_id)
        )
    )
