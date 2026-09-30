"""Restore a snapshot-consistent dump into a new disposable database, verify, then remove only that DB."""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import psycopg
from jc.config import Settings
from jc.ingestion import payload_hash
from psycopg import sql
from sqlalchemy.engine import make_url

IMMUTABLE = (
    "provider_raw_payloads",
    "match_versions",
    "odds_snapshots",
    "odds_observations",
    "odds_key_snapshots",
    "audit_logs",
)


def connect_args(url, database=None):
    return {
        "host": url.host or "localhost",
        "port": url.port or 5432,
        "user": url.username,
        "password": url.password,
        "dbname": database or url.database,
        "connect_timeout": 10,
        **dict(url.query),
        "options": "-c timezone=UTC",
    }


def fingerprint(connection):
    tables = [
        row[0]
        for row in connection.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"
        )
    ]
    result = {}
    for table in tables:
        # JSONB gives deterministic keys and the ORDER BY makes restored row order irrelevant.
        statement = sql.SQL("SELECT to_jsonb(t)::text FROM {} t ORDER BY to_jsonb(t)::text").format(
            sql.Identifier("public", table)
        )
        digest, count = hashlib.sha256(), 0
        with connection.cursor(name="verify_" + uuid4().hex[:12]) as cursor:
            cursor.execute(statement)
            for (row,) in cursor:
                digest.update((row + "\n").encode())
                count += 1
        result[table] = {"rows": count, "sha256": digest.hexdigest()}
    constraints = list(
        connection.execute(
            "SELECT c.relname, con.conname, pg_get_constraintdef(con.oid) "
            "FROM pg_constraint con JOIN pg_class c ON c.oid=con.conrelid "
            "JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' "
            "ORDER BY c.relname, con.conname"
        )
    )
    triggers = list(
        connection.execute(
            "SELECT c.relname, t.tgname, pg_get_triggerdef(t.oid) "
            "FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid "
            "JOIN pg_namespace n ON n.oid=c.relnamespace "
            "WHERE n.nspname='public' AND NOT t.tgisinternal ORDER BY c.relname,t.tgname"
        )
    )
    return {"tables": result, "constraints": constraints, "triggers": triggers}


def verify_guards(connection):
    result = {}
    for table in IMMUTABLE:
        qualified = sql.Identifier("public", table)
        if not connection.execute(sql.SQL("SELECT 1 FROM {} LIMIT 1").format(qualified)).fetchone():
            raise RuntimeError(f"Cannot exercise immutable guard on empty table: {table}")
        for operation in ("UPDATE", "DELETE"):
            prefix = sql.SQL("UPDATE {} SET id=id") if operation == "UPDATE" else sql.SQL("DELETE FROM {}")
            statement = prefix.format(qualified) + sql.SQL(" WHERE id=(SELECT id FROM {} LIMIT 1)").format(
                qualified
            )
            blocked = False
            try:
                with connection.transaction(force_rollback=True):
                    connection.execute(statement)
            except psycopg.errors.RaiseException as error:
                if "append-only table" not in str(error):
                    raise
                blocked = True
            if not blocked:
                raise RuntimeError(f"Immutable guard missing: {table}/{operation}")
            result[f"{table}:{operation}"] = "REJECTED"
    return result


def canonical_checks(connection, constraints):
    """PostgreSQL can rewrite array casts when parsing restored CHECK definitions.

    Reparse both sides with identical column types, rather than ignoring changed constraints.
    Only temporary, empty tables in the disposable restore database are touched.
    """
    result = []
    for table, name, definition in constraints:
        if definition.startswith("CHECK "):
            temporary = "verify_check_" + uuid4().hex[:16]
            with connection.transaction(force_rollback=True):
                connection.execute(
                    sql.SQL("CREATE TEMP TABLE {} (LIKE {})").format(
                        sql.Identifier(temporary), sql.Identifier("public", table)
                    )
                )
                connection.execute(
                    sql.SQL("ALTER TABLE {} ADD CONSTRAINT verify_check {}").format(
                        sql.Identifier(temporary), sql.SQL(definition)
                    )
                )
                definition = connection.execute(
                    "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid=%s::regclass "
                    "AND conname='verify_check'",
                    (temporary,),
                ).fetchone()[0]
        result.append((table, name, definition))
    return result


