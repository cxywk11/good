import asyncio
import logging
from collections.abc import Awaitable, Callable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx

from jc.config import Settings
from jc.providers.contracts import FetchedPayload
from jc.time import utcnow

logger = logging.getLogger(__name__)


class ProviderError(Exception):
    def __init__(self, code: str, message: str, raw_id: str | None = None):
        super().__init__(message)
        self.code = code
        self.raw_id = raw_id


def safe_url(url: str) -> str:
    parts = urlsplit(url)
    query = [
        (key, "REDACTED" if key.lower() in {"apikey", "api_key", "key", "token", "password"} else value)
        for key, value in parse_qsl(parts.query)
    ]
    return urlunsplit((parts.scheme, parts.hostname or "", parts.path, urlencode(query), ""))


class HttpTransport:
    def __init__(
        self,
        settings: Settings,
        record: Callable[[FetchedPayload], str],
        client: httpx.AsyncClient | None = None,
        sleep=asyncio.sleep,
    ):
        self.settings, self.record, self.client, self.sleep = settings, record, client, sleep
        self.before_request: Callable[[str], Awaitable[None]] | None = None
        self.on_rate_limit: Callable[[str, int], Awaitable[None]] | None = None

    async def fetch(
        self, provider: str, resource: str, url: str, params: dict | None = None
    ) -> FetchedPayload:
        if not url.startswith(("https://", "http://")):
            raise ProviderError("CONFIGURATION", "Provider URL is missing")
        async with httpx.AsyncClient(timeout=self.settings.provider_timeout, follow_redirects=False) as owned:
            client = self.client or owned
            for attempt in range(self.settings.provider_max_attempts):
                if self.before_request:
                    await self.before_request(provider)
                retry_after = 0.0
                try:
                    response = await client.get(url, params=params)
                    try:
                        payload = response.json()
                    except ValueError:
                        payload = {"_unparsed_body": response.text}
                    result = FetchedPayload(
                        provider,
                        resource,
                        payload,
                        safe_url(str(response.url)),
                        utcnow(),
                        response.status_code,
                    )
                    result.raw_id = self.record(result)
                    if response.is_success:
                        return result
                    code = f"HTTP_{response.status_code}"
                    retryable = response.status_code in {429, 500, 502, 503, 504}
                    if response.status_code == 429:
                        try:
                            retry_after = max(float(response.headers.get("Retry-After", 60)), 1)
                        except ValueError:
                            from email.utils import parsedate_to_datetime

                            try:
                                retry_after = max(
                                    (
                                        parsedate_to_datetime(response.headers["Retry-After"]) - utcnow()
                                    ).total_seconds(),
                                    1,
                                )
                            except (ValueError, KeyError, TypeError):
                                retry_after = 60
                        if self.on_rate_limit:
                            await self.on_rate_limit(provider, int(retry_after) + 1)
                        raise ProviderError(
                            "RATE_LIMITED", "Provider requested a cooldown; see raw HTTP 429", result.raw_id
                        )
                except (httpx.TimeoutException, httpx.NetworkError) as exc:
                    code = "TIMEOUT" if isinstance(exc, httpx.TimeoutException) else "NETWORK"
                    result = FetchedPayload(
                        provider, resource, {"transport_error": code}, safe_url(url), utcnow(), None
                    )
                    result.raw_id = self.record(result)
                    retryable = True
                logger.warning(
                    "Provider request failed",
                    extra={
                        "provider": provider,
                        "operation": resource,
                        "status": "FAILED",
                        "error_code": code,
                    },
                )
                if not retryable or attempt + 1 == self.settings.provider_max_attempts:
                    raise ProviderError(code, f"Provider request failed ({code})", result.raw_id)
                await self.sleep(max(2**attempt, retry_after))
        raise ProviderError("REQUEST_FAILED", "No response")
