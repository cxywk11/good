"""Protect provenance, audit and odds at the database boundary."""
from alembic import op

revision = "002_immutable"
down_revision = "f20024045a94"
branch_labels = None
depends_on = None
TABLES = ("provider_raw_payloads", "odds_snapshots", "odds_key_snapshots", "match_versions", "audit_logs")


def upgrade():
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        op.execute("""CREATE FUNCTION reject_immutable_change() RETURNS trigger AS $$
            BEGIN RAISE EXCEPTION 'append-only table: %', TG_TABLE_NAME; END;
            $$ LANGUAGE plpgsql""")
        for table in TABLES:
            op.execute(f"CREATE TRIGGER immutable_{table} BEFORE UPDATE OR DELETE ON {table} "
                       "FOR EACH ROW EXECUTE FUNCTION reject_immutable_change()")
    elif dialect == "sqlite":
        for table in TABLES:
            for operation in ("UPDATE", "DELETE"):
                op.execute(f"CREATE TRIGGER immutable_{table}_{operation} BEFORE {operation} ON {table} "
                           "BEGIN SELECT RAISE(ABORT, 'append-only table'); END")


def downgrade():
    dialect = op.get_bind().dialect.name
    for table in TABLES:
        if dialect == "postgresql":
            op.execute(f"DROP TRIGGER immutable_{table} ON {table}")
        else:
            for operation in ("UPDATE", "DELETE"):
                op.execute(f"DROP TRIGGER immutable_{table}_{operation}")
    if dialect == "postgresql":
        op.execute("DROP FUNCTION reject_immutable_change()")
