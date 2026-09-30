"""Record key observation time without changing immutable historical rows."""
from alembic import op
import sqlalchemy as sa

revision = "005_key_observation_time"
down_revision = "004_observation_guards"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("odds_key_snapshots", sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_audit_entity_time", "audit_logs", ["entity_type", "entity_id", "created_at"])


def downgrade():
    op.drop_index("ix_audit_entity_time", table_name="audit_logs")
    op.drop_column("odds_key_snapshots", "observed_at")
