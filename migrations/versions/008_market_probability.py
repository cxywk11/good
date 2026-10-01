"""Immutable market probability baseline derived only from frozen features."""

from pathlib import Path

import sqlalchemy as sa
from alembic import op, util
from sqlalchemy.dialects import postgresql

immutable_tables = util.load_python_file(Path(__file__).parents[1], "immutability.py").immutable_tables

revision = "008_market_probability"
down_revision = "007_feature_foundation"
branch_labels = None
depends_on = None
TABLES = ("market_model_snapshots",)


def upgrade():
    op.create_table(
        "market_model_snapshots",
        sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("match_id", sa.Uuid(as_uuid=False), sa.ForeignKey("matches.id"), nullable=False),
        sa.Column(
            "feature_snapshot_id",
            sa.Uuid(as_uuid=False),
            sa.ForeignKey("feature_snapshots.id"),
            nullable=False,
        ),
        sa.Column("analysis_cutoff", sa.DateTime(timezone=True), nullable=False),
        sa.Column("market_model_version", sa.String(60), nullable=False),
        sa.Column("normalization_method", sa.String(60), nullable=False),
        sa.Column("market_data", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False),
        sa.Column("mock", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("feature_snapshot_id", "market_model_version", name="uq_market_feature_version"),
        sa.CheckConstraint("analysis_cutoff <= created_at", name="market_not_future"),
    )
    immutable_tables(TABLES, create=True)


def downgrade():
    immutable_tables(TABLES, create=False)
    op.drop_table("market_model_snapshots")
