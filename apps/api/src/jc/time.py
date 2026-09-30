from datetime import UTC, datetime
from zoneinfo import ZoneInfo

BEIJING = ZoneInfo("Asia/Shanghai")


def utcnow() -> datetime:
    return datetime.now(UTC)


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("Timezone is required")
    return value.astimezone(UTC)


def parse_time(value: str, source_timezone: str | None = None) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        if source_timezone is None:
            raise ValueError("Missing timezone")
        parsed = parsed.replace(tzinfo=ZoneInfo(source_timezone))
    return as_utc(parsed)
