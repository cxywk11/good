"""Opt-in, single-request discovery with durable, secret-checked Raw first.

HTTP success is access evidence only, never official-pool verification.
No retries, redirects, WAF workarounds, or normalization happen here.
"""

import hashlib
import json
import os
import re
from dataclasses import asdict
from pathlib import Path
from urllib.parse import parse_qsl, quote, quote_plus, urlencode, urljoin, urlsplit, urlunsplit
from uuid import uuid4

import httpx

from jc.research.contracts import ResearchRawArtifactInput, canonical_bytes, reject_secrets
from jc.research.providers.inspection import inspect_odds_history_payload
from jc.time import parse_time, utcnow


def public_url(url: str) -> str:
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
        raise ValueError("Discovery requires HTTPS without embedded credentials")
    query = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        try:
            reject_secrets({key: value})
        except ValueError:
            continue
        if key.lower() != "key":
            query.append((key, value))
    result = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))
    reject_secrets(result)
    return result


def _scrub(body: str, confidential_values: tuple[str, ...]) -> tuple[str, str]:
    original = body
    for value in confidential_values:
        if value:
            body = body.replace(value, "[redacted]")
    body = re.sub(
        r"(?i)(?:api[_ -]?key|authorization|cookies?|password|passwd|"
        r"(?:access[_ -]?|refresh[_ -]?)?token|secret)[\"']?\s*[:=]\s*"
        r"(?:\"[^\"]*\"|'[^']*'|[^\s&,<>}]+)",
        "[credential redacted]",
        body,
    )
    try:
        reject_secrets(body)
    except ValueError:
        return "[response withheld by D2A secret guard]", "WITHHELD"
    return body, "REDACTED" if body != original else "UNCHANGED"


def _save(output: Path, value: dict) -> Path:
    reject_secrets(value)
    output.mkdir(parents=True, exist_ok=True)
    path = output / f"{utcnow():%Y%m%dT%H%M%S%fZ}-{uuid4().hex}.json"
    with path.open("xb") as stream:
        stream.write(canonical_bytes(value))
        stream.flush()
        os.fsync(stream.fileno())
    return path


def record_blocked(output: Path, source: str, url: str, reason: str) -> dict:
    """Configuration failure has no HTTP response or response hash to invent."""
    summary: dict = {
        "source": source,
        "status": "BLOCKED",
        "reason": reason,
        "timestamp": utcnow().isoformat(),
        "url": public_url(url),
        "http_status": None,
        "response_sha256": None,
        "raw_content_hash": None,
        "field_coverage": [],
        "sporttery_verification_status": "UNVERIFIED",
        "scan_status": "PASS",
    }
    path = _save(output, {"source_probe": summary, "raw": None})
    return {**summary, "probe_path": str(path)}


def probe_source(
    output: Path,
    source: str,
    url: str,
    *,
    params: dict | None = None,
    confidential_values: tuple[str, ...] = (),
    transport: httpx.BaseTransport | None = None,
) -> dict:
    if not isinstance(transport, httpx.MockTransport) and os.environ.get("RESEARCH_NETWORK_ENABLED") != "1":
        raise RuntimeError("Set RESEARCH_NETWORK_ENABLED=1 for real source requests")
    public_url(url)  # Validate before issuing any request.
    reject_secrets(source)
    confidential = list(confidential_values)
    for key, value in [*parse_qsl(urlsplit(url).query), *(params or {}).items()]:
        try:
            reject_secrets({key: value})
            if key.lower() != "key":
                continue
        except ValueError:
            pass
        if value:
            confidential.extend((str(value), quote(str(value), safe=""), quote_plus(str(value))))
    try:
        with httpx.Client(timeout=25, follow_redirects=False, transport=transport) as client:
            response = client.get(url, params=params)
    except httpx.RequestError as exc:
        # Exception text may contain a credential-bearing request URL.
        return record_blocked(output, source, url, type(exc).__name__)
    retrieved_at = utcnow()
    # Official static JS is sometimes GB18030 without a charset header. Never
    # preserve a lossy replacement-character decode as if it were the original.
    encoding = response.encoding or "utf-8"
    try:
        decoded = response.content.decode(encoding)
    except (UnicodeError, LookupError):
        encoding = "gb18030"
        try:
            decoded = response.content.decode(encoding)
        except UnicodeError:
            encoding = "undecodable"
            decoded = "[non-text response withheld]"
    body, retention = _scrub(decoded, tuple(confidential))
    if encoding == "undecodable":
        retention = "WITHHELD"
    media_type = response.headers.get("content-type", "").split(";", 1)[0].strip()
    if not re.fullmatch(r"[\w.+-]+/[\w.+-]+", media_type):
        media_type = "application/octet-stream"
    raw = ResearchRawArtifactInput(
        source_name=source,
        artifact_type="SOURCE_PROBE",
        retrieved_at=retrieved_at,
        content_type=media_type,
        payload=body,
        external_ref=public_url(str(response.url)),
        metadata={
            "http_status": response.status_code,
            "response_sha256": hashlib.sha256(response.content).hexdigest(),
            "retention": retention,
            "text_encoding": encoding,
            "published_at": None,
            "effective_at": None,
            "replay_available_at": None,
            "availability_basis": None,
        },
    )
    location = response.headers.get("location")
    if location:
        try:
            raw.metadata["redirect_location"] = public_url(urljoin(str(response.url), location))
        except ValueError:
            raw.metadata["redirect_location"] = "[withheld]"
    # Persist the response before any JSON decoding or field inspection.
    raw_path = _save(output, {"raw": asdict(raw), "raw_content_hash": raw.content_hash})
    fields = []
    try:
        payload = json.loads(body)
        if isinstance(payload, dict):
            fields = sorted(payload)
    except ValueError:
        pass
    summary = {
        "source": source,
        "status": "FETCHED" if response.is_success and retention != "WITHHELD" else "BLOCKED",
        "reason": "HTTP_RESPONSE" if retention != "WITHHELD" else "SECRET_GUARD",
        "timestamp": retrieved_at.isoformat(),
        "url": raw.external_ref,
        "http_status": response.status_code,
        "response_sha256": raw.metadata["response_sha256"],
        "raw_content_hash": raw.content_hash,
        "raw_path": str(raw_path),
        "retention": retention,
        "field_coverage": fields,
        "sporttery_verification_status": "UNVERIFIED",
        "scan_status": "PASS",
    }
    parts = urlsplit(raw.external_ref or "")
    if (
        parts.hostname == "api.the-odds-api.com" and parts.path.startswith("/v4/historical/")
        and response.is_success and retention == "UNCHANGED"
    ):
        requested = dict(parse_qsl(parts.query)).get("date")
        summary["inspection"] = inspect_odds_history_payload(
            body, requested_at=parse_time(requested) if requested else None, retrieved_at=retrieved_at,
        )
    path = _save(output, {"source_probe": summary})
    return {**summary, "probe_path": str(path)}
