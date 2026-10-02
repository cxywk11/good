"""Bounded D2B discovery, with no import/replay until official evidence is reviewed.

This command collects probes, not a normalized dataset. A FETCHED response must
be reviewed before implementing its historical adapter and using the D2A importer.
"""

import argparse
import json
import os
from collections import defaultdict
from dataclasses import replace
from datetime import date
from pathlib import Path
from uuid import uuid4

from dotenv import dotenv_values

from jc.analysis.market import build_market_data
from jc.analysis.research_replay import (
    NotReplayable,
    ReplayCutoffSpec,
    ResearchOddsQuote,
    build_research_feature,
)
from jc.research.contracts import (
    ResearchImport,
    canonical_bytes,
    content_hash,
    reject_secrets,
    validate_import,
)
from jc.research.providers.probe import probe_source, record_blocked
from jc.time import BEIJING, utcnow

SPORTTERY_HISTORY = "https://webapi.sporttery.cn/gateway/uniform/football/getUniformMatchResultV1.qry"
ODDS_HISTORY = "https://api.the-odds-api.com/v4/historical/sports/soccer_epl/odds"
CUTOFF_MINUTES = (30, 90, 360)


def assess_intake_gates(value: ResearchImport, *, cutoff_minutes: tuple[int, ...] = CUTOFF_MINUTES) -> dict:
    """Independent A/B evidence gates; never attest C/D/E/F from their success.

    Input must already pass unchanged D2A evidence validation. This helper does
    not produce matches, source verifications, entity mappings or a SEALED claim.
    """
    value = validate_import(value)
    targets = {v.research_match_id for v in value.sporttery_verifications if v.status == "VERIFIED"}
    sources = {s.source.source_name: s for s in value.sources}
    external = {
        name
        for name, source in sources.items()
        if source.source.source_type == "EXTERNAL_ODDS_HISTORY" and source.verification_status == "VERIFIED"
        and name != "sporttery" and source.provider_name != "sporttery"
    }
    coverage = {}
    markets: dict = {}
    matches = {match.research_match_id: match for match in value.dataset.matches}
    for minutes in cutoff_minutes:
        covered = set()
        markets[str(minutes)] = {}
        for target in sorted(targets):
            cutoff = ReplayCutoffSpec(minutes).at(matches[target].kickoff_at)
            # Select whole external snapshots BEFORE frozen v1 selects per-series
            # quotes. Otherwise three unrelated timestamps can look complete.
            snapshots: dict[tuple, list[ResearchOddsQuote]] = defaultdict(list)
            for quote in value.dataset.odds:
                if (quote.research_match_id == target and quote.provider in external
                        and quote.market_type == "1X2" and quote.line is None
                        and quote.replay_available_at is not None
                        and all(stamp is None or stamp <= cutoff < matches[target].kickoff_at
                                for stamp in (quote.replay_available_at, quote.published_at, quote.effective_at))):
                    snapshots[(quote.provider, quote.bookmaker, quote.replay_available_at,
                               quote.effective_at or quote.published_at or quote.replay_available_at)].append(quote)
            latest: dict[tuple, list[ResearchOddsQuote]] = {}
            ambiguous = set()
            for key, quotes in sorted(snapshots.items()):
                bookmaker = key[:2]
                if len({q.selection for q in quotes}) != len(quotes):
                    ambiguous.add(bookmaker)  # Never arbitrarily pick a duplicate/conflicting observation.
                if (len(quotes) == 3 and {q.selection for q in quotes} == {"HOME", "DRAW", "AWAY"}
                        and len({(q.availability_basis, q.published_at, q.effective_at) for q in quotes}) == 1):
                    latest[bookmaker] = quotes
            odds = tuple(q for q in value.dataset.odds if q.provider == "sporttery") + tuple(
                q for bookmaker, quotes in latest.items() if bookmaker not in ambiguous for q in quotes
            )
            try:
                feature = build_research_feature(replace(value.dataset, odds=odds), target,
                                                 ReplayCutoffSpec(minutes))
            except NotReplayable:
                continue
            market = build_market_data(feature)
            markets[str(minutes)][target] = market
            consensus = market["external_consensus"]
            if consensus["source_count"] >= 1 and consensus["p_market"] is not None:
                covered.add(target)
        coverage[str(minutes)] = len(covered)
    return {
        "verified_target_count": len(targets),
        "cutoff_coverage": coverage,
        "cutoff_markets": markets,
        "gates": {
            "A": "PASS" if targets else "BLOCKED",
            "B": "PASS" if any(coverage.values()) else "BLOCKED",
        },
    }


def validate_window(start: date, end: date) -> None:
    if not 0 <= (end - start).days <= 2:
        raise ValueError("Pilot discovery requires 1 to 3 calendar days")
    if end >= utcnow().astimezone(BEIJING).date():
        raise ValueError("Pilot discovery requires completed past dates")


