"""Single-target OddsPapi admission, outside frozen replay-v1 and D2A.

Historical createdAt is the provider's recorded snapshot instant, per its
reviewed documentation. Equal instants may be joined across outcome-filtered
responses; different instants may not. Always audit Raw again before replay.
"""

import json
from collections import defaultdict
from dataclasses import replace
from decimal import Decimal, InvalidOperation
from urllib.parse import parse_qs, urlsplit

from jc.analysis.research_replay import AvailabilityBasis, ReplayCutoffSpec, ResearchMatch, ResearchOddsQuote
from jc.research.contracts import (
    ResearchImport,
    ResearchRawArtifactInput,
    ResearchRecordProvenance,
    ResearchSourceInput,
    content_hash,
    validate_import,
)
from jc.research.pilot import assess_intake_gates
from jc.time import parse_time

CUTOFFS = (360, 90, 30, 15, 5)
POLICY = "oddspapi-same-instant-latest-1x2-v1"


def _body(raw: ResearchRawArtifactInput, endpoint: str):
    url = urlsplit(raw.external_ref or "")
    if (raw.source_name != "oddspapi" or (url.scheme, url.hostname, url.path) !=
            ("https", "api.oddspapi.io", f"/v4/{endpoint}") or
            raw.metadata.get("http_status") != 200 or raw.metadata.get("retention") != "UNCHANGED"):
        raise ValueError("Successful unchanged OddsPapi Raw bound to endpoint required")
    if not isinstance(raw.payload, str):
        raise ValueError("Preserve the actual HTTP response text")
    return json.loads(raw.payload, parse_float=Decimal), parse_qs(url.query)


