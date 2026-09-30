"""Post-match facts, conservative commit visibility, and immutable feature snapshots."""

from pathlib import Path

import sqlalchemy as sa
from alembic import op, util
from sqlalchemy.dialects import postgresql

immutable_tables = util.load_python_file(Path(__file__).parents[1], "immutability.py").immutable_tables

revision = "007_feature_foundation"
down_revision = "006_auth_rate_buckets"
branch_labels = None
depends_on = None
TABLES = ("analysis_visibility", "match_results", "team_match_stats", "feature_snapshots")


def evidence_columns():
    return [
        sa.Column("dedup_key", sa.String(64), nullable=False, unique=True),
        sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("match_id", sa.Uuid(as_uuid=False), sa.ForeignKey("matches.id"), nullable=False),
        sa.Column(
            "match_version_id", sa.Uuid(as_uuid=False), sa.ForeignKey("match_versions.id"), nullable=False
        ),
        sa.Column("source", sa.String(60), nullable=False),
        sa.Column(
            "raw_payload_id",
            sa.Uuid(as_uuid=False),
            sa.ForeignKey("provider_raw_payloads.id"),
            nullable=False,
        ),
        sa.Column("mapping_id", sa.Uuid(as_uuid=False), sa.ForeignKey("match_mapping.id")),
        sa.Column("mapping_version", sa.Integer()),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("effective_at", sa.DateTime(timezone=True)),
        sa.Column("mock", sa.Boolean(), nullable=False),
    ]


def upgrade():
    op.create_table(
        "analysis_visibility",
        sa.Column("entity_type", sa.String(60), primary_key=True),
        sa.Column("entity_id", sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column("visible_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "match_results",
        *evidence_columns(),
        sa.Column("home_score", sa.Integer(), nullable=False),
        sa.Column("away_score", sa.Integer(), nullable=False),
        sa.Column("half_home_score", sa.Integer()),
        sa.Column("half_away_score", sa.Integer()),
        sa.Column("first_goal_team", sa.String(10)),
        sa.Column("first_goal_minute", sa.Integer()),
        sa.CheckConstraint("home_score >= 0 AND away_score >= 0", name="valid_full_score"),
        sa.CheckConstraint("half_home_score >= 0 AND half_home_score <= home_score", name="valid_half_home"),
        sa.CheckConstraint("half_away_score >= 0 AND half_away_score <= away_score", name="valid_half_away"),
        sa.CheckConstraint("first_goal_team IN ('HOME', 'AWAY', 'NONE')", name="valid_first_goal_team"),
        sa.CheckConstraint("first_goal_minute >= 0", name="valid_first_goal_minute"),
        sa.CheckConstraint("finished_at <= observed_at", name="result_finished_before_observed"),
    )
    op.create_index("ix_results_cutoff", "match_results", ["match_id", "observed_at", "created_at"])
    op.create_table(
        "team_match_stats",
        *evidence_columns(),
        sa.Column("team_id", sa.Uuid(as_uuid=False), sa.ForeignKey("teams.id"), nullable=False),
        sa.Column("xg", sa.Numeric(10, 4)),
        sa.Column("xga", sa.Numeric(10, 4)),
        sa.Column("shots", sa.Integer()),
        sa.Column("shots_on_target", sa.Integer()),
        sa.Column("possession", sa.Numeric(7, 4)),
        sa.Column("corners", sa.Integer()),
        sa.Column("red_cards", sa.Integer()),
        sa.CheckConstraint("xg >= 0 AND xga >= 0", name="valid_xg"),
        sa.CheckConstraint("shots >= 0 AND shots_on_target >= 0", name="valid_shots"),
        sa.CheckConstraint("shots_on_target <= shots", name="valid_shots_on_target"),
        sa.CheckConstraint("possession >= 0 AND possession <= 100", name="valid_possession"),
        sa.CheckConstraint("corners >= 0 AND red_cards >= 0", name="valid_corners_cards"),
        sa.CheckConstraint("finished_at <= observed_at", name="stats_finished_before_observed"),
    )
    op.create_index("ix_stats_cutoff", "team_match_stats", ["team_id", "observed_at", "created_at"])
    op.create_table(
        "feature_snapshots",
        sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("match_id", sa.Uuid(as_uuid=False), sa.ForeignKey("matches.id"), nullable=False),
        sa.Column("analysis_cutoff", sa.DateTime(timezone=True), nullable=False),
        sa.Column("feature_version", sa.String(60), nullable=False),
        sa.Column("feature_data", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False),
        sa.Column("data_quality_score", sa.Integer(), nullable=False),
        sa.Column("mock", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("match_id", "analysis_cutoff", "feature_version", name="uq_feature_input"),
        sa.CheckConstraint("data_quality_score BETWEEN 0 AND 100", name="valid_feature_quality"),
        sa.CheckConstraint("analysis_cutoff <= created_at", name="feature_not_future"),
    )
    immutable_tables(TABLES, create=True)


def downgrade():
    immutable_tables(TABLES, create=False)
    for table in reversed(TABLES):
        op.drop_table(table)
