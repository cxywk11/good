import copy
import json
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from jc.providers.base import OddsProvider
from jc.providers.contracts import (
    FetchedPayload,
    NormalizedBatch,
    NormalizedMatch,
    NormalizedResult,
    NormalizedTeamStats,
    OddsQuote,
)
from jc.providers.http import ProviderError
from jc.providers.parsing import decimal_odds, parse_line
from jc.providers.sporttery import SportteryProvider
from jc.time import BEIJING, parse_time, utcnow

FIXTURES = Path(__file__).resolve().parents[5] / "tests" / "fixtures"


def read_fixture(name: str) -> dict:
    data = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    if data.get("mock") is not True:
        raise ProviderError("FIXTURE_UNLABELED", "Fixture must declare mock=true")
    return data


class MockSportteryProvider(SportteryProvider):
    def __init__(self, day: date | None = None):
        self.day = day or utcnow().astimezone(BEIJING).date()

    def payload(self) -> dict:
        data = read_fixture("sporttery")
        for group in data["value"]["matchInfoList"]:
            group["businessDate"] = self.day.isoformat()
            for row in group["subMatchList"]:
                row["businessDate"] = self.day.isoformat()
                row["matchDate"] = (self.day + timedelta(days=1)).isoformat()
                row["matchNumStr"] = "周" + "一二三四五六日"[self.day.weekday()] + row["matchNumStr"][-3:]
        return data

    async def fetch_matches(self) -> list[FetchedPayload]:
        return [
            FetchedPayload(
                self.name, "matches", self.payload(), "fixture://sporttery.json", utcnow(), mock=True
            )
        ]

    async def fetch_odds(self, external_ids: list[str] | None = None) -> list[FetchedPayload]:
        return [
            FetchedPayload(self.name, "odds", self.payload(), "fixture://sporttery.json", utcnow(), mock=True)
        ]

    async def fetch_results(self) -> list[FetchedPayload]:
        # Fixed synthetic completed fixture, not enabled by the scheduler or seed_demo.
        return [
            FetchedPayload(
                self.name,
                "results",
                read_fixture("post_match"),
                "fixture://post_match.json",
                utcnow(),
                mock=True,
            )
        ]

    def normalize(self, fetched: FetchedPayload) -> NormalizedBatch:
        if fetched.resource_type != "results":
            return super().normalize(fetched)
        if fetched.payload.get("mock") is not True or not fetched.mock:
            raise ProviderError("FIXTURE_UNLABELED", "Refuse unlabelled final-result fixture")
        return NormalizedBatch(
            results=[NormalizedResult.model_validate(row) for row in fetched.payload["results"]],
            team_stats=[NormalizedTeamStats.model_validate(row) for row in fetched.payload["team_stats"]],
        )


class MockOddsProvider(OddsProvider):
    supports_history = True

    def __init__(self, name: str, day: date | None = None, revision: int = 0):
        if name not in {"pinnacle", "bet365", "macau", "williamhill"}:
            raise ValueError("Unknown mock provider")
        self.name, self.day, self.revision = name, day or utcnow().astimezone(BEIJING).date(), revision

    def payload(self):
        data = copy.deepcopy(read_fixture(self.name))
        delta = self.day - date(2026, 9, 30)
        for item in data["matches"]:
            item["kickoff_at"] = (parse_time(item["kickoff_at"]) + delta).isoformat()
        for quote in data["odds"]:
            # Fixture revisions are explicit synthetic market changes. Observation time remains real.
            quote["decimal_odds"] = str(decimal_odds(quote["decimal_odds"]) - self.revision * Decimal("0.02"))
            quote["effective_at"] = (
                parse_time(quote["effective_at"])
                + delta
                - timedelta(hours=9)
                + timedelta(minutes=5 * self.revision)
            ).isoformat()
        return data

    async def fetch_matches(self) -> list[FetchedPayload]:
        return [
            FetchedPayload(
                self.name, "matches", self.payload(), f"fixture://{self.name}.json", utcnow(), mock=True
            )
        ]

    async def fetch_odds(self, external_ids: list[str] | None = None) -> list[FetchedPayload]:
        return [
            FetchedPayload(
                self.name, "odds", self.payload(), f"fixture://{self.name}.json", utcnow(), mock=True
            )
        ]

    async def fetch_odds_history(self, external_ids: list[str], at: datetime) -> list[FetchedPayload]:
        fetched = (await self.fetch_odds())[0]
        fetched.resource_type = "history"
        fetched.payload["odds"] = [
            q
            for q in fetched.payload["odds"]
            if q["external_match_id"] in external_ids and parse_time(q["effective_at"]) <= at
        ]
        return [fetched]

    def normalize(self, fetched: FetchedPayload) -> NormalizedBatch:
        if fetched.payload.get("mock") is not True or not fetched.mock:
            raise ProviderError("FIXTURE_UNLABELED", "Refuse an unlabelled mock payload")
        matches = [NormalizedMatch.model_validate(item) for item in fetched.payload["matches"]]
        if len({m.external_id for m in matches}) != len(matches):
            raise ProviderError("DUPLICATE_CONFLICT", "Duplicate provider matches")
        quotes = [
            OddsQuote(
                **{
                    **q,
                    "raw_odds": q["decimal_odds"],
                    "decimal_odds": decimal_odds(q["decimal_odds"]),
                    "line": parse_line(q.get("line")),
                }
            )
            for q in fetched.payload["odds"]
        ]
        return NormalizedBatch(matches if fetched.resource_type == "matches" else [], quotes)