def audit_oddspapi(raws: tuple[ResearchRawArtifactInput, ...], match: ResearchMatch, identity: dict) -> dict:
    """Inspect a manually reviewed identity and literal history; no source attestation here."""
    metadata = {}
    for endpoint in ("fixtures", "markets", "bookmakers"):
        found = [r for r in raws if r.artifact_type == f"ODDSPAPI_{endpoint.upper()}"]
        if len(found) != 1:
            raise ValueError("Exactly one preserved fixture/market/bookmaker catalogue required")
        metadata[endpoint], _ = _body(found[0], endpoint)
        if not isinstance(metadata[endpoint], list) or any(not isinstance(r, dict) for r in metadata[endpoint]):
            raise ValueError("Metadata catalogue must be an array of objects")
    expected = identity["provider_fields"]
    required = {"fixtureId", "participant1Id", "participant2Id", "participant1Name", "participant2Name",
                "sportId", "sportName", "tournamentId", "tournamentName", "categoryName"}
    if set(expected) != required or any(v is None or v == "" for v in expected.values()):
        raise ValueError("Explicit ordered teams, stable IDs, sport and competition review required")
    if (identity["canonical"] != {"sporttery_match_id": match.sporttery_match_id,
                                 "home_team_id": match.home_team_id, "away_team_id": match.away_team_id}
            or expected["sportId"] != 10 or expected["participant1Id"] == expected["participant2Id"]):
        raise ValueError("Canonical target identity mismatch")
    fixtures = [f for f in metadata["fixtures"] if f.get("fixtureId") == expected["fixtureId"]]
    if (len(fixtures) != 1 or any(fixtures[0].get(k) != v for k, v in expected.items())
            or parse_time(fixtures[0]["startTime"]) != match.kickoff_at):
        raise ValueError("Reviewed fixture identity/kickoff mismatch")
    markets = [m for m in metadata["markets"] if m.get("sportId") == 10
               and m.get("marketType") == "1x2" and m.get("period") == "fulltime"
               and m.get("handicap") == 0 and m.get("playerProp") is False and m.get("marketLength") == 3]
    if len(markets) != 1:
        raise ValueError("Unique full-time three-way market required")
    market = markets[0]
    labels = {"1": "HOME", "X": "DRAW", "2": "AWAY"}
    outcomes = market.get("outcomes")
    if (not isinstance(outcomes, list) or len(outcomes) != 3
            or {o.get("outcomeName") for o in outcomes} != set(labels)
            or len({o.get("outcomeId") for o in outcomes}) != 3):
        raise ValueError("Explicit HOME/DRAW/AWAY outcome catalogue required")
    selections = {str(o["outcomeId"]): labels[o["outcomeName"]] for o in outcomes}
    catalogue = {b.get("slug"): b for b in metadata["bookmakers"]}
    if len(catalogue) != len(metadata["bookmakers"]):
        raise ValueError("Duplicate bookmaker identity")
    groups: dict = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    requested: dict = defaultdict(set)
    for raw in raws:
        if raw.artifact_type != "ODDSPAPI_HISTORY":
            continue
        body, query = _body(raw, "historical-odds")
        raw_hash = raw.content_hash
        oid = query.get("outcomeId", [None])[0]
        if (query.get("fixtureId") != [expected["fixtureId"]] or oid not in selections
                or len(query.get("outcomeId", [])) != 1
                or set(query) - {"fixtureId", "bookmakers", "outcomeId"}
                or len(query.get("bookmakers", [])) != 1):
            raise ValueError("Unfiltered full outcome history for this fixture required")
        books = query["bookmakers"][0].split(",")
        if len(set(books)) != len(books) or not 1 <= len(books) <= 3:
            raise ValueError("Invalid bookmaker request binding")
        for book in books:
            if book not in catalogue or catalogue[book].get("cloneOf") is not None:
                raise ValueError("Real non-clone bookmaker catalogue identity required")
            if oid in requested[book]:
                raise ValueError("Duplicate acquisition of the same bookmaker/outcome")
            requested[book].add(oid)
        if (not isinstance(body, dict) or body.get("fixtureId") != expected["fixtureId"]
                or not isinstance(body.get("bookmakers"), dict) or set(body["bookmakers"]) - set(books)):
            raise ValueError("Historical response identity mismatch")
        for book, b in body["bookmakers"].items():
            m = b.get("markets", {})
            if not m:  # Empty history is evidence of no data, not a fabricated quote.
                continue
            if set(m) != {str(market["marketId"])}:
                raise ValueError("Unexpected market in outcome-filtered response")
            entries = m[str(market["marketId"])].get("outcomes", {})
            if set(entries) != {oid} or set(entries[oid].get("players", {})) != {"0"}:
                raise ValueError("Unexpected outcome/player in historical response")
            rows = entries[oid]["players"]["0"]
            if not isinstance(rows, list):
                raise ValueError("Historical outcome must be an array")
            for index, row in enumerate(rows):
                if not isinstance(row, dict) or type(row.get("active")) is not bool:
                    raise ValueError("Historical row requires an explicit active flag")
                stamp = parse_time(row["createdAt"])
                if stamp > raw.retrieved_at:
                    raise ValueError("Historical snapshot cannot follow retrieval")
                try:
                    if type(row.get("price")) not in (int, Decimal):
                        raise ValueError("Numeric decimal price required")
                    price = Decimal(row["price"])
                    if not price.is_finite() or price <= 0:
                        raise ValueError("Finite positive recorded price required")
                except InvalidOperation as exc:
                    raise ValueError("Invalid recorded price") from exc
                groups[book][stamp][selections[oid]].append({
                    "price": str(price), "active": row["active"], "raw_content_hash": raw_hash,
                    "raw_path": f"$.bookmakers.{book}.markets.{market['marketId']}.outcomes.{oid}.players.0[{index}]",
                })
    if not requested or any(oids != set(selections) for oids in requested.values()):
        raise ValueError("All three unfiltered outcome histories must be acquired for each bookmaker")

    def complete(group):
        return (set(group) == set(labels.values()) and all(len(rows) == 1 and rows[0]["active"]
                and Decimal(rows[0]["price"]) > 1 for rows in group.values()))

    audit: dict = {"policy": POLICY, "fixture_id": expected["fixtureId"], "market_id": str(market["marketId"]),
                  "outcome_mapping": selections, "books": {}, "cutoffs": {}}
    for book in sorted(requested):
        observations = groups[book]
        audit["books"][book] = {
            "history_entry_count": sum(len(rows) for g in observations.values() for rows in g.values()),
            "prematch_entry_count": sum(len(rows) for t, g in observations.items() if t < match.kickoff_at for rows in g.values()),
            "timestamp_groups": len(observations),
            "complete_prematch_groups": sum(complete(g) for t, g in observations.items() if t < match.kickoff_at),
        }
    for minutes in CUTOFFS:
        cutoff = ReplayCutoffSpec(minutes).at(match.kickoff_at)
        per_book = {}
        for book in sorted(requested):
            observations = groups[book]
            latest = max((t for t in observations if t <= cutoff), default=None)
            group = observations[latest] if latest is not None else {}
            reason = ("NO_DATA" if latest is None else "INCOMPLETE_SNAPSHOT" if set(group) != set(labels.values())
                      else "DUPLICATE_SNAPSHOT" if any(len(rows) != 1 for rows in group.values())
                      else "INACTIVE_OR_INVALID_PRICE" if not complete(group) else None)
            per_book[book] = {"timestamp": latest.isoformat() if latest else None,
                              "status": "PASS" if reason is None else "BLOCKED", "reason": reason,
                              "present_selections": sorted(group),
                              "rows": {k: v[0] for k, v in group.items()} if reason is None else {}}
        audit["cutoffs"][str(minutes)] = {"cutoff": cutoff.isoformat(), "bookmakers": per_book}
    return audit


