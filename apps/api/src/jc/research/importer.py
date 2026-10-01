"""Validate → source/raw first → BUILDING commit → seal in a separate Core transaction."""

from sqlalchemy import Engine, select
from sqlalchemy.exc import IntegrityError

from jc.research import schema as s
from jc.research.contracts import ResearchImport, dataset_content_hash, validate_import
from jc.research.repository import (
    DatasetConflict,
    append_raw_artifact,
    append_records,
    append_source,
    create_research_dataset,
    load_research_dataset,
    seal_dataset,
)


def _existing(connection, value: ResearchImport, digest: str) -> dict | None:
    row = (
        connection.execute(
            select(s.datasets).where(
                s.datasets.c.dataset_key == value.dataset.dataset_id,
                s.datasets.c.dataset_version == value.dataset.dataset_version,
            )
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        return None
    if row["status"] != "SEALED" or row["content_hash"] != digest:
        raise DatasetConflict("CONFLICT: dataset key/version already names different or unfinished content")
    load_research_dataset(connection, value.dataset.dataset_id, value.dataset.dataset_version)
    return dict(row)


def import_research_dataset(engine: Engine, value: ResearchImport) -> dict:
    if not isinstance(engine, Engine):
        raise TypeError("Research importer requires an Engine, never an ORM Session")
    value = validate_import(value)
    digest = dataset_content_hash(value)
    try:
        with engine.begin() as connection:
            existing = _existing(connection, value, digest)
            if existing is not None:
                return existing
            dataset_id = create_research_dataset(
                connection, value.dataset, description=value.description, manifest=value.manifest
            )
            for source in value.sources:
                append_source(connection, dataset_id, source)
            for artifact in value.raw_artifacts:
                append_raw_artifact(connection, dataset_id, artifact)
            append_records(
                connection, dataset_id, value.dataset, value.provenance, value.sporttery_verifications
            )
    except IntegrityError:
        # A concurrent identical importer may have won the unique key. No overwrite/upsert.
        with engine.connect() as connection:
            existing = _existing(connection, value, digest)
            if existing is not None:
                return existing
        raise
    # A seal failure leaves the committed BUILDING version intact for inspection
    # or explicit rejection; no rows are skipped and no existing records are repaired.
    with engine.begin() as connection:
        sealed = seal_dataset(connection, dataset_id)
        if sealed["content_hash"] != digest:
            raise ValueError("Persistence changed canonical research content")
        return sealed
