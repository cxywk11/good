"""Stable migration helper; reuse the PostgreSQL function created by revision 002."""

import re

from alembic import op


def immutable_tables(tables: tuple[str, ...], *, create: bool) -> None:
    for table in tables:
        if not re.fullmatch(r"[a-z_]+", table):
            raise ValueError("Invalid migration table identifier")
        if op.get_bind().dialect.name == "postgresql":
            if create:
                op.execute(
                    f"CREATE TRIGGER immutable_{table} BEFORE UPDATE OR DELETE ON {table} "
                    "FOR EACH ROW EXECUTE FUNCTION reject_immutable_change()"
                )
            else:
                op.execute(f"DROP TRIGGER immutable_{table} ON {table}")
        elif op.get_bind().dialect.name == "sqlite":
            for operation in ("UPDATE", "DELETE"):
                if create:
                    op.execute(
                        f"CREATE TRIGGER immutable_{table}_{operation} BEFORE {operation} ON {table} "
                        "BEGIN SELECT RAISE(ABORT, 'append-only table'); END"
                    )
                else:
                    op.execute(f"DROP TRIGGER immutable_{table}_{operation}")
        else:
            raise RuntimeError("Unsupported database for immutable tables")
