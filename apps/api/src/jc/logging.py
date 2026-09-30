import json
import logging
from datetime import UTC, datetime

FIELDS = ("provider", "operation", "request_id", "match_id", "duration_ms", "status", "error_code")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "level": record.levelname,
                "module": record.name,
                "message": record.getMessage(),
                **{field: getattr(record, field, None) for field in FIELDS},
            },
            ensure_ascii=False,
        )


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logging.basicConfig(level=level, handlers=[handler], force=True)
    # httpx INFO includes the complete URL (potentially including an API key).
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
