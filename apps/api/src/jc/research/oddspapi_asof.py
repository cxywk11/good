"""Reviewed OddsPapi as-of admission, independent of immutable same-instant V1."""

from collections import defaultdict
from dataclasses import replace
from decimal import Decimal
from urllib.parse import urlsplit

from jc.analysis.market import build_market_data
from jc.analysis.research_replay import (
    AvailabilityBasis,
    ReplayCutoffSpec,
    ResearchMatch,
    ResearchOddsQuote,
    build_research_feature,
)
from jc.research.contracts import (
    ResearchImport,
    ResearchRawArtifactInput,
    ResearchRecordProvenance,
    ResearchSourceInput,
    content_hash,
    validate_import,
)
from jc.research.oddspapi import CUTOFFS, _body, audit_oddspapi
from jc.research.pilot import assess_intake_gates
from jc.time import parse_time

POLICY = "oddspapi-asof-outcome-state-v2"
VERSION = "2041790-external-1x2-asof-v2"


def _review(semantics: dict) -> None:
    if (semantics.get("status") != "VERIFIED" or semantics.get("policy") != POLICY
            or not semantics.get("review_note") or not semantics.get("evidence")
            or not semantics.get("bookmakers")
            or len(set(semantics["bookmakers"])) != len(semantics["bookmakers"])):
        raise ValueError("Explicit reviewed as-of semantics and bookmaker scope required")
    parse_time(semantics["reviewed_at"])
    for evidence in semantics["evidence"]:
        url = urlsplit(evidence["url"])
        digest = evidence["response_sha256"]
        if (url.scheme != "https" or url.hostname != "oddspapi.io"
                or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest)):
            raise ValueError("Official semantics evidence URL and response hash required")


def audit_oddspapi_asof(raws: tuple[ResearchRawArtifactInput, ...], match: ResearchMatch,
                       identity: dict, semantics: dict) -> dict:
    _review(semantics)
    # Reuse the frozen trust-boundary validator, not its same-instant selection.
    v1 = audit_oddspapi(raws, match, identity)
    if set(v1["books"]) != set(semantics["bookmakers"]):
        raise ValueError("Bookmaker scope differs from the reviewed source")
    history: dict = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    for raw in raws:
        if raw.artifact_type != "ODDSPAPI_HISTORY":
            continue
        body, _ = _body(raw, "historical-odds")
        digest = raw.content_hash
        for book, value in body["bookmakers"].items():
            markets = value.get("markets", {})
            if not markets:
                continue
            for oid, outcome in markets[v1["market_id"]]["outcomes"].items():
                selection = v1["outcome_mapping"][oid]
                for index, row in enumerate(outcome["players"]["0"]):
                    ref = {"source_raw_hash": digest,
                           "source_raw_path": f"$.bookmakers.{book}.markets.{v1['market_id']}.outcomes.{oid}.players.0[{index}]"}
                    history[book][selection][parse_time(row["createdAt"])].append((row, ref))
    audit: dict = {"policy": POLICY, "fixture_id": v1["fixture_id"], "market_id": v1["market_id"],
                  "semantics_hash": content_hash(semantics), "books": {}, "cutoffs": {}}
    for book in sorted(v1["books"]):
        groups = [rows for series in history[book].values() for rows in series.values()]
        audit["books"][book] = {
            "history_entry_count": v1["books"][book]["history_entry_count"],
            "inactive_entry_count": sum(not row["active"] for rows in groups for row, _ in rows),
            "conflicting_state_groups": sum(len({content_hash(row) for row, _ in rows}) > 1 for rows in groups),
            "identical_duplicate_rows": sum(len(rows) - len({content_hash(row) for row, _ in rows}) for rows in groups),
        }
    for minutes in CUTOFFS:
        cutoff = ReplayCutoffSpec(minutes).at(match.kickoff_at)
        books = {}
        for book in sorted(v1["books"]):
            states = {}
            for selection in ("HOME", "DRAW", "AWAY"):
                series = history[book][selection]
                stamp = max((t for t in series if t <= cutoff), default=None)
                rows = series[stamp] if stamp is not None else []
                conflict = len({content_hash(row) for row, _ in rows}) > 1
                state = {"selection": selection, "status": "BLOCKED", "reason": "NO_DATA",
                         "price": None, "active": None, "original_created_at": None,
                         "source_created_at": None, "source_raw_hash": None, "source_raw_path": None,
                         "raw_references": [ref for _, ref in rows], "identical_duplicate_count": 0}
                if conflict:
                    state["reason"] = "CONFLICTING_STATE"
                elif rows:
                    assert stamp is not None
                    row, ref = rows[0]
                    reason = ("NOT_PREMATCH" if stamp >= match.kickoff_at else "INACTIVE" if not row["active"]
                              else "INVALID_PRICE" if row["price"] <= 1 else None)
                    state.update(price=str(row["price"]), active=row["active"],
                                 original_created_at=row["createdAt"], source_created_at=row["createdAt"],
                                 **ref, identical_duplicate_count=len(rows) - 1,
                                 status="PASS" if reason is None else "BLOCKED", reason=reason)
                states[selection] = state
            books[book] = {"market_state_asof": cutoff.isoformat(), "outcomes": states,
                           "market_state_status": "PASS" if all(s["status"] == "PASS" for s in states.values()) else "BLOCKED"}
        audit["cutoffs"][str(minutes)] = {"market_state_asof": cutoff.isoformat(), "bookmakers": books}
    return audit


