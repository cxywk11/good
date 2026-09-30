from abc import ABC, abstractmethod
from datetime import datetime

from jc.providers.contracts import FetchedPayload, NormalizedBatch
from jc.providers.http import ProviderError


class OddsProvider(ABC):
    """Provider transport + normalization boundary, independent of jobs and persistence."""

    name: str
    is_primary: bool = False
    supports_history: bool = False

    @abstractmethod
    async def fetch_matches(self) -> list[FetchedPayload]:
        raise NotImplementedError

    @abstractmethod
    async def fetch_odds(self, external_ids: list[str] | None = None) -> list[FetchedPayload]:
        raise NotImplementedError

    async def fetch_odds_history(self, external_ids: list[str], at: datetime) -> list[FetchedPayload]:
        raise ProviderError("HISTORY_UNSUPPORTED", "Provider historical backfill is not configured")

    @abstractmethod
    def normalize(self, fetched: FetchedPayload) -> NormalizedBatch:
        raise NotImplementedError

    async def health_check(self) -> dict:
        try:
            payloads = await self.fetch_matches()
            for payload in payloads:
                self.normalize(payload)
            return {"status": "HEALTHY" if payloads else "DEGRADED", "provider": self.name}
        except ProviderError as exc:
            return {"status": "DOWN", "provider": self.name, "error_code": exc.code}
