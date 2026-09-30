import re
from datetime import date
from decimal import Decimal

from jc.config import Settings
from jc.providers.base import OddsProvider
from jc.providers.contracts import (
    SPORTTERY_POOLS,
    FetchedPayload,
    NormalizedBatch,
    NormalizedMatch,
    OddsQuote,
)
from jc.providers.http import HttpTransport, ProviderError
from jc.time import parse_time


def rows(payload: dict) -> list[dict]:
    if not isinstance(payload, dict) or str(payload.get("errorCode")) != "0":
        raise ProviderError("SCHEMA_CHANGED", "Missing success code")
    value = payload.get("value")
    if not isinstance(value, dict) or not isinstance(value.get("matchInfoList"), list):
        raise ProviderError("SCHEMA_CHANGED", "Missing matchInfoList")
    result: list[dict] = []
    for group in value["matchInfoList"]:
        if not isinstance(group, dict) or not isinstance(group.get("subMatchList"), list):
            raise ProviderError("SCHEMA_CHANGED", "Missing subMatchList")
        result.extend(
            dict(row, businessDate=row.get("businessDate", group.get("businessDate")))
            for row in group["subMatchList"]
        )
    return result


def selection_name(pool: str, key: str) -> str | None:
    if pool in {"had", "hhad"}:
        return {"h": "HOME", "d": "DRAW", "a": "AWAY"}.get(key)
    if pool == "ttg" and re.fullmatch(r"s[0-7]", key):
        return key[1] + ("+" if key == "s7" else "")
    if pool == "hafu" and re.fullmatch(r"[hda]{2}", key):
        return "/".join({"h": "H", "d": "D", "a": "A"}[letter] for letter in key)
    if pool == "crs":
        if re.fullmatch(r"s\d{2}s\d{2}", key):
            return f"{int(key[1:3])}:{int(key[4:6])}"
        return {"s1sh": "HOME_OTHER", "s1sd": "DRAW_OTHER", "s1sa": "AWAY_OTHER"}.get(key)
    return None


class SportteryProvider(OddsProvider):
    name = "sporttery"
    is_primary = True

    def __init__(self, settings: Settings, transport: HttpTransport):
        self.settings, self.transport = settings, transport

    async def fetch_matches(self) -> list[FetchedPayload]:
        return [
            await self.transport.fetch(
                self.name,
                "matches",
                self.settings.sporttery_base_url.rstrip("/") + self.settings.sporttery_matches_path,
                {"clientCode": "3001"},
            )
        ]

    async def fetch_odds(self, external_ids: list[str] | None = None) -> list[FetchedPayload]:
        return [
            await self.transport.fetch(
                self.name,
                "odds",
                self.settings.sporttery_base_url.rstrip("/") + self.settings.sporttery_odds_path,
                {"channel": "c"},
            )
        ]

    def normalize(self, fetched: FetchedPayload) -> NormalizedBatch:
        batch = NormalizedBatch()
        seen: dict[str, dict] = {}
        try:
            for row in rows(fetched.payload):
                external_id = str(row["matchId"])
                if external_id in seen:
                    if seen[external_id] != row:
                        raise ProviderError("DUPLICATE_CONFLICT", "Conflicting provider match IDs")
                    continue
                seen[external_id] = row
                pools = {p["poolCode"].lower(): p for p in row["poolList"]}
                markets = {}
                for pool in SPORTTERY_POOLS:
                    market = pools.get(pool)
                    # Official schedule: sellStatus=1 is on sale; pool absence means unavailable.
                    available = (
                        market is not None
                        and str(row.get("sellStatus", "1")) == "1"
                        and str(market.get("cbtValue")) == "1"
                    )
                    markets[pool] = {
                        "available": available,
                        "single_allowed": str(market.get("cbtSingle", market.get("single"))) == "1"
                        if market
                        else None,
                    }
                    values = row.get(pool, {})
                    if available:
                        for key, odds in values.items():
                            selection = selection_name(pool, key)
                            if selection is None or odds in ("", None, "--"):
                                continue
                            batch.odds.append(
                                OddsQuote(
                                    external_match_id=external_id,
                                    bookmaker="Sporttery",
                                    market_type="SPORTTERY_" + pool.upper(),
                                    selection=selection,
                                    line=Decimal(str(values["goalLine"]))
                                    if pool == "hhad" and values.get("goalLine") not in (None, "")
                                    else None,
                                    raw_odds=str(odds),
                                    decimal_odds=Decimal(str(odds)),
                                )
                            )
                if fetched.resource_type == "matches":
                    batch.matches.append(
                        NormalizedMatch(
                            external_id=external_id,
                            home_name=row["homeTeamAllName"],
                            away_name=row["awayTeamAllName"],
                            home_external_id=str(row["homeTeamId"]) if row.get("homeTeamId") else None,
                            away_external_id=str(row["awayTeamId"]) if row.get("awayTeamId") else None,
                            competition=row["leagueAllName"],
                            competition_external_id=str(row["leagueId"]),
                            kickoff_at=parse_time(row["matchDate"] + "T" + row["matchTime"], "Asia/Shanghai"),
                            match_num=row["matchNumStr"],
                            match_date=date.fromisoformat(row["matchDate"]),
                            sell_date=date.fromisoformat(row["businessDate"]),
                            sell_status={"1": "ON_SALE", "2": "SUSPENDED"}.get(
                                str(row["sellStatus"]), "CLOSED"
                            ),
                            single_allowed=any(v["single_allowed"] is True for v in markets.values()),
                            markets=markets,
                        )
                    )
        except ProviderError:
            raise
        except (KeyError, TypeError, ValueError, ArithmeticError) as exc:
            raise ProviderError("PARSE_ERROR", f"Sporttery payload rejected: {type(exc).__name__}") from exc
        return batch
