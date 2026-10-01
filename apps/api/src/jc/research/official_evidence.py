"""Offline intake of a manually saved official JSON, HTML or single HAR response body.

No network or browser control. A supplied official URL establishes claimed
provenance, not authenticity or VERIFIED status. Inspect first, review via D2A.
"""

import argparse
import hashlib
import json
import re
from dataclasses import asdict
from html import unescape
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

from jc.research.contracts import ResearchRawArtifactInput, reject_secrets
from jc.research.providers.inspection import inspect_sporttery_history_payload
from jc.research.providers.probe import _save, public_url
from jc.time import as_utc, parse_time, utcnow

OFFICIAL_HOSTS = {"sporttery.cn", "www.sporttery.cn", "static.sporttery.cn", "webapi.sporttery.cn"}


def validate_official_url(url: str) -> str:
    reject_secrets(url)
    parts = urlsplit(url)
    if (
        parts.scheme != "https"
        or parts.hostname not in OFFICIAL_HOSTS
        or parts.username is not None
        or parts.password is not None
        or parts.port not in (None, 443)
        or parts.fragment
        or any(c.isspace() for c in url)
        or any(key.lower() in ("key", "auth", "credential", "signature") for key, _ in parse_qsl(parts.query))
    ):
        raise ValueError("Official evidence requires an allowed HTTPS host and a credential-free URL")
    return url


def intake_official_evidence(input_path: Path, source_url: str, retrieved_at, output: Path) -> dict:
    source_url = validate_official_url(source_url)
    provided_source_url = source_url
    source_url = public_url(source_url)
    retrieved_at = as_utc(retrieved_at)
    if retrieved_at > utcnow():
        raise ValueError("retrieved_at cannot be in the future")
    original = input_path.read_bytes()
    encoding = "utf-8"
    try:
        body = original.decode(encoding)
    except UnicodeError:
        encoding = "gb18030"
        body = original.decode(encoding)  # Fail closed on undecodable content.
    # Scan text before parsing or copying. Rejected files are not persisted.
    scanned = unescape(re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m[1], 16)), body))
    reject_secrets(scanned)
    # Apply the existing nested-metadata key guard without decoding the payload
    # schema before persistence (e.g. client_secret_value, not only apiKey).
    for key in re.findall(r"""["']([^"']+)["']\s*:""", scanned):
        reject_secrets({key: None})
    if re.search(r'"log"\s*:', scanned) and re.search(r'"entries"\s*:', scanned):
        raise ValueError("Select a single HAR response body; never import a complete HAR")
    raw = ResearchRawArtifactInput(
        source_name="sporttery_history_offline",
        artifact_type="OFFICIAL_EVIDENCE_INTAKE",
        retrieved_at=retrieved_at,
        content_type="text/html" if body.lstrip().startswith("<") else "application/json",
        payload=body,
        external_ref=source_url,
        metadata={
            "response_sha256": hashlib.sha256(original).hexdigest(),
            "text_encoding": encoding,
            "retention": "UNCHANGED",
            "provenance": "USER_EXPORTED_SINGLE_RESPONSE_BODY",
            "provided_source_url": provided_source_url,
            "source_authenticity": "REQUIRES_REVIEW",
            "intake_at": utcnow().isoformat(),
            "http_status": None,
            "replay_available_at": None,
            "availability_basis": None,
        },
    )
    raw_path = _save(output, {"raw": asdict(raw), "raw_content_hash": raw.content_hash})
    inspection = inspect_sporttery_history_payload(body.lstrip("\ufeff"))
    summary = {
        "source": raw.source_name,
        "status": inspection["evidence_decision"],
        "reason": inspection["reason"],
        "timestamp": retrieved_at.isoformat(),
        "url": source_url,
        "http_status": None,
        "response_sha256": raw.metadata["response_sha256"],
        "raw_content_hash": raw.content_hash,
        "raw_path": str(raw_path.resolve()),
        "retention": "UNCHANGED",
        "scan_status": "PASS",
        "schema_status": inspection["schema_status"],
        "sporttery_verification_status": "UNVERIFIED",
    }
    path = _save(output, {"source_probe": summary, "inspection": inspection})
    return {**summary, "probe_path": str(path), "inspection": inspection}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--source-url", required=True)
    parser.add_argument("--retrieved-at", required=True, type=parse_time)
    parser.add_argument("--output", type=Path, default=Path("artifacts/research-probes/offline"))
    args = parser.parse_args()
    try:
        result = intake_official_evidence(args.input, args.source_url, args.retrieved_at, args.output)
    except (ValueError, OSError):
        print(json.dumps({"status": "INVALID_EVIDENCE", "reason": "INPUT_VALIDATION_FAILED"}))
        return 2  # Never echo input, URL or potentially sensitive exception text.
    print(json.dumps({key: result[key] for key in ("status", "schema_status", "probe_path")}))
    return 2 if result["status"] == "BLOCKED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