def blocked_pilot_report(start: date, end: date, probes: list[dict]) -> dict:
    """Only report the no-dataset discovery branch; never manufacture passed gates."""
    validate_window(start, end)
    reject_secrets(probes)
    if not any(p["source"].startswith("sporttery_history") for p in probes):
        raise ValueError("An actual official historical source probe is required")
    if any(p.get("sporttery_verification_status") == "VERIFIED" for p in probes):
        raise ValueError("Probe metadata cannot certify an official target; use D2A evidence validation")
    mapping = {
        "status": "BLOCKED_NO_VERIFIED_TARGETS",
        "mappings": [],
        "unresolved": [],
        "note": "No source team IDs acquired; no name-based mapping performed.",
    }
    return {
        "status": "BLOCKED",
        "message": "Pilot blocked by target-pool evidence",
        "generated_at": utcnow().isoformat(),
        "requested_history_window": {"start": start.isoformat(), "end": end.isoformat()},
        "verified_sale_dates": [],
        "scope_note": "Official match-date filters do not yet prove sales-day membership.",
        "dataset_key_requested": "jc-football-pilot",
        "dataset": None,
        "probe_response_raw_count": sum(p.get("raw_content_hash") is not None for p in probes),
        "dataset_raw_count": 0,
        "historical_envelopes": [
            p["inspection"]
            for p in probes
            if p.get("inspection", {}).get("schema_status") == "HISTORICAL_ENVELOPE_OBSERVED"
        ],
        "entity_mapping": mapping,
        "entity_mapping_hash": content_hash(mapping),
        "coverage": {
            "acquired_targets": 0,
            "verified_targets": 0,
            "sporttery_had": 0,
            "sporttery_hhad": 0,
            "sporttery_ttg": 0,
            "external_1x2": 0,
            "asian_handicap": 0,
            "totals": 0,
            "regulation_results": 0,
            "both_teams_at_least_five_history_results": 0,
            "market_evaluable": 0,
            "goals_evaluable": 0,
            "common_evaluable": 0,
            "denominator": 0,
            "coverage_percent": None,
        },
        "runs": [
            {
                "cutoff_minutes": minutes,
                "status": "BLOCKED_NOT_RUN",
                "run_id": None,
                "odds_replay_coverage": 0,
                "market_evaluable": 0,
                "goals_evaluable": 0,
                "common_evaluable": 0,
            }
            for minutes in CUTOFF_MINUTES
        ],
        "gates": {
            key: {"status": "BLOCKED", "reason": reason}
            for key, reason in {
                "A": "No reviewed official historical Sporttery target",
                "B": "No historical external odds joined to verified targets with time evidence",
                "C": "No REGULATION result acquired for verified targets",
                "D": "No acquired target team IDs or evidenced canonical mapping",
                "E": "No eligible ResearchImport; no dataset created or sealed",
                "F": "No SEALED real dataset; RESEARCH_REPLAY not executed",
            }.items()
        },
        "suitable_for_three_seasons": False,
        "probes": probes,
    }


def discover_pilot(start: date, end: date, output: Path) -> dict:
    validate_window(start, end)
    if os.environ.get("RESEARCH_NETWORK_ENABLED") != "1":
        raise RuntimeError("Set RESEARCH_NETWORK_ENABLED=1 for real source requests")
    if output.exists():
        raise ValueError("Use a new artifact directory for each discovery attempt")
    probes = [
        probe_source(
            output,
            "sporttery_history",
            SPORTTERY_HISTORY,
            params={
                "matchBeginDate": start.isoformat(),
                "matchEndDate": end.isoformat(),
                "leagueId": "",
                "pageSize": "30",
                "pageNo": "1",
                "isFix": "0",
                "matchPage": "1",
                "pcOrWap": "1",
            },
        )
    ]
    # Discovery is intentionally one page, not an unverified pagination crawler.
    # Read only this credential; do not instantiate or modify LIVE settings.
    credential = os.environ.get("ODDS_PROVIDER_API_KEY") or dotenv_values(".env").get("ODDS_PROVIDER_API_KEY")
    if not credential:
        probes.append(
            record_blocked(output, "the_odds_api_history", ODDS_HISTORY, "BLOCKED_MISSING_CREDENTIAL")
        )
    else:
        probes.append(
            probe_source(
                output,
                "the_odds_api_history",
                ODDS_HISTORY,
                params={
                    "apiKey": credential,
                    "date": f"{start.isoformat()}T12:00:00Z",
                    "regions": "uk",
                    "markets": "h2h,spreads,totals",
                    "oddsFormat": "decimal",
                },
            )
        )
    report = blocked_pilot_report(start, end, probes)
    with (output / "pilot-report.json").open("xb") as stream:
        stream.write(canonical_bytes(report))
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-date", required=True, type=date.fromisoformat)
    parser.add_argument("--end-date", required=True, type=date.fromisoformat)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = args.output or Path("artifacts/research-probes") / f"{utcnow():%Y%m%dT%H%M%SZ}-{uuid4().hex[:8]}"
    report = discover_pilot(args.start_date, args.end_date, output)
    print(json.dumps({"status": report["status"], "report": str(output / "pilot-report.json")}))
    return 2  # A blocked pilot must not look like a successful acquisition job.


if __name__ == "__main__":
    raise SystemExit(main())