def _records(audit: dict, match: ResearchMatch):
    quotes, provenance = {}, {}
    eligible: dict[str, set[str]] = {}
    for minutes, cutoff in audit["cutoffs"].items():
        eligible[minutes] = set()
        for book, group in cutoff["bookmakers"].items():
            if group["market_state_status"] != "PASS":
                continue
            for selection, state in group["outcomes"].items():
                stamp = parse_time(state["original_created_at"])
                rid = f"oddspapi-asof-v2:{audit['fixture_id']}:{book}:{audit['market_id']}:{selection}:{stamp.isoformat()}"
                quotes[rid] = ResearchOddsQuote(
                    record_id=rid, research_match_id=match.research_match_id, provider="oddspapi",
                    bookmaker=f"oddspapi:{book}", market_type="1X2", selection=selection, line=None,
                    decimal_odds=Decimal(state["price"]), replay_available_at=stamp,
                    availability_basis=AvailabilityBasis.SOURCE_SNAPSHOT_AT,
                )
                provenance[rid] = ResearchRecordProvenance(record_type="ODDS", record_id=rid,
                    source_name="oddspapi", raw_content_hash=state["source_raw_hash"])
                eligible[minutes].add(rid)
    return quotes, provenance, eligible


def _source(source: ResearchSourceInput) -> None:
    if (source.source.source_name != "oddspapi" or source.provider_name != "oddspapi"
            or source.source.source_type != "EXTERNAL_ODDS_HISTORY" or source.verification_status != "VERIFIED"):
        raise ValueError("Explicit VERIFIED OddsPapi source required")


def build_oddspapi_asof_import(base: ResearchImport, *, raws: tuple[ResearchRawArtifactInput, ...],
                              identity: dict, semantics: dict, source: ResearchSourceInput,
                              dataset_version: str = VERSION) -> ResearchImport:
    base = validate_import(base)
    if (len(base.dataset.matches) != 1 or base.dataset.results
            or any(q.provider != "sporttery" for q in base.dataset.odds)
            or assess_intake_gates(base)["gates"]["A"] != "PASS"
            or dataset_version == base.dataset.dataset_version or dataset_version.endswith("-v1")):
        raise ValueError("Independent V2 version of one verified official target with zero Results required")
    _source(source)
    audit = audit_oddspapi_asof(raws, base.dataset.matches[0], identity, semantics)
    quotes, provenance, _ = _records(audit, base.dataset.matches[0])
    if not quotes:
        raise ValueError("No complete qualified as-of market at any fixed cutoff")
    return validate_import(replace(base,
        dataset=replace(base.dataset, dataset_version=dataset_version, odds=(*base.dataset.odds, *quotes.values()),
                        source_manifest=(*base.dataset.source_manifest, source.source)),
        description="Single verified Sporttery target with separately qualified OddsPapi as-of 1X2 states",
        sources=(*base.sources, source), raw_artifacts=(*base.raw_artifacts, *raws),
        provenance=(*base.provenance, *provenance.values()),
        manifest={**base.manifest, "oddspapi_asof_v2": {
            "policy": POLICY, "identity": identity, "semantics": semantics, "cutoff_minutes": list(CUTOFFS),
            "source_hash": content_hash(source), "audit_hash": content_hash(audit), "audit": audit,
        }},
    ))


def assess_oddspapi_asof_intake(value: ResearchImport) -> dict:
    """Rebuild all selected states from Raw; preserve original per-outcome availability."""
    value = validate_import(value)
    policy = value.manifest["oddspapi_asof_v2"]
    if (policy["policy"] != POLICY or policy["cutoff_minutes"] != list(CUTOFFS)
            or len(value.dataset.matches) != 1 or value.dataset.results
            or any(q.provider not in ("sporttery", "oddspapi") for q in value.dataset.odds)
            or assess_intake_gates(value)["gates"]["A"] != "PASS"):
        raise ValueError("Unexpected as-of V2 scope")
    source = next(s for s in value.sources if s.source.source_name == "oddspapi")
    _source(source)
    match = value.dataset.matches[0]
    audit = audit_oddspapi_asof(tuple(r for r in value.raw_artifacts if r.source_name == "oddspapi"),
                              match, policy["identity"], policy["semantics"])
    quotes, provenance, eligible = _records(audit, match)
    if (content_hash(source) != policy["source_hash"] or content_hash(audit) != policy["audit_hash"]
            or content_hash(policy["audit"]) != policy["audit_hash"]
            or {q.record_id: q for q in value.dataset.odds if q.provider == "oddspapi"} != quotes
            or {p.record_id: p for p in value.provenance if p.source_name == "oddspapi"} != provenance):
        raise ValueError("Raw, as-of manifest, source, quotes and provenance must agree")
    markets, coverage = {}, {}
    for minutes in CUTOFFS:
        key = str(minutes)
        odds = tuple(q for q in value.dataset.odds if q.provider == "sporttery" or q.record_id in eligible[key])
        # V1 admission enforces common timestamps; V2 has already audited the asynchronous state.
        feature = build_research_feature(replace(value.dataset, odds=odds), match.research_match_id,
                                         ReplayCutoffSpec(minutes))
        market = build_market_data(feature)
        markets[key] = {match.research_match_id: market}
        consensus = market["external_consensus"]
        coverage[key] = int(consensus["source_count"] >= 1 and consensus["p_market"] is not None)
    return {"audit": audit, "cutoff_markets": markets, "cutoff_coverage": coverage,
            "gates": {"A": "PASS", "B": "PASS" if any(coverage.values()) else "BLOCKED"}}
