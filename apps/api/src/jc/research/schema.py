"""Independent Core metadata. PostgreSQL NUMERIC; lossless decimal text on SQLite."""

from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from jc.time import utcnow

metadata = sa.MetaData()
JSON = sa.JSON().with_variant(JSONB(), "postgresql")
DECIMAL = sa.Numeric().with_variant(sa.Text(), "sqlite")


def identity():
    return [
        sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid4())),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, default=utcnow),
    ]


def dataset_column():
    return sa.Column(
        "dataset_id", sa.Uuid(as_uuid=False), sa.ForeignKey("research_datasets.id"), nullable=False
    )


def availability():
    return [
        *(
            sa.Column(name, sa.DateTime(timezone=True))
            for name in ("published_at", "effective_at", "replay_available_at")
        ),
        sa.Column("availability_basis", sa.Text()),
        sa.CheckConstraint(
            "(replay_available_at IS NULL AND availability_basis IS NULL) OR "
            "(replay_available_at IS NOT NULL AND availability_basis IS NOT NULL AND availability_basis IN "
            "('SOURCE_SNAPSHOT_AT','PROVIDER_PUBLISHED_AT','PROVIDER_EFFECTIVE_AT','VERIFIED_ARCHIVE_TIMESTAMP'))",
            name="availability_pair",
        ),
        sa.CheckConstraint(
            "availability_basis <> 'PROVIDER_PUBLISHED_AT' OR "
            "(published_at IS NOT NULL AND replay_available_at = published_at)",
            name="published_evidence",
        ),
        sa.CheckConstraint(
            "availability_basis <> 'PROVIDER_EFFECTIVE_AT' OR "
            "(effective_at IS NOT NULL AND replay_available_at = effective_at)",
            name="effective_evidence",
        ),
    ]