def _records(audit: dict, match: ResearchMatch):
    quotes, provenance = {}, {}
    eligible: dict[str, set[str]] = {}
    for minutes, cutoff in audit["cutoffs"].items():
        eligible[minutes] = set()
        for book, group in cutoff["bookmakers"].items():
            for selection, row in group["rows"].items():
                rid = f"oddspapi:{audit['fixture_id']}:{book}:{audit['market_id']}:{group['timestamp']}:{selection}"
                quotes[rid] = ResearchOddsQuote(
                    record_id=rid, research_match_id=match.research_match_id, provider="oddspapi",
                    bookmaker=f"oddspapi:{book}", market_type="1X2", selection=selection, line=None,
                    decimal_odds=Decimal(row["price"]), replay_available_at=parse_time(group["timestamp"]),
                    availability_basis=AvailabilityBasis.SOURCE_SNAPSHOT_AT,
                )
                provenance[rid] = ResearchRecordProvenance(record_type="ODDS", record_id=rid,
                    source_name="oddspapi", raw_content_hash=row["raw_content_hash"])
                eligible[minutes].add(rid)
    return quotes, provenance, eligible


def build_oddspapi_import(base: ResearchImport, *, raws: tuple[ResearchRawArtifactInput, ...],
                         identity: dict, source: ResearchSourceInput, dataset_version: str) -> ResearchImport:
    """Requires explicit human/agent-reviewed source declarations, never promotes HTTP 200."""
    base = validate_import(base)
    if (len(base.dataset.matches) != 1 or base.dataset.results
            or any(q.provider != "sporttery" for q in base.dataset.odds)
            or assess_intake_gates(base)["gates"]["A"] != "PASS"):
        raise ValueError("One verified official target, official quotes only and zero Results required")
    if (source.source.source_name != "oddspapi" or source.provider_name != "oddspapi"
            or source.source.source_type != "EXTERNAL_ODDS_HISTORY" or source.verification_status != "VERIFIED"):
        raise ValueError("Explicit VERIFIED historical source with reviewed time, identity and license required")
    match = base.dataset.matches[0]
    audit = audit_oddspapi(raws, match, identity)
    quotes, provenance, _ = _records(audit, match)
    if not quotes:
        raise ValueError("No qualified complete snapshot at the requested cutoffs")
    return validate_import(replace(base,
        dataset=replace(base.dataset, dataset_version=dataset_version,
                        odds=(*base.dataset.odds, *quotes.values()),
                        source_manifest=(*base.dataset.source_manifest, source.source)),
        description="Single verified Sporttery target with qualified same-instant OddsPapi 1X2 snapshots",
        sources=(*base.sources, source), raw_artifacts=(*base.raw_artifacts, *raws),
        provenance=(*base.provenance, *provenance.values()),
        manifest={**base.manifest, "oddspapi_qualification": {"identity": identity, "policy": POLICY,
                  "audit_hash": content_hash(audit), "cutoff_minutes": list(CUTOFFS)}},
    ))


def assess_oddspapi_intake(value: ResearchImport) -> dict:
    """Re-audit preserved history before each fixed cutoff; never carry older snapshots forward.

Call this for this provider's admission/replay, including after D2A reload.
Bare replay-v1 selects per quote series and cannot enforce whole-snapshot scope.
"""
    value = validate_import(value)
    policy = value.manifest["oddspapi_qualification"]
    if policy["policy"] != POLICY or policy["cutoff_minutes"] != list(CUTOFFS) or len(value.dataset.matches) != 1:
        raise ValueError("Unexpected OddsPapi admission policy")
    match = value.dataset.matches[0]
    audit = audit_oddspapi(tuple(r for r in value.raw_artifacts if r.source_name == "oddspapi"), match, policy["identity"])
    quotes, provenance, eligible = _records(audit, match)
    if (content_hash(audit) != policy["audit_hash"] or
            {q.record_id: q for q in value.dataset.odds if q.provider == "oddspapi"} != quotes or
            {p.record_id: p for p in value.provenance if p.source_name == "oddspapi"} != provenance):
        raise ValueError("Raw, qualification, normalized quotes and provenance must agree")
    reports = {}
    for minutes in CUTOFFS:
        odds = tuple(q for q in value.dataset.odds if q.provider == "sporttery" or q.record_id in eligible[str(minutes)])
        ids = {q.record_id for q in odds}
        filtered = replace(value, dataset=replace(value.dataset, odds=odds),
                           provenance=tuple(p for p in value.provenance if p.record_type != "ODDS" or p.record_id in ids))
        reports[str(minutes)] = assess_intake_gates(filtered, cutoff_minutes=(minutes,))
    return {"audit": audit, "cutoff_markets": {m: r["cutoff_markets"][m] for m, r in reports.items()},
            "cutoff_coverage": {m: r["cutoff_coverage"][m] for m, r in reports.items()},
            "gates": {"A": reports["360"]["gates"]["A"],
                      "B": "PASS" if any(r["gates"]["B"] == "PASS" for r in reports.values()) else "BLOCKED"}}
