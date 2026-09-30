from datetime import datetime
from urllib.parse import quote

from jc.config import Settings
from jc.providers.base import OddsProvider
from jc.providers.contracts import FetchedPayload, NormalizedBatch, NormalizedMatch, OddsQuote
from jc.providers.http import HttpTransport, ProviderError
from jc.providers.parsing import decimal_odds, parse_line
from jc.time import as_utc, parse_time


class TheOddsApiProvider(OddsProvider):
    name = "the_odds_api"
    supports_history = True

    def __init__(self, settings: Settings, transport: HttpTransport):
        self.settings, self.transport = settings, transport

    async def _fetch(
        self, resource: str, external_ids: list[str] | None = None, at: datetime | None = None
    ) -> list[FetchedPayload]:
        if not self.settings.odds_provider_api_key:
            raise ProviderError("MISSING_API_KEY", "Set ODDS_PROVIDER_API_KEY to use the live provider")
        params = {
            "apiKey": self.settings.odds_provider_api_key,
            "oddsFormat": "decimal",
            "dateFormat": "iso",
            "markets": "h2h,spreads,totals",
            "bookmakers": self.settings.odds_provider_bookmakers,
        }
        if external_ids:
            params["eventIds"] = ",".join(external_ids)
        if at:
            params["date"] = as_utc(at).strftime("%Y-%m-%dT%H:%M:%SZ")
        result = []
        for sport in self.settings.odds_provider_sports.split(","):
            sport = sport.strip()
            if not sport.startswith("soccer_"):
                raise ProviderError("INVALID_SPORT", "Only explicit soccer sport keys are allowed")
            path = f"/v4/{'historical/' if at else ''}sports/{quote(sport, safe='')}/odds"
            fetched = await self.transport.fetch(
                self.name, resource, self.settings.odds_provider_base_url.rstrip("/") + path, params
            )
            result.append(fetched)
        return result

    async def fetch_matches(self) -> list[FetchedPayload]:
        return await self._fetch("matches")

    async def fetch_odds(self, external_ids: list[str] | None = None) -> list[FetchedPayload]:
        return await self._fetch("odds", external_ids)

    async def fetch_odds_history(self, external_ids: list[str], at: datetime) -> list[FetchedPayload]:
        return await self._fetch("history", external_ids, at)

    def normalize(self, fetched: FetchedPayload) -> NormalizedBatch:
        data = fetched.payload.get("data") if fetched.resource_type == "history" else fetched.payload
        if not isinstance(data, list):
            raise ProviderError("SCHEMA_CHANGED", "Expected an event array")
        batch = NormalizedBatch()
        seen: dict[str, dict] = {}
        try:
            for event in data:
                eid = str(event["id"])
                if eid in seen:
                    if seen[eid] != event:
                        raise ProviderError("DUPLICATE_CONFLICT", "Conflicting event IDs")
                    continue
                seen[eid] = event
                # This API does not supply stable team IDs. Names must never be promoted into fake IDs.
                batch.matches.append(
                    NormalizedMatch(
                        external_id=eid,
                        home_name=event["home_team"],
                        away_name=event["away_team"],
                        competition=event["sport_title"],
                        competition_external_id=event["sport_key"],
                        kickoff_at=parse_time(event["commence_time"]),
                    )
                )
                for bookmaker in event.get("bookmakers", []):
                    for market in bookmaker["markets"]:
                        kind = {"h2h": "1X2", "spreads": "ASIAN_HANDICAP", "totals": "TOTALS"}.get(
                            market["key"]
                        )
                        if kind is None:
                            continue
                        effective = market.get("last_update") or bookmaker.get("last_update")
                        for outcome in market["outcomes"]:
                            selection = {
                                event["home_team"]: "HOME",
                                event["away_team"]: "AWAY",
                                "Draw": "DRAW",
                                "Over": "OVER",
                                "Under": "UNDER",
                            }.get(outcome["name"])
                            if selection is None:
                                raise ProviderError("UNKNOWN_SELECTION", "Unrecognized market outcome")
                            line = parse_line(outcome.get("point"))
                            if kind != "1X2" and line is None:
                                raise ProviderError("MISSING_LINE", "Handicap or totals line is missing")
                            batch.odds.append(
                                OddsQuote(
                                    external_match_id=eid,
                                    bookmaker=bookmaker["key"],
                                    market_type=kind,
                                    selection=selection,
                                    line=line,
                                    raw_odds=str(outcome["price"]),
                                    decimal_odds=decimal_odds(str(outcome["price"])),
                                    effective_at=parse_time(effective) if effective else None,
                                )
                            )
        except ProviderError:
            raise
        except (ValueError, TypeError, KeyError) as exc:
            raise ProviderError("PARSE_ERROR", f"Odds API payload rejected: {type(exc).__name__}") from exc
        return batch