def provenance():
    return [
        dataset_column(),
        sa.Column("source_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("raw_artifact_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.ForeignKeyConstraint(
            ["dataset_id", "source_id"], ["research_sources.dataset_id", "research_sources.id"]
        ),
        sa.ForeignKeyConstraint(
            ["dataset_id", "source_id", "raw_artifact_id"],
            [
                "research_raw_artifacts.dataset_id",
                "research_raw_artifacts.source_id",
                "research_raw_artifacts.id",
            ],
        ),
    ]


datasets = sa.Table(
    "research_datasets",
    metadata,
    *identity(),
    sa.Column("dataset_key", sa.Text(), nullable=False),
    sa.Column("dataset_version", sa.Text(), nullable=False),
    sa.Column("replay_version", sa.Text(), nullable=False),
    sa.Column("status", sa.Text(), nullable=False, server_default="BUILDING"),
    sa.Column("description", sa.Text(), nullable=False),
    sa.Column("manifest_json", JSON, nullable=False),
    sa.Column("content_hash", sa.String(64)),
    sa.Column("quality_summary", JSON),
    sa.Column("sealed_at", sa.DateTime(timezone=True)),
    sa.UniqueConstraint("dataset_key", "dataset_version", name="uq_research_dataset_version"),
    sa.CheckConstraint("replay_version = 'research-replay-v1'", name="research_replay_version"),
    sa.CheckConstraint(
        "(status IN ('BUILDING','REJECTED') AND sealed_at IS NULL AND content_hash IS NULL "
        "AND quality_summary IS NULL) OR (status = 'SEALED' AND sealed_at IS NOT NULL "
        "AND content_hash IS NOT NULL AND length(content_hash) = 64 AND quality_summary IS NOT NULL)",
        name="research_dataset_lifecycle",
    ),
)

sources = sa.Table(
    "research_sources",
    metadata,
    *identity(),
    dataset_column(),
    *(
        sa.Column(name, sa.Text(), nullable=False)
        for name in ("source_name", "source_type", "provider_name", "license_note", "retrieval_note")
    ),
    sa.Column("base_url", sa.Text()),
    sa.Column("verification_status", sa.Text(), nullable=False, server_default="UNVERIFIED"),
    sa.Column("verified_at", sa.DateTime(timezone=True)),
    sa.Column("verification_note", sa.Text()),
    sa.UniqueConstraint("dataset_id", "id", name="uq_research_source_dataset_id"),
    sa.UniqueConstraint("dataset_id", "source_name", name="uq_research_source_name"),
    sa.CheckConstraint("verification_status IN ('UNVERIFIED','VERIFIED','REJECTED')", name="source_status"),
    sa.CheckConstraint(
        "verification_status <> 'VERIFIED' OR (verified_at IS NOT NULL AND "
        "verification_note IS NOT NULL AND length(trim(verification_note)) > 0)",
        name="source_verification",
    ),
    sa.CheckConstraint(
        "source_type <> 'SYNTHETIC_FIXTURE' OR verification_status = 'UNVERIFIED'",
        name="fixture_unverified",
    ),
)

raw_artifacts = sa.Table(
    "research_raw_artifacts",
    metadata,
    *identity(),
    dataset_column(),
    sa.Column("source_id", sa.Uuid(as_uuid=False), nullable=False),
    sa.Column("artifact_type", sa.Text(), nullable=False),
    sa.Column("external_ref", sa.Text()),
    sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("content_hash", sa.String(64), nullable=False),
    sa.Column("content_type", sa.Text(), nullable=False),
    sa.Column("payload", JSON, nullable=False),
    sa.Column("metadata", JSON, nullable=False),
    sa.ForeignKeyConstraint(
        ["dataset_id", "source_id"], ["research_sources.dataset_id", "research_sources.id"]
    ),
    sa.UniqueConstraint("dataset_id", "source_id", "content_hash", name="uq_research_raw_hash"),
    sa.UniqueConstraint("dataset_id", "source_id", "id", name="uq_research_raw_source_id"),
    sa.UniqueConstraint("dataset_id", "id", name="uq_research_raw_dataset_id"),
    sa.CheckConstraint("length(content_hash) = 64", name="raw_sha256"),
)
sa.Index("ix_research_raw_source", raw_artifacts.c.dataset_id, raw_artifacts.c.source_id)

matches = sa.Table(
    "research_matches",
    metadata,
    *identity(),
    *provenance(),
    *availability(),
    sa.Column("research_match_id", sa.Text(), nullable=False),
    *(
        sa.Column(name, sa.Text())
        for name in ("sporttery_match_id", "competition_id", "home_team_id", "away_team_id")
    ),
    sa.Column("kickoff_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("source_record_id", sa.Text(), nullable=False),
    sa.Column("sporttery_verification_status", sa.Text(), nullable=False, server_default="UNVERIFIED"),
    sa.Column("sporttery_verification_artifact_id", sa.Uuid(as_uuid=False)),
    sa.ForeignKeyConstraint(
        ["dataset_id", "sporttery_verification_artifact_id"],
        ["research_raw_artifacts.dataset_id", "research_raw_artifacts.id"],
    ),
    sa.UniqueConstraint("dataset_id", "research_match_id", name="uq_research_match"),
    sa.UniqueConstraint(
        "dataset_id", "source_id", "source_record_id", name="uq_research_match_source_record"
    ),
    sa.CheckConstraint(
        "sporttery_verification_status IN ('UNVERIFIED','VERIFIED','REJECTED')", name="sporttery_status"
    ),
    sa.CheckConstraint(
        "sporttery_verification_status <> 'VERIFIED' OR (sporttery_match_id IS NOT NULL "
        "AND length(trim(sporttery_match_id)) > 0 AND sporttery_verification_artifact_id IS NOT NULL)",
        name="sporttery_evidence_required",
    ),
    sa.CheckConstraint("home_team_id <> away_team_id", name="match_distinct_teams"),
)
sa.Index("ix_research_matches_kickoff", matches.c.dataset_id, matches.c.kickoff_at)

odds_quotes = sa.Table(
    "research_odds_quotes",
    metadata,
    *identity(),
    *provenance(),
    *availability(),
    *(
        sa.Column(name, sa.Text(), nullable=False)
        for name in ("record_id", "research_match_id", "provider", "bookmaker", "market_type", "selection")
    ),
    sa.Column("line", DECIMAL),
    sa.Column("decimal_odds", DECIMAL, nullable=False),
    sa.ForeignKeyConstraint(
        ["dataset_id", "research_match_id"],
        ["research_matches.dataset_id", "research_matches.research_match_id"],
    ),
    sa.UniqueConstraint("dataset_id", "record_id", name="uq_research_odds_record"),
    sa.CheckConstraint("decimal_odds > '1'", name="research_valid_odds"),
    sa.CheckConstraint(
        "CAST(decimal_odds AS TEXT) NOT IN ('NaN','Infinity','-Infinity') AND "
        "CAST(line AS TEXT) NOT IN ('NaN','Infinity','-Infinity')",
        name="research_finite_odds",
    ),
)
sa.Index(
    "ix_research_odds_series",
    *(
        odds_quotes.c[name]
        for name in ("dataset_id", "research_match_id", "provider", "bookmaker", "market_type")
    ),
)

results = sa.Table(
    "research_results",
    metadata,
    *identity(),
    *provenance(),
    *availability(),
    sa.Column("record_id", sa.Text(), nullable=False),
    sa.Column("research_match_id", sa.Text(), nullable=False),
    sa.Column("home_team_id", sa.Text()),
    sa.Column("away_team_id", sa.Text()),
    sa.Column("home_score", sa.Integer(), nullable=False),
    sa.Column("away_score", sa.Integer(), nullable=False),
    sa.Column("finished_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("score_scope", sa.Text(), nullable=False),
    sa.ForeignKeyConstraint(
        ["dataset_id", "research_match_id"],
        ["research_matches.dataset_id", "research_matches.research_match_id"],
    ),
    sa.UniqueConstraint("dataset_id", "record_id", name="uq_research_result_record"),
    sa.CheckConstraint("home_score >= 0 AND away_score >= 0", name="research_scores"),
    sa.CheckConstraint("score_scope = 'REGULATION'", name="research_regulation"),
    sa.CheckConstraint("home_team_id <> away_team_id", name="result_distinct_teams"),
    sa.CheckConstraint(
        "replay_available_at IS NULL OR replay_available_at >= finished_at",
        name="result_available_after_finish",
    ),
)
sa.Index("ix_research_results_match", results.c.dataset_id, results.c.research_match_id)