def run_tool(binary, arguments, environment):
    # Password travels through the child's environment, never the command line or report.
    completed = subprocess.run([str(binary), *arguments], env=environment, capture_output=True, timeout=300)
    if completed.returncode:
        raise RuntimeError(f"{Path(binary).name} failed with exit code {completed.returncode}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pg-bin", type=Path, default=Path(".runtime/pgsql/bin"))
    parser.add_argument("--output", type=Path, default=Path("artifacts/backups"))
    args = parser.parse_args()
    url = make_url(Settings().database_url)
    if url.get_backend_name() != "postgresql":
        raise SystemExit("A PostgreSQL source database is required")
    suffix = ".exe" if os.name == "nt" else ""
    binaries = {}
    for name in ("pg_dump", "pg_restore"):
        path = args.pg_bin / (name + suffix)
        binary = path.resolve() if path.is_file() else shutil.which(name)
        if not binary:
            raise SystemExit(f"Missing {name}; pass --pg-bin")
        binaries[name] = binary
    args.output.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid4().hex[:8]
    target = "jc_restore_" + uuid4().hex[:16] + "_test"
    archive = (args.output / (stamp + ".dump")).resolve()
    report_path = args.output / (stamp + ".json")
    report = {
        "started_at": datetime.now(UTC).isoformat(),
        "status": "FAILED",
        "archive": str(archive),
        "source_database": url.database,
        "restore_database": target,
        "temporary_database_removed": False,
    }
    environment = {
        **os.environ,
        "PGHOST": url.host or "localhost",
        "PGPORT": str(url.port or 5432),
        "PGUSER": url.username or "",
        "PGPASSWORD": url.password or "",
        "PGDATABASE": url.database or "",
        "PGCONNECT_TIMEOUT": "10",
        "PGOPTIONS": "-c timezone=UTC",
    }
    for parameter, variable in {
        "sslmode": "PGSSLMODE",
        "sslcert": "PGSSLCERT",
        "sslkey": "PGSSLKEY",
        "sslrootcert": "PGSSLROOTCERT",
        "sslcrl": "PGSSLCRL",
        "channel_binding": "PGCHANNELBINDING",
    }.items():
        if url.query.get(parameter):
            environment[variable] = url.query[parameter]
    created = False
    try:
        report["stage"] = "dump_and_fingerprint"
        # Keep one read-only snapshot for both pg_dump and the source fingerprints.
        with psycopg.connect(**connect_args(url)) as source:
            source.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            snapshot = source.execute("SELECT pg_export_snapshot()").fetchone()[0]
            run_tool(
                binaries["pg_dump"],
                [
                    "--format=custom",
                    "--no-owner",
                    "--no-acl",
                    "--no-password",
                    "--snapshot=" + snapshot,
                    "--file=" + str(archive),
                ],
                environment,
            )
            expected = fingerprint(source)
        with psycopg.connect(**connect_args(url, "postgres"), autocommit=True) as admin:
            admin.execute(sql.SQL("CREATE DATABASE {} TEMPLATE template0").format(sql.Identifier(target)))
            created = True  # Never drop a database unless this invocation created it successfully.
        restore_environment = {**environment, "PGDATABASE": target}
        report["stage"] = "restore"
        run_tool(
            binaries["pg_restore"],
            [
                "--dbname=" + target,
                "--no-owner",
                "--no-acl",
                "--no-password",
                "--exit-on-error",
                "--single-transaction",
                str(archive),
            ],
            restore_environment,
        )
        with psycopg.connect(**connect_args(url, target)) as restored:
            report["stage"] = "compare"
            actual = fingerprint(restored)
            expected["constraints"] = canonical_checks(restored, expected["constraints"])
            actual["constraints"] = canonical_checks(restored, actual["constraints"])
            if actual != expected:
                report["mismatch_sections"] = [key for key in expected if expected[key] != actual[key]]
                report["constraint_diff"] = {
                    "source_only": sorted(set(expected["constraints"]) - set(actual["constraints"])),
                    "restored_only": sorted(set(actual["constraints"]) - set(expected["constraints"])),
                }
                raise RuntimeError("Restored row hashes, constraints or triggers differ")
            report["stage"] = "immutable_guards"
            report["immutable_guards"] = verify_guards(restored)
            raw_verified = 0
            for payload, stored_hash in restored.execute(
                "SELECT payload,payload_hash FROM provider_raw_payloads"
            ):
                if payload_hash(payload) != stored_hash:
                    raise RuntimeError("Restored Raw content does not match its recorded payload hash")
                raw_verified += 1
            report["raw_payload_hashes_verified"] = raw_verified
            report["tables"] = actual["tables"]
            report["constraint_count"] = len(actual["constraints"])
            report["trigger_count"] = len(actual["triggers"])
        report["archive_sha256"] = hashlib.sha256(archive.read_bytes()).hexdigest()
        report["archive_bytes"] = archive.stat().st_size
        report["status"] = "PASSED"
        report["stage"] = "complete"
    except Exception as error:
        report["error_type"] = type(error).__name__  # Never echo DSNs or data-bearing SQL errors.
        if type(error) is RuntimeError:
            report["error_message"] = str(error)
    finally:
        if created:
            try:
                with psycopg.connect(**connect_args(url, "postgres"), autocommit=True) as admin:
                    admin.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(target)))
                report["temporary_database_removed"] = True
            except Exception:
                report["status"] = "FAILED"
                report["cleanup_error"] = "Temporary database cleanup failed; see restore_database"
        report["duration_seconds"] = round(time.perf_counter() - started, 3)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "status": report["status"],
                "report": str(report_path.resolve()),
                "temporary_database_removed": report["temporary_database_removed"],
            },
            ensure_ascii=False,
        )
    )
    return 0 if report["status"] == "PASSED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
