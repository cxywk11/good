"""Persistence evidence around the unchanged research-replay-v1 contracts."""

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field, is_dataclass, replace
from datetime import datetime
from decimal import Decimal
from typing import Any
from urllib.parse import parse_qsl, unquote, urlsplit

from jc.analysis.research_replay import ResearchDataset, ResearchSource
from jc.time import as_utc


def decimal_text(value: Decimal) -> str:
    # No normalize(): that would round under the caller's Decimal context.
    text = format(value, "f")
    return (text.rstrip("0").rstrip(".") if "." in text else text) if value else "0"


def _canonical_value(value):
    if isinstance(value, datetime):
        return as_utc(value).isoformat()
    if isinstance(value, Decimal) and value.is_finite():
        return decimal_text(value)
    if is_dataclass(value) and not isinstance(value, type):
        return _canonical_value(asdict(value))
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise ValueError("Canonical object keys must be strings")
        return {key: _canonical_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_canonical_value(item) for item in value]
    if isinstance(value, float) and value.is_integer():
        # JSONB can expand exponent notation into integers. Canonicalize those
        # identically without introducing binary-float digits into the hash.
        return int(Decimal(str(value)))
    return value


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        _canonical_value(value),
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def content_hash(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _secret_key(key: str) -> bool:
    key = re.sub(r"[^a-z0-9]", "", key.lower())
    return any(
        word in key for word in ("apikey", "authorization", "cookie", "password", "passwd", "token", "secret")
    )


def reject_secrets(value: Any) -> None:
    """Reject, never log/echo sensitive values, including nested metadata and URLs."""
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str) or _secret_key(key):
                raise ValueError("Research input contains a prohibited metadata field")
            reject_secrets(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            reject_secrets(item)
    elif isinstance(value, str):
        decoded = unquote(value)
        if re.search(
            r"(?i)(?:bearer\s+\S+|(?:api[_ -]?key|authorization|cookies?|password|passwd|"
            r"(?:access[_ -]?|refresh[_ -]?)?token|secret)[\"']?\s*[:=]\s*\S+)",
            decoded,
        ):
            raise ValueError("Research input contains credential-like text")
        if "://" in decoded:
            for candidate in re.findall(r"\S+://\S+", decoded):
                url = urlsplit(candidate)
                if (
                    url.username is not None
                    or url.password is not None
                    or any(_secret_key(key) for key, _ in parse_qsl(url.query))
                ):
                    raise ValueError("Research URL contains credentials")


@dataclass(frozen=True, kw_only=True)
class ResearchSourceInput:
    source: ResearchSource
    provider_name: str
    license_note: str
    base_url: str | None = None
    verification_status: str = "UNVERIFIED"
    verified_at: datetime | None = None
    verification_note: str | None = None

    def __post_init__(self):
        replace(self.source)  # Revalidate the frozen D1 contract.
        if not self.provider_name.strip() or not self.license_note.strip():
            raise ValueError("Provider and license declaration are required")
        if self.verification_status not in ("UNVERIFIED", "VERIFIED", "REJECTED"):
            raise ValueError("Invalid source verification status")
        if self.verified_at is not None:
            object.__setattr__(self, "verified_at", as_utc(self.verified_at))
        if self.verification_status == "VERIFIED" and (
            self.verified_at is None or not self.verification_note or not self.verification_note.strip()
        ):
            raise ValueError("Explicit source verification time and note required")
        if self.source.source_type == "SYNTHETIC_FIXTURE" and self.verification_status != "UNVERIFIED":
            raise ValueError("Synthetic fixture sources must remain UNVERIFIED")
        reject_secrets(asdict(self))


@dataclass(frozen=True, kw_only=True)
class ResearchRawArtifactInput:
    source_name: str
    artifact_type: str
    retrieved_at: datetime
    content_type: str
    payload: Any
    external_ref: str | None = None
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        for value in (self.source_name, self.artifact_type, self.content_type):
            if not isinstance(value, str) or not value.strip():
                raise ValueError("Raw artifact identity is required")
        object.__setattr__(self, "retrieved_at", as_utc(self.retrieved_at))
        # Raw payload must be JSON or text, not arbitrary Python/ORM objects.
        for name in ("payload", "metadata"):
            encoded = json.dumps(getattr(self, name), sort_keys=True, ensure_ascii=False, allow_nan=False)
            object.__setattr__(self, name, json.loads(encoded))
        if self.payload is None or not isinstance(self.metadata, dict):
            raise ValueError("Raw payload and metadata object required")
        reject_secrets(asdict(self))

    @property
    def content_hash(self) -> str:
        return content_hash(self.payload)


@dataclass(frozen=True, kw_only=True)
class ResearchRecordProvenance:
    record_type: str  # MATCH / ODDS / RESULT
    record_id: str
    source_name: str
    raw_content_hash: str


@dataclass(frozen=True, kw_only=True)
class SportteryVerificationInput:
    research_match_id: str
    status: str = "UNVERIFIED"
    artifact_source_name: str | None = None
    artifact_content_hash: str | None = None


@dataclass(frozen=True, kw_only=True)
class ResearchImport:
    dataset: ResearchDataset
    description: str
    manifest: dict
    sources: tuple[ResearchSourceInput, ...]
    raw_artifacts: tuple[ResearchRawArtifactInput, ...]
    provenance: tuple[ResearchRecordProvenance, ...]
    sporttery_verifications: tuple[SportteryVerificationInput, ...] = ()


def validate_import(value: ResearchImport) -> ResearchImport:
    """Validate the complete content, keeping v1 validation as the semantic authority."""
    ds = replace(
        value.dataset,
        matches=tuple(replace(row) for row in value.dataset.matches),
        odds=tuple(replace(row) for row in value.dataset.odds),
        results=tuple(replace(row) for row in value.dataset.results),
        source_manifest=tuple(replace(row) for row in value.dataset.source_manifest),
    )
    sources = {s.source.source_name: replace(s) for s in value.sources}
    if len(sources) != len(value.sources) or {s.source for s in sources.values()} != set(ds.source_manifest):
        raise ValueError("Source definitions must exactly match source_manifest")
    if not isinstance(value.manifest, dict):
        raise ValueError("Dataset manifest must be an object")
    raw: dict[tuple[str, str], ResearchRawArtifactInput] = {}
    for original in value.raw_artifacts:
        artifact = replace(original)
        if artifact.source_name not in sources:
            raise ValueError("Raw source missing from manifest")
        key = artifact.source_name, artifact.content_hash
        if key in raw and raw[key] != artifact:
            raise ValueError("Same raw hash has conflicting artifact metadata")
        raw[key] = artifact
    records = {("MATCH", m.research_match_id): m.source for m in ds.matches}
    records.update({("ODDS", q.record_id): q.provider for q in ds.odds})
    records.update({("RESULT", r.record_id): r.source for r in ds.results})
    provenance = {(p.record_type, p.record_id): p for p in value.provenance}
    if len(provenance) != len(value.provenance) or provenance.keys() != records.keys():
        raise ValueError("Exactly one raw provenance link is required for every normalized record")
    for key, source_name in records.items():
        p = provenance[key]
        if p.source_name != source_name or (p.source_name, p.raw_content_hash) not in raw:
            raise ValueError("Raw artifact must belong to the record's dataset and source")
    matches_by_id = {m.research_match_id: m for m in ds.matches}
    verification = {v.research_match_id: v for v in value.sporttery_verifications}
    if len(verification) != len(value.sporttery_verifications) or verification.keys() - matches_by_id.keys():
        raise ValueError("Duplicate or unknown sporttery verification match")
    for mid, match in matches_by_id.items():
        v = verification.setdefault(mid, SportteryVerificationInput(research_match_id=mid))
        if v.status not in ("UNVERIFIED", "VERIFIED", "REJECTED"):
            raise ValueError("Invalid sporttery verification status")
        if (v.artifact_source_name is None) != (v.artifact_content_hash is None):
            raise ValueError("Incomplete sporttery artifact identity")
        evidence = raw.get((v.artifact_source_name or "", v.artifact_content_hash or ""))
        if v.artifact_source_name is not None and evidence is None:
            raise ValueError("Sporttery artifact missing from dataset")
        if v.status != "VERIFIED":
            continue
        if evidence is None or not match.sporttery_match_id:
            raise ValueError("VERIFIED sporttery target requires official raw evidence")
        source = sources[evidence.source_name]
        if (
            source.source.source_type != "OFFICIAL_SPORTTERY_HISTORY"
            or source.provider_name != "sporttery"
            or source.verification_status != "VERIFIED"
            or evidence.artifact_type != "SPORTTERY_POOL"
        ):
            raise ValueError("Sporttery verification requires an explicitly verified official source")
        # This is an explicit verifier's attestation tied to the preserved raw, not an inferred ID.
        expected = {
            "sporttery_match_id": match.sporttery_match_id,
            "home_team_id": match.home_team_id,
            "away_team_id": match.away_team_id,
            "kickoff_at": match.kickoff_at.isoformat(),
        }
        if (
            match.home_team_id is None
            or match.away_team_id is None
            or (evidence.metadata.get("sporttery_pool_evidence") != expected)
        ):
            raise ValueError("Official raw evidence must identify this match, teams and kickoff")
    result = replace(
        value,
        dataset=ds,
        manifest=json.loads(json.dumps(value.manifest, allow_nan=False)),
        sources=tuple(sources[k] for k in sorted(sources)),
        raw_artifacts=tuple(raw[k] for k in sorted(raw)),
        provenance=tuple(provenance[k] for k in sorted(provenance)),
        sporttery_verifications=tuple(verification[k] for k in sorted(verification)),
    )
    reject_secrets(asdict(result))
    canonical_bytes(result)
    return result


def dataset_content_hash(value: ResearchImport) -> str:
    value = validate_import(value)
    # Natural record identities are content; storage UUIDs, lifecycle clocks and
    # dataset key/version labels are not. Arrays representing sets are sorted above.
    return content_hash(
        {
            "hash_format": "research-content-v1",
            "replay_version": value.dataset.replay_version,
            "description": value.description,
            "manifest": value.manifest,
            "source_manifest": value.dataset.source_manifest,
            "sources": value.sources,
            "matches": value.dataset.matches,
            "odds": value.dataset.odds,
            "results": value.dataset.results,
            "raw_artifacts": [{**asdict(a), "content_hash": a.content_hash} for a in value.raw_artifacts],
            "provenance": value.provenance,
            "sporttery_verifications": value.sporttery_verifications,
        }
    )
