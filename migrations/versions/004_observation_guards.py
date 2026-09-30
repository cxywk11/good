"""Immutable observations and one confirmed fixture per provider/target."""
from alembic import op

revision = "004_observation_guards"
down_revision = "549daf86d8c7"
branch_labels = None
depends_on = None


def upgrade():
    if op.get_bind().dialect.name == "postgresql":
        op.execute("CREATE TRIGGER immutable_odds_observations BEFORE UPDATE OR DELETE ON odds_observations "
                   "FOR EACH ROW EXECUTE FUNCTION reject_immutable_change()")
    else:
        for operation in ("UPDATE", "DELETE"):
            op.execute(f"CREATE TRIGGER immutable_odds_observations_{operation} BEFORE {operation} ON odds_observations "
                       "BEGIN SELECT RAISE(ABORT, 'append-only table'); END")
    op.execute("CREATE UNIQUE INDEX uq_confirmed_provider_target ON match_mapping(provider, match_id) "
               "WHERE status IN ('AUTO_CONFIRMED', 'CONFIRMED')")


def downgrade():
    op.execute("DROP INDEX uq_confirmed_provider_target")
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TRIGGER immutable_odds_observations ON odds_observations")
    else:
        for operation in ("UPDATE", "DELETE"):
            op.execute(f"DROP TRIGGER immutable_odds_observations_{operation}")
