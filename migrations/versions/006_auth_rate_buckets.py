"""Persistent bounded authentication attempts shared by API workers."""

import sqlalchemy as sa
from alembic import op

revision = "006_auth_rate_buckets"
down_revision = "005_key_observation_time"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "auth_rate_buckets",
        sa.Column("key", sa.String(120), primary_key=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("attempts > 0", name="positive_auth_attempts"),
    )
    op.create_index("ix_auth_rate_buckets_expires_at", "auth_rate_buckets", ["expires_at"])


def downgrade():
    op.drop_index("ix_auth_rate_buckets_expires_at", table_name="auth_rate_buckets")
    op.drop_table("auth_rate_buckets")
