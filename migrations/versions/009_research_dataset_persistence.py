"""Independent append-only research datasets; frozen schema for revision 009."""

from pathlib import Path

import sqlalchemy as sa
from alembic import op, util
from sqlalchemy.dialects import postgresql

immutable_tables = util.load_python_file(Path(__file__).parents[1], "immutability.py").immutable_tables
revision = "009_research_dataset_persistence"
down_revision = "008_market_probability"
branch_labels = None
depends_on = None
MEMBERS = (
    "research_sources",
    "research_raw_artifacts",
    "research_matches",
    "research_odds_quotes",
    "research_results",
)


def upgrade():
    op.create_table(
        "research_datasets",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("dataset_key", sa.Text(), nullable=False),
        sa.Column("dataset_version", sa.Text(), nullable=False),
        sa.Column("replay_version", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default="BUILDING", nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("manifest_json", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=True),
        sa.Column("quality_summary", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=True),
        sa.Column("sealed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "(status IN ('BUILDING','REJECTED') AND sealed_at IS NULL AND content_hash IS NULL AND quality_summary IS NULL) OR (status = 'SEALED' AND sealed_at IS NOT NULL AND content_hash IS NOT NULL AND length(content_hash) = 64 AND quality_summary IS NOT NULL)",
            name="research_dataset_lifecycle",
        ),
        sa.CheckConstraint("replay_version = 'research-replay-v1'", name="research_replay_version"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dataset_key", "dataset_version", name="uq_research_dataset_version"),
    )
    op.create_table(
        "research_sources",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("dataset_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("source_name", sa.Text(), nullable=False),
        sa.Column("source_type", sa.Text(), nullable=False),
        sa.Column("provider_name", sa.Text(), nullable=False),
        sa.Column("license_note", sa.Text(), nullable=False),
        sa.Column("retrieval_note", sa.Text(), nullable=False),
        sa.Column("base_url", sa.Text(), nullable=True),
        sa.Column("verification_status", sa.Text(), server_default="UNVERIFIED", nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verification_note", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "source_type <> 'SYNTHETIC_FIXTURE' OR verification_status = 'UNVERIFIED'",
            name="fixture_unverified",
        ),
        sa.CheckConstraint(
            "verification_status <> 'VERIFIED' OR (verified_at IS NOT NULL AND verification_note IS NOT NULL AND length(trim(verification_note)) > 0)",
            name="source_verification",
        ),
        sa.CheckConstraint(
            "verification_status IN ('UNVERIFIED','VERIFIED','REJECTED')", name="source_status"
        ),
        sa.ForeignKeyConstraint(
            ["dataset_id"],
            ["research_datasets.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dataset_id", "id", name="uq_research_source_dataset_id"),
        sa.UniqueConstraint("dataset_id", "source_name", name="uq_research_source_name"),
    )
    op.create_table(
        "research_raw_artifacts",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("dataset_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("source_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("artifact_type", sa.Text(), nullable=False),
        sa.Column("external_ref", sa.Text(), nullable=True),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("content_type", sa.Text(), nullable=False),
        sa.Column("payload", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False),
        sa.Column("metadata", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False),
        sa.CheckConstraint("length(content_hash) = 64", name="raw_sha256"),
        sa.ForeignKeyConstraint(
            ["dataset_id", "source_id"],
            ["research_sources.dataset_id", "research_sources.id"],
        ),
        sa.ForeignKeyConstraint(
            ["dataset_id"],
            ["research_datasets.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dataset_id", "id", name="uq_research_raw_dataset_id"),
        sa.UniqueConstraint("dataset_id", "source_id", "content_hash", name="uq_research_raw_hash"),
        sa.UniqueConstraint("dataset_id", "source_id", "id", name="uq_research_raw_source_id"),
    )
    op.create_index(
        "ix_research_raw_source", "research_raw_artifacts", ["dataset_id", "source_id"], unique=False
    )
    op.create_table(
        "research_matches",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("dataset_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("source_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("raw_artifact_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replay_available_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("availability_basis", sa.Text(), nullable=True),
        sa.Column("research_match_id", sa.Text(), nullable=False),
        sa.Column("sporttery_match_id", sa.Text(), nullable=True),
        sa.Column("competition_id", sa.Text(), nullable=True),
        sa.Column("home_team_id", sa.Text(), nullable=True),
        sa.Column("away_team_id", sa.Text(), nullable=True),
        sa.Column("kickoff_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_record_id", sa.Text(), nullable=False),
        sa.Column("sporttery_verification_status", sa.Text(), server_default="UNVERIFIED", nullable=False),
        sa.Column("sporttery_verification_artifact_id", sa.Uuid(as_uuid=False), nullable=True),
        sa.CheckConstraint(
            "(replay_available_at IS NULL AND availability_basis IS NULL) OR (replay_available_at IS NOT NULL AND availability_basis IS NOT NULL AND availability_basis IN ('SOURCE_SNAPSHOT_AT','PROVIDER_PUBLISHED_AT','PROVIDER_EFFECTIVE_AT','VERIFIED_ARCHIVE_TIMESTAMP'))",
            name="availability_pair",
        ),
        sa.CheckConstraint(
            "availability_basis <> 'PROVIDER_EFFECTIVE_AT' OR (effective_at IS NOT NULL AND replay_available_at = effective_at)",
            name="effective_evidence",
        ),
        sa.CheckConstraint(
            "availability_basis <> 'PROVIDER_PUBLISHED_AT' OR (published_at IS NOT NULL AND replay_available_at = published_at)",
            name="published_evidence",
        ),
        sa.CheckConstraint(
            "sporttery_verification_status <> 'VERIFIED' OR (sporttery_match_id IS NOT NULL AND length(trim(sporttery_match_id)) > 0 AND sporttery_verification_artifact_id IS NOT NULL)",
            name="sporttery_evidence_required",
        ),
        sa.CheckConstraint(
            "sporttery_verification_status IN ('UNVERIFIED','VERIFIED','REJECTED')", name="sporttery_status"
        ),
        sa.CheckConstraint("home_team_id <> away_team_id", name="match_distinct_teams"),
        sa.ForeignKeyConstraint(
            ["dataset_id", "source_id", "raw_artifact_id"],
            [
                "research_raw_artifacts.dataset_id",
                "research_raw_artifacts.source_id",
                "research_raw_artifacts.id",
            ],
        ),
        sa.ForeignKeyConstraint(
            ["dataset_id", "source_id"],
            ["research_sources.dataset_id", "research_sources.id"],
        ),
        sa.ForeignKeyConstraint(
            ["dataset_id", "sporttery_verification_artifact_id"],
            ["research_raw_artifacts.dataset_id", "research_raw_artifacts.id"],
        ),
        sa.ForeignKeyConstraint(
            ["dataset_id"],
            ["research_datasets.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dataset_id", "research_match_id", name="uq_research_match"),
        sa.UniqueConstraint(
            "dataset_id", "source_id", "source_record_id", name="uq_research_match_source_record"
        ),
    )
    op.create_index(
        "ix_research_matches_kickoff", "research_matches", ["dataset_id", "kickoff_at"], unique=False
    )
    op.create_table(
        "research_odds_quotes",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("dataset_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("source_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("raw_artifact_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replay_available_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("availability_basis", sa.Text(), nullable=True),
        sa.Column("record_id", sa.Text(), nullable=False),
        sa.Column("research_match_id", sa.Text(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("bookmaker", sa.Text(), nullable=False),
        sa.Column("market_type", sa.Text(), nullable=False),
        sa.Column("selection", sa.Text(), nullable=False),
        sa.Column("line", sa.Numeric().with_variant(sa.Text(), "sqlite"), nullable=True),
        sa.Column("decimal_odds", sa.Numeric().with_variant(sa.Text(), "sqlite"), nullable=False),
        sa.CheckConstraint(
            "(replay_available_at IS NULL AND availability_basis IS NULL) OR (replay_available_at IS NOT NULL AND availability_basis IS NOT NULL AND availability_basis IN ('SOURCE_SNAPSHOT_AT','PROVIDER_PUBLISHED_AT','PROVIDER_EFFECTIVE_AT','VERIFIED_ARCHIVE_TIMESTAMP'))",
            name="availability_pair",
        ),
        sa.CheckConstraint(
            "CAST(decimal_odds AS TEXT) NOT IN ('NaN','Infinity','-Infinity') AND CAST(line AS TEXT) NOT IN ('NaN','Infinity','-Infinity')",
            name="research_finite_odds",
        ),
        sa.CheckConstraint(
            "availability_basis <> 'PROVIDER_EFFECTIVE_AT' OR (effective_at IS NOT NULL AND replay_available_at = effective_at)",
            name="effective_evidence",
        ),
        sa.CheckConstraint(
            "availability_basis <> 'PROVIDER_PUBLISHED_AT' OR (published_at IS NOT NULL AND replay_available_at = published_at)",
            name="published_evidence",
        ),
        sa.CheckConstraint("decimal_odds > '1'", name="research_valid_odds"),
        sa.ForeignKeyConstraint(
            ["dataset_id", "research_match_id"],
            ["research_matches.dataset_id", "research_matches.research_match_id"],
        ),
        sa.ForeignKeyConstraint(
            ["dataset_id", "source_id", "raw_artifact_id"],
            [
                "research_raw_artifacts.dataset_id",
                "research_raw_artifacts.source_id",
                "research_raw_artifacts.id",
            ],
        ),
        sa.ForeignKeyConstraint(
            ["dataset_id", "source_id"],
            ["research_sources.dataset_id", "research_sources.id"],
        ),
        sa.ForeignKeyConstraint(
            ["dataset_id"],
            ["research_datasets.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dataset_id", "record_id", name="uq_research_odds_record"),
    )
    op.create_index(
        "ix_research_odds_series",
        "research_odds_quotes",
        ["dataset_id", "research_match_id", "provider", "bookmaker", "market_type"],
        unique=False,
    )
    op.create_table(
        "research_results",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("dataset_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("source_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("raw_artifact_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replay_available_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("availability_basis", sa.Text(), nullable=True),
        sa.Column("record_id", sa.Text(), nullable=False),
        sa.Column("research_match_id", sa.Text(), nullable=False),
        sa.Column("home_team_id", sa.Text(), nullable=True),
        sa.Column("away_team_id", sa.Text(), nullable=True),
        sa.Column("home_score", sa.Integer(), nullable=False),
        sa.Column("away_score", sa.Integer(), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("score_scope", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "(replay_available_at IS NULL AND availability_basis IS NULL) OR (replay_available_at IS NOT NULL AND availability_basis IS NOT NULL AND availability_basis IN ('SOURCE_SNAPSHOT_AT','PROVIDER_PUBLISHED_AT','PROVIDER_EFFECTIVE_AT','VERIFIED_ARCHIVE_TIMESTAMP'))",
            name="availability_pair",
        ),
        sa.CheckConstraint(
            "availability_basis <> 'PROVIDER_EFFECTIVE_AT' OR (effective_at IS NOT NULL AND replay_available_at = effective_at)",
            name="effective_evidence",
        ),
        sa.CheckConstraint(
            "availability_basis <> 'PROVIDER_PUBLISHED_AT' OR (published_at IS NOT NULL AND replay_available_at = published_at)",
            name="published_evidence",
        ),
        sa.CheckConstraint("score_scope = 'REGULATION'", name="research_regulation"),
        sa.CheckConstraint("home_score >= 0 AND away_score >= 0", name="research_scores"),
        sa.CheckConstraint("home_team_id <> away_team_id", name="result_distinct_teams"),
        sa.CheckConstraint(
            "replay_available_at IS NULL OR replay_available_at >= finished_at",
            name="result_available_after_finish",
        ),
        sa.ForeignKeyConstraint(
            ["dataset_id", "research_match_id"],
            ["research_matches.dataset_id", "research_matches.research_match_id"],
        ),
        sa.ForeignKeyConstraint(
            ["dataset_id", "source_id", "raw_artifact_id"],
            [
                "research_raw_artifacts.dataset_id",
                "research_raw_artifacts.source_id",
                "research_raw_artifacts.id",
            ],
        ),
        sa.ForeignKeyConstraint(
            ["dataset_id", "source_id"],
            ["research_sources.dataset_id", "research_sources.id"],
        ),
        sa.ForeignKeyConstraint(
            ["dataset_id"],
            ["research_datasets.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dataset_id", "record_id", name="uq_research_result_record"),
    )
    op.create_index(
        "ix_research_results_match", "research_results", ["dataset_id", "research_match_id"], unique=False
    )
    _protect()


def _protect():
    immutable_tables(MEMBERS, create=True)
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        op.execute("""CREATE FUNCTION research_dataset_guard() RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'research dataset cannot be deleted'; END IF;
            IF TG_OP = 'INSERT' THEN
                IF NEW.status <> 'BUILDING' THEN RAISE EXCEPTION 'dataset must start BUILDING'; END IF;
            ELSE
                IF OLD.status <> 'BUILDING' OR NEW.status NOT IN ('SEALED','REJECTED') OR
                    (to_jsonb(NEW) - ARRAY['status','sealed_at','content_hash','quality_summary']) IS DISTINCT FROM
                    (to_jsonb(OLD) - ARRAY['status','sealed_at','content_hash','quality_summary'])
                THEN RAISE EXCEPTION 'illegal research dataset transition'; END IF;
            END IF;
            RETURN NEW;
        END; $$ LANGUAGE plpgsql""")
        op.execute("""CREATE TRIGGER research_dataset_lifecycle BEFORE INSERT OR UPDATE OR DELETE
            ON research_datasets FOR EACH ROW EXECUTE FUNCTION research_dataset_guard()""")
        op.execute("""CREATE FUNCTION research_member_guard() RETURNS trigger AS $$
        DECLARE dataset_status text;
        BEGIN
            SELECT status INTO dataset_status FROM research_datasets WHERE id = NEW.dataset_id FOR UPDATE;
            IF dataset_status IS DISTINCT FROM 'BUILDING' THEN
                RAISE EXCEPTION 'research dataset is not BUILDING';
            END IF;
            RETURN NEW;
        END; $$ LANGUAGE plpgsql""")
        for table in MEMBERS:
            op.execute(
                f"CREATE TRIGGER research_member_insert BEFORE INSERT ON {table} "
                "FOR EACH ROW EXECUTE FUNCTION research_member_guard()"
            )
        for table in ("research_datasets", *MEMBERS):
            op.execute(
                f"CREATE TRIGGER research_no_truncate BEFORE TRUNCATE ON {table} "
                "FOR EACH STATEMENT EXECUTE FUNCTION reject_immutable_change()"
            )
    else:
        unchanged = " OR ".join(
            f"NEW.{name} IS NOT OLD.{name}"
            for name in (
                "id",
                "created_at",
                "dataset_key",
                "dataset_version",
                "replay_version",
                "description",
                "manifest_json",
            )
        )
        op.execute("""CREATE TRIGGER research_dataset_insert BEFORE INSERT ON research_datasets
            WHEN NEW.status <> 'BUILDING' BEGIN SELECT RAISE(ABORT, 'dataset must start BUILDING'); END""")
        op.execute(f"""CREATE TRIGGER research_dataset_update BEFORE UPDATE ON research_datasets
            WHEN OLD.status <> 'BUILDING' OR NEW.status NOT IN ('SEALED','REJECTED') OR {unchanged}
            BEGIN SELECT RAISE(ABORT, 'illegal research dataset transition'); END""")
        op.execute("""CREATE TRIGGER research_dataset_delete BEFORE DELETE ON research_datasets
            BEGIN SELECT RAISE(ABORT, 'research dataset cannot be deleted'); END""")
        for table in MEMBERS:
            op.execute(f"""CREATE TRIGGER research_member_insert_{table} BEFORE INSERT ON {table}
                WHEN NOT EXISTS (SELECT 1 FROM research_datasets WHERE id = NEW.dataset_id AND status = 'BUILDING')
                BEGIN SELECT RAISE(ABORT, 'research dataset is not BUILDING'); END""")
    _evidence_guards(dialect)


def _evidence_guards(dialect):
    rules = {
        "research_results": """EXISTS (SELECT 1 FROM research_matches m
            WHERE m.dataset_id = NEW.dataset_id AND m.research_match_id = NEW.research_match_id
            AND NEW.finished_at > m.kickoff_at
            AND (NEW.home_team_id IS NULL OR m.home_team_id IS NULL OR NEW.home_team_id = m.home_team_id)
            AND (NEW.away_team_id IS NULL OR m.away_team_id IS NULL OR NEW.away_team_id = m.away_team_id))""",
        "research_odds_quotes": """EXISTS (SELECT 1 FROM research_sources s
            WHERE s.dataset_id = NEW.dataset_id AND s.id = NEW.source_id AND s.source_name = NEW.provider)""",
    }
    official = """SELECT 1 FROM research_raw_artifacts a JOIN research_sources s
        ON s.id = a.source_id AND s.dataset_id = a.dataset_id
        WHERE a.id = NEW.sporttery_verification_artifact_id AND a.dataset_id = NEW.dataset_id
        AND a.artifact_type = 'SPORTTERY_POOL' AND s.source_type = 'OFFICIAL_SPORTTERY_HISTORY'
        AND s.provider_name = 'sporttery' AND s.verification_status = 'VERIFIED'"""
    if dialect == "postgresql":
        evidence = "a.metadata -> 'sporttery_pool_evidence'"
        official += f""" AND {evidence} ->> 'sporttery_match_id' = NEW.sporttery_match_id
            AND {evidence} ->> 'home_team_id' = NEW.home_team_id
            AND {evidence} ->> 'away_team_id' = NEW.away_team_id
            AND ({evidence} ->> 'kickoff_at')::timestamptz = NEW.kickoff_at"""
    else:
        for name in ("sporttery_match_id", "home_team_id", "away_team_id"):
            official += f" AND json_extract(a.metadata, '$.sporttery_pool_evidence.{name}') = NEW.{name}"
        official += " AND julianday(json_extract(a.metadata, '$.sporttery_pool_evidence.kickoff_at')) = julianday(NEW.kickoff_at)"
    rules["research_matches"] = f"NEW.sporttery_verification_status <> 'VERIFIED' OR EXISTS ({official})"
    for table, condition in rules.items():
        if dialect == "postgresql":
            op.execute(f"""CREATE FUNCTION evidence_{table}() RETURNS trigger AS $$
                BEGIN IF NOT ({condition}) THEN RAISE EXCEPTION 'invalid research evidence'; END IF;
                RETURN NEW; END; $$ LANGUAGE plpgsql""")
            op.execute(
                f"CREATE TRIGGER research_evidence BEFORE INSERT ON {table} "
                f"FOR EACH ROW EXECUTE FUNCTION evidence_{table}()"
            )
        else:
            op.execute(f"""CREATE TRIGGER evidence_{table} BEFORE INSERT ON {table} WHEN NOT ({condition})
                BEGIN SELECT RAISE(ABORT, 'invalid research evidence'); END""")


def downgrade():
    immutable_tables(MEMBERS, create=False)
    # Dropping only the new tables also removes their table-local triggers.
    for table in reversed(MEMBERS):
        op.drop_table(table)
    op.drop_table("research_datasets")
    if op.get_bind().dialect.name == "postgresql":
        for function in (
            "research_dataset_guard",
            "research_member_guard",
            "evidence_research_matches",
            "evidence_research_results",
            "evidence_research_odds_quotes",
        ):
            op.execute(f"DROP FUNCTION {function}()")
