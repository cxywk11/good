"""Create a local-only demo environment without overwriting existing configuration."""

import secrets
from pathlib import Path

root = Path(__file__).resolve().parents[1]
env = root / ".env"
if env.exists():
    print("Existing .env preserved")
else:
    lines = [
        "APP_ENV=development",
        "DATABASE_URL=sqlite:///./jc-demo.db",
        "REDIS_URL=redis://localhost:6379/0",
        "DEMO_MODE=true",
        "SPORTTERY_ENABLED=false",
        "ODDS_PROVIDER_ENABLED=false",
        "SCHEDULER_ENABLED=false",
        "LOG_LEVEL=INFO",
        f"JWT_SECRET={secrets.token_urlsafe(48)}",
        "ADMIN_EMAIL=admin@example.com",
        f"ADMIN_PASSWORD={secrets.token_urlsafe(18)}",
        "POSTGRES_USER=jc",
        f"POSTGRES_PASSWORD={secrets.token_urlsafe(18)}",
        "POSTGRES_DB=jc",
    ]
    env.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("Created .env for local Mock preview; administrator credentials are stored only in .env")
