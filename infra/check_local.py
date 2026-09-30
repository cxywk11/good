"""Read-only preflight; missing dependencies remain BLOCKED and produce a nonzero exit code."""

import argparse
import json
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import httpx
from alembic.config import Config
from alembic.script import ScriptDirectory
from jc.config import Settings
from jc.db import make_engine
from redis import Redis
from sqlalchemy import text


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://127.0.0.1:8000")
    parser.add_argument("--output", type=Path, default=Path("artifacts/local-preflight.json"))
    args = parser.parse_args()
    settings = Settings()
    checks = {}
    engine = make_engine(settings.database_url)
    try:
        with engine.connect() as db:
            checks["postgres"] = {"status": "PASS" if engine.dialect.name == "postgresql" else "BLOCKED"}
            expected = ScriptDirectory.from_config(Config("alembic.ini")).get_current_head()
            current = db.scalar(text("SELECT version_num FROM alembic_version"))
            checks["migration"] = {
                "status": "PASS" if current == expected else "BLOCKED",
                "current": current,
                "expected": expected,
            }
    except Exception as error:
        checks["postgres"] = {"status": "BLOCKED", "reason": type(error).__name__}
    finally:
        engine.dispose()
    try:
        with Redis.from_url(settings.redis_url, socket_timeout=2, socket_connect_timeout=2) as client:
            checks["redis"] = {"status": "PASS" if client.ping() else "BLOCKED"}
    except Exception as error:
        checks["redis"] = {"status": "BLOCKED", "reason": type(error).__name__}
    if not shutil.which("docker"):
        checks["docker_engine"] = {"status": "BLOCKED", "reason": "Docker CLI not installed"}
    else:
        try:
            docker = subprocess.run(
                ["docker", "info", "--format", "{{.ServerVersion}}"], capture_output=True, timeout=15
            )
            checks["docker_engine"] = {"status": "PASS" if docker.returncode == 0 else "BLOCKED"}
        except Exception as error:
            checks["docker_engine"] = {"status": "BLOCKED", "reason": type(error).__name__}
    with httpx.Client(base_url=args.api, timeout=10) as client:
        for name, path in (
            ("api_health", "/health"),
            ("api_ready", "/ready"),
            ("today", "/api/v1/matches/today"),
        ):
            try:
                response = client.get(path)
                checks[name] = {
                    "status": "PASS" if response.status_code == 200 else "BLOCKED",
                    "http_status": response.status_code,
                }
                if name == "today" and response.status_code == 200:
                    data = response.json()["data"]
                    checks[name].update(
                        total=data["total"], demo_mode=data["demo_mode"], sell_date=data["sell_date"]
                    )
                    checks["real_match_pool"] = {
                        "status": "BLOCKED" if data["demo_mode"] else "UNVERIFIED",
                        "reason": "Requires comparison with official sale list",
                    }
            except Exception as error:
                checks[name] = {"status": "BLOCKED", "reason": type(error).__name__}
    checks["overseas_live"] = {
        "status": "UNVERIFIED" if settings.odds_provider_api_key else "BLOCKED",
        "configured": bool(settings.odds_provider_api_key),
    }
    result = {
        "checked_at": datetime.now(UTC).isoformat(),
        "checks": checks,
        "all_gates_verified": False,
        "note": "Preflight is not full Gate acceptance",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if any(check["status"] != "PASS" for check in checks.values()) else 0


if __name__ == "__main__":
    raise SystemExit(main())
